import requests
import pandas as pd
import numpy as np
import io
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from database import init_db, get_connection, get_universe_data, upsert_technicals, upsert_fundamentals

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
            volume = fi.get('lastVolume', fi.get('last_volume', 0))
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
    val_str = val_str.replace('%', '').replace(',', '').strip()
    try:
        return float(val_str)
    except ValueError:
        return None

def _fetch_fundamental_screener(symbol, company_name=None):
    """
    Scrape fundamental data from Screener.in.
    Returns a dict or None on failure.
    """
    # 1. Resolve URL
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    try:
        r = _session.get(url, timeout=5)
    except Exception:
        r = None
        
    if not r or r.status_code == 404:
        url = f"https://www.screener.in/company/{symbol}/"
        try:
            r = _session.get(url, timeout=5)
        except Exception:
            r = None
        
    if (not r or r.status_code == 404):
        # Try search API with symbol
        search_url = f"https://www.screener.in/api/company/search/?q={symbol}"
        try:
            sr = _session.get(search_url, timeout=5)
            if sr.status_code == 200 and sr.json():
                url = f"https://www.screener.in{sr.json()[0]['url']}"
                r = _session.get(url, timeout=5)
        except Exception:
            pass
            
    if (not r or r.status_code == 404) and company_name:
        # Try search API with company name
        search_url = f"https://www.screener.in/api/company/search/?q={company_name}"
        try:
            sr = _session.get(search_url, timeout=5)
            if sr.status_code == 200 and sr.json():
                url = f"https://www.screener.in{sr.json()[0]['url']}"
                r = _session.get(url, timeout=5)
        except Exception:
            pass
            
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
        institutional = None
        sh_section = soup.find('section', {'id': 'shareholding'})
        if sh_section:
            table = sh_section.find('table')
            if table:
                headers_list = [th.text.strip() for th in table.find_all('th')]
                last_col_idx = len(headers_list) - 1 if headers_list else -1
                
                fiis = 0.0
                diis = 0.0
                
                for row in table.find_all('tr'):
                    cells = [cell.text.strip() for cell in row.find_all(['td', 'th'])]
                    if cells and last_col_idx < len(cells):
                        row_name = cells[0].lower()
                        val = clean_float(cells[last_col_idx])
                        if val is not None:
                            if 'fiis' in row_name:
                                fiis = val
                            elif 'diis' in row_name:
                                diis = val
                institutional = round(fiis + diis, 2)

        # Require at least ROE or Sales/EPS growth to count as a success
        if roe is not None or sales_growth is not None or eps_growth is not None:
            return {
                'symbol': symbol,
                'eps_growth': eps_growth,
                'sales_growth': sales_growth,
                'roe': roe,
                'debt_to_equity': de_ratio,
                'institutional_holding': institutional,
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
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    except Exception:
        return None

def _fetch_fundamental(symbol, company_name=None):
    """Primary: Screener.in, Fallback: yfinance"""
    res = _fetch_fundamental_screener(symbol, company_name)
    if res:
        return res
    # Fallback to yfinance
    return _fetch_fundamental_yfinance(symbol)

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
    tasks = [(sym, name_map.get(sym, "")) for sym in symbols]
    
    # Use 15 workers for speed
    with ThreadPoolExecutor(max_workers=15) as executor:
        results = executor.map(_fetch_fundamental_wrapper, tasks)
        for i, res in enumerate(results):
            if res:
                all_records.append(res)
            if (i + 1) % 50 == 0 or (i + 1) == total:
                pct = int((i + 1) / total * 100)
                print(f"  Fundamentals: {i + 1}/{total} ({pct}%)")
                if progress_callback:
                    progress_callback(i + 1, total)

    if all_records:
        upsert_fundamentals(all_records)
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
