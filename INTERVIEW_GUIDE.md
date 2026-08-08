# Interview Guide — Portfolio Risk Analytics Dashboard

## 60-Second Explanation (memorize the shape, not the words)

"I built a portfolio risk analytics dashboard — users can create a
portfolio, buy and sell stocks, and see real-time valuation, profit and
loss, and risk metrics like volatility and concentration risk. It's
backed by a normalized SQLite database with four tables — users,
portfolios, holdings, and transactions — and I used raw SQL throughout,
no ORM, so I'd actually understand and be able to explain every query.
The architecture is split into layers: database access, business logic,
risk analytics, and the Streamlit UI, each in its own file, so any one
layer could be swapped out without touching the others."

## Architecture Explanation

Four layers, each with one job:
1. **database.py** — the only file that writes SQL
2. **portfolio.py** — business rules (buy/sell logic, valuation, P/L)
3. **analytics.py** — risk math (volatility, concentration, risk score)
4. **dashboard.py** — Streamlit UI, calls the other three, contains no
   logic of its own

**Why layered like this:** separation of concerns. If the database
changed (SQLite → PostgreSQL), only database.py changes. If the UI
changed (Streamlit → React+Flask), only dashboard.py changes. Business
logic and risk math stay untouched either way.

## Database Explanation

- **users** → **portfolios** (1:many) → **holdings** + **transactions**
- Holdings = current snapshot (fast to read, updated on every trade)
- Transactions = full append-only history (source of truth, audit trail)
- Why both exist: mirrors real accounting systems — you never edit
  history, you only add to it, but you also want a fast "what do I own
  right now" view without recomputing it from scratch every time.

## Likely SQL Questions + Answers

**Q: Show me a query using JOIN.**
A: `get_portfolio_with_user()` in database.py — joins portfolios and
users to get owner name/email for a given portfolio in one query
instead of two separate lookups combined in Python.

**Q: Show me a query using GROUP BY and aggregates.**
A: `get_transaction_summary()` — groups transactions by symbol, using
`COUNT(*)` for number of trades and `SUM(CASE WHEN...)` to total bought
vs. sold quantity per symbol.

**Q: Why raw SQL instead of an ORM like SQLAlchemy?**
A: Deliberate choice — an ORM would abstract the SQL away, and the goal
was to genuinely understand and be able to explain every query, which
matters more for an interview (and for understanding what's actually
happening) than developer convenience at this project's scale.

**Q: How do you prevent SQL injection?**
A: Every query uses `?` placeholders with parameters passed separately
— never string concatenation or f-strings to build SQL. SQLite treats
placeholder values strictly as data, never as executable SQL.

**Q: Why UNIQUE(portfolio_id, symbol) on holdings?**
A: Ensures one row per stock per portfolio — buying more of a stock you
already own updates that existing row (recalculating average price)
instead of creating a duplicate.

**Q: What's an upsert, and why use one here?**
A: "Insert or update" in one atomic operation. Used when buying a stock
— if you don't own it yet, insert a new holdings row; if you do,
update the existing row's quantity and average price. SQLite does this
via `ON CONFLICT ... DO UPDATE`.

**Q: Why is foreign_keys=ON not the default in SQLite?**
A: Historical/backward-compatibility reasons in SQLite's design — it
must be explicitly enabled per connection. Without it, deleting a
portfolio wouldn't cascade-delete its holdings/transactions, leaving
orphaned rows.

## Likely Python Questions + Answers

**Q: Why separate files instead of one big script?**
A: Each file has a single responsibility (SQL, business logic, risk
math, UI). Easier to test, easier to explain, easier to change one part
without breaking another — a basic but real software engineering
principle.

**Q: How do you handle errors, e.g. if the stock API fails?**
A: `market_data.py` wraps every external call in try/except and returns
`None` on failure rather than crashing or raising, so callers can check
for `None` and display something reasonable ("price unavailable")
instead of the whole app breaking.

**Q: Walk me through what happens when I click "Buy" on the dashboard.**
A: dashboard.py collects the form input → calls `portfolio.buy_stock()`
→ that checks if a holding already exists (recalculates weighted
average price if so, via `db.get_holding()`) → calls
`db.upsert_holding()` to save the new/updated holding → calls
`db.add_transaction()` to log the trade in the permanent ledger →
Streamlit reruns and the UI reflects the new state.

**Q: What's the weighted average price formula and why?**
A: `new_avg = (old_qty * old_avg + new_qty * new_price) / (old_qty + new_qty)`
— this is exactly how real brokerages calculate your "average cost" when
you buy the same stock at different prices over time.

## Likely Finance Questions + Answers

**Q: What's the difference between realized and unrealized P/L?**
A: Unrealized = paper gain/loss on shares you still hold, comparing
current price to what you paid (what this project calculates).
Realized = actual profit/loss locked in from completed sells — this
project's `get_profit_loss()` calculates unrealized P/L specifically;
realized P/L would need to be derived from the transaction history.

**Q: What does volatility mean here, and is it a "real" volatility model?**
A: Standard deviation of daily returns for each stock, weighted-averaged
across the portfolio. Explicitly a simplification — a true portfolio
volatility model needs a covariance matrix to account for how stocks
move relative to each other, which this doesn't do. Good to state this
limitation proactively.

**Q: What is HHI (Herfindahl-Hirschman Index) and why use it here?**
A: A real concentration metric from economics/finance — sum of squared
portfolio weights. Squaring punishes large single positions more than
many small ones, which is exactly what "concentration risk" should
capture.

**Q: Why weight volatility 60% and concentration 40% in the risk score?**
A: A reasonable, explainable judgment call, not a scientifically derived
weighting — volatility reflects immediate day-to-day risk, concentration
reflects slower structural risk. There's no universally "correct" split;
the honest answer is that it's a deliberate, simple design choice.

## Most Likely Coding Follow-Ups

**"Modify buy_stock to also charge a flat $5 transaction fee."**
A: Add `price = price + (5 / quantity)` adjustment or track fee
separately in the transactions table (would need a new column) —
be ready to reason through this live, don't just state the answer.

**"How would you add support for multiple currencies?**
A: Add a `currency` column to holdings/transactions, and a conversion
step in `get_portfolio_value()` before summing — everything would need
to normalize to one base currency before aggregating.

**"How would you paginate transaction history for a portfolio with
thousands of trades?"**
A: Add `LIMIT` and `OFFSET` to the SQL query in `get_transactions()`
instead of fetching and returning everything at once.

## Limitations (say these proactively if asked "what would you improve")

- Single demo user, no real authentication
- Volatility calculation ignores correlation between holdings
- No caching — every dashboard refresh re-hits the yfinance API
- Only unrealized P/L is shown, not realized P/L from actual sales
- SQLite is fine for a single-user demo but wouldn't scale to concurrent
  multi-user production use — PostgreSQL would be the real next step
