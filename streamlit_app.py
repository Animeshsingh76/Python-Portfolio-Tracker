# streamlit_app.py
import streamlit as st
import pandas as pd
import yfinance as yf
import datetime
from sqlalchemy import create_engine
import matplotlib.pyplot as plt
import os
import sqlite3

DB_PATH = "portfolio.db"
st.set_page_config(page_title="Portfolio Tracker", layout="wide")

# -------------------------
# DB helpers
# -------------------------
@st.cache_resource
def get_engine(path=DB_PATH):
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

from sqlalchemy import text

def init_db():
    engine = get_engine()
    # use a transaction; pass SQL via sqlalchemy.text()
    create_sql = text("""
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        shares REAL NOT NULL,
        cost_per_share REAL NOT NULL,
        trade_date TEXT NOT NULL,
        note TEXT
    );
    """)
    with engine.begin() as conn:
        conn.execute(create_sql)
    return engine


def read_positions_df():
    engine = get_engine()
    df = pd.read_sql("SELECT * FROM positions", engine)
    if not df.empty:
        df['symbol'] = df['symbol'].str.upper()
    return df

# -------------------------
# Price fetching
# -------------------------
@st.cache_data(ttl=60)
def fetch_current_prices(symbols):
    prices = {}
    for s in symbols:
        try:
            t = yf.Ticker(s)
            hist = t.history(period="5d")
            if not hist.empty:
                prices[s] = float(hist['Close'].iloc[-1])
            else:
                info_price = None
                try:
                    info_price = t.info.get('regularMarketPrice')
                except Exception:
                    info_price = None
                prices[s] = float(info_price) if info_price is not None else 0.0
        except Exception:
            prices[s] = 0.0
    return prices

# -------------------------
# DB write helpers
# -------------------------
from sqlalchemy import text   # add this at top of file if not already present

def add_trade(symbol, shares, price, date, note=""):
    engine = get_engine()
    symbol = symbol.upper()
    insert_sql = text("""
        INSERT INTO positions (symbol, shares, cost_per_share, trade_date, note)
        VALUES (:symbol, :shares, :price, :date, :note)
    """)
    params = {
        "symbol": symbol,
        "shares": float(shares),
        "price": float(price),
        "date": date,
        "note": note or ""
    }
    with engine.begin() as conn:
        conn.execute(insert_sql, params)


def import_csv_to_db(uploaded_file):
    df = pd.read_csv(uploaded_file)
    df = df.rename(columns=lambda c: c.strip())
    engine = get_engine()
    df.to_sql("positions", engine, if_exists="append", index=False)

# -------------------------
# UI: Sidebar
# -------------------------
init_db()
st.sidebar.title("Portfolio Controls")

with st.sidebar.expander("Add trade manually", True):
    c_symbol = st.text_input("Symbol (e.g. AAPL)")
    c_shares = st.number_input("Shares", min_value=0.0, value=1.0, step=1.0)
    c_price = st.number_input("Cost per share", min_value=0.0, value=100.0, step=0.01, format="%.2f")
    c_date = st.date_input("Trade date", datetime.date.today())
    c_note = st.text_input("Note (optional)")
    if st.button("Add trade"):
        if c_symbol.strip() == "":
            st.error("Enter a symbol")
        else:
            add_trade(c_symbol.strip(), float(c_shares), float(c_price), c_date.isoformat(), c_note)
            st.success(f"Added {c_shares} {c_symbol.upper()} at {c_price}")

st.sidebar.markdown("---")
uploaded = st.sidebar.file_uploader("Import trades CSV", type=["csv"])
if uploaded:
    try:
        import_csv_to_db(uploaded)
        st.sidebar.success("Imported CSV to DB")
    except Exception as e:
        st.sidebar.error(f"Import failed: {e}")

if st.sidebar.button("Refresh data"):
    fetch_current_prices.clear()
    st.experimental_rerun()

st.sidebar.markdown("---")
if st.sidebar.button("Generate HTML report (report/report.html)"):
    # quick small report
    df = read_positions_df()
    if df.empty:
        st.sidebar.warning("No positions to report")
    else:
        prices = fetch_current_prices(df['symbol'].unique().tolist())
        pos = df.copy()
        pos['current_price'] = pos['symbol'].map(prices)
        pos['current_value'] = pos['shares'] * pos['current_price']
        pos['cost_basis'] = pos['shares'] * pos['cost_per_share']
        pos['pnl_abs'] = pos['current_value'] - pos['cost_basis']
        out_folder = "report"
        os.makedirs(out_folder, exist_ok=True)
        html_path = os.path.join(out_folder, "report.html")
        pos_table = pos[['symbol','shares','current_price','cost_basis','current_value','pnl_abs']].round(2).to_html(index=False)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(f"<h1>Portfolio Report</h1>\n")
            f.write(f"<p>Total value: {pos['current_value'].sum():.2f}</p>\n")
            f.write(pos_table)
        st.sidebar.success(f"Report written to {html_path}")

# -------------------------
# Main page
# -------------------------
st.title("📊 Portfolio Tracker Dashboard")

df = read_positions_df()

if df.empty:
    st.info("No positions yet — add trades in the sidebar to begin.")
    st.stop()

# Fetch prices and compute metrics
symbols = df['symbol'].unique().tolist()
prices = fetch_current_prices(symbols)
df['current_price'] = df['symbol'].map(prices)
df['current_value'] = df['shares'] * df['current_price']
df['cost_basis'] = df['shares'] * df['cost_per_share']
df['pnl_abs'] = df['current_value'] - df['cost_basis']
df['pnl_pct'] = (df['pnl_abs'] / df['cost_basis']).fillna(0)

# Aggregated per symbol
agg = df.groupby('symbol').agg({
    'shares':'sum',
    'cost_basis':'sum',
    'current_value':'sum',
    'pnl_abs':'sum'
}).reset_index()
agg['pnl_pct'] = (agg['pnl_abs'] / agg['cost_basis']).fillna(0)
total_value = agg['current_value'].sum()
total_cost = agg['cost_basis'].sum()
total_pnl = total_value - total_cost
agg['allocation_pct'] = agg['current_value'] / (total_value if total_value else 1)

# KPI row
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total market value", f"${total_value:,.2f}")
col2.metric("Total cost", f"${total_cost:,.2f}")
col3.metric("Total P&L (abs)", f"${total_pnl:,.2f}")
col4.metric("Total P&L (%)", f"{(total_pnl/total_cost*100) if total_cost else 0:.2f}%")

st.markdown("---")

# Charts using matplotlib
left, right = st.columns([1,1])

with left:
    st.subheader("Allocation")
    fig1, ax1 = plt.subplots(figsize=(5,5))
    labels = agg['symbol'].tolist()
    sizes = agg['current_value'].tolist()
    if sum(sizes) == 0:
        sizes = [1 for _ in sizes]
    explode = [0.03]*len(labels)
    ax1.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, explode=explode)
    ax1.set_title('Portfolio Allocation')
    ax1.axis('equal')
    st.pyplot(fig1)
    plt.close(fig1)

with right:
    st.subheader("Position P&L (abs)")
    fig2, ax2 = plt.subplots(figsize=(6,4))
    colors = ['#2ca02c' if v>=0 else '#d62728' for v in agg['pnl_abs']]
    ax2.bar(agg['symbol'], agg['pnl_abs'], color=colors)
    ax2.set_ylabel('P&L (abs)')
    ax2.set_title('Position P&L')
    st.pyplot(fig2)
    plt.close(fig2)

st.markdown("---")
st.subheader("Positions")
st.dataframe(agg[['symbol','shares','current_value','cost_basis','pnl_abs','pnl_pct','allocation_pct']].sort_values('current_value', ascending=False).style.format({
    'current_value':'${:,.2f}', 'cost_basis':'${:,.2f}', 'pnl_abs':'${:,.2f}', 'pnl_pct':'{:.2%}', 'allocation_pct':'{:.2%}'
}), height=300)

st.subheader("All Trades (raw)")
st.dataframe(df.sort_values('trade_date', ascending=False).style.format({
    'current_price':'${:,.2f}', 'cost_per_share':'${:,.2f}', 'current_value':'${:,.2f}', 'cost_basis':'${:,.2f}', 'pnl_abs':'${:,.2f}', 'pnl_pct':'{:.2%}'
}), height=240)

# CSV download
@st.cache_data
def df_to_csv_bytes(df_):
    return df_.to_csv(index=False).encode('utf-8')

st.download_button("Download positions CSV", data=df_to_csv_bytes(df), file_name="positions_export.csv", mime="text/csv")


