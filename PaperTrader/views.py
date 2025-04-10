from django.shortcuts import render, redirect
from .models import Holding, Portfolio, Stock, Transaction, PortfolioSnapshot
import yfinance as yf
from django.contrib import messages
from decimal import Decimal
import plotly.graph_objects as go
import plotly.io as pio
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import now
from datetime import datetime, time
from pytz import timezone


def home(request):
    portfolio = Portfolio.objects.first()
    if portfolio is None:
        portfolio = Portfolio.objects.create(cash=1000)

    holdings = Holding.objects.all()

    total_stock_value = 0
    holding_data = []

    for holding in holdings:
        ticker = holding.stock.ticker
        data = yf.Ticker(ticker).history(period="1d")
        current_price = data["Close"].iloc[-1] if not data.empty else 0
        value = current_price * holding.quantity
        total_stock_value += value

        open_pl = (current_price - float(holding.average_price)) * holding.quantity

        holding_data.append({
            "ticker": ticker,
            "quantity": holding.quantity,
            "average_price": holding.average_price,
            "current_price": current_price,
            "value": value,
            "open_pl": open_pl
        })

    total_value = Decimal(total_stock_value) + portfolio.cash
    PortfolioSnapshot.objects.create(value=total_value)
    today = now().date()
    snapshots = PortfolioSnapshot.objects.filter(timestamp__date=today).order_by('timestamp')

    eastern = timezone("US/Eastern")

    if not snapshots:
        noon_et = eastern.localize(datetime.combine(datetime.now(), time(12, 0)))
        chart_data = [{
            "x": noon_et.isoformat(),
            "y": float(portfolio.cash)
        }]
    else:
        chart_data = [
            {
                "x": s.timestamp.astimezone(eastern).isoformat(),
                "y": float(s.value)
            }
            for s in snapshots
        ]

    now_et = datetime.now(eastern)
    market_open = time(9, 30)
    market_close = time(16, 0)
    market_closed = now_et.weekday() >= 5 or not (market_open <= now_et.time() <= market_close)

    return render(request, "PaperTrader/home.html", {
        "portfolio_value": total_value,
        "cash": portfolio.cash,
        "holdings": holding_data,
        "chart_data": chart_data,
        "market_closed": market_closed
    })


def search_stock(request):
    ticker = request.GET.get('ticker', '').upper()
    timeframe = request.GET.get('timeframe', '1d')  # default timneframe
    portfolio = Portfolio.objects.first()

    if request.method == "POST":
        quantity = Decimal(request.POST.get('quantity'))

        data = yf.Ticker(ticker).history(period="7d", interval=timeframe)
        current_price = Decimal(str(data["Close"].iloc[-1])) if not data.empty else None

        if current_price is None:
            messages.error(request, f"Invalid stock ticker: {ticker}")
            return redirect("home")

        total_cost = current_price * quantity

        if portfolio.cash < total_cost:
            messages.error(request, "Not enough cash to complete the purchase.")
            return redirect("home")

        stock, _ = Stock.objects.get_or_create(ticker=ticker)

        holding, created = Holding.objects.get_or_create(
            stock=stock,
            defaults={
                'quantity': quantity,
                'average_price': current_price
            }
        )

        if not created:
            total_quantity = holding.quantity + quantity
            holding.average_price = (
                (holding.average_price * holding.quantity) + (current_price * quantity)
            ) / total_quantity
            holding.quantity = total_quantity
            holding.save()

        portfolio.cash -= total_cost
        portfolio.save()

        Transaction.objects.create(
            side="BUY",
            ticker=ticker,
            price=current_price,
            quantity=int(quantity),
        )

        messages.success(request, f"Bought {quantity} shares of {ticker} at ${current_price:.2f}")
        return redirect("home")

    # Display stock info + chart
    yf_ticker = yf.Ticker(ticker)
    data = yf_ticker.history(period="60d", interval=timeframe)

    if data.empty:
        messages.error(request, f"Could not retrieve data for {ticker}.")
        return redirect("home")

    current_price = Decimal(str(data["Close"].iloc[-1]))

    fig = go.Figure(data=[go.Candlestick(
        x=data.index,
        open=data['Open'],
        high=data['High'],
        low=data['Low'],
        close=data['Close']
    )])

    fig.update_layout(title=f'{ticker} - {timeframe} Chart', xaxis_rangeslider_visible=False)
    chart_html = pio.to_html(fig, full_html=False)

    return render(request, "PaperTrader/search_result.html", {
        "ticker": ticker,
        "price": current_price,
        "chart": chart_html,
        "selected_timeframe": timeframe,
        "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d", "1wk", "1mo"]
    })

def orders(request):
    transactions = Transaction.objects.order_by('-timestamp')
    return render(request, "PaperTrader/orders.html", {"transactions": transactions})

def sell_stock(request):
    ticker = request.GET.get('ticker', '').upper()
    portfolio = Portfolio.objects.first()
    stock = Stock.objects.get(ticker=ticker)
    holding = Holding.objects.get(stock=stock)

    if request.method == "POST":
        quantity = Decimal(request.POST.get("quantity"))

        if quantity > holding.quantity:
            messages.error(request, "You can't sell more than you own.")
            return redirect("home")

        data = yf.Ticker(ticker).history(period="1d")
        current_price = Decimal(str(data["Close"].iloc[-1])) if not data.empty else None

        if current_price is None:
            messages.error(request, f"Could not fetch price for {ticker}")
            return redirect("home")

        # P&L for the quantity being sold
        pnl = (current_price - holding.average_price) * quantity

        # Update holding
        holding.quantity -= quantity
        if holding.quantity == 0:
            holding.delete()
        else:
            holding.save()

        # Add cash
        sale_value = current_price * quantity
        portfolio.cash += sale_value
        portfolio.save()

        # Log transaction
        Transaction.objects.create(
            side="SELL",
            ticker=ticker,
            price=current_price,
            quantity=int(quantity),
            pnl=pnl
        )

        messages.success(request, f"Sold {quantity} shares of {ticker} at ${current_price:.2f} (P&L: ${pnl:.2f})")
        return redirect("home")

    # GET request – render form
    return render(request, "PaperTrader/sell.html", {
        "ticker": ticker,
        "quantity_owned": holding.quantity
    })

@csrf_exempt
def reset_portfolio(request):
    if request.method == "POST":
        starting_cash = Decimal(request.POST.get("starting_cash"))

        # Clear all related data
        Holding.objects.all().delete()
        Stock.objects.all().delete()
        Transaction.objects.all().delete()
        Portfolio.objects.all().delete()

        # Create new portfolio
        Portfolio.objects.create(cash=starting_cash)

        messages.success(request, f"Portfolio reset to ${starting_cash:.2f}")
        return redirect("home")

    return render(request, "PaperTrader/reset.html")

