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
import streamlit as st


@st.cache_data(ttl=60)
def get_current_price(symbol):
    """
    Returns the latest available closing price for a stock symbol.
    Returns None if the symbol is invalid or the API call fails --
    callers must handle that None case rather than assuming a price
    is always available. This is a deliberate design choice: fail
    loudly enough to be handled, not silently with a fake 0.

    CACHING (ttl=60): this function was previously called 3+ times per
    single page load for the SAME symbol -- once each from
    get_portfolio_value(), get_profit_loss(), and get_unpriced_symbols(),
    and again on every Streamlit rerun (which happens on every click,
    since Streamlit reruns the whole script top-to-bottom). None of that
    redundancy was intentional; it's just what happens when several
    functions each independently need "the current price" and none of
    them share results. @st.cache_data stores the result keyed by the
    function's arguments (symbol) and returns the cached value instead
    of re-hitting the Yahoo Finance API, for 60 seconds. 60s is a
    deliberate choice: short enough that prices still feel "live" for a
    demo, long enough to eliminate the redundant calls within a single
    page interaction (which all happen within milliseconds of each
    other, not 60 seconds apart).
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


@st.cache_data(ttl=3600)
def get_sector(symbol):
    """
    Returns the sector classification for a stock (e.g. "Technology",
    "Financial Services"), used for sector-wise allocation analytics.
    Falls back to "Unknown" if the API doesn't return sector info --
    some symbols (ETFs, indices) don't have a single sector.

    CACHING (ttl=3600, i.e. 1 hour): a stock's sector classification
    changes extremely rarely (basically never, in practice, for a demo
    project's timeframe) -- a much longer TTL than price is correct
    here, not just convenient. Caching this aggressively also means we
    only pay the sector-lookup API cost once per symbol per hour, not on
    every single buy/rerun.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info.get("sector", "Unknown") or "Unknown"
    except Exception:
        return "Unknown"


@st.cache_data(ttl=300)
def get_historical_prices(symbol, period="1mo"):
    """
    Returns a pandas Series of daily closing prices over the given period.
    This is used by analytics.py to calculate daily returns and
    volatility -- you cannot calculate volatility from a single price,
    you need a history of prices to see how much they fluctuate.

    period examples: "1mo", "3mo", "6mo", "1y"

    CACHING (ttl=300, i.e. 5 minutes): this is the most expensive call in
    the whole app -- it downloads a full price history, not just one
    number -- and it's called separately for EVERY holding, EVERY time
    the Analytics page recalculates volatility/concentration/
    diversification. A 5-minute TTL is longer than get_current_price's
    because daily-return-based volatility genuinely doesn't need to be
    fresher than that; a 5-minute-old history produces the same
    volatility figure as a 5-second-old one in practice.
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

    NOT separately cached: it calls get_current_price() internally,
    which is already cached above. Caching this too would just be a
    second cache layer wrapping the first one, with no real benefit.
    """
    price = get_current_price(symbol)
    return price is not None
