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
        last_updated TIMESTAMP
    )
    ''')
    # Migrations for existing tables
    for col, table in [('rs_rating', 'technicals')]:
        try:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {col} REAL')
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
           t.rs_rating,
           f.eps_growth, f.sales_growth, f.roe, f.debt_to_equity, f.institutional_holding
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
        (symbol, current_price, sma_50, sma_150, sma_200, week_high_52, week_low_52, high_3m, rs_rating, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (r['symbol'], r['current_price'], r['sma_50'], r['sma_150'], r['sma_200'],
              r['week_high_52'], r['week_low_52'], r['high_3m'], r.get('rs_rating'), r['last_updated']))
    conn.commit()
    conn.close()

def upsert_fundamentals(records):
    """Bulk insert/update fundamentals rows. records is a list of dicts."""
    conn = get_connection()
    c = conn.cursor()
    for r in records:
        c.execute('''
        INSERT OR REPLACE INTO fundamentals
        (symbol, eps_growth, sales_growth, roe, debt_to_equity, institutional_holding, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (r['symbol'], r.get('eps_growth'), r.get('sales_growth'), r.get('roe'),
              r.get('debt_to_equity'), r.get('institutional_holding'), r['last_updated']))
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

