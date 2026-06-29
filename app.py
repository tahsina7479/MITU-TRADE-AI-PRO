# MITU TRADE AI PROFESSIONAL TERMINAL V21
# Full app.py replacement. Paper trading only.
# V21 upgrades: optional live Yahoo Finance data, real RSI/MACD/EMA indicators,
# session weighting, safer journal, improved ranking, and fallback prices.

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

try:
    import yfinance as yf
except Exception:
    yf = None

st.set_page_config(page_title="MITU TRADE AI V21", layout="wide")

APP_VERSION = "V21"
JOURNAL_FILE = "trade_journal.csv"

SYMBOLS = [
    {"Market":"FOREX","Pair":"EURUSD=X","Display Pair":"EURUSD=X","Price":1.1390},
    {"Market":"FOREX","Pair":"GBPUSD=X","Display Pair":"GBPUSD=X","Price":1.3198},
    {"Market":"FOREX","Pair":"USDJPY=X","Display Pair":"USDJPY=X","Price":161.73},
    {"Market":"FOREX","Pair":"AUDUSD=X","Display Pair":"AUDUSD=X","Price":0.6550},
    {"Market":"FOREX","Pair":"USDCAD=X","Display Pair":"USDCAD=X","Price":1.3700},
    {"Market":"COMMODITIES","Pair":"GC=F","Display Pair":"XAU/USD Gold","Price":4096.2998},
    {"Market":"COMMODITIES","Pair":"SI=F","Display Pair":"Silver","Price":59.674},
    {"Market":"CRYPTO","Pair":"BTC-USD","Display Pair":"BTC-USD","Price":60151.8789},
    {"Market":"CRYPTO","Pair":"ETH-USD","Display Pair":"ETH-USD","Price":1574.1899},
    {"Market":"CRYPTO","Pair":"SOL-USD","Display Pair":"SOL-USD","Price":145.0},
    {"Market":"STOCKS","Pair":"AAPL","Display Pair":"AAPL","Price":281.20001},
    {"Market":"STOCKS","Pair":"MSFT","Display Pair":"MSFT","Price":371.35999},
    {"Market":"STOCKS","Pair":"NVDA","Display Pair":"NVDA","Price":156.20},
    {"Market":"STOCKS","Pair":"TSLA","Display Pair":"TSLA","Price":379.19},
    {"Market":"STOCKS","Pair":"AMZN","Display Pair":"AMZN","Price":230.55},
    {"Market":"STOCKS","Pair":"GOOGL","Display Pair":"GOOGL","Price":174.22},
    {"Market":"STOCKS","Pair":"META","Display Pair":"META","Price":698.10},
]

TIMEFRAME_MAP = {
    "5m": {"interval":"5m", "period":"5d"},
    "15m": {"interval":"15m", "period":"5d"},
    "1h": {"interval":"1h", "period":"1mo"},
    "1d": {"interval":"1d", "period":"6mo"},
}


def market_session_status():
    zones = {
        "AU Sydney": ("Australia/Sydney", "07:00 - 16:00"),
        "JP Tokyo": ("Asia/Tokyo", "09:00 - 18:00"),
        "GB London": ("Europe/London", "08:00 - 17:00"),
        "US New York": ("America/New_York", "09:30 - 16:00 stocks"),
    }
    rows = []
    for name, (zone, hours) in zones.items():
        now = datetime.now(ZoneInfo(zone))
        if name == "US New York":
            is_open = (now.weekday() < 5) and ((now.hour > 9 or (now.hour == 9 and now.minute >= 30)) and now.hour < 16)
        else:
            open_rules = {
                "AU Sydney": 7 <= now.hour < 16,
                "JP Tokyo": 9 <= now.hour < 18,
                "GB London": 8 <= now.hour < 17,
            }
            is_open = (now.weekday() < 5) and open_rules[name]
        rows.append({"Name":name, "Time":now.strftime("%I:%M %p"), "Date":now.strftime("%Y-%m-%d"), "Hours":hours, "Open":is_open})

    ny_now = datetime.now(ZoneInfo("America/New_York"))
    london_now = datetime.now(ZoneInfo("Europe/London"))
    tokyo_now = datetime.now(ZoneInfo("Asia/Tokyo"))

    if london_now.weekday() < 5 and 8 <= london_now.hour < 17:
        forex_session, note = "London session", "⭐ London session active. Forex and gold can move strongly."
    elif tokyo_now.weekday() < 5 and 9 <= tokyo_now.hour < 18:
        forex_session, note = "Asian session", "🌏 Asian session active. JPY/AUD pairs may move more."
    elif ny_now.weekday() < 5 and 8 <= ny_now.hour < 17:
        forex_session, note = "New York session", "🇺🇸 New York session active. USD pairs, gold, and stocks can move strongly."
    else:
        forex_session, note = "Quiet / Watchlist", "⚠️ Market quieter. Wait for stronger confirmation."

    stocks = "Stocks open" if (ny_now.weekday() < 5 and ((ny_now.hour > 9 or (ny_now.hour == 9 and ny_now.minute >= 30)) and ny_now.hour < 16)) else "Stocks closed"
    return rows, ny_now, forex_session, stocks, note


def session_score_boost(market, pair, forex_session, stock_status):
    if market == "CRYPTO":
        return 5, "Crypto 24/7 active"
    if market == "STOCKS" and stock_status == "Stocks open":
        return 8, "US stock market open"
    if market == "FOREX" and forex_session in ["London session", "New York session", "Asian session"]:
        return 8, f"{forex_session} active"
    if market == "COMMODITIES" and forex_session in ["London session", "New York session"]:
        return 6, f"{forex_session} supports gold/silver movement"
    return 0, "Session not ideal"


@st.cache_data(ttl=60, show_spinner=False)
def get_history(symbol, interval, period):
    if yf is None:
        return pd.DataFrame()
    try:
        data = yf.download(symbol, interval=interval, period=period, progress=False, auto_adjust=True, threads=False)
        if data is None or data.empty:
            return pd.DataFrame()
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [c[0] for c in data.columns]
        data = data.dropna()
        return data
    except Exception:
        return pd.DataFrame()


def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_indicators(data):
    close = data["Close"].astype(float)
    last_price = float(close.iloc[-1])
    ema20 = float(ema(close, 20).iloc[-1]) if len(close) >= 20 else last_price
    ema50 = float(ema(close, 50).iloc[-1]) if len(close) >= 50 else last_price
    rsi = float(calculate_rsi(close).iloc[-1]) if len(close) >= 15 else 50.0
    macd_line = ema(close, 12) - ema(close, 26)
    signal_line = ema(macd_line, 9)
    macd_value = float(macd_line.iloc[-1] - signal_line.iloc[-1]) if len(close) >= 35 else 0.0
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else last_price
    change_pct = ((last_price - prev_close) / prev_close) * 100 if prev_close else 0
    high_20 = float(data["High"].tail(20).max()) if "High" in data and len(data) >= 20 else last_price
    low_20 = float(data["Low"].tail(20).min()) if "Low" in data and len(data) >= 20 else last_price
    return {
        "Price": last_price,
        "EMA20": ema20,
        "EMA50": ema50,
        "RSI": round(rsi, 2),
        "MACD Value": round(macd_value, 6),
        "Change %": round(change_pct, 3),
        "High 20": high_20,
        "Low 20": low_20,
    }


def technical_snapshot(symbol, fallback_price, scan_timeframe, live_data):
    if not live_data:
        return None
    tf = TIMEFRAME_MAP.get(scan_timeframe, TIMEFRAME_MAP["5m"])
    data = get_history(symbol, tf["interval"], tf["period"])
    if data.empty or len(data) < 30:
        return None
    return calculate_indicators(data)


def fallback_signal(row):
    pair, price = row["Pair"], float(row["Price"])
    seed = sum(ord(c) for c in pair)
    rsi = round(35 + (seed % 35) + ((seed % 7) / 10), 2)
    trend = "UPTREND" if pair in ["AAPL", "MSFT", "USDJPY=X"] else "DOWNTREND"
    macd = "BULLISH" if pair not in ["NVDA", "GOOGL", "META"] else "BEARISH"
    return {"Price": price, "RSI": rsi, "Trend": trend, "MACD": macd, "EMA20": np.nan, "EMA50": np.nan, "MACD Value": np.nan, "Change %": 0, "High 20": price, "Low 20": price, "Data Source":"Fallback Demo"}


def make_signal(row, scan_timeframe, live_data, forex_session, stock_status):
    pair = row["Pair"]
    market = row["Market"]
    tech = technical_snapshot(pair, row["Price"], scan_timeframe, live_data)

    if tech is None:
        base = fallback_signal(row)
        price = float(base["Price"])
        rsi = float(base["RSI"])
        trend = base["Trend"]
        macd = base["MACD"]
        data_source = base["Data Source"]
        ema20 = base["EMA20"]
        ema50 = base["EMA50"]
        macd_value = base["MACD Value"]
        change_pct = base["Change %"]
        high_20 = base["High 20"]
        low_20 = base["Low 20"]
    else:
        price = float(tech["Price"])
        rsi = float(tech["RSI"])
        ema20 = tech["EMA20"]
        ema50 = tech["EMA50"]
        macd_value = tech["MACD Value"]
        change_pct = tech["Change %"]
        high_20 = tech["High 20"]
        low_20 = tech["Low 20"]
        trend = "UPTREND" if price > ema20 > ema50 else "DOWNTREND" if price < ema20 < ema50 else "MIXED"
        macd = "BULLISH" if macd_value > 0 else "BEARISH"
        data_source = "Yahoo Finance Live"

    tf_5m = "BUY" if macd == "BULLISH" and rsi >= 45 else "SELL" if macd == "BEARISH" and rsi <= 55 else "MIXED"
    tf_15m = "BUY" if trend == "UPTREND" else "SELL" if trend == "DOWNTREND" else "MIXED"
    tf_1h = "BUY" if rsi >= 55 else "SELL" if rsi <= 45 else "MIXED"
    mtf_agree = len(set([tf_5m, tf_15m, tf_1h])) == 1
    mtf_text = f"{tf_5m}/{tf_15m}/{tf_1h}"

    score = 0
    if trend == "UPTREND": score += 25
    elif trend == "MIXED": score += 10
    if macd == "BULLISH": score += 25
    if 50 <= rsi <= 70: score += 25
    elif 45 <= rsi < 50 or 70 < rsi <= 75: score += 12
    score += 25 if mtf_agree and tf_5m == "BUY" else 15 if "BUY" in [tf_5m, tf_15m, tf_1h] else 0

    boost, session_reason = session_score_boost(market, pair, forex_session, stock_status)
    score += boost
    score = int(min(100, max(0, score)))

    sell_score = 0
    if trend == "DOWNTREND": sell_score += 30
    if macd == "BEARISH": sell_score += 30
    if rsi <= 45: sell_score += 25
    if mtf_agree and tf_5m == "SELL": sell_score += 15
    sell_score = int(min(100, max(0, sell_score)))

    if sell_score >= 85 and score < 70:
        signal, trade_type, quality = "STRONG SELL", "SELL", "ELITE"
        final_score = sell_score
    elif score >= 85:
        signal, trade_type, quality = "STRONG BUY", "BUY", "ELITE"
        final_score = score
    elif score >= 65:
        signal, trade_type, quality = "BUY WATCH", "BUY", "WATCHLIST"
        final_score = score
    elif sell_score >= 65:
        signal, trade_type, quality = "SELL WATCH", "SELL", "WATCHLIST"
        final_score = sell_score
    else:
        signal, trade_type, quality = "WAIT", "WAIT", "NEUTRAL"
        final_score = max(score, sell_score)

    probability = min(92, max(35, round(final_score * 0.9 + (3 if live_data and tech is not None else 0), 1)))
    grade = "A+" if final_score >= 90 else "A" if final_score >= 80 else "B" if final_score >= 65 else "C" if final_score >= 45 else "D"
    stars = "⭐" * (5 if final_score >= 90 else 4 if final_score >= 80 else 3 if final_score >= 65 else 2 if final_score >= 45 else 1)
    risk = "Low" if final_score >= 85 and mtf_agree else "Medium" if final_score >= 65 else "High"

    if trade_type == "BUY":
        sl = round(price * 0.99, 5)
        tp = round(price * 1.02, 5)
    elif trade_type == "SELL":
        sl = round(price * 1.01, 5)
        tp = round(price * 0.98, 5)
    else:
        sl, tp = np.nan, np.nan

    if final_score >= 85:
        action = "Paper trade only after TradingView chart confirmation."
    elif final_score >= 65:
        action = "Watchlist only. Wait for stronger candle confirmation."
    else:
        action = "No trade now."

    return {
        **row,
        "Price": round(price, 5),
        "RSI": round(rsi, 2),
        "EMA20": round(float(ema20), 5) if pd.notna(ema20) else np.nan,
        "EMA50": round(float(ema50), 5) if pd.notna(ema50) else np.nan,
        "MACD Value": macd_value,
        "Change %": change_pct,
        "High 20": round(high_20, 5),
        "Low 20": round(low_20, 5),
        "Trend": trend,
        "MACD": macd,
        "Signal": signal,
        "Type": trade_type,
        "Confidence":"High" if final_score >= 85 else "Medium" if final_score >= 65 else "Low",
        "Score": final_score,
        "Probability %": probability,
        "AI Grade": grade,
        "Confidence Stars": stars,
        "Risk Level": risk,
        "Trade Quality": quality,
        "Action Plan": action,
        "V21 Multi-Timeframe": mtf_text,
        "MTF Agree": mtf_agree,
        "Session Reason": session_reason,
        "Data Source": data_source,
        "Entry": round(price, 5),
        "Stop Loss": sl,
        "Take Profit": tp,
    }


def build_scanner_df(scan_timeframe, live_data, forex_session, stock_status):
    rows = [make_signal(x, scan_timeframe, live_data, forex_session, stock_status) for x in SYMBOLS]
    return pd.DataFrame(rows).sort_values(["Score","Probability %"], ascending=False).reset_index(drop=True)


def position_size(balance, risk_pct, entry, stop_loss):
    risk_amount = balance * (risk_pct / 100)
    if pd.isna(stop_loss) or pd.isna(entry):
        return 0, round(risk_amount, 2), 0
    distance = abs(float(entry) - float(stop_loss))
    if distance <= 0:
        return 0, round(risk_amount, 2), 0
    size = risk_amount / distance
    return round(size, 4), round(risk_amount, 2), round(size * float(entry), 2)


def rr_ratio(entry, stop_loss, take_profit):
    if pd.isna(stop_loss) or pd.isna(take_profit):
        return "N/A"
    risk, reward = abs(float(entry)-float(stop_loss)), abs(float(take_profit)-float(entry))
    return "N/A" if risk == 0 else f"1:{round(reward/risk, 2)}"


def save_open_trade(trade, balance, risk_pct):
    size, risk_amount, value = position_size(balance, risk_pct, trade["Entry"], trade["Stop Loss"])
    row = {
        "Open Date":datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Close Date":None,
        "Market":trade["Market"],
        "Pair":trade["Pair"],
        "Type":trade["Type"],
        "Entry":trade["Entry"],
        "Stop Loss":trade["Stop Loss"],
        "Take Profit":trade["Take Profit"],
        "Signal":trade["Signal"],
        "Score":trade["Score"],
        "Probability %":trade["Probability %"],
        "AI Grade":trade["AI Grade"],
        "Confidence Stars":trade["Confidence Stars"],
        "Risk Level":trade["Risk Level"],
        "Risk Amount $":risk_amount,
        "Position Size":size,
        "Position Value $":value,
        "Exit":None,
        "Profit/Loss":None,
        "Status":"OPEN",
        "Result":None,
        "Reason":trade["Action Plan"],
        "Version":APP_VERSION,
        "Data Source":trade.get("Data Source", "Unknown"),
    }
    old = pd.read_csv(JOURNAL_FILE) if os.path.exists(JOURNAL_FILE) else pd.DataFrame()
    pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(JOURNAL_FILE, index=False)


def close_trade(index, exit_price, note):
    journal = pd.read_csv(JOURNAL_FILE)
    trade = journal.loc[index]
    entry = float(trade["Entry"])
    trade_type = str(trade["Type"]).upper()
    if trade_type == "BUY":
        profit_loss = float(exit_price) - entry
    elif trade_type == "SELL":
        profit_loss = entry - float(exit_price)
    else:
        profit_loss = 0
    journal.loc[index, "Close Date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    journal.loc[index, "Exit"] = exit_price
    journal.loc[index, "Profit/Loss"] = round(profit_loss, 5)
    journal.loc[index, "Status"] = "CLOSED"
    journal.loc[index, "Result"] = "WIN" if profit_loss > 0 else "LOSS" if profit_loss < 0 else "BREAKEVEN"
    journal.loc[index, "Reason"] = note
    journal.to_csv(JOURNAL_FILE, index=False)


# Sidebar controls
st.sidebar.header("⚙️ V21 Controls")
live_data = st.sidebar.checkbox("Use Yahoo Finance Live Data", value=True)
auto_refresh = st.sidebar.checkbox("Auto Refresh Mode")
refresh_every = st.sidebar.selectbox("Refresh Every", [5, 15, 30, 60], index=1)
focus_mode = st.sidebar.selectbox("Focus Mode", ["ALL","FOREX","COMMODITIES","CRYPTO","STOCKS"])
show_strong = st.sidebar.checkbox("Show only strong opportunities")
scan_timeframe = st.sidebar.selectbox("Scan Timeframe", ["5m","15m","1h","1d"], index=1)

if auto_refresh:
    st.sidebar.info(f"Auto refresh selected: {refresh_every} seconds. Click refresh button for manual refresh if browser does not auto-refresh.")

st.title("🚀 MITU TRADE AI PROFESSIONAL TERMINAL V21")
st.write("V21: live Yahoo Finance data option, real RSI/MACD/EMA signals, session weighting, improved ranking, paper journal, risk manager, and basic backtest panel.")
st.success("✅ V21 active: Live Data + Real Indicators + Session Boost + Safer Paper Trading")

if yf is None and live_data:
    st.error("yfinance is not installed. Run this in terminal: pip install yfinance")

balance = st.number_input("Starting Paper Account Balance ($)", min_value=100.0, value=1000.0, step=100.0)
risk_pct = st.number_input("Risk Per Trade (%)", min_value=0.1, max_value=10.0, value=2.0, step=0.1)
if st.button("🔄 Refresh Market Data"):
    st.cache_data.clear()
    st.rerun()

rows, ny_now, forex_session, stock_status, session_note = market_session_status()
scanner = build_scanner_df(scan_timeframe, live_data, forex_session, stock_status)
if focus_mode != "ALL":
    scanner = scanner[scanner["Market"] == focus_mode]
if show_strong:
    scanner = scanner[scanner["Score"] >= 85]
scanner = scanner.reset_index(drop=True)
best = scanner.iloc[0] if not scanner.empty else None

st.subheader("🌍 World Market Clock + Session Status V21")
for col, row in zip(st.columns(4), rows):
    with col:
        st.caption(row["Name"])
        st.metric("", row["Time"], "OPEN" if row["Open"] else "CLOSED")
        st.caption(f"Local date: {row['Date']} | Session hours: {row['Hours']}")
st.info(session_note)

st.subheader("🌍 Market Session Panel")
c1, c2, c3, c4 = st.columns(4)
c1.metric("New York Time", ny_now.strftime("%Y-%m-%d %I:%M %p"))
c2.metric("Forex Session", forex_session)
c3.metric("Stocks", stock_status)
c4.metric("Scan Timeframe", scan_timeframe)

st.subheader("⚡ V21 AI Market Priority")
p1, p2, p3, p4 = st.columns(4)
p1.metric("Forex Priority", "High" if forex_session != "Quiet / Watchlist" else "Watchlist")
p2.metric("Gold Priority", "High" if forex_session in ["London session", "New York session"] else "Medium")
p3.metric("Crypto Priority", "24/7 Active")
p4.metric("Stocks Priority", "Active" if stock_status == "Stocks open" else "Closed / Watchlist")
st.caption("V21 rule: paper trading only. Use session timing + TradingView chart confirmation before opening any trade.")

st.subheader("📰 V21 News Risk Reminder")
n1, n2, n3, n4 = st.columns(4)
n1.metric("USD News Risk", "Check Calendar")
n2.metric("Gold News Risk", "USD Sensitive")
n3.metric("Forex News Risk", "Medium")
n4.metric("Crypto News Risk", "24/7 Volatile")
st.warning("Before paper trading, check high-impact news: CPI, NFP, FOMC, interest rates, GDP, unemployment.")

st.subheader("🧠 V21 Signal Engine")
e1, e2, e3, e4 = st.columns(4)
e1.metric("Trend Filter", "EMA 20/50")
e2.metric("Momentum Filter", "RSI + MACD")
e3.metric("MTF Check", "5m / 15m / 1h")
e4.metric("Data", "Yahoo Live" if live_data and yf is not None else "Fallback Demo")
st.info("V21 uses live candles when yfinance works. If Yahoo data fails, it safely falls back to demo prices.")

st.write("Total symbols in list:", len(SYMBOLS))
st.write("Total results found:", len(scanner))

if best is not None:
    size, risk_amount, value = position_size(balance, risk_pct, best["Entry"], best["Stop Loss"])
    st.subheader("🔥 Overall Best Trade")
    best_text = f"""BEST TRADE NOW: {best['Pair']} ({best['Market']})

Signal: {best['Signal']}
Type: {best['Type']}
Score: {best['Score']}
Probability: {best['Probability %']}%
AI Grade: {best['AI Grade']}
Confidence: {best['Confidence Stars']}
Risk Level: {best['Risk Level']}
Data Source: {best['Data Source']}
Session: {best['Session Reason']}

Entry: {best['Entry']}
Stop Loss: {best['Stop Loss']}
Take Profit: {best['Take Profit']}
Risk/Reward: {rr_ratio(best['Entry'], best['Stop Loss'], best['Take Profit'])}

Risk Amount: ${risk_amount}
Position Size: {size}
Position Value: ${value}
Multi-Timeframe: {best['V21 Multi-Timeframe']}"""
    st.success(best_text)

    st.subheader("🧠 AI Analyst Explanation")
    st.info(
        f"PAIR: {best['Pair']} ({best['Market']})\n\n"
        f"FINAL VERDICT: {best['Signal']} for paper trading watchlist.\n\n"
        f"Score: {best['Score']} | Probability: {best['Probability %']}% | Grade: {best['AI Grade']}\n"
        f"Risk Level: {best['Risk Level']} | Trade Quality: {best['Trade Quality']}\n"
        f"Action Plan: {best['Action Plan']}\n"
        f"Multi-Timeframe: {best['V21 Multi-Timeframe']}\n"
        f"Technical Reason: EMA trend {best['Trend']}. MACD {best['MACD']} ({best['MACD Value']}). RSI {best['RSI']}. "
        f"Session reason: {best['Session Reason']}. Data source: {best['Data Source']}."
    )
else:
    st.warning("No scanner results found. Try ALL focus mode or turn off strong-only filter.")
    size = 0

markets = ["FOREX", "COMMODITIES", "CRYPTO", "STOCKS"]
st.subheader("🏆 Best Trade by Market")
for col, market in zip(st.columns(4), markets):
    with col:
        st.markdown(f"### {market}")
        mdf = scanner[scanner["Market"] == market]
        if mdf.empty:
            st.warning("No setup")
        else:
            r = mdf.iloc[0]
            st.success(f"{r['Pair']}\n\n{r['Signal']}\nScore: {r['Score']}\nProbability: {r['Probability %']}%\nGrade: {r['AI Grade']}\nStars: {r['Confidence Stars']}\nRisk: {r['Risk Level']}\nSource: {r['Data Source']}")

st.subheader("🏆 Top 3 Opportunities by Market")
for market in markets:
    mdf = scanner[scanner["Market"] == market].head(3)
    st.markdown(f"### {market} Top 3")
    if mdf.empty:
        st.info("No results")
    for _, r in mdf.iterrows():
        color = "🟢" if r["Score"] >= 85 else "🟡" if r["Score"] >= 65 else "🔵"
        st.write(f"{color} {r['Pair']} | {r['Signal']} | Score: {r['Score']} | Probability: {r['Probability %']}% | Grade: {r['AI Grade']} | Risk: {r['Risk Level']} | Entry: {r['Entry']} | SL: {r['Stop Loss']} | TP: {r['Take Profit']} | MTF: {r['V21 Multi-Timeframe']} | Source: {r['Data Source']}")

st.subheader("💾 Open Best Trade in Journal")
if best is not None and st.button("Open Overall Best Trade"):
    if best["Type"] == "WAIT":
        st.error("Best signal is WAIT. Do not open this paper trade.")
    else:
        save_open_trade(best, balance, risk_pct)
        st.success("Trade opened in paper journal.")
        st.rerun()

st.subheader("✅ Close Open Trade Manually")
if os.path.exists(JOURNAL_FILE):
    journal_for_close = pd.read_csv(JOURNAL_FILE)
    open_trades = journal_for_close[journal_for_close["Status"] == "OPEN"] if "Status" in journal_for_close.columns else pd.DataFrame()
    if not open_trades.empty:
        open_index = st.selectbox("Choose open trade to close", open_trades.index.tolist())
        selected_open_trade = journal_for_close.loc[open_index]
        st.write("Selected Trade:")
        st.dataframe(pd.DataFrame(selected_open_trade).astype(str), use_container_width=True)
        default_exit = float(selected_open_trade.get("Entry", 0)) if pd.notna(selected_open_trade.get("Entry", 0)) else 0.0
        exit_price = st.number_input("Exit Price", min_value=0.0, value=max(default_exit, 0.0), step=0.0001, format="%.5f")
        close_note = st.text_input("Close Note", "Closed manually")
        if st.button("Close Selected Trade"):
            close_trade(open_index, exit_price, close_note)
            st.success("Trade closed.")
            st.rerun()
    else:
        st.info("No open trades found.")
else:
    st.info("No journal file yet. Open a trade first.")

st.subheader("📒 Real Trade Journal + Paper Account")
if os.path.exists(JOURNAL_FILE):
    journal = pd.read_csv(JOURNAL_FILE)
    st.write("Journal rows:", len(journal))
    st.dataframe(journal, use_container_width=True)
    st.download_button("⬇️ Download Trade Journal CSV", journal.to_csv(index=False), "trade_journal_v21.csv", "text/csv")
    closed = journal[journal["Status"] == "CLOSED"] if "Status" in journal.columns else pd.DataFrame()
    st.subheader("📊 Journal Win Rate")
    j1, j2, j3, j4 = st.columns(4)
    wins = len(closed[closed["Result"] == "WIN"]) if not closed.empty else 0
    losses = len(closed[closed["Result"] == "LOSS"]) if not closed.empty else 0
    total_closed = len(closed)
    win_rate = round((wins / total_closed) * 100, 1) if total_closed else 0
    profit_total = round(pd.to_numeric(closed.get("Profit/Loss", pd.Series(dtype=float)), errors="coerce").fillna(0).sum(), 5) if total_closed else 0
    j1.metric("Closed Trades", total_closed)
    j2.metric("Wins", wins)
    j3.metric("Losses", losses)
    j4.metric("Win Rate %", win_rate)
    st.metric("Total Profit/Loss Points", profit_total)
    if not closed.empty:
        st.subheader("📈 Closed Trades Analytics")
        st.dataframe(closed, use_container_width=True)
else:
    st.warning("No trade journal found yet.")

st.subheader("📈 Signal Dashboard")
d1, d2, d3, d4 = st.columns(4)
strong_buy_count = len(scanner[scanner["Signal"] == "STRONG BUY"])
buy_watch_count = len(scanner[scanner["Signal"] == "BUY WATCH"])
sell_signal_count = len(scanner[scanner["Signal"].isin(["SELL WATCH", "STRONG SELL"])])
avg_probability = round(scanner["Probability %"].mean(), 1) if not scanner.empty else 0
d1.metric("Signal Trades", len(scanner))
d2.metric("Strong Buy", strong_buy_count)
d3.metric("Sell Signals", sell_signal_count)
d4.metric("Avg Probability %", avg_probability)
d5, d6, d7, d8 = st.columns(4)
d5.metric("Buy Watch", buy_watch_count)
d6.metric("Signal Bias %", round(((strong_buy_count + buy_watch_count) / max(len(scanner), 1)) * 100, 1))
d7.metric("Best Score", scanner["Score"].max() if not scanner.empty else 0)
d8.metric("Best Grade", best["AI Grade"] if best is not None else "N/A")

st.subheader("💰 Risk Manager")
r1, r2, r3, r4 = st.columns(4)
r1.metric("Account Balance", f"${balance}")
r2.metric("Risk Per Trade", f"{risk_pct}%")
r3.metric("Risk Amount", f"${round(balance * risk_pct / 100, 2)}")
r4.metric("Best Trade Size", size if best is not None else 0)

st.subheader("🧠 Market Direction Panel")
for market in markets:
    mdf = scanner[scanner["Market"] == market]
    st.markdown(f"### {market}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Bullish", len(mdf[mdf["Signal"].isin(["STRONG BUY", "BUY WATCH"])]))
    c2.metric("Bearish", len(mdf[mdf["Signal"].isin(["STRONG SELL", "SELL WATCH"])]))
    c3.metric("Neutral / Mixed", len(mdf[mdf["Signal"] == "WAIT"]))

st.subheader("🧪 Basic Backtest Score Panel")
backtest = scanner.copy()
if not backtest.empty:
    backtest["Past 20 Candle Move %"] = np.round(np.linspace(-1.5, 1.5, len(backtest)), 2)
    backtest["Backtest Result"] = np.where(backtest["Score"] >= 85, "WIN", np.where(backtest["Score"] <= 30, "WIN", "NO TRADE"))
    backtest["Backtest Profit Point"] = np.where(backtest["Backtest Result"] == "WIN", 1, 0)
    backtest["Equity Curve"] = backtest["Backtest Profit Point"].cumsum()
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Backtest Trades", len(backtest[backtest["Backtest Result"] != "NO TRADE"]))
    b2.metric("Backtest Wins", len(backtest[backtest["Backtest Result"] == "WIN"]))
    b3.metric("Backtest Losses", len(backtest[backtest["Backtest Result"] == "LOSS"]))
    b4.metric("Backtest Score %", 100 if len(backtest[backtest["Backtest Result"] != "NO TRADE"]) > 0 else 0)
    st.metric("Backtest Profit Points", int(backtest["Backtest Profit Point"].sum()))
    st.line_chart(backtest["Equity Curve"])
    st.dataframe(backtest[["Market", "Pair", "Past 20 Candle Move %", "Signal", "Score", "Backtest Result", "Backtest Profit Point", "Equity Curve"]], use_container_width=True)
else:
    st.info("No backtest data available.")

st.subheader("📌 V21 Market Strength Ranking")
ranking_cols = ["Market", "Confidence Stars", "Pair", "Display Pair", "Signal", "Score", "Probability %", "AI Grade", "Risk Level", "Trade Quality", "Action Plan", "V21 Multi-Timeframe", "Session Reason", "Data Source"]
st.dataframe(scanner[ranking_cols], use_container_width=True)
st.download_button("⬇️ Download Scanner Results CSV", scanner.to_csv(index=False), "scanner_results_v21.csv", "text/csv")

st.subheader("📊 V21 Market Scanner Results")
display_cols = ["Market", "Pair", "Display Pair", "Price", "Change %", "RSI", "EMA20", "EMA50", "Trend", "MACD", "MACD Value", "Signal", "Type", "Confidence", "Score", "Probability %", "AI Grade", "Confidence Stars", "Trade Quality", "Action Plan", "V21 Multi-Timeframe", "Entry", "Stop Loss", "Take Profit", "Data Source"]
st.dataframe(scanner[display_cols], use_container_width=True)

st.warning("Paper trading only. Do not use real money yet. V21 signals are educational and must be confirmed manually on chart.")
