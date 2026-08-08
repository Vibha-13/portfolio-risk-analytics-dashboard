# Portfolio Risk Analytics Dashboard

A Python + SQL portfolio tracking and risk analytics tool. Users create a
portfolio, buy/sell stocks, and get real-time valuation, profit/loss,
allocation, and simplified quantitative risk metrics (volatility,
concentration risk, diversification score) — all backed by a normalized
SQLite database queried with raw SQL.

## Why This Project

Built to demonstrate three things together: practical SQL usage (schema
design, JOINs, GROUP BY, aggregates), clean modular Python architecture,
and basic financial/quantitative reasoning — applied to a domain (stock
portfolio risk) relevant to financial technology work.

## Architecture

```
main.py         -> Setup/seed script (creates DB, optional demo data)
dashboard.py    -> Streamlit UI layer (presentation only)
portfolio.py    -> Business logic: buy/sell, valuation, P/L, allocation
analytics.py    -> Risk analytics: volatility, concentration, risk score
market_data.py  -> External API wrapper (yfinance) — isolates the one
                   dependency most likely to change or fail
database.py     -> All raw SQL — the only file that talks to SQLite
utils.py        -> Shared formatting/validation helpers
```

**Design principle:** each layer only talks to the layer directly below
it. `dashboard.py` never writes SQL. `database.py` never contains
business rules (like "average buy price"). This separation means any
single layer (e.g. swapping SQLite for PostgreSQL, or Streamlit for a
React frontend) can be replaced without touching the others.

## Database Schema

Four normalized tables:

- **users** — root entity, one row per user
- **portfolios** — one user can own many portfolios (1:many)
- **holdings** — current snapshot of what's owned (derived/cached from
  transaction history, for fast reads)
- **transactions** — the full, append-only, immutable trade ledger
  (source of truth, mirrors how real accounting/ledger systems work)

Foreign keys enforced (`PRAGMA foreign_keys = ON`), with a
`UNIQUE(portfolio_id, symbol)` constraint on holdings and a
`CHECK(type IN ('BUY','SELL'))` constraint on transactions — both
database-level guardrails, not just application-level checks.

## Folder Structure

```
portfolio-risk-dashboard/
├── main.py
├── dashboard.py
├── portfolio.py
├── analytics.py
├── market_data.py
├── database.py
├── utils.py
├── requirements.txt
├── README.md
├── INTERVIEW_GUIDE.md
└── portfolio.db          (created on first run)
```

## Installation

```bash
pip install -r requirements.txt
```

## How to Run

```bash
# 1. (Optional) seed the database with demo data
python main.py

# 2. Launch the dashboard
streamlit run dashboard.py
```

## Technologies Used

- **Python 3** — core logic
- **SQLite (raw sqlite3, no ORM)** — persistent storage, real SQL
- **Streamlit** — dashboard UI
- **pandas** — data shaping for display/charts
- **plotly** — interactive charts
- **yfinance** — live/recent stock price and sector data
- **numpy** — volatility (standard deviation) calculations

## Risk Metrics (Simplified, Interview-Scoped)

- **Volatility** — weighted average of each holding's daily-return
  standard deviation (does not account for correlation between
  holdings — a known, stated simplification)
- **Concentration Risk (HHI)** — sum of squared portfolio weights;
  higher = more concentrated in fewer positions
- **Diversification Score** — `(1 - HHI) * 100`
- **Risk Score** — weighted blend of volatility (60%) and concentration
  (40%) into a single 0–100 headline number

## Engineering Improvements Made After Initial Build

While testing, two real gaps were found and fixed:

- **Symbol validation** — `buy_stock()` previously accepted any string
  as a stock symbol without checking it was real, silently creating a
  "phantom" holding that would never show a value. Fixed by calling
  `market_data.validate_symbol()` before any database write (placed
  *after* the cheap quantity/price check, so we don't waste an API
  call validating a request that's already invalid for a cheaper reason).
- **Atomic transactions** — `buy_stock()` and `sell_stock()` originally
  wrote to the `holdings` and `transactions` tables using two separate
  database connections. If the app crashed between those two writes,
  the database could end up inconsistent (a holding updated with no
  matching transaction record, or vice versa). Fixed by wrapping both
  writes in a single shared connection with `BEGIN` / `COMMIT` /
  `ROLLBACK`, so either both writes succeed together or neither does.
- **Graceful market data failure handling** — previously, if
  `get_current_price()` failed for a holding (API down, rate limit,
  network issue), that holding was silently dropped from every
  calculation and from the holdings table entirely, with no indication
  anything was wrong — portfolio totals could quietly understate
  reality. Fixed by: (1) `get_profit_loss()` now includes a row for
  every holding even when pricing fails, with pricing fields set to
  `None` instead of the row vanishing; (2) a new `get_unpriced_symbols()`
  function surfaces exactly which symbols failed; (3) the dashboard
  shows an explicit warning banner naming the affected symbols whenever
  this happens, on both the Dashboard and Portfolio pages. Totals
  (portfolio value, P/L) still correctly exclude unpriced holdings
  numerically — you can't sum an unknown value — but that exclusion is
  now visible to the user instead of silent.

## Future Improvements

- Real user authentication (currently uses a single demo user)
- True covariance-matrix-based portfolio volatility
- Realized vs. unrealized P/L split (transaction-based, not just
  current-holdings-based)
- Caching layer for market data to reduce repeated API calls
- Migrate to PostgreSQL for multi-user concurrent access
