"""
analytics.py
------------
Contains the RISK ANALYTICS calculations -- this is the part of the
project that most directly maps to LSEG's "Quantitative Analytics"
pathway (Data Science / Financial Engineering).

DELIBERATE SCOPE DECISION:
Real quant risk models (VaR, Sharpe ratio, beta vs. a benchmark, Monte
Carlo simulation) are far beyond what's expected from a final-year
student project. This file implements simplified but CORRECT versions
of real concepts -- volatility as standard deviation of daily returns,
concentration risk via a Herfindahl-style index, diversification as a
simple count/spread measure. Every formula here is a genuine, defensible
simplification of something real, not a made-up number. That distinction
matters a lot if an interviewer probes "is this how real risk models
work" -- the honest answer is "this is a simplified but conceptually
correct version of it."
"""

import numpy as np
import portfolio
import market_data


def get_daily_returns(symbol, period="1mo"):
    """
    Daily return = (today's price - yesterday's price) / yesterday's price

    This is the single most fundamental building block of quantitative
    finance -- almost every risk metric (volatility, Sharpe ratio, VaR)
    is built on top of a series of daily returns, not raw prices
    themselves. Raw prices aren't comparable across stocks (a $5 move on
    a $50 stock is huge; on a $500 stock it's tiny) -- returns normalize
    that.
    """
    prices = market_data.get_historical_prices(symbol, period)
    if prices.empty or len(prices) < 2:
        return np.array([])
    returns = prices.pct_change().dropna().values
    return returns


def get_portfolio_volatility(portfolio_id, period="1mo"):
    """
    SIMPLE IMPLEMENTATION (as required): weighted average of each
    holding's individual volatility, NOT a true covariance-matrix-based
    portfolio volatility (which would also account for how stocks move
    relative to EACH OTHER -- correlation).

    Individual stock volatility = standard deviation of its daily returns.
    Higher std dev = price swings around more = riskier.

    HONEST LIMITATION TO STATE IN INTERVIEW:
    A true portfolio volatility calculation requires a covariance matrix
    between all holdings, because diversification benefit comes from
    stocks NOT moving in perfect lockstep. This weighted-average version
    ignores that -- it treats each stock's risk independently and just
    blends them by portfolio weight. That's a real, known simplification,
    and saying so proactively is a strong interview answer, not a
    weakness to hide.
    """
    allocation = portfolio.get_allocation(portfolio_id)
    if not allocation:
        return 0.0

    weighted_vol = 0.0
    for holding in allocation:
        returns = get_daily_returns(holding["symbol"], period)
        if len(returns) < 2:
            continue
        stock_vol = np.std(returns)
        weight = holding["weight_percent"] / 100
        weighted_vol += stock_vol * weight

    # Annualize-ish: multiply by sqrt(252) trading days is the standard
    # convention for turning daily volatility into a yearly figure.
    # We keep it as a simple daily-scale % for interview-friendliness,
    # but this is worth mentioning as the "real" next step.
    return round(weighted_vol * 100, 2)  # expressed as a percentage


def get_concentration_risk(portfolio_id):
    """
    Uses a simplified Herfindahl-Hirschman Index (HHI) style calculation
    -- a genuinely real concept used in finance and antitrust economics
    to measure concentration.

    HHI = sum of (weight_i)^2 for each holding, where weight is a
    fraction (0 to 1) of the total portfolio.

    Interpretation:
    - A portfolio with 1 stock at 100% weight -> HHI = 1.0 (maximally
      concentrated / risky)
    - A portfolio with 10 equally-weighted stocks (10% each) ->
      HHI = 10 * (0.1)^2 = 0.10 (well diversified)

    WHY SQUARING THE WEIGHTS (a likely follow-up question):
    Squaring disproportionately punishes large positions. A stock at 50%
    weight contributes 0.25 to the index, while two stocks at 25% each
    only contribute 0.125 total -- so HHI captures not just HOW MANY
    stocks you hold, but whether any single one dominates the portfolio.
    That's exactly what "concentration risk" means in practice.
    """
    allocation = portfolio.get_allocation(portfolio_id)
    if not allocation:
        return 0.0

    hhi = sum((h["weight_percent"] / 100) ** 2 for h in allocation)
    return round(hhi, 4)


def get_diversification_score(portfolio_id):
    """
    A simple, interview-friendly diversification score derived directly
    from concentration risk: diversification and concentration are two
    ways of describing the same underlying structure, just inverted.

    score = (1 - HHI) * 100, expressed 0-100 where higher = more
    diversified. This is a deliberate simplification -- real
    diversification scoring would also weigh SECTOR spread and
    correlation between holdings, not just position-size concentration.
    """
    hhi = get_concentration_risk(portfolio_id)
    score = (1 - hhi) * 100
    return round(max(0, score), 2)


def get_sector_allocation(portfolio_id):
    """
    GROUP BY sector, summing the weight of every holding in that sector.
    Conceptually identical to a SQL "GROUP BY sector, SUM(weight)" query
    -- we do it in Python here since the sector data comes from the
    market_data API, not directly from a single SQL table, but it's
    worth explicitly drawing that SQL parallel if asked.
    """
    allocation = portfolio.get_allocation(portfolio_id)
    sector_totals = {}
    for h in allocation:
        sector = h["sector"] or "Unknown"
        sector_totals[sector] = sector_totals.get(sector, 0) + h["weight_percent"]
    return {k: round(v, 2) for k, v in sorted(sector_totals.items(), key=lambda x: -x[1])}


def get_risk_score(portfolio_id):
    """
    Combines volatility + concentration into a single 0-100 "risk score"
    for a headline dashboard number. This is INTENTIONALLY a simple
    weighted blend, not a scientifically rigorous model -- the goal is
    an interview-friendly, explainable composite metric, not a
    production risk engine.

    risk_score = (volatility_component * 0.6) + (concentration_component * 0.4)

    WHY THESE WEIGHTS (be ready for this question):
    Volatility is weighted higher (60%) because day-to-day price
    swings are the more immediate, tangible risk a retail investor
    feels. Concentration (40%) matters but is a slower-moving,
    structural risk. There's no single "correct" weighting here --
    it's a reasonable, explainable judgment call, which is exactly
    what you should say if pushed on why 60/40 specifically.
    """
    volatility = get_portfolio_volatility(portfolio_id)
    hhi = get_concentration_risk(portfolio_id)

    # Normalize volatility roughly onto a 0-100 scale (capping extreme
    # values so one wild stock doesn't blow the whole score off-scale).
    vol_component = min(volatility * 10, 100)
    concentration_component = hhi * 100

    risk_score = (vol_component * 0.6) + (concentration_component * 0.4)
    return round(min(risk_score, 100), 2)


def get_investment_insights(portfolio_id):
    """
    Translates the raw numbers above into plain-English insight strings
    for the dashboard -- this is a common pattern in real analytics
    products: numbers alone don't help a user, a short interpretation
    does. Simple rule-based thresholds, deliberately not ML-based --
    keeping this interview-explainable rather than a black box.
    """
    insights = []
    hhi = get_concentration_risk(portfolio_id)
    volatility = get_portfolio_volatility(portfolio_id)
    allocation = portfolio.get_allocation(portfolio_id)

    if hhi > 0.4:
        insights.append("Your portfolio is heavily concentrated in a small number of holdings. Consider diversifying further.")
    elif hhi < 0.15 and len(allocation) >= 5:
        insights.append("Your portfolio is well diversified across holdings.")

    if volatility > 3:
        insights.append("Your portfolio shows high day-to-day volatility -- expect larger short-term swings.")
    elif volatility < 1 and volatility > 0:
        insights.append("Your portfolio is relatively stable day-to-day.")

    sector_alloc = get_sector_allocation(portfolio_id)
    if sector_alloc:
        top_sector, top_weight = next(iter(sector_alloc.items()))
        if top_weight > 50:
            insights.append(f"Over half your portfolio is concentrated in the {top_sector} sector.")

    if not insights:
        insights.append("No significant risk flags detected based on current holdings.")

    return insights
