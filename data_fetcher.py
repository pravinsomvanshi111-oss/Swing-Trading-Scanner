import requests
import pandas as pd
import numpy as np
import io
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from database import (
    init_db,
    get_connection,
    get_universe_data,
    upsert_technicals,
    upsert_fundamentals,
    upsert_shareholding_history,
)

# ── Universe fetcher (Phase 2) ────────────────────────────────

def fetch_universe_symbols():
    """Fetch ALL NSE-listed equity symbols (not just an index)."""
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {'User-Agent': 'Mozilla/5.0'}
    print("Fetching ALL NSE-listed equities...")
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        df = pd.read_csv(io.StringIO(r.text))
        # Filter to EQ series only (excludes BE, BZ, etc.)
        eq_mask = df[' SERIES'].str.strip() == 'EQ'
        symbols = df[eq_mask]['SYMBOL'].tolist()
        print(f"  Found {len(symbols)} EQ-series stocks out of {len(df)} total listings.")
        return symbols
    else:
        print(f"Failed to fetch CSV: {r.status_code}")
        return []

def fetch_stock_data(symbol):
    """Fetch basic stock info using fast_info (lightweight, less rate-limiting)."""
    import time
    for attempt in range(3):
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            fi = ticker.fast_info

            market_cap = fi.get('marketCap', fi.get('market_cap', 0))
            if market_cap:
                market_cap = market_cap / 10000000  # Convert to Crores
            else:
                market_cap = 0

            price = fi.get('lastPrice', fi.get('last_price', 0))
            if not price:
                price = fi.get('previousClose', fi.get('previous_close', 0))

            # For name and volume, try fast_info first
            volume = fi.get('threeMonthAverageVolume', fi.get('three_month_average_volume', fi.get('lastVolume', fi.get('last_volume', 0))))

            # fast_info doesn't have name, use symbol as placeholder
            name = symbol

            if price == 0 or market_cap == 0:
                return None

            return {
                'symbol': symbol,
                'name': name,
                'market_cap': market_cap,
                'avg_volume': volume if volume else 0,
                'current_price': price,
                'is_t2t': False,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception:
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
            continue
    return None

def update_universe():
    init_db()
    symbols = fetch_universe_symbols()

    if not symbols:
        print("No symbols found.")
        return

    total = len(symbols)
    print(f"Found {total} symbols. Fetching details via fast_info...")

    data_to_insert = []
    # Use 10 workers to reduce rate-limit pressure
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_stock_data, symbols)
        for i, res in enumerate(results):
            if res:
                data_to_insert.append(res)
            if (i + 1) % 100 == 0:
                print(f"  Universe: {i + 1}/{total} ({len(data_to_insert)} successful)")

    if data_to_insert:
        conn = get_connection()
        c = conn.cursor()
        for d in data_to_insert:
            c.execute('''
            INSERT OR REPLACE INTO stocks_universe
            (symbol, name, market_cap, avg_volume, current_price, is_t2t, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (d['symbol'], d['name'], d['market_cap'], d['avg_volume'],
                  d['current_price'], d['is_t2t'], d['last_updated']))
        conn.commit()
        conn.close()
        print(f"Successfully updated {len(data_to_insert)} stocks in the database.")
    else:
        print("Failed to fetch data.")


# ── Technical data fetcher (Phase 4 + Phase 5 RS Rating) ─────

def update_technicals(symbols=None, progress_callback=None):
    """
    Download 1 year of daily OHLCV for every symbol in the universe,
    compute 50/150/200-day SMAs, 52-week high/low, 3-month high,
    and RS Rating (percentile-ranked relative strength).

    Uses yf.download() in batches for speed.
    """
    init_db()

    if symbols is None:
        df_uni = get_universe_data()
        if df_uni.empty:
            print("Universe table is empty. Run update_universe() first.")
            return
        symbols = df_uni['symbol'].tolist()

    total = len(symbols)
    print(f"Fetching technical data for {total} stocks...")

    BATCH = 50
    all_records = []
    rs_scores = {}
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    benchmark_close = _fetch_benchmark_close()

    for batch_start in range(0, total, BATCH):
        batch_symbols = symbols[batch_start : batch_start + BATCH]
        tickers_str = " ".join([f"{s}.NS" for s in batch_symbols])

        try:
            data = yf.download(
                tickers_str,
                period="1y",
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as e:
            print(f"  Batch download error ({batch_start}): {e}")
            continue

        for sym in batch_symbols:
            yf_sym = f"{sym}.NS"
            try:
                if len(batch_symbols) == 1:
                    hist = data.copy()
                else:
                    hist = data[yf_sym].copy()

                hist = hist.dropna(subset=["Close"])
                if len(hist) < 50:
                    continue

                close = hist["Close"]
                high  = hist["High"]
                low   = hist["Low"]
                volume = hist["Volume"]

                current_price = float(close.iloc[-1])
                sma_50  = float(close.rolling(50).mean().iloc[-1])  if len(close) >= 50  else None
                sma_150 = float(close.rolling(150).mean().iloc[-1]) if len(close) >= 150 else None
                sma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

                week_high_52 = float(high.max())
                week_low_52  = float(low.min())

                high_3m = float(high.iloc[-63:].max()) if len(high) >= 63 else float(high.max())

                ret_13w = _pct_return(close, 63)
                ret_26w = _pct_return(close, 126)
                ret_52w = _pct_return(close, 252)

                raw_rs = (ret_13w * 0.4) + (ret_26w * 0.3) + (ret_52w * 0.3)
                rs_scores[sym] = raw_rs
                setup = _compute_setup_metrics(hist, benchmark_close)
                tight = _compute_tight_area_metrics(hist)

                all_records.append({
                    'symbol':        sym,
                    'current_price': current_price,
                    'sma_50':        sma_50,
                    'sma_150':       sma_150,
                    'sma_200':       sma_200,
                    'week_high_52':  week_high_52,
                    'week_low_52':   week_low_52,
                    'high_3m':       high_3m,
                    'rs_rating':     None,
                    'vcp_score':     setup['vcp_score'],
                    'vcp_pullbacks': setup['vcp_pullbacks'],
                    'volume_dryup_score': setup['volume_dryup_score'],
                    'pivot_price':   setup['pivot_price'],
                    'pivot_distance_pct': setup['pivot_distance_pct'],
                    'breakout_score': setup['breakout_score'],
                    'breakout_volume_multiple': setup['breakout_volume_multiple'],
                    'rs_line_new_high': setup['rs_line_new_high'],
                    'rs_line_pct_from_high': setup['rs_line_pct_from_high'],
                    'setup_score':   setup['setup_score'],
                    'setup_labels':  setup['setup_labels'],
                    'atr_14': tight['atr_14'],
                    'atr_contraction_pct': tight['atr_contraction_pct'],
                    'atr_squeeze_score': tight['atr_squeeze_score'],
                    'tight_range_10d_pct': tight['tight_range_10d_pct'],
                    'tight_area_score': tight['tight_area_score'],
                    'last_updated':  now_str,
                })
            except Exception:
                continue

        done = min(batch_start + BATCH, total)
        pct = int(done / total * 100)
        print(f"  Technical data: {done}/{total} ({pct}%)")
        if progress_callback:
            progress_callback(done, total)

    if rs_scores:
        from scipy.stats import percentileofscore
        all_raw = list(rs_scores.values())
        for rec in all_records:
            sym = rec['symbol']
            if sym in rs_scores:
                rec['rs_rating'] = round(percentileofscore(all_raw, rs_scores[sym]), 2)

    if all_records:
        upsert_technicals(all_records)
        print(f"Successfully updated technicals for {len(all_records)} stocks (with RS Ratings).")
    else:
        print("No technical records computed.")


def _pct_return(close_series, days):
    """Calculate percentage return over the last N trading days."""
    if len(close_series) >= days:
        old = float(close_series.iloc[-days])
        new = float(close_series.iloc[-1])
        if old > 0:
            return ((new - old) / old) * 100
    old = float(close_series.iloc[0])
    new = float(close_series.iloc[-1])
    if old > 0:
        return ((new - old) / old) * 100
    return 0.0


def _fetch_benchmark_close():
    """Fetch NIFTY 50 closes once, for RS-line checks."""
    try:
        data = yf.download("^NSEI", period="1y", interval="1d", progress=False)
        if data.empty:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] for col in data.columns]
        return data["Close"].dropna()
    except Exception:
        return None


def _compute_setup_metrics(hist, benchmark_close=None):
    """
    Compute actionable setup signals from the already-downloaded OHLCV frame:
    VCP/volume dry-up, pivot breakout readiness, and RS-line new high vs NIFTY.
    """
    empty = {
        'vcp_score': None,
        'vcp_pullbacks': None,
        'volume_dryup_score': None,
        'pivot_price': None,
        'pivot_distance_pct': None,
        'breakout_score': None,
        'breakout_volume_multiple': None,
        'rs_line_new_high': None,
        'rs_line_pct_from_high': None,
        'setup_score': None,
        'setup_labels': None,
    }
    if hist is None or hist.empty or len(hist) < 50:
        return empty

    if isinstance(hist.columns, pd.MultiIndex):
        hist = hist.copy()
        hist.columns = [col[0] for col in hist.columns]

    close = hist["Close"].dropna()
    high = hist["High"].reindex(close.index)
    low = hist["Low"].reindex(close.index)
    volume = hist["Volume"].reindex(close.index).fillna(0)
    if close.empty:
        return empty

    vcp = _detect_vcp(hist)
    breakout = _detect_breakout_readiness(close, high, volume)
    rs_line = _detect_rs_line_new_high(close, benchmark_close)
    tight = _compute_tight_area_metrics(hist)

    labels = []
    if vcp['vcp_score'] is not None and vcp['vcp_score'] >= 70:
        labels.append("VCP Candidate")
    if vcp['volume_dryup_score'] is not None and vcp['volume_dryup_score'] >= 70:
        labels.append("Volume Dry-Up")
    if breakout['pivot_distance_pct'] is not None:
        if breakout['pivot_distance_pct'] >= 0 and breakout['breakout_volume_multiple'] is not None and breakout['breakout_volume_multiple'] >= 1.5:
            labels.append("Fresh Breakout")
        elif -5 <= breakout['pivot_distance_pct'] < 0:
            labels.append("Near Breakout")
    if rs_line['rs_line_new_high']:
        labels.append("RS Line New High")
    if tight['tight_area_score'] is not None and tight['tight_area_score'] >= 70:
        labels.append("Tight Area")
    if tight['atr_squeeze_score'] is not None and tight['atr_squeeze_score'] >= 70:
        labels.append("ATR Squeeze")

    scored_parts = [
        (vcp['vcp_score'], 0.35),
        (breakout['breakout_score'], 0.30),
        (100 if rs_line['rs_line_new_high'] else 0 if rs_line['rs_line_new_high'] == 0 else None, 0.20),
        (tight['tight_area_score'], 0.15),
    ]
    usable_weight = sum(weight for score, weight in scored_parts if score is not None)
    setup_score = None
    if usable_weight > 0:
        setup_score = round(sum(score * weight for score, weight in scored_parts if score is not None) / usable_weight, 1)

    return {
        'vcp_score': vcp['vcp_score'],
        'vcp_pullbacks': vcp['vcp_pullbacks'],
        'volume_dryup_score': vcp['volume_dryup_score'],
        'pivot_price': breakout['pivot_price'],
        'pivot_distance_pct': breakout['pivot_distance_pct'],
        'breakout_score': breakout['breakout_score'],
        'breakout_volume_multiple': breakout['breakout_volume_multiple'],
        'rs_line_new_high': rs_line['rs_line_new_high'],
        'rs_line_pct_from_high': rs_line['rs_line_pct_from_high'],
        'setup_score': setup_score,
        'setup_labels': ", ".join(labels) if labels else "Leader, No Setup",
    }


def _detect_vcp(hist):
    weekly = hist.resample("W-FRI").agg({
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna().tail(26)

    if len(weekly) < 8:
        return {'vcp_score': None, 'vcp_pullbacks': None, 'volume_dryup_score': None}

    pullbacks = _find_weekly_pullbacks(weekly)
    price_score = None
    if len(pullbacks) >= 2:
        recent = pullbacks[-4:]
        contractions = sum(recent[i] > recent[i + 1] for i in range(len(recent) - 1))
        contraction_ratio = contractions / max(len(recent) - 1, 1)
        latest_tight = max(0, min(1, (18 - recent[-1]) / 15))
        price_score = round((contraction_ratio * 70) + (latest_tight * 30), 1)
    elif len(pullbacks) == 1:
        price_score = round(max(0, min(60, (18 - pullbacks[0]) * 4)), 1)

    volume_score = _volume_dryup_score(weekly["Volume"])

    if price_score is None and volume_score is None:
        vcp_score = None
    elif price_score is None:
        vcp_score = round(volume_score * 0.4, 1)
    elif volume_score is None:
        vcp_score = round(price_score * 0.6, 1)
    else:
        vcp_score = round((price_score * 0.6) + (volume_score * 0.4), 1)

    return {
        'vcp_score': vcp_score,
        'vcp_pullbacks': " > ".join(f"{p:.1f}%" for p in pullbacks[-4:]) if pullbacks else None,
        'volume_dryup_score': volume_score,
    }


def _find_weekly_pullbacks(weekly):
    highs = weekly["High"].to_numpy()
    lows = weekly["Low"].to_numpy()
    pullbacks = []

    for i in range(1, len(weekly) - 1):
        is_swing_high = highs[i] >= highs[i - 1] and highs[i] > highs[i + 1]
        if not is_swing_high:
            continue

        next_low_idx = None
        for j in range(i + 1, len(weekly) - 1):
            is_swing_low = lows[j] <= lows[j - 1] and lows[j] < lows[j + 1]
            if is_swing_low:
                next_low_idx = j
                break

        if next_low_idx is None:
            continue

        high_val = highs[i]
        low_val = lows[next_low_idx]
        if high_val > 0 and low_val < high_val:
            correction = ((high_val - low_val) / high_val) * 100
            if 2 <= correction <= 45:
                pullbacks.append(round(float(correction), 1))

    if len(pullbacks) >= 2:
        return pullbacks

    fallback = []
    recent = weekly.tail(15)
    chunks = np.array_split(recent, 3)
    for chunk in chunks:
        if chunk.empty:
            continue
        high_val = float(chunk["High"].max())
        low_val = float(chunk["Low"].min())
        if high_val > 0 and low_val < high_val:
            correction = ((high_val - low_val) / high_val) * 100
            if 2 <= correction <= 45:
                fallback.append(round(correction, 1))
    return fallback


def _volume_dryup_score(weekly_volume):
    vol = weekly_volume.tail(8).astype(float)
    vol = vol[vol > 0]
    if len(vol) < 5:
        return None

    x = np.arange(len(vol))
    slope = np.polyfit(x, vol.to_numpy(), 1)[0]
    mean_vol = vol.mean()
    slope_pct = slope / mean_vol if mean_vol else 0

    recent_avg = vol.tail(2).mean()
    earlier_avg = vol.head(3).mean()
    dryup_ratio = 1 - (recent_avg / earlier_avg) if earlier_avg else 0

    slope_component = max(0, min(60, -slope_pct * 600))
    dryup_component = max(0, min(40, dryup_ratio * 100))
    return round(float(slope_component + dryup_component), 1)


def _detect_breakout_readiness(close, high, volume):
    if len(close) < 21:
        return {
            'pivot_price': None,
            'pivot_distance_pct': None,
            'breakout_score': None,
            'breakout_volume_multiple': None,
        }

    lookback = min(40, len(high) - 1)
    pivot_window = high.iloc[-lookback - 1:-1] if lookback > 0 else high.iloc[:-1]
    pivot_price = float(pivot_window.max()) if not pivot_window.empty else None
    current_close = float(close.iloc[-1])

    pivot_distance_pct = None
    if pivot_price and pivot_price > 0:
        pivot_distance_pct = round(((current_close - pivot_price) / pivot_price) * 100, 2)

    avg_20_volume = volume.iloc[-21:-1].replace(0, np.nan).mean()
    current_volume = float(volume.iloc[-1])
    volume_multiple = None
    if pd.notna(avg_20_volume) and avg_20_volume > 0:
        volume_multiple = round(current_volume / float(avg_20_volume), 2)

    score = 0
    if pivot_distance_pct is not None:
        if pivot_distance_pct >= 0:
            if volume_multiple is not None and volume_multiple >= 3:
                score = 100
            elif volume_multiple is not None and volume_multiple >= 2:
                score = 90
            elif volume_multiple is not None and volume_multiple >= 1.5:
                score = 80
            else:
                score = 60
        elif pivot_distance_pct >= -2:
            score = 65
        elif pivot_distance_pct >= -5:
            score = 50
        elif pivot_distance_pct >= -8:
            score = 30

    return {
        'pivot_price': round(pivot_price, 2) if pivot_price is not None else None,
        'pivot_distance_pct': pivot_distance_pct,
        'breakout_score': score,
        'breakout_volume_multiple': volume_multiple,
    }


def _detect_rs_line_new_high(close, benchmark_close):
    if benchmark_close is None or benchmark_close.empty:
        return {'rs_line_new_high': None, 'rs_line_pct_from_high': None}

    benchmark = benchmark_close.reindex(close.index).ffill().dropna()
    aligned_close = close.reindex(benchmark.index).dropna()
    benchmark = benchmark.reindex(aligned_close.index).dropna()
    aligned_close = aligned_close.reindex(benchmark.index).dropna()

    if len(aligned_close) < 50 or benchmark.empty:
        return {'rs_line_new_high': None, 'rs_line_pct_from_high': None}

    rs_line = (aligned_close / benchmark).replace([np.inf, -np.inf], np.nan).dropna()
    if len(rs_line) < 50:
        return {'rs_line_new_high': None, 'rs_line_pct_from_high': None}

    recent = rs_line.tail(252)
    current = float(recent.iloc[-1])
    high_52w = float(recent.max())
    if high_52w <= 0:
        return {'rs_line_new_high': None, 'rs_line_pct_from_high': None}

    pct_from_high = round(((current - high_52w) / high_52w) * 100, 2)
    return {
        'rs_line_new_high': 1 if current >= high_52w * 0.995 else 0,
        'rs_line_pct_from_high': pct_from_high,
    }


def _compute_tight_area_metrics(hist):
    """Detect volatility compression with ATR contraction and 10-day price tightness."""
    empty = {
        'atr_14': None,
        'atr_contraction_pct': None,
        'atr_squeeze_score': None,
        'tight_range_10d_pct': None,
        'tight_area_score': None,
    }
    if hist is None or hist.empty or len(hist) < 20:
        return empty

    if isinstance(hist.columns, pd.MultiIndex):
        hist = hist.copy()
        hist.columns = [col[0] for col in hist.columns]

    high = hist["High"].astype(float)
    low = hist["Low"].astype(float)
    close = hist["Close"].astype(float)

    prev_close = close.shift(1)
    true_range = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = true_range.rolling(14).mean()
    current_atr = atr.iloc[-1]
    if pd.isna(current_atr):
        return empty

    atr_baseline = atr.rolling(60).mean().iloc[-1] if len(atr.dropna()) >= 60 else atr.dropna().mean()
    atr_contraction_pct = None
    atr_squeeze_score = None
    if pd.notna(atr_baseline) and atr_baseline > 0:
        atr_contraction_pct = round((float(current_atr) / float(atr_baseline)) * 100, 2)
        atr_squeeze_score = round(max(0, min(100, (1.1 - (atr_contraction_pct / 100)) * 250)), 1)

    current_close = float(close.iloc[-1])
    tight_range_pct = None
    tight_score = None
    if len(close) >= 10 and current_close > 0:
        high_10 = float(high.tail(10).max())
        low_10 = float(low.tail(10).min())
        tight_range_pct = round(((high_10 - low_10) / current_close) * 100, 2)
        if tight_range_pct <= 5:
            tight_score = 100
        elif tight_range_pct <= 8:
            tight_score = 80
        elif tight_range_pct <= 10:
            tight_score = 65
        elif tight_range_pct <= 12:
            tight_score = 45
        else:
            tight_score = 0

    scored = [
        (atr_squeeze_score, 0.55),
        (tight_score, 0.45),
    ]
    usable_weight = sum(weight for score, weight in scored if score is not None)
    tight_area_score = None
    if usable_weight > 0:
        tight_area_score = round(sum(score * weight for score, weight in scored if score is not None) / usable_weight, 1)

    return {
        'atr_14': round(float(current_atr), 2),
        'atr_contraction_pct': atr_contraction_pct,
        'atr_squeeze_score': atr_squeeze_score,
        'tight_range_10d_pct': tight_range_pct,
        'tight_area_score': tight_area_score,
    }


# ── Fundamental data fetcher (Phase 6) ───────────────────────

# Global requests session for connection pooling and HTTP Keep-Alive
_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
})

from bs4 import BeautifulSoup

def clean_float(val_str):
    if not val_str:
        return None
    val_str = val_str.replace('%', '').replace(',', '').replace('+', '').strip()
    if val_str in {'', '-', '--'}:
        return None
    try:
        return float(val_str)
    except ValueError:
        return None


def _parse_shareholding_history(sh_section, symbol):
    """Parse Screener.in shareholding history into quarter rows."""
    if not sh_section:
        return []

    table = sh_section.find('table')
    if not table:
        return []

    header_row = table.find('thead')
    if header_row:
        raw_headers = [th.text.strip() for th in header_row.find_all('th')]
    else:
        first_row = table.find('tr')
        raw_headers = [cell.text.strip() for cell in first_row.find_all(['th', 'td'])] if first_row else []
    quarters = [h for h in raw_headers[1:] if h]
    if not quarters:
        return []

    quarter_rows = {
        quarter: {
            'symbol': symbol,
            'quarter': quarter,
            'source_order': idx,
            'promoter': None,
            'fii': None,
            'dii': None,
            'mutual_fund': None,
            'institutional': None,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        for idx, quarter in enumerate(quarters)
    }

    for row in table.find_all('tr'):
        cells = [cell.text.strip() for cell in row.find_all(['td', 'th'])]
        if len(cells) < 2:
            continue

        row_name = cells[0].lower()
        values = cells[1:len(quarters) + 1]

        key = None
        if 'promoter' in row_name:
            key = 'promoter'
        elif 'fii' in row_name or 'foreign' in row_name:
            key = 'fii'
        elif 'mutual fund' in row_name:
            key = 'mutual_fund'
        elif 'dii' in row_name or 'domestic' in row_name:
            key = 'dii'

        if key is None:
            continue

        for idx, val in enumerate(values):
            if idx >= len(quarters):
                break
            quarter = quarters[idx]
            quarter_rows[quarter][key] = clean_float(val)

    rows = []
    for row in quarter_rows.values():
        fii = row.get('fii') or 0.0
        dii = row.get('dii') or 0.0
        mutual_fund = row.get('mutual_fund')
        row['institutional'] = round(fii + dii, 2)
        if mutual_fund is not None and dii == 0:
            row['institutional'] = round(fii + mutual_fund, 2)

        if any(row.get(k) is not None for k in ('promoter', 'fii', 'dii', 'mutual_fund')):
            rows.append(row)

    return rows


def _compute_accumulation_metrics(history_records):
    """Score quarter-over-quarter FII/DII accumulation trends."""
    empty = {
        'fii_holding': None,
        'dii_holding': None,
        'mutual_fund_holding': None,
        'institutional_holding': None,
        'institutional_delta_qoq': None,
        'institutional_delta_2q': None,
        'fii_delta_qoq': None,
        'dii_delta_qoq': None,
        'accumulation_score': None,
        'accumulation_labels': None,
    }
    if not history_records:
        return empty

    rows = sorted(history_records, key=lambda r: r.get('source_order') if r.get('source_order') is not None else 0)
    rows = [r for r in rows if r.get('institutional') is not None]
    if not rows:
        return empty

    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None
    prev2 = rows[-3] if len(rows) >= 3 else None

    inst_latest = latest.get('institutional')
    fii_latest = latest.get('fii')
    dii_latest = latest.get('dii')
    mf_latest = latest.get('mutual_fund')

    inst_delta_qoq = round(inst_latest - prev.get('institutional'), 2) if prev and prev.get('institutional') is not None else None
    inst_delta_2q = round(inst_latest - prev2.get('institutional'), 2) if prev2 and prev2.get('institutional') is not None else None
    fii_delta_qoq = round((fii_latest or 0) - (prev.get('fii') or 0), 2) if prev and fii_latest is not None else None
    dii_delta_qoq = round((dii_latest or 0) - (prev.get('dii') or 0), 2) if prev and dii_latest is not None else None

    score = 0
    if inst_latest is not None:
        if inst_latest >= 25:
            score += 25
        elif inst_latest >= 15:
            score += 18
        elif inst_latest >= 8:
            score += 10

    if inst_delta_qoq is not None:
        if inst_delta_qoq >= 2:
            score += 30
        elif inst_delta_qoq > 0:
            score += 20
        elif inst_delta_qoq < -1:
            score -= 10

    if inst_delta_2q is not None:
        if inst_delta_2q >= 3:
            score += 25
        elif inst_delta_2q > 0:
            score += 15

    fii_values = [r.get('fii') for r in rows[-3:] if r.get('fii') is not None]
    dii_values = [r.get('dii') for r in rows[-3:] if r.get('dii') is not None]
    if len(fii_values) >= 3 and fii_values[0] < fii_values[1] < fii_values[2]:
        score += 10
    if len(dii_values) >= 3 and dii_values[0] < dii_values[1] < dii_values[2]:
        score += 10

    score = round(max(0, min(100, score)), 1)

    labels = []
    if score >= 70:
        labels.append("Institutional Accumulation")
    if fii_delta_qoq is not None and fii_delta_qoq > 0:
        labels.append("FII Buying")
    if dii_delta_qoq is not None and dii_delta_qoq > 0:
        labels.append("DII Buying")
    if inst_delta_qoq is not None and inst_delta_qoq < -1:
        labels.append("Institutional Selling")

    return {
        'fii_holding': fii_latest,
        'dii_holding': dii_latest,
        'mutual_fund_holding': mf_latest,
        'institutional_holding': inst_latest,
        'institutional_delta_qoq': inst_delta_qoq,
        'institutional_delta_2q': inst_delta_2q,
        'fii_delta_qoq': fii_delta_qoq,
        'dii_delta_qoq': dii_delta_qoq,
        'accumulation_score': score,
        'accumulation_labels': ", ".join(labels) if labels else "No Accumulation Trend",
    }

def _fetch_fundamental_screener(symbol, company_name=None):
    """
    Scrape fundamental data from Screener.in.
    Returns a dict or None on failure.
    """
    # 1. Resolve URL
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    try:
        r = _session.get(url, timeout=3)
    except Exception:
        r = None
        
    if not r or r.status_code == 404:
        url = f"https://www.screener.in/company/{symbol}/"
        try:
            r = _session.get(url, timeout=3)
        except Exception:
            r = None
            
    if not r or r.status_code != 200:
        return None


    try:
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 1. Warehouse ratios
        warehouse = {}
        top_div = soup.find('div', {'id': 'top'}) or soup.find('ul', {'id': 'top-ratios'})
        if top_div:
            for li in top_div.find_all('li'):
                name_span = li.find('span', {'class': 'name'})
                val_span = li.find('span', {'class': 'number'})
                if name_span and val_span:
                    name = name_span.text.strip().lower()
                    val = val_span.text.strip()
                    warehouse[name] = val

        # ROE
        roe = clean_float(warehouse.get('roe'))
        if roe is None:
            for table in soup.find_all('table'):
                header = table.find('th')
                if header and 'Return on Equity' in header.text:
                    for row in table.find_all('tr'):
                        cells = [td.text.strip() for td in row.find_all('td')]
                        if cells and '3 Years:' in cells[0]:
                            roe = clean_float(cells[1])
                        elif cells and '5 Years:' in cells[0] and roe is None:
                            roe = clean_float(cells[1])

        # 2. Compounded Sales & Profit Growth
        sales_growth = None
        eps_growth = None
        
        for table in soup.find_all('table'):
            header = table.find('th')
            if header:
                header_text = header.text.strip()
                if 'Compounded Sales Growth' in header_text:
                    for row in table.find_all('tr'):
                        cells = [td.text.strip() for td in row.find_all('td')]
                        if cells:
                            if 'TTM:' in cells[0]:
                                sales_growth = clean_float(cells[1])
                            elif '3 Years:' in cells[0] and sales_growth is None:
                                sales_growth = clean_float(cells[1])
                elif 'Compounded Profit Growth' in header_text:
                    for row in table.find_all('tr'):
                        cells = [td.text.strip() for td in row.find_all('td')]
                        if cells:
                            if 'TTM:' in cells[0]:
                                eps_growth = clean_float(cells[1])
                            elif '3 Years:' in cells[0] and eps_growth is None:
                                eps_growth = clean_float(cells[1])

        # 3. Debt to Equity
        de_ratio = None
        bs_section = soup.find('section', {'id': 'balance-sheet'})
        if bs_section:
            equity_cap = 0
            reserves = 0
            borrowings = 0
            
            table = bs_section.find('table')
            if table:
                headers_list = [th.text.strip() for th in table.find_all('th')]
                last_col_idx = len(headers_list) - 1 if headers_list else -1
                
                for row in table.find_all('tr'):
                    cells = [cell.text.strip() for cell in row.find_all(['td', 'th'])]
                    if cells and last_col_idx < len(cells):
                        row_name = cells[0].lower()
                        val = clean_float(cells[last_col_idx])
                        if val is not None:
                            if 'equity capital' in row_name:
                                equity_cap = val
                            elif 'reserves' in row_name:
                                reserves = val
                            elif 'borrowings' in row_name:
                                borrowings = val
                
                total_equity = equity_cap + reserves
                if total_equity > 0:
                    de_ratio = round(borrowings / total_equity, 2)
                else:
                    de_ratio = 0.0

        # 4. Shareholding Pattern
        shareholding_history = []
        accumulation = _compute_accumulation_metrics([])
        sh_section = soup.find('section', {'id': 'shareholding'})
        if sh_section:
            shareholding_history = _parse_shareholding_history(sh_section, symbol)
            accumulation = _compute_accumulation_metrics(shareholding_history)

        # Require at least ROE or Sales/EPS growth to count as a success
        if roe is not None or sales_growth is not None or eps_growth is not None:
            return {
                'symbol': symbol,
                'eps_growth': eps_growth,
                'sales_growth': sales_growth,
                'roe': roe,
                'debt_to_equity': de_ratio,
                'institutional_holding': accumulation['institutional_holding'],
                'fii_holding': accumulation['fii_holding'],
                'dii_holding': accumulation['dii_holding'],
                'mutual_fund_holding': accumulation['mutual_fund_holding'],
                'institutional_delta_qoq': accumulation['institutional_delta_qoq'],
                'institutional_delta_2q': accumulation['institutional_delta_2q'],
                'fii_delta_qoq': accumulation['fii_delta_qoq'],
                'dii_delta_qoq': accumulation['dii_delta_qoq'],
                'accumulation_score': accumulation['accumulation_score'],
                'accumulation_labels': accumulation['accumulation_labels'],
                'shareholding_history': shareholding_history,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
    except Exception as e:
        print(f"  Screener scrape error for {symbol}: {e}")
    return None

def _fetch_fundamental_yfinance(symbol):
    """
    Fetch fundamental data for one stock from yfinance.
    Returns a dict or None on failure.
    """
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info

        roe_raw = info.get('returnOnEquity')
        roe = round(roe_raw * 100, 2) if roe_raw is not None else None

        de = info.get('debtToEquity')
        if de is not None:
            de = round(de / 100, 2) if de > 10 else round(de, 2)

        eps_raw = info.get('earningsQuarterlyGrowth', info.get('earningsGrowth'))
        eps_growth = round(eps_raw * 100, 2) if eps_raw is not None else None

        rev_raw = info.get('revenueGrowth')
        sales_growth = round(rev_raw * 100, 2) if rev_raw is not None else None

        inst_raw = info.get('heldPercentInstitutions')
        institutional = round(inst_raw * 100, 2) if inst_raw is not None else None

        return {
            'symbol': symbol,
            'eps_growth': eps_growth,
            'sales_growth': sales_growth,
            'roe': roe,
            'debt_to_equity': de,
            'institutional_holding': institutional,
            'fii_holding': None,
            'dii_holding': None,
            'mutual_fund_holding': None,
            'institutional_delta_qoq': None,
            'institutional_delta_2q': None,
            'fii_delta_qoq': None,
            'dii_delta_qoq': None,
            'accumulation_score': None,
            'accumulation_labels': None,
            'shareholding_history': [],
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    except Exception:
        return None

def _fetch_fundamental(symbol, company_name=None):
    """Primary: Screener.in (no yfinance fallback for bulk speed)"""
    return _fetch_fundamental_screener(symbol, company_name)

def _fetch_fundamental_wrapper(args):
    return _fetch_fundamental(args[0], args[1])


def update_fundamentals(symbols=None, progress_callback=None):
    """
    Fetch fundamental data (ROE, D/E, EPS growth, Sales growth,
    Institutional holding) for all stocks in the universe.
    Uses Screener.in with yfinance fallback.
    """
    init_db()

    # Load symbol-to-name mapping from universe database
    conn = get_connection()
    df_names = pd.read_sql_query("SELECT symbol, name FROM stocks_universe", conn)
    conn.close()
    name_map = dict(zip(df_names['symbol'], df_names['name']))

    if symbols is None:
        symbols = list(name_map.keys())
        if not symbols:
            print("Universe table is empty. Run update_universe() first.")
            return

    total = len(symbols)
    print(f"Fetching fundamental data for {total} stocks...")

    all_records = []
    shareholding_records = []
    tasks = [(sym, name_map.get(sym, "")) for sym in symbols]
    
    # Use 15 workers for speed
    with ThreadPoolExecutor(max_workers=15) as executor:
        results = executor.map(_fetch_fundamental_wrapper, tasks)
        for i, res in enumerate(results):
            if res:
                shareholding_records.extend(res.pop('shareholding_history', []) or [])
                all_records.append(res)
            if (i + 1) % 50 == 0 or (i + 1) == total:
                pct = int((i + 1) / total * 100)
                print(f"  Fundamentals: {i + 1}/{total} ({pct}%)")
                if progress_callback:
                    progress_callback(i + 1, total)

    if all_records:
        upsert_fundamentals(all_records)
        upsert_shareholding_history(shareholding_records)
        print(f"Successfully updated fundamentals for {len(all_records)} stocks.")
    else:
        print("No fundamental records fetched.")


# ── CLI entry point ───────────────────────────────────────────

if __name__ == "__main__":
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    if arg == "technicals":
        update_technicals()
    elif arg == "fundamentals":
        update_fundamentals()
    else:
        update_universe()
        update_technicals()
        update_fundamentals()
