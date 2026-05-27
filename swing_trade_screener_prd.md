# Product Requirements Document (PRD)
## Swing Trade Stock Screener - Indian Markets

---

## 1. PRODUCT OVERVIEW

### 1.1 Product Name
**SwingScreener** - A simple, fast stock screener for swing traders (1-2 month hold period)

### 1.2 Purpose
Identify high-probability swing trade setups in Indian markets (NSE) using 4 core filter categories, showing only stocks that pass 90-100% of criteria.

### 1.3 Target Users
- Swing traders holding positions for 1-2 months
- Retail investors looking for momentum stocks
- Part-time traders who need quick, actionable results

### 1.4 Core Philosophy
**Simple, Fast, Actionable**
- No complex workflows
- One-click screening
- Clear results
- User can customize filters as needed

---

## 2. SCREENING CRITERIA (4 CATEGORIES)

### 2.1 UNIVERSE FILTERS (Pre-Screen)

**Purpose**: Narrow down the universe to liquid, tradeable stocks.

| Filter | Criteria | User Adjustable? |
|--------|----------|------------------|
| Market Cap | ₹3,000 cr - ₹50,000 cr | YES (slider) |
| Avg Daily Volume | > 100,000 shares | YES (input box) |
| Price Range | > ₹50 | YES (input box) |
| Exclude T2T Stocks | Yes | NO (always exclude) |

**Default Settings**:
- Market cap: ₹3,000 cr - ₹50,000 cr
- Volume: 100,000 shares
- Price: ₹50

**Expected Output**: ~400-500 stocks (from NSE universe of ~1,700)

---

### 2.2 FUNDAMENTAL FILTERS (Relaxed for Swing)

**Purpose**: Ensure basic fundamental quality without being too strict.

| Filter | Criteria | User Adjustable? | Data Source |
|--------|----------|------------------|-------------|
| Quarterly EPS Growth | ≥ 20% YoY | YES (dropdown: 15%, 20%, 25%, 30%) | Screener.in |
| Quarterly Sales Growth | ≥ 20% YoY | YES (dropdown: 15%, 20%, 25%) | Screener.in |
| ROE | ≥ 15% | YES (dropdown: 10%, 15%, 17%, 20%) | Screener.in |
| Debt-to-Equity | < 1.5 | YES (dropdown: 1.0, 1.5, 2.0) | Screener.in |
| FII + DII Holding | ≥ 5% | YES (dropdown: 5%, 10%, 15%) | Screener.in |

**Default Settings**:
- EPS Growth: 20%
- Sales Growth: 20%
- ROE: 15%
- D/E: 1.5
- Institutional Holding: 5%

**Weightage**: Each filter = 20% (total 100% for this category)

---

### 2.3 TREND TEMPLATE (6 out of 8 Checks)

**Purpose**: Confirm stock is in a strong uptrend.

| Check # | Criteria | User Adjustable? | Data Source |
|---------|----------|------------------|-------------|
| 1 | Price > 150-day SMA | NO | TradingView / NSE |
| 2 | Price > 200-day SMA | NO | TradingView / NSE |
| 3 | 150-day SMA > 200-day SMA | NO | TradingView / NSE |
| 4 | 50-day SMA > 150-day SMA | NO | TradingView / NSE |
| 5 | Price > 50-day SMA | NO | TradingView / NSE |
| 6 | Price within 30% of 52-week high | YES (dropdown: 20%, 25%, 30%) | TradingView / NSE |

**Pass Criteria**: Minimum 5 out of 6 checks must pass (83.3%)

**Weightage**: Each check = ~16.7% (total 100% for this category)

---

### 2.4 MOMENTUM FILTERS (Key for Swing)

**Purpose**: Identify stocks with strong recent momentum.

| Filter | Criteria | User Adjustable? | Data Source |
|--------|----------|------------------|-------------|
| RS Rating | ≥ 70 | YES (dropdown: 65, 70, 75, 80) | Calculated from NSE data |
| Distance from 52W High | Within 15% | YES (dropdown: 10%, 15%, 20%) | TradingView / NSE |
| Recent Price Action | New 3-month high OR near breakout | NO | TradingView / NSE |

**RS Rating Calculation**:
```
RS Score = (13-week return × 0.4) + (26-week return × 0.3) + (52-week return × 0.3)
RS Rating = Percentile rank of RS Score across all NSE stocks
```

**Default Settings**:
- RS Rating: 70
- Distance from 52W High: 15%

**Weightage**: Each filter = 33.3% (total 100% for this category)

---

## 3. OVERALL SCORING SYSTEM

### 3.1 Category Weights

| Category | Weight |
|----------|--------|
| Universe Filters | Pass/Fail (not scored) |
| Fundamental Filters | 30% |
| Trend Template | 40% |
| Momentum Filters | 30% |

**Total Score**: 0-100%

### 3.2 Result Thresholds

**Perfect Match**: 100% score
- Passes ALL filters in all categories

**Approximate Match**: 90-99% score
- Minor deviations allowed (e.g., ROE 14% instead of 15%, or 5/6 Trend Template checks)

**Below Threshold**: < 90% score
- Not shown in results

---

## 4. DATA SOURCES & INTEGRATION

### 4.1 Data Source Hierarchy

**Primary Source**: NSE India (for price data, volume, 52-week high/low)
- API: NSE public data (if available)
- Fallback: Web scraping NSE Bhavcopy

**Secondary Source**: Screener.in (for fundamental data)
- Web scraping (no official API)
- Cache data for 24 hours (refresh daily)

**Tertiary Source**: TradingView (for technical indicators backup)
- Use if NSE data incomplete
- Python library: `tvdatafeed` (unofficial)

### 4.2 Data Refresh Strategy

**Daily Refresh** (automated at 6 PM IST):
- Price data (close, high, low, volume)
- 50-day, 150-day, 200-day SMAs
- 52-week high/low
- RS Rating calculation

**Weekly Refresh** (automated on Sunday):
- Fundamental data (EPS, Sales, ROE, D/E, Holdings)
- Universe list (market cap changes)

**User-Triggered**:
- User can manually click "Refresh Data" if needed

### 4.3 Data Storage

**Local SQLite Database**:
```
stocks_universe (symbol, name, market_cap, avg_volume, price)
fundamentals (symbol, eps_growth, sales_growth, roe, de_ratio, institutional)
technicals (symbol, sma50, sma150, sma200, week_high_52, week_low_52, rs_rating)
scan_results (scan_id, symbol, score, category_scores, timestamp)
```

---

## 5. USER INTERFACE (UI/UX)

### 5.1 Main Screen Layout

```
┌─────────────────────────────────────────────────────────────┐
│  SWINGSCREENER - Indian Markets                              │
│  ─────────────────────────────────────────────────────────  │
│  Last Data Update: May 24, 2026 6:00 PM                     │
│  ─────────────────────────────────────────────────────────  │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FILTERS (Click to Expand/Collapse)                  │   │
│  │  ─────────────────────────────────────────────────── │   │
│  │                                                        │   │
│  │  🔽 Universe Filters                                  │   │
│  │     Market Cap: [3000] - [50000] cr (slider)         │   │
│  │     Min Volume: [100000] shares                       │   │
│  │     Min Price: [50] ₹                                 │   │
│  │                                                        │   │
│  │  🔽 Fundamental Filters                               │   │
│  │     EPS Growth: [20%▼]   Sales Growth: [20%▼]        │   │
│  │     ROE: [15%▼]          D/E Ratio: [1.5▼]           │   │
│  │     Institutional: [5%▼]                              │   │
│  │                                                        │   │
│  │  🔽 Trend Template (5/6 minimum)                      │   │
│  │     Distance from 52W High: [30%▼]                   │   │
│  │                                                        │   │
│  │  🔽 Momentum Filters                                  │   │
│  │     RS Rating: [70▼]                                  │   │
│  │     Distance from 52W High: [15%▼]                   │   │
│  │                                                        │   │
│  │  [Reset to Default]  [Save Preset]  [Load Preset]   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │            🚀 [RUN SCREENER]                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  Progress: ████████████████░░░░░░░░ 80% (320/400 stocks)   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Results Screen Layout

```
┌─────────────────────────────────────────────────────────────┐
│  RESULTS - Scan completed in 12 seconds                      │
│  ─────────────────────────────────────────────────────────  │
│  Found: 12 stocks                                            │
│                                                               │
│  View: ● Perfect Match (100%) - 5 stocks                    │
│        ○ Approximate Match (90-99%) - 7 stocks               │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Rank | Symbol    | Score | Fundamental | Trend | Momentum│
│  ├─────────────────────────────────────────────────────┤   │
│  │  1   | DIXON     | 100%  | 100%        | 100%  | 100%   │
│  │  2   | POLYCAB   | 100%  | 100%        | 100%  | 100%   │
│  │  3   | PERSISTENT| 100%  | 100%        | 100%  | 100%   │
│  │  4   | COFORGE   | 100%  | 100%        | 100%  | 100%   │
│  │  5   | TECHM     | 100%  | 100%        | 100%  | 100%   │
│  ├─────────────────────────────────────────────────────┤   │
│  │  [Click row to see detailed breakdown]                  │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  [Export to CSV]  [Export to Excel]  [Save as Watchlist]   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Stock Detail View (Click on Row)

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back to Results          DIXON - Dixon Technologies       │
│  ─────────────────────────────────────────────────────────  │
│  Overall Score: 100%  |  Price: ₹8,245  |  RS Rating: 96   │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  SCORE BREAKDOWN                                      │   │
│  │  ─────────────────────────────────────────────────── │   │
│  │                                                        │   │
│  │  Fundamental (30%): ████████████████████ 100%        │   │
│  │    ✓ EPS Growth: 52% (target: 20%)                   │   │
│  │    ✓ Sales Growth: 68% (target: 20%)                 │   │
│  │    ✓ ROE: 28% (target: 15%)                          │   │
│  │    ✓ D/E: 0.3 (target: <1.5)                         │   │
│  │    ✓ Institutional: 18% (target: 5%)                 │   │
│  │                                                        │   │
│  │  Trend Template (40%): ████████████████████ 100%     │   │
│  │    ✓ Price > 150 SMA (₹8,245 > ₹7,450)               │   │
│  │    ✓ Price > 200 SMA (₹8,245 > ₹6,980)               │   │
│  │    ✓ 150 SMA > 200 SMA                                │   │
│  │    ✓ 50 SMA > 150 SMA                                 │   │
│  │    ✓ Price > 50 SMA (₹8,245 > ₹8,100)                │   │
│  │    ✓ Within 30% of 52W High (₹8,500) - Distance: 3%  │   │
│  │                                                        │   │
│  │  Momentum (30%): ████████████████████ 100%           │   │
│  │    ✓ RS Rating: 96 (target: 70)                      │   │
│  │    ✓ Distance from 52W High: 3% (target: <15%)       │   │
│  │    ✓ Recent High: Yes (new 3-month high)             │   │
│  │                                                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  [View on TradingView]  [View on Screener.in]  [Add to Watchlist]│
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. TECHNICAL ARCHITECTURE

### 6.1 Technology Stack

**Backend (Python)**:
- `pandas` - Data manipulation
- `numpy` - Calculations
- `requests` / `beautifulsoup4` - Web scraping
- `yfinance` - NSE data (via Yahoo Finance India)
- `sqlite3` - Local database
- `schedule` - Automated data refresh

**Frontend (Simple Web UI)**:
- **Option 1**: Streamlit (easiest, fastest to build)
- **Option 2**: Flask + HTML/CSS/JavaScript (more control)
- **Recommended**: Streamlit for MVP

**Data Visualization**:
- `plotly` - Interactive tables
- `pandas.DataFrame.style` - Colored score bars

### 6.2 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      USER INTERFACE                          │
│             (Streamlit / Flask Web App)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  SCREENER ENGINE                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  1. Load User Filter Settings                        │   │
│  │  2. Apply Universe Filters (SQL query)               │   │
│  │  3. Apply Fundamental Filters (scoring)              │   │
│  │  4. Apply Trend Template (scoring)                   │   │
│  │  5. Apply Momentum Filters (scoring)                 │   │
│  │  6. Calculate Overall Score                          │   │
│  │  7. Filter Results (score >= 90%)                    │   │
│  │  8. Rank by Score (descending)                       │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   DATA LAYER                                 │
│  ┌──────────────┬──────────────┬──────────────┐            │
│  │ NSE Data     │ Screener.in  │ TradingView  │            │
│  │ Fetcher      │ Scraper      │ Fetcher      │            │
│  └──────┬───────┴──────┬───────┴──────┬───────┘            │
│         │              │              │                     │
│  ┌──────▼──────────────▼──────────────▼───────┐            │
│  │       SQLite Database (Local)                │            │
│  │  - stocks_universe                           │            │
│  │  - fundamentals                              │            │
│  │  - technicals                                │            │
│  │  - scan_results                              │            │
│  └──────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 Database Schema

**Table: stocks_universe**
```sql
CREATE TABLE stocks_universe (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    market_cap REAL,
    avg_volume INTEGER,
    current_price REAL,
    is_t2t BOOLEAN,
    last_updated TIMESTAMP
);
```

**Table: fundamentals**
```sql
CREATE TABLE fundamentals (
    symbol TEXT PRIMARY KEY,
    eps_growth_q1 REAL,
    eps_growth_q2 REAL,
    sales_growth_q1 REAL,
    sales_growth_q2 REAL,
    roe REAL,
    debt_to_equity REAL,
    fii_holding REAL,
    dii_holding REAL,
    last_updated TIMESTAMP
);
```

**Table: technicals**
```sql
CREATE TABLE technicals (
    symbol TEXT PRIMARY KEY,
    current_price REAL,
    sma_50 REAL,
    sma_150 REAL,
    sma_200 REAL,
    week_high_52 REAL,
    week_low_52 REAL,
    rs_rating REAL,
    last_updated TIMESTAMP
);
```

**Table: scan_results**
```sql
CREATE TABLE scan_results (
    scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date TIMESTAMP,
    symbol TEXT,
    overall_score REAL,
    fundamental_score REAL,
    trend_score REAL,
    momentum_score REAL,
    details JSON
);
```

---

## 7. CORE ALGORITHMS

### 7.1 Universe Filter (SQL Query)

```python
def apply_universe_filters(market_cap_min, market_cap_max, min_volume, min_price):
    query = """
    SELECT symbol 
    FROM stocks_universe 
    WHERE market_cap >= ? 
      AND market_cap <= ? 
      AND avg_volume >= ?
      AND current_price >= ?
      AND is_t2t = 0
    """
    return execute_query(query, (market_cap_min, market_cap_max, min_volume, min_price))
```

**Output**: List of stock symbols (e.g., ['DIXON', 'POLYCAB', 'TECHM', ...])

---

### 7.2 Fundamental Scoring

```python
def calculate_fundamental_score(symbol, user_criteria):
    """
    Each filter worth 20% (5 filters total = 100%)
    """
    data = get_fundamental_data(symbol)
    score = 0
    
    # EPS Growth (20%)
    if data['eps_growth_q1'] >= user_criteria['eps_growth'] and \
       data['eps_growth_q2'] >= user_criteria['eps_growth']:
        score += 20
    
    # Sales Growth (20%)
    if data['sales_growth_q1'] >= user_criteria['sales_growth'] and \
       data['sales_growth_q2'] >= user_criteria['sales_growth']:
        score += 20
    
    # ROE (20%)
    if data['roe'] >= user_criteria['roe']:
        score += 20
    
    # Debt-to-Equity (20%)
    if data['debt_to_equity'] < user_criteria['de_ratio']:
        score += 20
    
    # Institutional Holding (20%)
    if (data['fii_holding'] + data['dii_holding']) >= user_criteria['institutional']:
        score += 20
    
    return score  # 0-100
```

---

### 7.3 Trend Template Scoring

```python
def calculate_trend_score(symbol, user_criteria):
    """
    6 checks, each worth 16.67% (6 checks × 16.67% ≈ 100%)
    Minimum 5/6 checks must pass to qualify
    """
    data = get_technical_data(symbol)
    checks_passed = 0
    
    # Check 1: Price > 150 SMA
    if data['current_price'] > data['sma_150']:
        checks_passed += 1
    
    # Check 2: Price > 200 SMA
    if data['current_price'] > data['sma_200']:
        checks_passed += 1
    
    # Check 3: 150 SMA > 200 SMA
    if data['sma_150'] > data['sma_200']:
        checks_passed += 1
    
    # Check 4: 50 SMA > 150 SMA
    if data['sma_50'] > data['sma_150']:
        checks_passed += 1
    
    # Check 5: Price > 50 SMA
    if data['current_price'] > data['sma_50']:
        checks_passed += 1
    
    # Check 6: Price within X% of 52-week high
    distance_from_high = ((data['week_high_52'] - data['current_price']) / data['week_high_52']) * 100
    if distance_from_high <= user_criteria['distance_from_52w_high']:
        checks_passed += 1
    
    # Score
    score = (checks_passed / 6) * 100
    
    # Minimum threshold: 5/6 checks (83.3%)
    if score < 83.3:
        return 0  # Disqualify if below threshold
    
    return score  # 83.3-100
```

---

### 7.4 Momentum Scoring

```python
def calculate_momentum_score(symbol, user_criteria):
    """
    3 filters, each worth 33.3% (3 filters × 33.3% ≈ 100%)
    """
    data = get_technical_data(symbol)
    score = 0
    
    # RS Rating (33.3%)
    if data['rs_rating'] >= user_criteria['rs_rating']:
        score += 33.3
    
    # Distance from 52-week high (33.3%)
    distance_from_high = ((data['week_high_52'] - data['current_price']) / data['week_high_52']) * 100
    if distance_from_high <= user_criteria['distance_from_52w_high_momentum']:
        score += 33.3
    
    # Recent Price Action (33.3%)
    # Check if making new 3-month high
    three_month_high = get_3_month_high(symbol)
    if data['current_price'] >= three_month_high * 0.98:  # Within 2% of 3-month high
        score += 33.4  # Rounded to make total 100
    
    return score  # 0-100
```

---

### 7.5 Overall Scoring

```python
def calculate_overall_score(symbol, user_criteria):
    """
    Weighted average:
    - Fundamental: 30%
    - Trend Template: 40%
    - Momentum: 30%
    """
    fundamental_score = calculate_fundamental_score(symbol, user_criteria)
    trend_score = calculate_trend_score(symbol, user_criteria)
    momentum_score = calculate_momentum_score(symbol, user_criteria)
    
    # If Trend Template fails minimum threshold, disqualify
    if trend_score == 0:
        return None  # Don't include in results
    
    overall_score = (
        (fundamental_score * 0.30) +
        (trend_score * 0.40) +
        (momentum_score * 0.30)
    )
    
    return {
        'overall': round(overall_score, 2),
        'fundamental': round(fundamental_score, 2),
        'trend': round(trend_score, 2),
        'momentum': round(momentum_score, 2)
    }
```

---

### 7.6 RS Rating Calculation

```python
def calculate_rs_rating(symbol):
    """
    Calculate relative strength rating (0-100)
    Compare stock's performance vs all other stocks
    """
    # Get returns
    returns_13w = get_return(symbol, weeks=13)
    returns_26w = get_return(symbol, weeks=26)
    returns_52w = get_return(symbol, weeks=52)
    
    # Weighted score
    stock_score = (returns_13w * 0.4) + (returns_26w * 0.3) + (returns_52w * 0.3)
    
    # Get all stocks' scores
    all_scores = []
    for s in get_all_symbols():
        r13 = get_return(s, weeks=13)
        r26 = get_return(s, weeks=26)
        r52 = get_return(s, weeks=52)
        score = (r13 * 0.4) + (r26 * 0.3) + (r52 * 0.3)
        all_scores.append(score)
    
    # Calculate percentile rank
    from scipy.stats import percentileofscore
    rs_rating = percentileofscore(all_scores, stock_score)
    
    return round(rs_rating, 2)
```

---

## 8. USER WORKFLOW

### 8.1 First-Time User

**Step 1**: User opens the app
- Sees default filter settings (already configured)
- Sees "RUN SCREENER" button

**Step 2**: User clicks "RUN SCREENER"
- Progress bar appears
- Screener processes ~400 stocks in 10-15 seconds

**Step 3**: Results appear
- User sees table with 10-15 stocks (90-100% match)
- Can toggle between "Perfect Match" and "Approximate Match"

**Step 4**: User clicks on a stock
- Detailed breakdown appears
- Can export to CSV or add to watchlist

**Total Time**: < 1 minute from open to results

---

### 8.2 Advanced User

**Step 1**: Adjust filters
- Opens filter panel
- Changes EPS growth from 20% → 25%
- Changes RS Rating from 70 → 80
- Saves as "Aggressive Preset"

**Step 2**: Run screener with custom settings
- Results now show only 5 stocks (stricter criteria)

**Step 3**: Compare presets
- Loads "Conservative Preset" (EPS 15%, RS 65)
- Runs again → sees 20 stocks

**Step 4**: Exports both results to Excel for comparison

---

## 9. FEATURE SPECIFICATIONS

### 9.1 Core Features (MVP - Must Have)

**F1: Data Refresh**
- Automatic daily refresh at 6 PM IST
- Manual "Refresh Now" button

**F2: Run Screener**
- One-click execution
- Progress indicator
- ETA display

**F3: Results Display**
- Tabular format
- Sortable columns (by score, symbol, etc.)
- Toggle between Perfect/Approximate matches

**F4: Stock Detail View**
- Score breakdown (visual bars)
- All filter values displayed
- Links to TradingView & Screener.in

**F5: Export Results**
- Export to CSV
- Export to Excel
- Copy to clipboard

**F6: Filter Customization**
- All filters user-adjustable via dropdowns/sliders
- "Reset to Default" button
- "Save Preset" / "Load Preset"

---

### 9.2 Nice-to-Have Features (Future)

**F7: Historical Scan Comparison**
- Compare today's scan vs last week's scan
- See which stocks entered/exited the list

**F8: Watchlist Management**
- Add stocks to personal watchlist
- Get alerts when watchlist stock hits 100% score

**F9: Backtesting**
- "If I ran this scan 6 months ago, what would the returns be?"

**F10: Email Alerts**
- Daily email with scan results
- Only if perfect matches found

---

## 10. DATA FETCHING IMPLEMENTATION

### 10.1 NSE Data Fetcher

```python
import yfinance as yf
import pandas as pd

def fetch_nse_data(symbol):
    """
    Fetch price data and calculate SMAs
    Symbol format: 'RELIANCE.NS' (NSE), 'RELIANCE.BO' (BSE)
    """
    ticker = yf.Ticker(f"{symbol}.NS")
    
    # Get 1 year of data (for 200-day SMA calculation)
    hist = ticker.history(period="1y")
    
    # Calculate SMAs
    hist['SMA50'] = hist['Close'].rolling(window=50).mean()
    hist['SMA150'] = hist['Close'].rolling(window=150).mean()
    hist['SMA200'] = hist['Close'].rolling(window=200).mean()
    
    # Get current values
    current_price = hist['Close'].iloc[-1]
    sma50 = hist['SMA50'].iloc[-1]
    sma150 = hist['SMA150'].iloc[-1]
    sma200 = hist['SMA200'].iloc[-1]
    week_high_52 = hist['High'].iloc[-252:].max()  # ~252 trading days in a year
    week_low_52 = hist['Low'].iloc[-252:].min()
    
    # Calculate volume
    avg_volume = hist['Volume'].iloc[-50:].mean()
    
    return {
        'current_price': current_price,
        'sma50': sma50,
        'sma150': sma150,
        'sma200': sma200,
        'week_high_52': week_high_52,
        'week_low_52': week_low_52,
        'avg_volume': avg_volume
    }
```

---

### 10.2 Screener.in Scraper

```python
import requests
from bs4 import BeautifulSoup
import time

def fetch_screener_data(symbol):
    """
    Scrape fundamental data from Screener.in
    """
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract data (example selectors - may need adjustment)
        eps_growth = extract_eps_growth(soup)
        sales_growth = extract_sales_growth(soup)
        roe = extract_roe(soup)
        de_ratio = extract_de_ratio(soup)
        fii_holding = extract_fii_holding(soup)
        dii_holding = extract_dii_holding(soup)
        
        time.sleep(2)  # Rate limiting (be respectful)
        
        return {
            'eps_growth_q1': eps_growth[0],
            'eps_growth_q2': eps_growth[1],
            'sales_growth_q1': sales_growth[0],
            'sales_growth_q2': sales_growth[1],
            'roe': roe,
            'debt_to_equity': de_ratio,
            'fii_holding': fii_holding,
            'dii_holding': dii_holding
        }
    
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None
```

**Note**: Screener.in structure may change. The scraper needs to be robust with try-catch blocks.

---

### 10.3 Data Caching Strategy

```python
from datetime import datetime, timedelta
import sqlite3

def get_cached_data(symbol, data_type='technical'):
    """
    Check if data is in cache and still fresh
    """
    conn = sqlite3.connect('screener.db')
    cursor = conn.cursor()
    
    if data_type == 'technical':
        cursor.execute("""
            SELECT * FROM technicals 
            WHERE symbol = ? 
              AND last_updated > datetime('now', '-1 day')
        """, (symbol,))
    elif data_type == 'fundamental':
        cursor.execute("""
            SELECT * FROM fundamentals 
            WHERE symbol = ? 
              AND last_updated > datetime('now', '-7 days')
        """, (symbol,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return result  # Return cached data
    else:
        return None  # Need to fetch fresh data
```

---

## 11. ERROR HANDLING

### 11.1 Data Fetch Failures

**Scenario**: NSE API is down, or Screener.in blocks the request.

**Handling**:
```python
def fetch_data_with_retry(symbol, max_retries=3):
    for attempt in range(max_retries):
        try:
            data = fetch_nse_data(symbol)
            if data:
                return data
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)  # Wait 5 seconds before retry
                continue
            else:
                # Log error and use cached data if available
                cached = get_cached_data(symbol)
                if cached:
                    return cached
                else:
                    # Skip this stock in the scan
                    return None
```

**User Experience**:
- Display warning: "Some stocks skipped due to data unavailability"
- Show count of skipped stocks

---

### 11.2 Invalid User Input

**Scenario**: User enters invalid filter values (e.g., negative market cap).

**Validation**:
```python
def validate_filters(filters):
    errors = []
    
    if filters['market_cap_min'] < 0:
        errors.append("Market cap minimum cannot be negative")
    
    if filters['market_cap_min'] > filters['market_cap_max']:
        errors.append("Market cap minimum cannot exceed maximum")
    
    if filters['eps_growth'] < 0:
        errors.append("EPS growth cannot be negative")
    
    # ... more validations
    
    return errors
```

**User Experience**:
- Show error messages in red
- Prevent "RUN SCREENER" button from working until fixed

---

### 11.3 Empty Results

**Scenario**: No stocks pass the 90% threshold.

**Handling**:
- Display message: "No stocks found matching your criteria (≥90% score)"
- Show suggestion: "Try relaxing your filters (e.g., lower RS Rating to 65)"
- Show top 5 stocks even if below 90% (with clear warning)

---

## 12. PERFORMANCE REQUIREMENTS

### 12.1 Scan Speed

**Target**: Complete scan in < 20 seconds for 400 stocks

**Optimization Strategies**:
- Use cached data (refresh only once daily)
- Parallel processing (process 10 stocks at a time using `multiprocessing`)
- Pre-calculate SMAs during daily refresh (don't recalculate during scan)

```python
from multiprocessing import Pool

def scan_stocks_parallel(symbols, user_criteria):
    with Pool(processes=10) as pool:
        results = pool.starmap(
            calculate_overall_score, 
            [(symbol, user_criteria) for symbol in symbols]
        )
    return results
```

---

### 12.2 Data Refresh Speed

**Target**: Daily refresh completes in < 5 minutes for 400 stocks

**Strategy**:
- Run refresh as background task (doesn't block user)
- Show "Data refreshing..." indicator
- Use parallel API calls

---

### 12.3 UI Responsiveness

**Target**: UI loads in < 2 seconds

**Strategy**:
- Use lazy loading for results table (load first 20 rows, then load more on scroll)
- Cache filter settings in browser localStorage
- Minimize database queries

---

## 13. TESTING STRATEGY

### 13.1 Unit Tests

**Test Data Fetchers**:
```python
def test_fetch_nse_data():
    data = fetch_nse_data('RELIANCE')
    assert data is not None
    assert data['current_price'] > 0
    assert data['sma50'] > 0
```

**Test Scoring Functions**:
```python
def test_fundamental_scoring():
    mock_data = {
        'eps_growth_q1': 25,
        'eps_growth_q2': 30,
        'sales_growth_q1': 22,
        'sales_growth_q2': 28,
        'roe': 20,
        'debt_to_equity': 0.5,
        'fii_holding': 10,
        'dii_holding': 5
    }
    score = calculate_fundamental_score('TEST', mock_data)
    assert score == 100  # Should pass all filters
```

---

### 13.2 Integration Tests

**Test Full Scan**:
```python
def test_full_scan():
    user_criteria = get_default_criteria()
    results = run_screener(user_criteria)
    
    assert len(results) > 0
    assert all(r['overall'] >= 90 for r in results)
```

---

### 13.3 User Acceptance Testing

**Test Cases**:
1. User opens app → sees default filters
2. User clicks "RUN SCREENER" → results appear in < 20 seconds
3. User adjusts EPS filter → scan re-runs with new criteria
4. User clicks stock → detail view appears
5. User exports to CSV → file downloads successfully

---

## 14. DEPLOYMENT

### 14.1 Local Deployment (Recommended for MVP)

**Steps**:
1. Install Python 3.10+
2. Install dependencies: `pip install -r requirements.txt`
3. Run data refresh: `python refresh_data.py`
4. Start app: `streamlit run app.py`
5. Open browser: `http://localhost:8501`

**Pros**:
- Simple
- No hosting costs
- Fast performance
- Data privacy (local database)

**Cons**:
- Must keep computer running
- Not accessible from other devices

---

### 14.2 Cloud Deployment (Future)

**Options**:
- **Streamlit Cloud** (easiest, free tier available)
- **Heroku** (simple, paid)
- **AWS EC2** (full control, requires DevOps knowledge)

**Considerations**:
- Data refresh needs cron job (scheduled task)
- Database: Migrate from SQLite to PostgreSQL (if multiple users)

---

## 15. TIMELINE & MILESTONES

### 15.1 Development Phases

**Week 1-2: Data Layer**
- [ ] Set up SQLite database
- [ ] Build NSE data fetcher (yfinance)
- [ ] Build Screener.in scraper
- [ ] Test data refresh for 50 stocks
- [ ] Implement caching

**Week 3: Scoring Engine**
- [ ] Implement fundamental scoring
- [ ] Implement trend template scoring
- [ ] Implement momentum scoring
- [ ] Implement RS rating calculation
- [ ] Test scoring on sample stocks

**Week 4: User Interface**
- [ ] Build filter panel (Streamlit)
- [ ] Build "RUN SCREENER" functionality
- [ ] Build results table
- [ ] Build stock detail view
- [ ] Add export functionality

**Week 5: Testing & Polish**
- [ ] Unit tests
- [ ] Integration tests
- [ ] User testing (5 people)
- [ ] Bug fixes
- [ ] Documentation (README, user guide)

**Week 6: Deployment**
- [ ] Local deployment instructions
- [ ] (Optional) Deploy to Streamlit Cloud
- [ ] Create demo video

---

### 15.2 Success Metrics

**Technical**:
- Scan completes in < 20 seconds ✓
- Data refresh completes in < 5 minutes ✓
- 95%+ uptime (data sources accessible) ✓

**User**:
- User can complete first scan in < 1 minute ✓
- Results are accurate (manually verify 10 stocks) ✓
- Export works for CSV and Excel ✓

---

## 16. FUTURE ENHANCEMENTS

### 16.1 Phase 2 Features (After MVP)

**1. Alerts System**
- Email/SMS when new perfect match appears
- Watchlist alerts (when stock enters 100% zone)

**2. Mobile App**
- React Native app (iOS/Android)
- Push notifications

**3. Backtesting**
- "What if I bought every 100% match 6 months ago?"
- Show theoretical returns

**4. Advanced Filters**
- VCP pattern detection (volatility contraction)
- Base formation quality (cup-with-handle, flat base)
- Volume analysis (breakout volume)

**5. Social Features**
- Share scan results with friends
- Community presets (e.g., "Aggressive Growth" preset shared by other users)

---

### 16.2 Phase 3 Features (Long-Term)

**1. AI-Powered Insights**
- "Why did this stock score 100%?" (natural language explanation)
- "Stocks similar to DIXON" (ML-based recommendations)

**2. Portfolio Tracking**
- Track your actual trades
- Compare your picks vs scan results
- Performance analytics

**3. Real-Time Screening**
- Intraday scans (every 15 minutes)
- Catch breakouts as they happen

---

## 17. APPENDIX

### 17.1 Sample Output (JSON)

```json
{
  "scan_id": 12345,
  "scan_date": "2026-05-24T18:00:00",
  "total_stocks_scanned": 412,
  "results_count": 12,
  "results": [
    {
      "rank": 1,
      "symbol": "DIXON",
      "name": "Dixon Technologies",
      "overall_score": 100.0,
      "fundamental_score": 100.0,
      "trend_score": 100.0,
      "momentum_score": 100.0,
      "current_price": 8245,
      "rs_rating": 96,
      "details": {
        "fundamental": {
          "eps_growth_q1": 52,
          "eps_growth_q2": 48,
          "sales_growth_q1": 68,
          "sales_growth_q2": 55,
          "roe": 28,
          "de_ratio": 0.3,
          "institutional": 18
        },
        "trend": {
          "price_vs_150sma": "PASS",
          "price_vs_200sma": "PASS",
          "150_vs_200": "PASS",
          "50_vs_150": "PASS",
          "price_vs_50sma": "PASS",
          "distance_from_52w_high": 3.0
        },
        "momentum": {
          "rs_rating": 96,
          "distance_from_52w_high": 3.0,
          "new_3month_high": true
        }
      }
    }
  ]
}
```

---

### 17.2 Sample User Preset

```json
{
  "preset_name": "Aggressive Growth",
  "created_by": "user123",
  "filters": {
    "universe": {
      "market_cap_min": 5000,
      "market_cap_max": 30000,
      "min_volume": 200000,
      "min_price": 100
    },
    "fundamental": {
      "eps_growth": 30,
      "sales_growth": 25,
      "roe": 20,
      "de_ratio": 1.0,
      "institutional": 10
    },
    "trend": {
      "distance_from_52w_high": 20
    },
    "momentum": {
      "rs_rating": 80,
      "distance_from_52w_high": 10
    }
  }
}
```

---

## 18. GLOSSARY

**EPS**: Earnings Per Share (₹ per share)
**YoY**: Year-over-Year (comparing same quarter last year)
**ROE**: Return on Equity (Net Income / Shareholders' Equity × 100)
**D/E**: Debt-to-Equity Ratio (Total Debt / Shareholders' Equity)
**FII**: Foreign Institutional Investor
**DII**: Domestic Institutional Investor
**SMA**: Simple Moving Average (average price over N days)
**RS Rating**: Relative Strength Rating (0-100, comparing stock vs market)
**52W High**: Highest price in last 52 weeks (1 year)
**T2T**: Trade-to-Trade segment (stocks with settlement restrictions)
**Swing Trade**: Trading style holding positions for 1-2 months

---

## 19. CONTACT & SUPPORT

**For Developers Building This**:
- This PRD is complete and ready to hand off to AI coding tools (ChatGPT, Claude, GitHub Copilot)
- Recommended approach: Build in phases (Data Layer → Scoring → UI)
- Start with Streamlit for fastest MVP

**For Users**:
- Expected first version: 6 weeks from start
- Platform: Local web app (accessible via browser)
- Cost: Free (runs on your computer)

---

**END OF PRD**

**Document Version**: 1.0  
**Last Updated**: May 24, 2026  
**Total Pages**: ~35  
**Ready for**: AI-assisted development
