"""
market_data.py
---------------
Isolates every call to the external stock market API (yfinance).

WHY THIS FILE EXISTS SEPARATELY:
If yfinance ever goes down, changes its API, or we want to switch to a
paid/more reliable data provider later (e.g. Alpha Vantage, a real broker
API), we only change this ONE file. Nothing in portfolio.py or analytics.py
needs to know HOW we get a price -- just that get_current_price(symbol)
returns a number. This is the same "isolate the volatile dependency"
principle as database.py.

We also add basic error handling here, because external APIs are
unreliable by nature (network issues, rate limits, invalid symbols) --
a real production system must never crash just because a stock symbol
lookup failed.
"""

import yfinance as yf
import pandas as pd


def get_current_price(symbol):
    """
    Returns the latest available closing price for a stock symbol.
    Returns None if the symbol is invalid or the API call fails --
    callers must handle that None case rather than assuming a price
    is always available. This is a deliberate design choice: fail
    loudly enough to be handled, not silently with a fake 0.
    """
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if data.empty:
            return None
        return round(float(data["Close"].iloc[-1]), 2)
    except Exception:
        # In a real production system we would log this exception with
        # proper logging (not just swallow it). For this project's scope,
        # returning None and letting the caller decide what to display
        # (e.g. "price unavailable") is enough.
        return None


def get_sector(symbol):
    """
    Returns the sector classification for a stock (e.g. "Technology",
    "Financial Services"), used for sector-wise allocation analytics.
    Falls back to "Unknown" if the API doesn't return sector info --
    some symbols (ETFs, indices) don't have a single sector.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info.get("sector", "Unknown") or "Unknown"
    except Exception:
        return "Unknown"


def get_historical_prices(symbol, period="1mo"):
    """
    Returns a pandas Series of daily closing prices over the given period.
    This is used by analytics.py to calculate daily returns and
    volatility -- you cannot calculate volatility from a single price,
    you need a history of prices to see how much they fluctuate.

    period examples: "1mo", "3mo", "6mo", "1y"
    """
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period)
        if data.empty:
            return pd.Series(dtype=float)
        return data["Close"]
    except Exception:
        return pd.Series(dtype=float)


def validate_symbol(symbol):
    """
    Quick check used by the dashboard before allowing a BUY -- prevents
    a user from adding a stock that doesn't actually exist/trade.
    """
    price = get_current_price(symbol)
    return price is not None
