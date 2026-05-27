# Swing Trade Screener - Indian Markets

A premium stock screening application for Indian Markets (NSE) built with Python and Streamlit. It uses a **Filter-First Scan Flow** based on Minervini's Trend Template, relative strength (RS) ratings, and comprehensive fundamental metrics.

---

## 🚀 Key Features

### 1. Advanced Stock Universe Filtering
- Transitioned to scan **all NSE listed equities** (~2,300+ stocks).
- **Filter-First Scan Flow**: Filters the entire market cap down to the target range (e.g., ₹1,000–10,000 Cr) *before* making technical and fundamental scans to ensure speed and efficiency.

### 2. Minervini Trend Template (6 Rules)
Evaluates whether a stock is in a confirmed stage 2 uptrend:
- Price > 150 SMA & 200 SMA
- 150 SMA > 200 SMA
- 50 SMA > 150 SMA & 200 SMA
- Price > 50 SMA
- Price within selected % of 52-week High

### 3. Momentum & Relative Strength (RS) Ratings
- Calculates a custom RS Rating based on weighted returns (40% 3-month, 30% 6-month, 30% 12-month) and ranks stocks from 1 to 99 against the entire universe.
- Filters for near 3-month highs and 52-week high distances.

### 4. Fast & Robust Fundamental Data Scraper
- **Screener.in Scraping**: Primary data fetcher crawls public Screener.in company pages in parallel to extract ROE, Debt-to-Equity, Compounded Sales Growth (TTM), Compounded Profit Growth (TTM), and Institutional Holding (FIIs + DIIs).
- **YFinance Fallback**: Falls back automatically to Yahoo Finance API if a ticker is not found on Screener.in.

### 5. Interactive Dashboard & Detail Inspector
- **Dynamic Plotly Candlestick Chart**: Toggle to the chart tab under any selected stock to view its 1-year price chart mapped with 50, 150, and 200 SMAs.
- **External Links**: Direct buttons to view stocks on **TradingView** and **Screener.in**.
- **Functional Exports**: Download screened results instantly as **CSV**, **Excel** (via `openpyxl`), or as a **TradingView Watchlist** text file (pre-formatted as `NSE:SYMBOL` for copy-pasting).

---

## 🛠️ Tech Stack
- **Frontend**: Streamlit
- **Data Calculations**: Pandas, NumPy, SciPy
- **Data Scraping & APIs**: BeautifulSoup4, Requests, YFinance
- **Charts**: Plotly
- **Database**: SQLite3

---

## 🏁 How to Run

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch the Application
```bash
streamlit run app.py
```

### 3. Usage
1. Click **🔄 Refresh Universe** to sync the latest NSE listings and market cap data.
2. Select your desired filters on the sidebar (Market Cap, Volume, Price, Fundamentals, etc.).
3. Click **🚀 RUN SCREENER** to filter, fetch technicals/fundamentals, and score the stocks.
4. Drill down on any stock using the **Stock Detail Inspector** and export lists using the download buttons.
