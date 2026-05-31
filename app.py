import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime
from database import get_filtered_universe, init_db, get_last_update_times

# Page config
st.set_page_config(page_title="SwingScreener", layout="wide", initial_sidebar_state="expanded")


# ── Trend Template scoring ───────────────────────────────────

def compute_trend_score(row):
    """
    Evaluate the 5-check Trend Template on one stock row.
    Returns (score_pct, checks_passed, total_checks, details_list).
    """
    checks = []
    price = row.get("current_price")
    sma50 = row.get("sma_50")
    sma150 = row.get("sma_150")
    sma200 = row.get("sma_200")

    if pd.isna(price) or pd.isna(sma50):
        return None, 0, 5, []

    if pd.notna(sma150):
        p = price > sma150
        checks.append(("Price > 150 SMA", p, f"₹{price:,.0f} vs ₹{sma150:,.0f}"))
    else:
        checks.append(("Price > 150 SMA", False, "N/A (< 150 days data)"))

    if pd.notna(sma200):
        p = price > sma200
        checks.append(("Price > 200 SMA", p, f"₹{price:,.0f} vs ₹{sma200:,.0f}"))
    else:
        checks.append(("Price > 200 SMA", False, "N/A (< 200 days data)"))

    if pd.notna(sma150) and pd.notna(sma200):
        p = sma150 > sma200
        checks.append(("150 SMA > 200 SMA", p, f"₹{sma150:,.0f} vs ₹{sma200:,.0f}"))
    else:
        checks.append(("150 SMA > 200 SMA", False, "N/A"))

    if pd.notna(sma150):
        p = sma50 > sma150
        checks.append(("50 SMA > 150 SMA", p, f"₹{sma50:,.0f} vs ₹{sma150:,.0f}"))
    else:
        checks.append(("50 SMA > 150 SMA", False, "N/A"))

    p = price > sma50
    checks.append(("Price > 50 SMA", p, f"₹{price:,.0f} vs ₹{sma50:,.0f}"))

    passed_count = sum(1 for _, p, _ in checks if p)
    total = len(checks)
    score_pct = (passed_count / total) * 100
    if passed_count < 5:
        score_pct = 0

    return score_pct, passed_count, total, checks


# ── Momentum scoring ─────────────────────────────────────────

def compute_momentum_score(row, min_rs, mom_dist_pct):
    """
    3 filters, each 33.3%.
    Returns (score_pct, details_list).
    """
    details = []
    price = row.get("current_price")
    rs_rating = row.get("rs_rating")
    w52_high = row.get("week_high_52")
    high_3m = row.get("high_3m")
    score = 0

    if pd.notna(rs_rating):
        p = rs_rating >= min_rs
        details.append(("RS Rating", p, f"{rs_rating:.0f} (target: ≥{min_rs})"))
        if p: score += 33.3
    else:
        details.append(("RS Rating", False, "N/A"))

    if pd.notna(w52_high) and pd.notna(price) and w52_high > 0:
        distance = ((w52_high - price) / w52_high) * 100
        p = distance <= mom_dist_pct
        details.append((f"Within {mom_dist_pct}% of 52W High", p, f"{distance:.1f}% away"))
        if p: score += 33.3
    else:
        details.append((f"Within {mom_dist_pct}% of 52W High", False, "N/A"))

    if pd.notna(high_3m) and pd.notna(price) and high_3m > 0:
        pct_from_3m = ((high_3m - price) / high_3m) * 100
        p = pct_from_3m <= 2.0
        details.append(("Near 3-Month High", p, f"{pct_from_3m:.1f}% away (₹{high_3m:,.0f})"))
        if p: score += 33.4
    else:
        details.append(("Near 3-Month High", False, "N/A"))

    return round(score, 1), details


# ── Fundamental scoring ──────────────────────────────────────

def compute_fundamental_score(row, criteria):
    """
    5 filters, each 20%.
    criteria = dict with keys: eps_growth, sales_growth, roe, de_ratio, institutional
    Returns (score_pct, details_list).
    """
    details = []
    score = 0

    # EPS Growth
    val = row.get("eps_growth")
    target = criteria["eps_growth"]
    if pd.notna(val):
        p = val >= target
        details.append(("EPS Growth (YoY)", p, f"{val:.1f}% (target: ≥{target}%)"))
        if p: score += 20
    else:
        details.append(("EPS Growth (YoY)", False, "N/A"))

    # Sales Growth
    val = row.get("sales_growth")
    target = criteria["sales_growth"]
    if pd.notna(val):
        p = val >= target
        details.append(("Sales Growth (YoY)", p, f"{val:.1f}% (target: ≥{target}%)"))
        if p: score += 20
    else:
        details.append(("Sales Growth (YoY)", False, "N/A"))

    # ROE
    val = row.get("roe")
    target = criteria["roe"]
    if pd.notna(val):
        p = val >= target
        details.append(("ROE", p, f"{val:.1f}% (target: ≥{target}%)"))
        if p: score += 20
    else:
        details.append(("ROE", False, "N/A"))

    # Debt-to-Equity
    val = row.get("debt_to_equity")
    target = criteria["de_ratio"]
    if pd.notna(val):
        p = val < target
        details.append(("Debt-to-Equity", p, f"{val:.2f} (target: <{target})"))
        if p: score += 20
    else:
        details.append(("Debt-to-Equity", False, "N/A"))

    # Institutional Holding
    val = row.get("institutional_holding")
    target = criteria["institutional"]
    if pd.notna(val):
        p = val >= target
        details.append(("Institutional Holding", p, f"{val:.1f}% (target: ≥{target}%)"))
        if p: score += 20
    else:
        details.append(("Institutional Holding", False, "N/A"))

    return score, details


# ── Overall scoring ──────────────────────────────────────────

def compute_overall_score(trend_score, momentum_score, fundamental_score):
    """
    Weighted average: Fundamental 30%, Trend 40%, Momentum 30%.
    trend_score can be None (no data) or 0 (fail).
    Returns overall score or None if trend disqualifies.
    """
    if trend_score is None or trend_score == 0:
        return None  # Trend fail = disqualified
    return round(
        (fundamental_score * 0.30) +
        (trend_score * 0.40) +
        (momentum_score * 0.30),
        1
    )


def compute_actionable_score(overall_score, setup_score, accumulation_score=None):
    """
    Blend current leader quality with actionable setup and accumulation quality.
    Existing overall score stays intact; this is used for ranking setups.
    """
    if pd.isna(overall_score):
        return None
    if pd.isna(setup_score):
        setup_score = 0
    if pd.isna(accumulation_score):
        accumulation_score = 0
    return round(
        (overall_score * 0.60) +
        (setup_score * 0.30) +
        (accumulation_score * 0.10),
        1
    )


def compute_setup_details(row):
    """Human-readable details for VCP, breakout readiness, and RS-line checks."""
    details = []

    vcp_score = row.get("vcp_score")
    pullbacks = row.get("vcp_pullbacks")
    if pd.notna(vcp_score):
        ok = vcp_score >= 70
        info = f"{vcp_score:.0f}%"
        if isinstance(pullbacks, str) and pullbacks:
            info += f" | pullbacks: {pullbacks}"
        details.append(("VCP Contraction", ok, info))
    else:
        details.append(("VCP Contraction", False, "N/A"))

    dryup = row.get("volume_dryup_score")
    if pd.notna(dryup):
        details.append(("Volume Dry-Up", dryup >= 70, f"{dryup:.0f}%"))
    else:
        details.append(("Volume Dry-Up", False, "N/A"))

    pivot = row.get("pivot_price")
    pivot_dist = row.get("pivot_distance_pct")
    if pd.notna(pivot) and pd.notna(pivot_dist):
        ok = pivot_dist >= -5
        details.append(("Pivot Readiness", ok, f"{pivot_dist:.2f}% from pivot (Rs {pivot:,.2f})"))
    else:
        details.append(("Pivot Readiness", False, "N/A"))

    vol_mult = row.get("breakout_volume_multiple")
    if pd.notna(vol_mult):
        details.append(("Breakout Volume", vol_mult >= 1.5, f"{vol_mult:.2f}x 20-day average"))
    else:
        details.append(("Breakout Volume", False, "N/A"))

    rs_new_high = row.get("rs_line_new_high")
    rs_dist = row.get("rs_line_pct_from_high")
    if pd.notna(rs_new_high):
        details.append(("RS Line New High", bool(rs_new_high), f"{rs_dist:.2f}% from 52W RS high" if pd.notna(rs_dist) else "N/A"))
    else:
        details.append(("RS Line New High", False, "N/A"))

    atr_score = row.get("atr_squeeze_score")
    atr_contract = row.get("atr_contraction_pct")
    if pd.notna(atr_score):
        details.append(("ATR Squeeze", atr_score >= 70, f"{atr_score:.0f}% | ATR at {atr_contract:.1f}% of baseline" if pd.notna(atr_contract) else f"{atr_score:.0f}%"))
    else:
        details.append(("ATR Squeeze", False, "N/A"))

    tight_score = row.get("tight_area_score")
    tight_range = row.get("tight_range_10d_pct")
    if pd.notna(tight_score):
        details.append(("10-Day Tight Area", tight_score >= 70, f"{tight_range:.2f}% range" if pd.notna(tight_range) else f"{tight_score:.0f}%"))
    else:
        details.append(("10-Day Tight Area", False, "N/A"))

    return details


def compute_accumulation_details(row):
    """Human-readable institutional accumulation details."""
    details = []

    score = row.get("accumulation_score")
    label = row.get("accumulation_labels")
    details.append((
        "Accumulation Score",
        pd.notna(score) and score >= 70,
        f"{score:.0f}% | {label}" if pd.notna(score) and isinstance(label, str) else "N/A",
    ))

    inst = row.get("institutional_holding")
    delta_qoq = row.get("institutional_delta_qoq")
    delta_2q = row.get("institutional_delta_2q")
    if pd.notna(inst):
        delta_txt = []
        if pd.notna(delta_qoq):
            delta_txt.append(f"QoQ {delta_qoq:+.2f} pp")
        if pd.notna(delta_2q):
            delta_txt.append(f"2Q {delta_2q:+.2f} pp")
        details.append(("Institutional Holding", pd.notna(delta_qoq) and delta_qoq > 0, f"{inst:.2f}% | {'; '.join(delta_txt) if delta_txt else 'trend N/A'}"))
    else:
        details.append(("Institutional Holding", False, "N/A"))

    fii = row.get("fii_holding")
    fii_delta = row.get("fii_delta_qoq")
    if pd.notna(fii):
        details.append(("FII Trend", pd.notna(fii_delta) and fii_delta > 0, f"{fii:.2f}% | QoQ {fii_delta:+.2f} pp" if pd.notna(fii_delta) else f"{fii:.2f}%"))
    else:
        details.append(("FII Trend", False, "N/A"))

    dii = row.get("dii_holding")
    dii_delta = row.get("dii_delta_qoq")
    if pd.notna(dii):
        details.append(("DII Trend", pd.notna(dii_delta) and dii_delta > 0, f"{dii:.2f}% | QoQ {dii_delta:+.2f} pp" if pd.notna(dii_delta) else f"{dii:.2f}%"))
    else:
        details.append(("DII Trend", False, "N/A"))

    return details


# ── Main app ─────────────────────────────────────────────────

def main():
    st.title("SWINGSCREENER - Indian Markets")
    st.markdown("---")

    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        uni, tech, fund = get_last_update_times()
        st.markdown(
            f"📅 **Universe Updated:** `{uni or 'Never'}` | "
            f"📈 **Technicals Scanned:** `{tech or 'Never'}` | "
            f"🔬 **Fundamentals Scanned:** `{fund or 'Never'}`"
        )
    with col2:
        if st.button("🔄 Refresh Universe", use_container_width=True):
            with st.spinner("Fetching all NSE-listed stocks..."):
                from data_fetcher import update_universe
                update_universe()
            st.success("Universe refreshed! Now use 🚀 RUN SCREENER to scan.")
            st.rerun()

    st.markdown("---")

    # ── Sidebar Filters ───────────────────────────────────────
    with st.sidebar:
        st.header("FILTERS")
        st.markdown("---")

        # Universe
        with st.expander("🔽 Universe Filters", expanded=True):
            mcap_range = st.slider(
                "Market Cap (₹ Cr)", min_value=0, max_value=200000,
                value=(1000, 10000), step=500
            )
            min_volume = st.number_input("Min Avg Volume", min_value=0, value=100000, step=10000)
            min_price = st.number_input("Min Price (₹)", min_value=0, value=50, step=10)

        # Fundamental
        with st.expander("🔽 Fundamental Filters", expanded=True):
            eps_opts = {"15%": 15, "20%": 20, "25%": 25, "30%": 30}
            eps_label = st.selectbox("Min EPS Growth (YoY)", list(eps_opts.keys()), index=1, key="eps")
            eps_val = eps_opts[eps_label]

            sales_opts = {"15%": 15, "20%": 20, "25%": 25}
            sales_label = st.selectbox("Min Sales Growth (YoY)", list(sales_opts.keys()), index=1, key="sales")
            sales_val = sales_opts[sales_label]

            roe_opts = {"10%": 10, "15%": 15, "17%": 17, "20%": 20}
            roe_label = st.selectbox("Min ROE", list(roe_opts.keys()), index=1, key="roe")
            roe_val = roe_opts[roe_label]

            de_opts = {"0.5": 0.5, "1.0": 1.0, "1.5": 1.5, "2.0": 2.0}
            de_label = st.selectbox("Max D/E Ratio", list(de_opts.keys()), index=2, key="de")
            de_val = de_opts[de_label]

            inst_opts = {"5%": 5, "10%": 10, "15%": 15}
            inst_label = st.selectbox("Min Institutional Holding", list(inst_opts.keys()), index=0, key="inst")
            inst_val = inst_opts[inst_label]

        fund_criteria = {
            "eps_growth": eps_val, "sales_growth": sales_val,
            "roe": roe_val, "de_ratio": de_val, "institutional": inst_val
        }

        # Trend Template
        with st.expander("🔽 Trend Template Filters (Active)", expanded=True):
            st.markdown("All 5 Trend rules are evaluated:")
            st.markdown("- **Price > 150 SMA**")
            st.markdown("- **Price > 200 SMA**")
            st.markdown("- **150 SMA > 200 SMA**")
            st.markdown("- **50 SMA > 150 SMA**")
            st.markdown("- **Price > 50 SMA**")


        # Momentum
        with st.expander("🔽 Momentum Filters"):
            rs_opts = {"65": 65, "70": 70, "75": 75, "80": 80}
            rs_label = st.selectbox("Min RS Rating", list(rs_opts.keys()), index=1, key="rs")
            min_rs = rs_opts[rs_label]

            mom_opts = {"10%": 10, "15%": 15, "20%": 20}
            mom_label = st.selectbox("Distance from 52W High", list(mom_opts.keys()), index=1, key="mom_dist")
            mom_dist_pct = mom_opts[mom_label]

        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        with c1: st.button("Reset")
        with c2: st.button("Save")
        with c3: st.button("Load")

        st.markdown("---")
        st.caption("Scans only stocks within market cap filter")
        if st.button("🚀 RUN SCREENER", type="primary", use_container_width=True):
            # Check if database has stocks
            from database import get_connection
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT count(*) FROM stocks_universe")
            db_count = c.fetchone()[0]
            conn.close()

            if db_count == 0:
                st.error("⚠️ The stock database is empty. Please click '🔄 Refresh Universe' first to download the stock list!")
            else:
                # Get symbols that pass the universe (market cap) filter
                from database import get_filtered_universe as _gfu
                _filtered = _gfu(mcap_range[0], mcap_range[1], min_volume, min_price)
                if _filtered.empty:
                    st.error("No stocks match the universe filters. Try adjusting your Market Cap, Volume, or Price filters.")
                else:
                    filtered_syms = _filtered["symbol"].tolist()
                    st.info(f"Scanning {len(filtered_syms)} stocks (MCap ₹{mcap_range[0]:,}–{mcap_range[1]:,} Cr)...")
                    with st.spinner(f"② Fetching technicals for {len(filtered_syms)} stocks..."):
                        from data_fetcher import update_technicals
                        update_technicals(symbols=filtered_syms)
                    with st.spinner(f"③ Fetching fundamentals for {len(filtered_syms)} stocks..."):
                        from data_fetcher import update_fundamentals
                        update_fundamentals(symbols=filtered_syms)
                    st.success(f"Scan complete for {len(filtered_syms)} stocks!")
                    st.rerun()

    # ── Main Content Area ─────────────────────────────────────
    st.subheader("RESULTS")

    if not os.path.exists("swing_screener.db"):
        st.warning("No database found. Click **Refresh All Data** to fetch from NSE.")
        return

    init_db()

    df = get_filtered_universe(
        mcap_min=mcap_range[0], mcap_max=mcap_range[1],
        min_volume=min_volume, min_price=min_price,
    )

    if df.empty:
        st.info("No stocks match the current universe filters.")
        return

    has_tech = df["sma_50"].notna().any()
    has_fund = df["roe"].notna().any()

    # ── Compute all scores ────────────────────────────────────
    if has_tech:
        trend_r = df.apply(lambda r: compute_trend_score(r), axis=1)
        df["trend_score"]   = trend_r.apply(lambda x: x[0])
        df["trend_passed"]  = trend_r.apply(lambda x: f"{x[1]}/{x[2]}")
        df["trend_details"] = trend_r.apply(lambda x: x[3])

        mom_r = df.apply(lambda r: compute_momentum_score(r, min_rs, mom_dist_pct), axis=1)
        df["momentum_score"]   = mom_r.apply(lambda x: x[0])
        df["momentum_details"] = mom_r.apply(lambda x: x[1])
    else:
        df["trend_score"] = df["momentum_score"] = None
        df["trend_passed"] = "—"
        df["trend_details"] = df["momentum_details"] = None

    if has_fund:
        fund_r = df.apply(lambda r: compute_fundamental_score(r, fund_criteria), axis=1)
        df["fundamental_score"]   = fund_r.apply(lambda x: x[0])
        df["fundamental_details"] = fund_r.apply(lambda x: x[1])
    else:
        df["fundamental_score"] = None
        df["fundamental_details"] = None

    # Overall score
    if has_tech:
        df["overall_score"] = df.apply(
            lambda r: compute_overall_score(
                r["trend_score"],
                r["momentum_score"] if pd.notna(r["momentum_score"]) else 0,
                r["fundamental_score"] if pd.notna(r["fundamental_score"]) else 0,
            ), axis=1
        )
    else:
        df["overall_score"] = None

    if has_tech and "setup_score" in df.columns:
        df["actionable_score"] = df.apply(
            lambda r: compute_actionable_score(
                r["overall_score"],
                r.get("setup_score"),
                r.get("accumulation_score"),
            ),
            axis=1
        )
    else:
        df["actionable_score"] = None

    # ── Build display columns ─────────────────────────────────
    display = df[["symbol", "name", "current_price", "market_cap", "avg_volume"]].copy()
    display.columns = ["Symbol", "Name", "Price (₹)", "MCap (Cr)", "Volume"]
    display["Price (₹)"] = display["Price (₹)"].round(2)
    display["MCap (Cr)"] = display["MCap (Cr)"].round(0).astype(int)
    display["Volume"] = display["Volume"].apply(lambda x: f"{x:,.0f}")

    def fmt_score(val, suffix="%"):
        if pd.isna(val): return "—"
        return f"{val:.0f}{suffix}"

    display["Overall"]     = df["overall_score"].apply(lambda x: fmt_score(x))
    display["Actionable"]  = df["actionable_score"].apply(lambda x: fmt_score(x))
    display["Setup"]       = df["setup_score"].apply(lambda x: fmt_score(x)) if "setup_score" in df.columns else "—"
    display["Accum"]       = df["accumulation_score"].apply(lambda x: fmt_score(x)) if "accumulation_score" in df.columns else "—"
    display["Fundamental"] = df["fundamental_score"].apply(lambda x: fmt_score(x))
    display["Trend"]       = df["trend_score"].apply(
        lambda x: f"{x:.0f}%" if pd.notna(x) and x > 0 else ("Fail" if pd.notna(x) else "—")
    )
    display["Momentum"]    = df["momentum_score"].apply(lambda x: fmt_score(x))
    display["RS"]          = df["rs_rating"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
    display["Labels"]      = df["setup_labels"].fillna("—") if "setup_labels" in df.columns else "—"
    display["Inst Trend"]  = df["accumulation_labels"].fillna("—") if "accumulation_labels" in df.columns else "—"

    # ── View filter ───────────────────────────────────────────
    view_mode = st.radio(
        "View:", [
            "All Universe",
            "Perfect Match (100% score)",
            "Almost Match (85% to 99% score)",
            "Trend Pass (100%)",
            "Setup Ready (70%+)",
            "Accumulation (70%+)",
            "Tight Area (70%+)",
        ],
        horizontal=True
    )

    mask = pd.Series(True, index=df.index)
    if view_mode == "Perfect Match (100% score)":
        mask = df["overall_score"].notna() & (df["overall_score"] == 100)
    elif view_mode == "Almost Match (85% to 99% score)":
        mask = df["overall_score"].notna() & (df["overall_score"] >= 85) & (df["overall_score"] < 100)
    elif view_mode == "Trend Pass (100%)":
        mask = df["trend_score"].notna() & (df["trend_score"] == 100)
    elif view_mode == "Setup Ready (70%+)":
        mask = df["setup_score"].notna() & (df["setup_score"] >= 70)
    elif view_mode == "Accumulation (70%+)":
        mask = df["accumulation_score"].notna() & (df["accumulation_score"] >= 70)
    elif view_mode == "Tight Area (70%+)":
        mask = df["tight_area_score"].notna() & (df["tight_area_score"] >= 70)

    display_filtered = display[mask]
    df_filtered = df[mask]

    # Sort by overall score descending where available
    if has_tech:
        sort_col = "actionable_score" if "actionable_score" in df_filtered.columns else "overall_score"
        sort_idx = df_filtered[sort_col].fillna(-1).sort_values(ascending=False).index
        display_filtered = display_filtered.loc[sort_idx]
        df_filtered = df_filtered.loc[sort_idx]

    # ── Stats bar ─────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks Shown", len(display_filtered))
    if has_tech:
        perfect_count = int(df["overall_score"].eq(100).sum()) if df["overall_score"].notna().any() else 0
        almost_count = int((df["overall_score"].ge(85) & df["overall_score"].lt(100)).sum()) if df["overall_score"].notna().any() else 0
        c2.metric("Perfect Match (100%)", perfect_count)
        c3.metric("Almost Match (85-99%)", almost_count)
    else:
        c2.metric("Perfect Match", "Not loaded")
        c3.metric("Almost Match", "Not loaded")
        
    if has_tech:
        trend_pass = int((df["trend_score"] == 100).sum())
        c4.metric("Trend Pass (100%)", trend_pass)
    else:
        c4.metric("Technicals", "Not loaded")

    st.markdown("---")

    # ── Results table ─────────────────────────────────────────
    cols = ["Symbol", "Name", "Price (₹)", "MCap (Cr)", "Actionable", "Overall",
            "Setup", "Labels", "Accum", "Inst Trend", "Fundamental", "Trend", "Momentum", "RS"]
    st.dataframe(
        display_filtered[cols],
        use_container_width=True, hide_index=True, height=600,
    )

    # ── Stock Detail Inspector ────────────────────────────────
    if has_tech and not df_filtered.empty:
        st.markdown("---")
        st.subheader("📋 Stock Detail Inspector")

        sym_list = df_filtered["symbol"].tolist()
        selected = st.selectbox("Select stock:", sym_list, key="detail_sym")
        row = df[df["symbol"] == selected].iloc[0]

        # Header metrics
        hc1, hc2, hc3, hc4, hc5, hc6 = st.columns(6)
        overall = row.get("overall_score")
        hc1.metric("Overall Score", f"{overall:.0f}%" if pd.notna(overall) else "N/A")
        actionable = row.get("actionable_score")
        hc2.metric("Actionable", f"{actionable:.0f}%" if pd.notna(actionable) else "N/A")
        setup_score = row.get("setup_score")
        hc3.metric("Setup", f"{setup_score:.0f}%" if pd.notna(setup_score) else "N/A")
        accumulation_score = row.get("accumulation_score")
        hc4.metric("Accumulation", f"{accumulation_score:.0f}%" if pd.notna(accumulation_score) else "N/A")
        hc5.metric("Price", f"₹{row['current_price']:,.2f}")
        hc6.metric("RS Rating", f"{row['rs_rating']:.0f}" if pd.notna(row['rs_rating']) else "N/A")

        # Tab views
        tab_fund, tab_trend, tab_mom, tab_setup, tab_accum, tab_chart = st.tabs([
            "Fundamental (30%)", 
            "Trend Template (40%)", 
            "Momentum (30%)",
            "Setup Quality",
            "Accumulation",
            "📈 Interactive Chart"
        ])

        with tab_fund:
            if has_fund:
                fscore, fdetails = compute_fundamental_score(row, fund_criteria)
                cd1, cd2 = st.columns([1, 3])
                with cd1:
                    st.metric("Score", f"{fscore:.0f}%")
                with cd2:
                    for label, ok, info in fdetails:
                        st.write(f"{'✅' if ok else '❌'} **{label}** — {info}")
            else:
                st.info("Fundamental data not loaded. Click **🚀 RUN SCREENER** in the sidebar.")

        with tab_trend:
            tscore, tpassed, ttotal, tdetails = compute_trend_score(row)
            cd1, cd2 = st.columns([1, 3])
            with cd1:
                st.metric("Score", f"{tscore:.0f}%" if tscore else "Fail")
                st.metric("Checks", f"{tpassed}/{ttotal}")
            with cd2:
                for label, ok, info in tdetails:
                    st.write(f"{'✅' if ok else '❌'} **{label}** — {info}")

        with tab_mom:
            mscore, mdetails = compute_momentum_score(row, min_rs, mom_dist_pct)
            cd1, cd2 = st.columns([1, 3])
            with cd1:
                st.metric("Score", f"{mscore:.0f}%")
            with cd2:
                for label, ok, info in mdetails:
                    st.write(f"{'✅' if ok else '❌'} **{label}** — {info}")

        with tab_setup:
            setup_score = row.get("setup_score")
            labels = row.get("setup_labels")
            cd1, cd2 = st.columns([1, 3])
            with cd1:
                st.metric("Setup Score", f"{setup_score:.0f}%" if pd.notna(setup_score) else "N/A")
                if isinstance(labels, str) and labels:
                    st.caption(labels)
            with cd2:
                for label, ok, info in compute_setup_details(row):
                    st.write(f"{'✅' if ok else '❌'} **{label}** — {info}")

        with tab_accum:
            accumulation_score = row.get("accumulation_score")
            labels = row.get("accumulation_labels")
            cd1, cd2 = st.columns([1, 3])
            with cd1:
                st.metric("Accumulation Score", f"{accumulation_score:.0f}%" if pd.notna(accumulation_score) else "N/A")
                if isinstance(labels, str) and labels:
                    st.caption(labels)
            with cd2:
                for label, ok, info in compute_accumulation_details(row):
                    st.write(f"{'✅' if ok else '❌'} **{label}** — {info}")

        with tab_chart:
            with st.spinner("Loading 1-Year Chart Data..."):
                @st.cache_data(ttl=3600)
                def fetch_chart_data(symbol):
                    try:
                        import yfinance as yf
                        hist = yf.download(f"{symbol}.NS", period="1y", interval="1d", progress=False)
                        if hist.empty:
                            return None
                        # Flatten multi-index columns first if they exist
                        if isinstance(hist.columns, pd.MultiIndex):
                            hist.columns = [col[0] for col in hist.columns]
                        hist = hist.reset_index()
                        # Rename the first column (which is the index/Date) to 'Date'
                        hist.rename(columns={hist.columns[0]: 'Date'}, inplace=True)
                        hist['SMA_50'] = hist['Close'].rolling(50).mean()
                        hist['SMA_150'] = hist['Close'].rolling(150).mean()
                        hist['SMA_200'] = hist['Close'].rolling(200).mean()
                        return hist
                    except Exception:
                        return None
                
                chart_data = fetch_chart_data(selected)
                if chart_data is not None and not chart_data.empty:
                    import plotly.graph_objects as go
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=chart_data['Date'],
                        open=chart_data['Open'],
                        high=chart_data['High'],
                        low=chart_data['Low'],
                        close=chart_data['Close'],
                        name='Price'
                    ))
                    fig.add_trace(go.Scatter(x=chart_data['Date'], y=chart_data['SMA_50'], name='50 SMA', line=dict(color='orange', width=1.5)))
                    fig.add_trace(go.Scatter(x=chart_data['Date'], y=chart_data['SMA_150'], name='150 SMA', line=dict(color='blue', width=1.5)))
                    fig.add_trace(go.Scatter(x=chart_data['Date'], y=chart_data['SMA_200'], name='200 SMA', line=dict(color='red', width=1.5)))
                    fig.update_layout(
                        xaxis_rangeslider_visible=False,
                        template="plotly_dark",
                        height=450,
                        margin=dict(l=10, r=10, t=10, b=10)
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Chart data unavailable from Yahoo Finance.")

        # External links
        st.markdown("##### 🔗 Research Links")
        el1, el2, _ = st.columns([1, 1, 4])
        with el1:
            st.link_button("📈 View on TradingView", f"https://in.tradingview.com/chart/?symbol=NSE:{selected}", use_container_width=True)
        with el2:
            st.link_button("🔍 View on Screener.in", f"https://www.screener.in/company/{selected}/", use_container_width=True)

    # Actions & Exports
    st.markdown("---")
    ca1, ca2, ca3, _ = st.columns([1.2, 1.2, 1.5, 4.1])
    with ca1:
        csv = display_filtered[cols].to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name="screener_results.csv",
            mime="text/csv",
            use_container_width=True
        )
    with ca2:
        import io
        excel_data = io.BytesIO()
        try:
            with pd.ExcelWriter(excel_data, engine='openpyxl') as writer:
                display_filtered[cols].to_excel(writer, index=False, sheet_name='Screener Results')
            excel_data.seek(0)
            st.download_button(
                label="📊 Download Excel",
                data=excel_data,
                file_name="screener_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Excel export failed: {e}")
    with ca3:
        watchlist_txt = "\n".join([f"NSE:{s}" for s in display_filtered['Symbol']])
        st.download_button(
            label="📋 Download TradingView Watchlist",
            data=watchlist_txt,
            file_name="tradingview_watchlist.txt",
            mime="text/plain",
            use_container_width=True
        )



if __name__ == "__main__":
    main()
