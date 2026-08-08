"""
main.py
-------
Entry point for two purposes:
1. Initializing the database (creating tables if they don't exist).
2. Optionally seeding a demo portfolio with sample data, so the
   dashboard has something to show immediately instead of an empty
   screen on first run -- useful both for your own testing and for
   demoing this live in an interview.

The actual app is run via Streamlit (`streamlit run dashboard.py`),
not this file directly -- this file is for setup/seeding only.
"""

import database as db
import portfolio


def seed_demo_data():
    """
    Creates one demo user, one demo portfolio, and a handful of BUY
    transactions across a few well-known, liquid stocks (so yfinance
    reliably returns data for them). Safe to run multiple times --
    get_user_by_email and the UNIQUE constraint on holdings prevent
    duplicate rows from piling up.
    """
    db.init_db()

    user = db.get_user_by_email("demo@portfolio.app")
    user_id = user["id"] if user else db.create_user("Demo User", "demo@portfolio.app")

    portfolios = db.get_portfolios_for_user(user_id)
    if portfolios:
        portfolio_id = portfolios[0]["id"]
        print(f"Using existing portfolio: {portfolios[0]['name']}")
    else:
        portfolio_id = db.create_portfolio(user_id, "My First Portfolio")
        print("Created new portfolio: My First Portfolio")

    sample_trades = [
        ("AAPL", 10, 180.00),
        ("MSFT", 5, 340.00),
        ("GOOGL", 8, 130.00),
    ]

    for symbol, qty, price in sample_trades:
        existing = db.get_holding(portfolio_id, symbol)
        if not existing:
            try:
                portfolio.buy_stock(portfolio_id, symbol, qty, price)
                print(f"Seeded: bought {qty} shares of {symbol} at {price}")
            except Exception as e:
                print(f"Could not seed {symbol}: {e}")

    print("\nDemo data ready. Run: streamlit run dashboard.py")


if __name__ == "__main__":
    seed_demo_data()
