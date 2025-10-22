# 🧠 Python Portfolio Tracker (CLI)

A command-line portfolio analytics tool built with Python.  
Tracks stock investments, fetches live prices, calculates P&L, and generates HTML reports.

---

## ⚙️ Features
- Store trades in a SQLite database  
- Fetch live stock data via Yahoo Finance (`yfinance`)  
- Calculate portfolio metrics (cost, value, profit/loss, allocation)  
- Generate visual reports with `matplotlib`  
- Simple CLI interface using `argparse`

---

## 🖥️ Usage
```bash
# Add a position
python python_portfolio_tracker.py add --symbol AAPL --shares 10 --price 150 --date 2024-07-01

# View your portfolio (fetches live prices)
python python_portfolio_tracker.py view

# Generate HTML report with charts
python python_portfolio_tracker.py report
