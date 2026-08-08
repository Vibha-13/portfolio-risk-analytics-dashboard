"""
portfolio.py
------------
Contains the core BUSINESS LOGIC for buying/selling stocks and computing
portfolio-level facts (value, profit/loss, allocation). This file sits
between database.py (raw SQL) and dashboard.py (UI) -- it's where the
actual "rules" of how a portfolio behaves live.

WHY THIS SEPARATION MATTERS (interview point):
database.py doesn't know what "average buy price" means or how to
recalculate it when you buy more of a stock you already own -- it just
stores/retrieves rows. portfolio.py is where that financial logic lives.
This means if the RULES change (e.g. we later want to support fractional
shares, or fees per transaction), we only touch this file, not the SQL
layer or the UI layer.
"""

import database as db
import market_data


def buy_stock(portfolio_id, symbol, quantity, price, sector=None):
    """
    Handles a BUY: records the transaction AND updates the holdings
    snapshot (recalculating average buy price if we already own some).

    WHY AVERAGE BUY PRICE MATTERS:
    If you buy 10 shares of AAPL at $150, then later buy 5 more at $180,
    you don't own two separate "batches" for our purposes -- we track a
    single weighted average buy price, which is standard for retail
    portfolio tracking (this is exactly what a real brokerage statement
    shows you as your "average cost").

    Weighted average formula:
        new_avg = (old_qty * old_avg + new_qty * new_price) / (old_qty + new_qty)
    """
    symbol = symbol.upper().strip()

    if quantity <= 0 or price <= 0:
        raise ValueError("Quantity and price must be positive numbers.")

    if not market_data.validate_symbol(symbol):
        raise ValueError(f"'{symbol}' is not a valid stock symbol.")

    existing = db.get_holding(portfolio_id, symbol)

    # ATOMICITY: open ONE connection and run both writes (holdings +
    # transaction ledger) inside it. Either both succeed and we commit,
    # or anything fails and we roll back -- there is no possible state
    # where the holding updates but the transaction record doesn't
    # get written, or vice versa.
    conn = db.get_connection()
    try:
        conn.execute("BEGIN")

        if existing:
            old_qty = existing["quantity"]
            old_avg = existing["avg_buy_price"]
            new_qty = old_qty + quantity
            new_avg = ((old_qty * old_avg) + (quantity * price)) / new_qty
            db.upsert_holding(portfolio_id, symbol, new_qty, round(new_avg, 2), existing["sector"], conn=conn)
        else:
            resolved_sector = sector or market_data.get_sector(symbol)
            db.upsert_holding(portfolio_id, symbol, quantity, price, resolved_sector, conn=conn)

        db.add_transaction(portfolio_id, symbol, "BUY", quantity, price, conn=conn)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def sell_stock(portfolio_id, symbol, quantity, price):
    """
    Handles a SELL: validates you're not selling more than you own
    (a real constraint any brokerage enforces), records the transaction,
    and reduces (or removes) the holding.

    NOTE: average buy price does NOT change on a sell -- it only changes
    on a buy. Selling shares doesn't change what you paid for the ones
    you still hold. This is a common point of confusion worth being able
    to explain clearly.
    """
    symbol = symbol.upper().strip()
    existing = db.get_holding(portfolio_id, symbol)

    if not existing:
        raise ValueError(f"Cannot sell {symbol}: no existing holding in this portfolio.")

    if quantity > existing["quantity"]:
        raise ValueError(
            f"Cannot sell {quantity} shares of {symbol}: only {existing['quantity']} held."
        )

    remaining_qty = existing["quantity"] - quantity

    # Same atomicity pattern as buy_stock() -- one connection, one
    # transaction, so the holding change and the ledger entry either
    # both happen or neither does.
    conn = db.get_connection()
    try:
        conn.execute("BEGIN")

        if remaining_qty == 0:
            # Fully sold out of this position -- remove the holdings row
            # entirely rather than leaving a zero-quantity row sitting around.
            db.delete_holding(portfolio_id, symbol, conn=conn)
        else:
            db.upsert_holding(portfolio_id, symbol, remaining_qty, existing["avg_buy_price"], existing["sector"], conn=conn)

        db.add_transaction(portfolio_id, symbol, "SELL", quantity, price, conn=conn)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_portfolio_value(portfolio_id):
    """
    Sums (current_price * quantity) across all holdings.
    This is CURRENT market value -- what the portfolio is worth right
    now, as opposed to what was originally paid for it.
    """
    holdings = db.get_holdings(portfolio_id)
    total_value = 0.0
    for h in holdings:
        current_price = market_data.get_current_price(h["symbol"])
        if current_price is not None:
            total_value += current_price * h["quantity"]
    return round(total_value, 2)


def get_profit_loss(portfolio_id):
    """
    For each holding: (current_price - avg_buy_price) * quantity
    This is UNREALIZED profit/loss -- it reflects paper gains/losses on
    shares still held, not gains already locked in by a past sale.
    Returns a list of per-stock P/L plus a total.

    Worth knowing the distinction if asked: "realized" P/L would come
    from the transaction history of actual sells, "unrealized" comes
    from comparing current holdings to what you paid for them. This
    function calculates unrealized P/L, which is what most portfolio
    dashboards show as the headline number.
    """
    holdings = db.get_holdings(portfolio_id)
    results = []
    total_pl = 0.0

    for h in holdings:
        current_price = market_data.get_current_price(h["symbol"])
        if current_price is None:
            # CHANGED: previously "continue" here silently dropped this
            # holding from the results list entirely -- it would just
            # vanish from the table with no trace. Now we still include
            # a row for it, with pricing fields set to None, so the UI
            # can show "price unavailable" instead of the holding
            # disappearing. It's deliberately excluded from total_pl
            # below, since you cannot add an unknown value to a sum --
            # that part of the original logic was already correct and
            # is unchanged.
            results.append({
                "symbol": h["symbol"],
                "quantity": h["quantity"],
                "avg_buy_price": h["avg_buy_price"],
                "current_price": None,
                "profit_loss": None,
                "profit_loss_percent": None,
            })
            continue
        pl = (current_price - h["avg_buy_price"]) * h["quantity"]
        pl_percent = ((current_price - h["avg_buy_price"]) / h["avg_buy_price"]) * 100
        results.append({
            "symbol": h["symbol"],
            "quantity": h["quantity"],
            "avg_buy_price": h["avg_buy_price"],
            "current_price": current_price,
            "profit_loss": round(pl, 2),
            "profit_loss_percent": round(pl_percent, 2)
        })
        total_pl += pl

    return results, round(total_pl, 2)


def get_allocation(portfolio_id):
    """
    Returns each holding's weight (%) of the total portfolio value.
    weight = (holding's current value) / (total portfolio value) * 100

    This feeds both the "Portfolio Allocation" feature and the
    concentration-risk calculation in analytics.py -- allocation and
    risk are closely related, which is worth pointing out if asked why
    this function is used in two different places.

    KNOWN LIMITATION (documented deliberately, not an oversight):
    Like get_portfolio_value(), this function excludes holdings with no
    available price from BOTH the numerator and denominator -- weights
    are calculated only among successfully-priced holdings, not the full
    portfolio. Unlike get_profit_loss(), this function does NOT include
    a placeholder row for unpriced holdings, because its output feeds
    four downstream analytics.py calculations (volatility, concentration,
    diversification, sector allocation) that all require a clean numeric
    weight_percent for every row. Introducing None values here would
    require defensive None-handling in all four of those functions --
    real scope creep for what should be a display-layer concern. The
    dashboard instead handles this at presentation time: the pie chart's
    title dynamically states "(priced holdings only)" whenever
    get_unpriced_symbols() is non-empty, so the visual is never presented
    as more complete than it actually is, without touching this
    function's data contract.
    """
    holdings = db.get_holdings(portfolio_id)
    total_value = get_portfolio_value(portfolio_id)

    if total_value == 0:
        return []

    allocation = []
    for h in holdings:
        current_price = market_data.get_current_price(h["symbol"])
        if current_price is None:
            continue
        value = current_price * h["quantity"]
        weight = (value / total_value) * 100
        allocation.append({
            "symbol": h["symbol"],
            "sector": h["sector"],
            "value": round(value, 2),
            "weight_percent": round(weight, 2)
        })

    return sorted(allocation, key=lambda x: x["weight_percent"], reverse=True)


def get_top_gainer_loser(portfolio_id):
    """
    Returns the single best and worst performing holding by P/L percent.
    Uses Python's built-in max()/min() with a key function -- a clean,
    idiomatic way to find an extreme value in a list of dicts, worth
    knowing cold since it's a common Python interview pattern in
    general, not just for this project.
    """
    results, _ = get_profit_loss(portfolio_id)

    # CHANGED: get_profit_loss() now includes rows for unpriced holdings
    # (profit_loss_percent = None) instead of skipping them. max()/min()
    # would crash trying to compare None to a float, so we filter those
    # out here specifically -- "no price data" isn't a meaningful
    # top-gainer/loser candidate anyway.
    priced_results = [r for r in results if r["profit_loss_percent"] is not None]
    if not priced_results:
        return None, None

    top_gainer = max(priced_results, key=lambda x: x["profit_loss_percent"])
    top_loser = min(priced_results, key=lambda x: x["profit_loss_percent"])
    return top_gainer, top_loser


def get_unpriced_symbols(portfolio_id):
    """
    Returns the list of symbols in this portfolio for which live price
    data could NOT be fetched (API failure, rate limit, or a genuinely
    invalid/delisted symbol slipping through).

    WHY THIS EXISTS AS ITS OWN FUNCTION rather than folding it into
    get_profit_loss(): dashboard.py needs a quick, explicit list to
    render a warning banner ("prices unavailable for: X, Y") without
    having to re-parse the profit/loss results structure to find the
    None entries. Small duplication of the get_current_price() calls
    already made elsewhere on the page -- a known, accepted tradeoff
    given there's no caching layer yet (documented in README).
    """
    holdings = db.get_holdings(portfolio_id)
    unpriced = []
    for h in holdings:
        if market_data.get_current_price(h["symbol"]) is None:
            unpriced.append(h["symbol"])
    return unpriced


def get_overall_return_percent(portfolio_id):
    """
    (current total value - total amount originally invested) / total
    amount originally invested * 100

    Different from per-stock P/L% -- this is the PORTFOLIO-level return,
    a single headline number summarizing overall performance.
    """
    holdings = db.get_holdings(portfolio_id)
    total_invested = sum(h["quantity"] * h["avg_buy_price"] for h in holdings)
    current_value = get_portfolio_value(portfolio_id)

    if total_invested == 0:
        return 0.0

    return round(((current_value - total_invested) / total_invested) * 100, 2)
