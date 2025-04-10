from apscheduler.schedulers.background import BackgroundScheduler
from .models import Portfolio, Holding, PortfolioSnapshot
import yfinance as yf
from decimal import Decimal
from datetime import datetime, time
import pytz

def log_portfolio_value():
    eastern = pytz.timezone('US/Eastern')
    now_et = datetime.now(eastern)

    market_open = time(9, 30)
    market_close = time(16, 0)

    if now_et.weekday() >= 5 or not (market_open <= now_et.time() <= market_close):
        print("Market closed — skipping portfolio snapshot.")
        return

    portfolio = Portfolio.objects.first()
    if not portfolio:
        return

    holdings = Holding.objects.all()
    total_value = Decimal(portfolio.cash)

    for holding in holdings:
        ticker = holding.stock.ticker
        data = yf.Ticker(ticker).history(period="1d", interval="1m")
        current_price = Decimal(str(data["Close"].iloc[-1])) if not data.empty else holding.average_price
        total_value += current_price * holding.quantity

    PortfolioSnapshot.objects.create(value=total_value)
    print(f"Logged portfolio value: ${total_value} at {now_et.strftime('%H:%M:%S')}")

def start():
    scheduler = BackgroundScheduler()
    scheduler.add_job(log_portfolio_value, 'interval', minutes=5)
    scheduler.start()
