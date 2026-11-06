import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="Quality on Sale", layout="centered")
st.title("Quality on Sale")
st.caption("Healthy companies that fell hard. Signals come from simple formulas, not financial advice. All prices in EUR.")

US = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "ADBE", "CRM", "NKE", "PYPL", "INTC", "PFE",
      "UNH", "DIS", "SBUX", "TGT", "EL", "LULU", "MRK", "CVS", "BMY", "ABBV", "JNJ", "KO", "PEP", "MCD",
      "QCOM", "TXN", "AMD", "ORCL", "CSCO", "V", "MA", "HD", "LOW", "COST", "WMT", "ELV", "HUM", "ZTS",
      "MDT", "DHR", "TMO", "BA", "UPS", "FDX", "MMM", "DE", "CAT", "ADM"]
EU = ["ASML.AS", "SAP.DE", "SIE.DE", "MC.PA", "OR.PA", "NOVO-B.CO", "NESN.SW", "ROG.SW", "NOVN.SW",
      "AIR.PA", "BAYN.DE", "ADS.DE", "KER.PA", "RMS.PA", "INGA.AS", "UNA.AS", "AZN.L", "GSK.L",
      "ULVR.L", "DGE.L", "BMW.DE", "MBG.DE", "VOW3.DE", "ALV.DE", "DTE.DE", "IFX.DE", "PUM.DE",
      "ZAL.DE", "SAN.PA", "BN.PA", "EL.PA", "CAP.PA", "STLAM.MI", "RACE.MI", "ENEL.MI", "ITX.MC",
      "IBE.MC", "PHIA.AS", "HEIA.AS", "ABI.BR", "NOKIA.HE", "ERIC-B.ST", "VOLV-B.ST", "DSV.CO"]

with st.sidebar:
    st.header("Settings")
    markets = st.multiselect("Markets", ["US", "Europe"], default=["US", "Europe"])
    min_drop = st.slider("Minimum drop from 52-week high (%)", 10, 70, 30)
    max_de = st.number_input("Max debt-to-equity", value=1.0, step=0.1)
    min_margin = st.number_input("Min profit margin (%)", value=10.0, step=1.0)
    top_n = st.slider("How many top stocks", 5, 30, 10)
    extra = st.text_input("Extra tickers (comma separated)", "")

universe = (US if "US" in markets else []) + (EU if "Europe" in markets else [])
universe += [t.strip().upper() for t in extra.split(",") if t.strip()]


@st.cache_data(ttl=4 * 3600)
def fx_to_eur(cur):
    if not cur or cur == "EUR":
        return 1.0
    factor = 1.0
    if cur in ("GBp", "GBX"):
        cur, factor = "GBP", 0.01
    h = yf.Ticker(cur + "EUR=X").history(period="5d")
    if h.empty:
        return 1.0
    return float(h["Close"].iloc[-1]) * factor


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    down = (-d.clip(upper=0)).rolling(n).mean()
    return float((100 - 100 / (1 + up / down)).iloc[-1])


@st.cache_data(ttl=4 * 3600)
def analyse(ticker):
    t = yf.Ticker(ticker)
    hist = t.history(period="1y")
    if hist.empty or len(hist) < 30:
        return None
    info = t.info or {}
    fx = fx_to_eur(info.get("currency"))
    close = hist["Close"]
    price = float(close.iloc[-1])
    high52 = float(hist["High"].max())
    low60 = float(hist["Low"].tail(60).min())
    tr = pd.concat([hist["High"] - hist["Low"],
                    (hist["High"] - close.shift()).abs(),
                    (hist["Low"] - close.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])

    de = info.get("debtToEquity")
    de = de / 100 if de is not None else None
    try:
        isin = t.isin if t.isin and t.isin != "-" else "n/a"
    except Exception:
        isin = "n/a"
    pm = info.get("profitMargins")
    rg = info.get("revenueGrowth")
    fcf = info.get("freeCashflow")

    return {
        "Ticker": ticker,
        "ISIN": isin,
        "Name": info.get("shortName", ticker),
        "Sector": info.get("sector"),
        "Price EUR": round(price * fx, 2),
        "Drop %": round((1 - price / high52) * 100, 1),
        "RSI": round(rsi(close), 1),
        "Debt/Equity": round(de, 2) if de is not None else None,
        "Free cash flow EUR M": round(fcf * fx / 1e6) if fcf else None,
        "Profit margin %": round(pm * 100, 1) if pm is not None else None,
        "Revenue growth %": round(rg * 100, 1) if rg is not None else None,
        "Current ratio": info.get("currentRatio"),
        "Forward P/E": info.get("forwardPE"),
        # Price levels in EUR, based on typical daily move (ATR) and the 52-week range
        "Strong buy at": round((price - atr) * fx, 2),
        "Do not buy above": round((price + 0.5 * atr) * fx, 2),
        "Take profit at": round((price + 0.5 * (high52 - price)) * fx, 2),
        "Stop loss at": round((min(low60, price) - atr) * fx, 2),
    }


def health(r):
    return {
        "Debt/Equity below " + str(max_de): r["Debt/Equity"] is not None and r["Debt/Equity"] < max_de,
        "Positive free cash flow": r["Free cash flow EUR M"] is not None and r["Free cash flow EUR M"] > 0,
        "Profit margin above " + str(min_margin) + "%": r["Profit margin %"] is not None and r["Profit margin %"] > min_margin,
        "Revenue growing": r["Revenue growth %"] is not None and r["Revenue growth %"] > 0,
        "Current ratio above 1 (can pay short-term bills)": r["Current ratio"] is not None and r["Current ratio"] > 1,
    }


def rating(r, score):
    if score == 5 and r["Drop %"] >= min_drop and r["RSI"] < 35:
        return "High buy"
    if score >= 4 and r["Drop %"] >= min_drop:
        return "Medium buy"
    if score >= 3 and r["Drop %"] >= min_drop * 0.66:
        return "Low buy"
    return "Watch"


RANK = {"High buy": 3, "Medium buy": 2, "Low buy": 1, "Watch": 0}


def eur(x):
    return "€" + str(x)


if st.button("Run screen", type="primary"):
    rows = []
    bar = st.progress(0.0, text="Scanning... the first run takes a few minutes")
    for i, tk in enumerate(universe):
        try:
            r = analyse(tk)
            if r:
                score = sum(health(r).values())
                r["Health score"] = str(score) + "/5"
                r["_score"] = score
                r["Rating"] = rating(r, score)
                rows.append(r)
        except Exception:
            pass
        bar.progress((i + 1) / len(universe))
    st.session_state["results"] = pd.DataFrame(rows)

df = st.session_state.get("results")
if df is not None and not df.empty:
    df["_rank"] = df["Rating"].map(RANK)
    top = df.sort_values(["_rank", "_score", "Drop %"], ascending=False).head(top_n)
    st.subheader("Top " + str(len(top)) + " candidates")
    st.dataframe(top[["Rating", "Name", "ISIN", "Ticker", "Price EUR", "Drop %", "Health score"]],
                 hide_index=True)

    with st.expander("How the health score and rating work"):
        st.markdown("""
**Health score (5 checks, 1 point each):** debt-to-equity below your limit, positive free cash flow,
profit margin above your limit, revenue growing, current ratio above 1.

**Rating:**
- **High buy**: 5/5 health, fallen at least your minimum drop, and RSI below 35 (oversold).
- **Medium buy**: at least 4/5 health and fallen at least your minimum drop.
- **Low buy**: at least 3/5 health and fallen at least two thirds of your minimum drop.

**Price levels:** based on the stock's typical daily move (ATR, 14 days).
- Strong buy at = current price minus one typical daily move.
- Do not buy above = current price plus half a typical daily move.
- Take profit at = halfway back up to the 52-week high.
- Stop loss at = one typical daily move below the 60-day low.
""")

    pick = st.selectbox("Open a stock", top["Ticker"].tolist())
    if pick:
        r = df[df["Ticker"] == pick].iloc[0]
        st.header(r["Name"])
        st.write("**ISIN:** " + str(r["ISIN"]) + "  |  **Ticker:** " + pick + "  |  **Sector:** " + str(r["Sector"]))
        st.write("Search the ISIN in Trade Republic or any broker app to find this exact stock.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Price", eur(r["Price EUR"]))
        c2.metric("Drop from high", str(r["Drop %"]) + "%")
        c3.metric("Rating", r["Rating"])

        st.subheader("Trading levels (EUR)")
        l1, l2 = st.columns(2)
        l1.metric("Strong buy at", eur(r["Strong buy at"]))
        l2.metric("Do not buy above", eur(r["Do not buy above"]))
        l3, l4 = st.columns(2)
        l3.metric("Take profit at", eur(r["Take profit at"]))
        l4.metric("Stop loss at", eur(r["Stop loss at"]))

        st.subheader("Health check: " + r["Health score"])
        for name, ok in health(r).items():
            st.write(("✅ " if ok else "❌ ") + name)
        cols = ["Debt/Equity", "Free cash flow EUR M", "Profit margin %", "Revenue growth %",
                "Current ratio", "Forward P/E", "RSI"]
        st.table(pd.DataFrame({"Value": r[cols].astype(str)}))

        st.subheader("4-hour chart (last 60 days, local currency)")
        h = yf.Ticker(pick).history(period="60d", interval="1h")
        if not h.empty:
            st.line_chart(h["Close"].resample("4h").last().dropna())

        st.subheader("Why is it down? Latest news")
        for n in (yf.Ticker(pick).news or [])[:8]:
            c = n.get("content", n)
            title = c.get("title")
            cu = c.get("canonicalUrl")
            link = cu.get("url") if isinstance(cu, dict) else c.get("link")
            pv = c.get("provider")
            src = pv.get("displayName") if isinstance(pv, dict) else c.get("publisher")
            if title:
                st.markdown("- [" + title + "](" + str(link) + ") — " + str(src or ""))
else:
    st.info("Tap 'Run screen' to start.")
