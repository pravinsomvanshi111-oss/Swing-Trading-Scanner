import sqlite3
import pandas as pd

DB_NAME = 'swing_screener.db'

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS stocks_universe (
        symbol TEXT PRIMARY KEY,
        name TEXT,
        market_cap REAL,
        avg_volume INTEGER,
        current_price REAL,
        is_t2t BOOLEAN,
        last_updated TIMESTAMP
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS technicals (
        symbol TEXT PRIMARY KEY,
        current_price REAL,
        sma_50 REAL,
        sma_150 REAL,
        sma_200 REAL,
        week_high_52 REAL,
        week_low_52 REAL,
        high_3m REAL,
        rs_rating REAL,
        vcp_score REAL,
        vcp_pullbacks TEXT,
        volume_dryup_score REAL,
        pivot_price REAL,
        pivot_distance_pct REAL,
        breakout_score REAL,
        breakout_volume_multiple REAL,
        rs_line_new_high INTEGER,
        rs_line_pct_from_high REAL,
        setup_score REAL,
        setup_labels TEXT,
        atr_14 REAL,
        atr_contraction_pct REAL,
        atr_squeeze_score REAL,
        tight_range_10d_pct REAL,
        tight_area_score REAL,
        last_updated TIMESTAMP
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS fundamentals (
        symbol TEXT PRIMARY KEY,
        eps_growth REAL,
        sales_growth REAL,
        roe REAL,
        debt_to_equity REAL,
        institutional_holding REAL,
        fii_holding REAL,
        dii_holding REAL,
        mutual_fund_holding REAL,
        institutional_delta_qoq REAL,
        institutional_delta_2q REAL,
        fii_delta_qoq REAL,
        dii_delta_qoq REAL,
        accumulation_score REAL,
        accumulation_labels TEXT,
        last_updated TIMESTAMP
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS shareholding_history (
        symbol TEXT,
        quarter TEXT,
        source_order INTEGER,
        promoter REAL,
        fii REAL,
        dii REAL,
        mutual_fund REAL,
        institutional REAL,
        last_updated TIMESTAMP,
        PRIMARY KEY (symbol, quarter)
    )
    ''')
    # Migrations for existing tables
    technical_migrations = [
        ('rs_rating', 'REAL'),
        ('vcp_score', 'REAL'),
        ('vcp_pullbacks', 'TEXT'),
        ('volume_dryup_score', 'REAL'),
        ('pivot_price', 'REAL'),
        ('pivot_distance_pct', 'REAL'),
        ('breakout_score', 'REAL'),
        ('breakout_volume_multiple', 'REAL'),
        ('rs_line_new_high', 'INTEGER'),
        ('rs_line_pct_from_high', 'REAL'),
        ('setup_score', 'REAL'),
        ('setup_labels', 'TEXT'),
        ('atr_14', 'REAL'),
        ('atr_contraction_pct', 'REAL'),
        ('atr_squeeze_score', 'REAL'),
        ('tight_range_10d_pct', 'REAL'),
        ('tight_area_score', 'REAL'),
    ]
    for col, col_type in technical_migrations:
        try:
            c.execute(f'ALTER TABLE technicals ADD COLUMN {col} {col_type}')
        except Exception:
            pass
    fundamental_migrations = [
        ('fii_holding', 'REAL'),
        ('dii_holding', 'REAL'),
        ('mutual_fund_holding', 'REAL'),
        ('institutional_delta_qoq', 'REAL'),
        ('institutional_delta_2q', 'REAL'),
        ('fii_delta_qoq', 'REAL'),
        ('dii_delta_qoq', 'REAL'),
        ('accumulation_score', 'REAL'),
        ('accumulation_labels', 'TEXT'),
    ]
    for col, col_type in fundamental_migrations:
        try:
            c.execute(f'ALTER TABLE fundamentals ADD COLUMN {col} {col_type}')
        except Exception:
            pass
    conn.commit()
    conn.close()

def get_universe_data():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM stocks_universe", conn)
    conn.close()
    return df

def get_filtered_universe(mcap_min, mcap_max, min_volume, min_price):
    """Return stocks that pass the universe pre-screen filters, joined with technicals and fundamentals."""
    conn = get_connection()
    query = """
    SELECT u.symbol, u.name, u.market_cap, u.avg_volume, u.current_price,
           t.sma_50, t.sma_150, t.sma_200, t.week_high_52, t.week_low_52, t.high_3m,
           t.rs_rating, t.vcp_score, t.vcp_pullbacks, t.volume_dryup_score,
           t.pivot_price, t.pivot_distance_pct, t.breakout_score, t.breakout_volume_multiple,
           t.rs_line_new_high, t.rs_line_pct_from_high, t.setup_score, t.setup_labels,
           t.atr_14, t.atr_contraction_pct, t.atr_squeeze_score, t.tight_range_10d_pct,
           t.tight_area_score,
           f.eps_growth, f.sales_growth, f.roe, f.debt_to_equity, f.institutional_holding,
           f.fii_holding, f.dii_holding, f.mutual_fund_holding, f.institutional_delta_qoq,
           f.institutional_delta_2q, f.fii_delta_qoq, f.dii_delta_qoq,
           f.accumulation_score, f.accumulation_labels
    FROM stocks_universe u
    LEFT JOIN technicals t ON u.symbol = t.symbol
    LEFT JOIN fundamentals f ON u.symbol = f.symbol
    WHERE u.market_cap >= ?
      AND u.market_cap <= ?
      AND u.avg_volume >= ?
      AND u.current_price >= ?
      AND u.is_t2t = 0
    ORDER BY u.market_cap DESC
    """
    df = pd.read_sql_query(query, conn, params=(mcap_min, mcap_max, min_volume, min_price))
    conn.close()
    return df

def upsert_technicals(records):
    """Bulk insert/update technicals rows. records is a list of dicts."""
    conn = get_connection()
    c = conn.cursor()
    for r in records:
        c.execute('''
        INSERT OR REPLACE INTO technicals
        (symbol, current_price, sma_50, sma_150, sma_200, week_high_52, week_low_52,
         high_3m, rs_rating, vcp_score, vcp_pullbacks, volume_dryup_score, pivot_price,
         pivot_distance_pct, breakout_score, breakout_volume_multiple, rs_line_new_high,
         rs_line_pct_from_high, setup_score, setup_labels, atr_14, atr_contraction_pct,
         atr_squeeze_score, tight_range_10d_pct, tight_area_score, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (r['symbol'], r['current_price'], r['sma_50'], r['sma_150'], r['sma_200'],
              r['week_high_52'], r['week_low_52'], r['high_3m'], r.get('rs_rating'),
              r.get('vcp_score'), r.get('vcp_pullbacks'), r.get('volume_dryup_score'),
              r.get('pivot_price'), r.get('pivot_distance_pct'), r.get('breakout_score'),
              r.get('breakout_volume_multiple'), r.get('rs_line_new_high'),
              r.get('rs_line_pct_from_high'), r.get('setup_score'), r.get('setup_labels'),
              r.get('atr_14'), r.get('atr_contraction_pct'), r.get('atr_squeeze_score'),
              r.get('tight_range_10d_pct'), r.get('tight_area_score'),
              r['last_updated']))
    conn.commit()
    conn.close()

def upsert_fundamentals(records):
    """Bulk insert/update fundamentals rows. records is a list of dicts."""
    conn = get_connection()
    c = conn.cursor()
    for r in records:
        c.execute('''
        INSERT OR REPLACE INTO fundamentals
        (symbol, eps_growth, sales_growth, roe, debt_to_equity, institutional_holding,
         fii_holding, dii_holding, mutual_fund_holding, institutional_delta_qoq,
         institutional_delta_2q, fii_delta_qoq, dii_delta_qoq, accumulation_score,
         accumulation_labels, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (r['symbol'], r.get('eps_growth'), r.get('sales_growth'), r.get('roe'),
              r.get('debt_to_equity'), r.get('institutional_holding'), r.get('fii_holding'),
              r.get('dii_holding'), r.get('mutual_fund_holding'),
              r.get('institutional_delta_qoq'), r.get('institutional_delta_2q'),
              r.get('fii_delta_qoq'), r.get('dii_delta_qoq'), r.get('accumulation_score'),
              r.get('accumulation_labels'), r['last_updated']))
    conn.commit()
    conn.close()

def upsert_shareholding_history(records):
    """Bulk insert/update historical shareholding rows."""
    if not records:
        return
    conn = get_connection()
    c = conn.cursor()
    for r in records:
        c.execute('''
        INSERT OR REPLACE INTO shareholding_history
        (symbol, quarter, source_order, promoter, fii, dii, mutual_fund, institutional, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (r['symbol'], r['quarter'], r.get('source_order'), r.get('promoter'),
              r.get('fii'), r.get('dii'), r.get('mutual_fund'), r.get('institutional'),
              r['last_updated']))
    conn.commit()
    conn.close()

def get_last_update_times():
    """Retrieve the maximum last_updated timestamp from each table."""
    conn = get_connection()
    c = conn.cursor()
    uni, tech, fund = None, None, None
    try:
        c.execute("SELECT MAX(last_updated) FROM stocks_universe")
        uni = c.fetchone()[0]
    except Exception:
        pass
    try:
        c.execute("SELECT MAX(last_updated) FROM technicals")
        tech = c.fetchone()[0]
    except Exception:
        pass
    try:
        c.execute("SELECT MAX(last_updated) FROM fundamentals")
        fund = c.fetchone()[0]
    except Exception:
        pass
    conn.close()
    return uni, tech, fund

