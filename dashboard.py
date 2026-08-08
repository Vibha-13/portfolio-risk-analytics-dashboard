"""
dashboard.py
------------
The Streamlit UI layer. This file's ONLY job is presentation -- reading
data by calling functions from portfolio.py / analytics.py / database.py
and rendering it. It does NOT contain business logic or SQL itself.

WHY THIS MATTERS (interview point on architecture):
If we swapped Streamlit for Flask + React tomorrow, only this file
(and a new frontend) would change -- database.py, portfolio.py, and
analytics.py wouldn't need a single line touched. That's the practical
payoff of keeping UI, business logic, and data access in separate files.

VISUAL DESIGN NOTE:
Styled as a light, data-dense institutional finance UI rather than a
default Streamlit look -- deep ink-navy sidebar, IBM Plex Mono for all
numeric data (mirrors how real trading terminals give numbers visual
authority), and a thin semantic color bar on every metric card (blue =
neutral, green = gain, red = risk/loss) so portfolio health reads at a
glance. This is presentation-only -- no calculation logic changed.
"""

import streamlit as st
import pandas as pd
import plotly.express as px

import database as db
import portfolio
import analytics
import market_data
import utils

st.set_page_config(page_title="Portfolio Risk Analytics Dashboard", layout="wide")

# -----------------------------------------------------------------------------
# VISUAL THEME -- CSS injection only. Nothing below this block touches data,
# calculations, or business logic; it only restyles how existing values render.
# -----------------------------------------------------------------------------
def inject_theme():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');

    :root {
        --ink: #0B1220;
        --muted: #5B6472;
        --accent: #1F4B99;
        --accent-dark: #16356E;
        --positive: #0F7B4E;
        --negative: #B23B3B;
        --border: #E2E5EA;
        --surface: #FFFFFF;
        --bg: #F7F8FA;
    }

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: var(--bg); }

    h1, h2, h3 {
        font-family: 'IBM Plex Sans', sans-serif !important;
        color: var(--ink) !important;
        letter-spacing: -0.01em;
        font-weight: 600 !important;
    }
    h1 {
        border-bottom: 1px solid var(--border);
        padding-bottom: 0.6rem;
        margin-bottom: 1.6rem !important;
        font-size: 1.7rem !important;
    }

    /* --- Sidebar: inverted to ink-navy, acts as the "control panel" --- */
    [data-testid="stSidebar"] {
        background-color: var(--ink);
        border-right: 1px solid #1C2740;
    }
    [data-testid="stSidebar"] * { color: #E7EAF0 !important; }
    [data-testid="stSidebar"] h1 {
        font-family: 'IBM Plex Sans', sans-serif !important;
        color: #FFFFFF !important;
        border-bottom: 1px solid #29344D;
        font-size: 1.15rem !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebar"] hr { border-color: #29344D; }
    [data-testid="stSidebar"] .stTextInput input,
    [data-testid="stSidebar"] .stSelectbox > div > div {
        background-color: #131C30;
        color: #E7EAF0;
        border: 1px solid #29344D;
        border-radius: 5px;
    }
    [data-testid="stSidebar"] .stButton button {
        background-color: var(--accent);
        color: #FFFFFF !important;
        border: none;
        border-radius: 5px;
        font-family: 'IBM Plex Sans', sans-serif;
        font-weight: 500;
        width: 100%;
    }
    [data-testid="stSidebar"] .stButton button:hover { background-color: var(--accent-dark); }
    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        font-family: 'IBM Plex Sans', sans-serif;
        font-weight: 500;
    }

    /* --- Custom metric cards (replaces default st.metric look) --- */
    .metric-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-top: 3px solid var(--accent);
        border-radius: 6px;
        padding: 1rem 1.2rem;
        box-shadow: 0 1px 2px rgba(11,18,32,0.04);
        height: 100%;
    }
    .metric-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        font-weight: 600;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.4rem;
    }
    .metric-value {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 1.6rem;
        font-weight: 600;
        color: var(--ink);
        font-variant-numeric: tabular-nums;
        line-height: 1.2;
    }
    .metric-sub {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.85rem;
        font-weight: 600;
        margin-top: 0.3rem;
    }

    /* --- Buttons in main content area --- */
    .stButton button, [data-testid="stFormSubmitButton"] button {
        background-color: var(--accent);
        color: #FFFFFF !important;
        border-radius: 5px;
        border: none;
        font-family: 'IBM Plex Sans', sans-serif;
        font-weight: 500;
        padding: 0.5rem 1.1rem;
    }
    .stButton button:hover, [data-testid="stFormSubmitButton"] button:hover {
        background-color: var(--accent-dark);
    }

    /* --- Data tables: monospace for that terminal-data feel --- */
    [data-testid="stDataFrame"] {
        font-family: 'IBM Plex Mono', monospace;
        border: 1px solid var(--border);
        border-radius: 6px;
        overflow: hidden;
    }

    /* --- Expanders (Buy/Sell forms) --- */
    [data-testid="stExpander"] {
        border: 1px solid var(--border);
        border-radius: 6px;
        background-color: var(--surface);
    }
    .streamlit-expanderHeader, [data-testid="stExpander"] summary {
        font-family: 'IBM Plex Sans', sans-serif !important;
        font-weight: 500 !important;
        color: var(--ink) !important;
    }

    /* --- Alerts/banners --- */
    [data-testid="stAlert"] {
        border-radius: 6px;
        font-family: 'Inter', sans-serif;
    }

    /* --- Subheaders --- */
    h3 { font-size: 1.05rem !important; margin-top: 0.5rem !important; }
    </style>
    """, unsafe_allow_html=True)


def metric_card(label, value, sub=None, tone="neutral"):
    """
    Renders one custom metric card. Replaces st.metric() so we get full
    control over the signature "colored top-edge" element -- tone maps
    to semantic color (neutral/positive/negative), matching how a
    trading terminal would flag portfolio health at a glance.

    PRESENTATION ONLY: takes already-calculated values as input, same as
    the st.metric() calls it replaces. No calculation logic lives here.
    """
    colors = {"neutral": "#1F4B99", "positive": "#0F7B4E", "negative": "#B23B3B"}
    color = colors.get(tone, "#1F4B99")
    sub_html = f'<div class="metric-sub" style="color:{color}">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div class="metric-card" style="border-top-color:{color}">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def style_plotly(fig, height=380):
    """
    Applies the same institutional color palette + typography to every
    Plotly chart, so charts and metric cards feel like one consistent
    system rather than default Plotly styling bolted onto custom cards.
    """
    fig.update_layout(
        font=dict(family="Inter, sans-serif", color="#0B1220", size=13),
        title_font=dict(family="IBM Plex Sans, sans-serif", size=16, color="#0B1220"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        colorway=["#1F4B99", "#0F7B4E", "#B23B3B", "#5B6472", "#7C93C4", "#C9791B", "#3E7CB1"],
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(font=dict(family="Inter, sans-serif", size=12)),
        height=height,
    )
    return fig


inject_theme()

# Ensure tables exist before anything else runs. Safe to call every time --
# init_db() uses "CREATE TABLE IF NOT EXISTS", so this is a no-op after
# the first run.
db.init_db()


def get_or_create_demo_user():
    """
    For a demo/interview project, we skip building a full login system
    (out of scope, would distract from the core SQL/analytics focus) and
    use a single fixed demo user, created once if it doesn't already
    exist. Worth stating plainly if asked "where's the login page" --
    this was a deliberate scope decision, not an oversight.
    """
    user = db.get_user_by_email("demo@portfolio.app")
    if user:
        return user["id"]
    return db.create_user("Demo User", "demo@portfolio.app")


user_id = get_or_create_demo_user()

# --- Sidebar: portfolio selection / creation --------------------------------
st.sidebar.title("Portfolio Risk Analytics")
page = st.sidebar.radio("Navigate", ["Dashboard", "Portfolio", "Transactions", "Analytics", "Settings"])

portfolios = db.get_portfolios_for_user(user_id)
portfolio_names = [p["name"] for p in portfolios]

st.sidebar.markdown("---")
new_portfolio_name = st.sidebar.text_input("New portfolio name")
if st.sidebar.button("Create Portfolio"):
    if new_portfolio_name.strip():
        db.create_portfolio(user_id, new_portfolio_name.strip())
        st.rerun()

if not portfolios:
    st.warning("No portfolios yet. Create one from the sidebar to get started.")
    st.stop()

selected_name = st.sidebar.selectbox("Select Portfolio", portfolio_names)
selected_portfolio = next(p for p in portfolios if p["name"] == selected_name)
portfolio_id = selected_portfolio["id"]


# --- PAGE: Dashboard ---------------------------------------------------------
if page == "Dashboard":
    st.title(f"Dashboard — {selected_name}")

    unpriced = portfolio.get_unpriced_symbols(portfolio_id)
    if unpriced:
        st.warning(
            f"Price data unavailable for: {', '.join(unpriced)}. "
            "Totals below may be incomplete until pricing is restored."
        )

    total_value = portfolio.get_portfolio_value(portfolio_id)
    _, total_pl = portfolio.get_profit_loss(portfolio_id)
    overall_return = portfolio.get_overall_return_percent(portfolio_id)
    risk_score = analytics.get_risk_score(portfolio_id)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card("Portfolio Value", utils.format_currency(total_value))
    with col2:
        metric_card(
            "Unrealized P/L", utils.format_currency(total_pl),
            tone="positive" if total_pl >= 0 else "negative"
        )
    with col3:
        metric_card(
            "Overall Return", utils.format_percent(overall_return),
            tone="positive" if overall_return >= 0 else "negative"
        )
    with col4:
        risk_tone = "negative" if risk_score >= 60 else ("neutral" if risk_score >= 30 else "positive")
        metric_card("Risk Score", f"{risk_score}/100", sub=utils.risk_label(risk_score), tone=risk_tone)

    st.markdown("---")

    allocation = portfolio.get_allocation(portfolio_id)
    if allocation:
        df = pd.DataFrame(allocation)
        fig = px.pie(df, names="symbol", values="weight_percent", title="Portfolio Allocation", hole=0.45)
        st.plotly_chart(style_plotly(fig), use_container_width=True)
    else:
        st.info("Add holdings to see your portfolio allocation.")

    top_gainer, top_loser = portfolio.get_top_gainer_loser(portfolio_id)
    c1, c2 = st.columns(2)
    with c1:
        if top_gainer:
            metric_card("Top Gainer", top_gainer["symbol"],
                        sub=utils.format_percent(top_gainer["profit_loss_percent"]), tone="positive")
        else:
            st.info("No holdings yet.")
    with c2:
        if top_loser:
            metric_card("Top Loser", top_loser["symbol"],
                        sub=utils.format_percent(top_loser["profit_loss_percent"]), tone="negative")
        else:
            st.info("No holdings yet.")


# --- PAGE: Portfolio (buy/sell/view holdings) --------------------------------
elif page == "Portfolio":
    st.title(f"Portfolio — {selected_name}")

    unpriced = portfolio.get_unpriced_symbols(portfolio_id)
    if unpriced:
        st.warning(
            f"Price data unavailable for: {', '.join(unpriced)}. "
            "These holdings are shown below but excluded from P/L totals."
        )

    with st.expander("➕ Buy Stock"):
        with st.form("buy_form"):
            symbol = st.text_input("Symbol (e.g. AAPL)").upper().strip()
            quantity = st.number_input("Quantity", min_value=0.0, step=1.0)
            price = st.number_input("Price per share", min_value=0.0, step=0.01)
            submitted = st.form_submit_button("Buy")
            if submitted:
                try:
                    portfolio.buy_stock(portfolio_id, symbol, quantity, price)
                    st.success(f"Bought {quantity} shares of {symbol}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    with st.expander("➖ Sell Stock"):
        with st.form("sell_form"):
            symbol = st.text_input("Symbol to sell").upper().strip()
            quantity = st.number_input("Quantity to sell", min_value=0.0, step=1.0)
            price = st.number_input("Sell price per share", min_value=0.0, step=0.01)
            submitted = st.form_submit_button("Sell")
            if submitted:
                try:
                    portfolio.sell_stock(portfolio_id, symbol, quantity, price)
                    st.success(f"Sold {quantity} shares of {symbol}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    st.markdown("---")
    st.subheader("Current Holdings")
    results, _ = portfolio.get_profit_loss(portfolio_id)
    if results:
        df = pd.DataFrame(results)
        df = df.fillna("Price unavailable")
        st.dataframe(df, use_container_width=True)

        if st.button("🗑️ Delete a holding"):
            st.session_state["show_delete"] = True

        if st.session_state.get("show_delete"):
            symbol_to_delete = st.selectbox("Select symbol to delete", [r["symbol"] for r in results])
            if st.button("Confirm Delete"):
                db.delete_holding(portfolio_id, symbol_to_delete)
                st.session_state["show_delete"] = False
                st.rerun()
    else:
        st.info("No holdings yet — buy a stock above to get started.")


# --- PAGE: Transactions -------------------------------------------------------
elif page == "Transactions":
    st.title(f"Transaction History — {selected_name}")

    transactions = db.get_transactions(portfolio_id)
    if transactions:
        df = pd.DataFrame(transactions)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No transactions yet.")

    st.markdown("---")
    st.subheader("Trading Activity Summary (GROUP BY symbol)")
    summary = db.get_transaction_summary(portfolio_id)
    if summary:
        st.dataframe(pd.DataFrame(summary), use_container_width=True)


# --- PAGE: Analytics -----------------------------------------------------------
elif page == "Analytics":
    st.title(f"Risk Analytics — {selected_name}")

    risk_score = analytics.get_risk_score(portfolio_id)
    diversification = analytics.get_diversification_score(portfolio_id)
    concentration = analytics.get_concentration_risk(portfolio_id)
    volatility = analytics.get_portfolio_volatility(portfolio_id)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        risk_tone = "negative" if risk_score >= 60 else ("neutral" if risk_score >= 30 else "positive")
        metric_card("Risk Score", f"{risk_score}/100", sub=utils.risk_label(risk_score), tone=risk_tone)
    with col2:
        div_tone = "positive" if diversification >= 60 else "negative"
        metric_card("Diversification Score", f"{diversification}/100", tone=div_tone)
    with col3:
        conc_tone = "negative" if concentration >= 0.4 else "neutral"
        metric_card("Concentration (HHI)", f"{concentration}", tone=conc_tone)
    with col4:
        metric_card("Volatility (daily, simplified)", f"{volatility}%", tone="neutral")

    st.markdown("---")
    st.subheader("Sector-wise Allocation")
    sector_alloc = analytics.get_sector_allocation(portfolio_id)
    if sector_alloc:
        df = pd.DataFrame(list(sector_alloc.items()), columns=["Sector", "Weight %"])
        fig = px.bar(df, x="Sector", y="Weight %", title="Sector Allocation")
        fig.update_traces(marker_color="#1F4B99")
        st.plotly_chart(style_plotly(fig), use_container_width=True)
    else:
        st.info("Add holdings to see sector allocation.")

    st.markdown("---")
    st.subheader("Investment Insights")
    for insight in analytics.get_investment_insights(portfolio_id):
        st.markdown(f"— {insight}")


# --- PAGE: Settings --------------------------------------------------------------
elif page == "Settings":
    st.title("Settings")
    st.write("Demo User: demo@portfolio.app")
    st.write(f"Current Portfolio: {selected_name}")
    st.caption("This is a demo project — user management is intentionally simplified. "
               "A production version would add authentication, multi-user support, "
               "and proper session handling.")
