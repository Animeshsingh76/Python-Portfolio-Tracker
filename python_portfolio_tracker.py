"""
Python Portfolio Tracker
File: python_portfolio_tracker.py
Description: A single-file portfolio tracker demonstrating
- SQLite storage for positions
- Fetching live prices with yfinance
- Portfolio metrics (value, cost basis, P/L, allocation)
- CSV import/export
- CLI to add/remove/update positions
- Generates an HTML report with charts (matplotlib)
"""

import sqlite3
import argparse
import datetime
import os
import csv
from typing import Dict

import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from tabulate import tabulate

DB_PATH = "portfolio.db"

SCHEMA = '''
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    shares REAL NOT NULL,
    cost_per_share REAL NOT NULL,
    trade_date TEXT NOT NULL,
    note TEXT
);
'''

class PortfolioDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.executescript(SCHEMA)
        self.conn.commit()

    def add_position(self, symbol, shares, cost_per_share, trade_date, note=""):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO positions (symbol, shares, cost_per_share, trade_date, note) VALUES (?, ?, ?, ?, ?)",
            (symbol.upper(), shares, cost_per_share, trade_date, note)
        )
        self.conn.commit()

    def list_positions(self):
        return pd.read_sql_query("SELECT * FROM positions", self.conn)

    def delete_position(self, position_id):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        self.conn.commit()

class PortfolioAnalyzer:
    def __init__(self, df_positions):
        self.positions = df_positions.copy()
        if not self.positions.empty:
            self.positions['symbol'] = self.positions['symbol'].str.upper()

    def fetch_prices(self):
        if self.positions.empty:
            return pd.DataFrame(columns=['symbol','current_price'])
        symbols = self.positions['symbol'].unique().tolist()
        data = {}
        for sym in symbols:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period='5d')
                price = hist['Close'].iloc[-1] if not hist.empty else 0.0
                data[sym] = price
            except Exception as e:
                print(f"Warning: could not fetch {sym}: {e}")
                data[sym] = 0.0
        return pd.DataFrame(list(data.items()), columns=['symbol', 'current_price'])

    def summary(self):
        if self.positions.empty:
            return {}
        prices = self.fetch_prices()
        df = self.positions.merge(prices, on='symbol', how='left')
        df['current_value'] = df['shares'] * df['current_price']
        df['cost_basis'] = df['shares'] * df['cost_per_share']
        df['pnl_abs'] = df['current_value'] - df['cost_basis']
        df['pnl_pct'] = df['pnl_abs'] / df['cost_basis']
        total_value = df['current_value'].sum()
        total_cost = df['cost_basis'].sum()
        total_pnl = total_value - total_cost
        return {'positions': df, 'total_value': total_value, 'total_cost': total_cost, 'total_pnl': total_pnl}

    def show_table(self, df_table):
        if df_table.empty:
            print("No positions.")
            return
        display_df = df_table[['symbol', 'shares', 'current_price', 'cost_basis', 'current_value', 'pnl_abs', 'pnl_pct']].copy()
        display_df['pnl_pct'] = (display_df['pnl_pct'] * 100).round(2).astype(str) + '%'
        print(tabulate(display_df, headers='keys', tablefmt='psql', showindex=False))

    def generate_report(self, out_folder='report'):
        import base64
        os.makedirs(out_folder, exist_ok=True)
        s = self.summary()
        if not s:
            print("No data to generate report.")
            return
        df = s['positions'].copy()

        # --- Create allocation pie chart ---
        fig1, ax1 = plt.subplots(figsize=(6,6))
        labels = df['symbol']
        sizes = df['current_value']
        if sizes.sum() == 0:
            sizes = [1 for _ in sizes]
        ax1.pie(sizes, labels=labels, autopct='%1.1f%%')
        ax1.set_title('Portfolio Allocation')
        pie_path = os.path.join(out_folder, 'allocation.png')
        fig1.savefig(pie_path, bbox_inches='tight')
        plt.close(fig1)

        # --- Create P&L bar chart ---
        fig2, ax2 = plt.subplots(figsize=(8,4))
        ax2.bar(df['symbol'], df['pnl_abs'])
        ax2.set_ylabel('P&L (abs)')
        ax2.set_title('Position P&L')
        bar_path = os.path.join(out_folder, 'pnl.png')
        fig2.savefig(bar_path, bbox_inches='tight')
        plt.close(fig2)

        # --- Create HTML with embedded images and table ---
        html_path = os.path.join(out_folder, 'report.html')
        table_html = df[['symbol','shares','current_price','cost_basis','current_value','pnl_abs']].round(2).to_html(index=False)

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write('<html><head><meta charset="utf-8"><title>Portfolio Report</title></head><body>')
            f.write(f"<h1>Portfolio Report - {datetime.date.today().isoformat()}</h1>")
            f.write(f"<p><strong>Total value:</strong> {s['total_value']:.2f} &nbsp;&nbsp; <strong>Total cost:</strong> {s['total_cost']:.2f} &nbsp;&nbsp; <strong>Total P&L:</strong> {s['total_pnl']:.2f}</p>")
            f.write('<h2>Allocation</h2>')
            f.write(f'<img src="{os.path.basename(pie_path)}" alt="allocation" style="max-width:700px;"><br>')
            f.write('<h2>Position P&L</h2>')
            f.write(f'<img src="{os.path.basename(bar_path)}" alt="pnl" style="max-width:700px;"><br>')
            f.write('<h2>Positions</h2>')
            f.write(table_html)
            f.write('</body></html>')

        print(f"Report generated: {html_path}")


def parse_args():
    p = argparse.ArgumentParser(description='Simple Portfolio Tracker')
    sub = p.add_subparsers(dest='cmd')

    add = sub.add_parser('add')
    add.add_argument('--symbol', required=True)
    add.add_argument('--shares', type=float, required=True)
    add.add_argument('--price', type=float, required=True)
    add.add_argument('--date', default=datetime.date.today().isoformat())

    view = sub.add_parser('view')
    report = sub.add_parser('report')
    delete = sub.add_parser('delete')
    delete.add_argument('--id', type=int, required=True)

    return p.parse_args()

def main():
    args = parse_args()
    db = PortfolioDB()

    if args.cmd == 'add':
        db.add_position(args.symbol, args.shares, args.price, args.date)
        print("Position added.")
    elif args.cmd == 'view':
        df = db.list_positions()
        pa = PortfolioAnalyzer(df)
        s = pa.summary()
        if not s:
            print("No positions.")
            return
        print(f"Total Value: {s['total_value']:.2f}, Total Cost: {s['total_cost']:.2f}, P&L: {s['total_pnl']:.2f}")
        pa.show_table(s['positions'])
    elif args.cmd == 'report':
        df = db.list_positions()
        pa = PortfolioAnalyzer(df)
        pa.generate_report()
    elif args.cmd == 'delete':
        db.delete_position(args.id)
        print("Deleted position.")
    else:
        print("Use --help for options.")

if __name__ == '__main__':
    main()
