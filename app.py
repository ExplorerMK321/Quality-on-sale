import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="Quality on Sale", layout="centered")
st.title("Quality on Sale")
st.caption("Healthy companies down 30%+ from their 52-week high. Not financial advice.")

# Starter universe: edit freely. European tickers use exchange suffixes.
US = ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","ADBE","CRM","NKE","PYPL",
      "INTC","PFE","UNH","DIS","SBUX","TGT","EL","LULU","MRK","CVS"]
EU = ["ASML.AS","SAP.DE","SIE.DE","MC.PA","OR.PA","NOVO-B.CO","NESN.SW","ROG.SW",
      "AIR.PA","BAYN.DE","ADS.DE","KER.PA","RMS.PA","INGA.AS","UNA.AS","AZN.L"]

with st.sidebar:
    st.header("Settings")
    markets = st.multiselect("Markets", ["US","Europe"], default=["US","Europe"])
    min_drop = st.slider("Minimum drop from 52-week high (%)", 10, 70, 30)
    max_de = st.number_input("Max debt-to-equity", value=1.0, step=0.1)
    min_margin = st.number_input("Min profit margin (%)", value=10.0, step=1.0)
    extra = st.text_input("Extra tickers (comma separated)", "")

universe = (US if "US" in markets else []) + (EU if "Europe" in markets else [])
universe += [t.strip().upper() for t in extra.split(",") if t.strip()]

@st.cache_data(ttl=4*3600)  # refresh every 4 hours
def analyse(ticker):
    t = yf.Ticker(ticker)
    hist = t.history(period="1y")
    if hist.empty:
        return None
    price = hist["Close"].iloc[-1]
    high = hist["High"].max()
    drop = (1 - price / high) * 100
    info = t.info or {}
    de = info.get("debtToEquity")  # Yahoo gives this as a percentage
    de = de / 100 if de is not None else None
    return {
        "Ticker": ticker,
        "Name": info.get("shortName", ticker),
        "Price": round(price, 2),
        "Drop %": round(drop, 1),
        "Debt/Equity": round(de, 2) if de is not None else None,
        "Free cash flow": info.get("freeCashflow"),
        "Profit margin %": round(info["profitMargins"]*100, 1) if info.get("profitMargins") is not None else None,
        "Revenue growth %": round(info["revenueGrowth"]*100, 1) if info.get("revenueGrowth") is not None else None,
        "Current ratio": info.get("currentRatio"),
        "Forward P/E": info.get("forwardPE"),
        "Sector": info.get("sector"),
    }

def healthy(r):
    checks = [
        r["Debt/Equity"] is not None and r["Debt/Equity"] < max_de,
        r["Free cash flow"] is not None and r["Free cash flow"] > 0,
        r["Profit margin %"] is not None and r["Profit margin %"] > min_margin,
        r["Revenue growth %"] is not None and r["Revenue growth %"] > 0,
    ]
    return sum(checks), all(checks)

if st.button("Run screen", type="primary"):
    rows = []
    bar = st.progress(0.0)
    for i, tk in enumerate(universe):
        try:
            r = analyse(tk)
            if r:
                r["Health score"], r["Passes"] = healthy(r)
                rows.append(r)
        except Exception:
            pass
        bar.progress((i+1)/len(universe))
    st.session_state["results"] = pd.DataFrame(rows)

df = st.session_state.get("results")
if df is not None and not df.empty:
    hits = df[(df["Drop %"] >= min_drop) & (df["Passes"])].sort_values("Drop %", ascending=False)
    st.subheader(f"Matches: {len(hits)}")
    st.dataframe(hits[["Ticker","Name","Price","Drop %","Health score"]], hide_index=True)
    with st.expander("Near misses (fallen, 3 of 4 health checks)"):
        near = df[(df["Drop %"] >= min_drop) & (df["Health score"] == 3)]
        st.dataframe(near[["Ticker","Name","Drop %","Health score"]], hide_index=True)

    pick = st.selectbox("Open a stock", hits["Ticker"].tolist() or df["Ticker"].tolist())
    if pick:
        r = df[df["Ticker"] == pick].iloc[0]
        st.header(f"{r['Name']} ({pick})")
        c1, c2, c3 = st.columns(3)
        c1.metric("Price", r["Price"])
        c2.metric("Drop from high", f"{r['Drop %']}%")
        c3.metric("Health score", f"{r['Health score']}/4")
        st.subheader("Health check")
        st.table(r[["Debt/Equity","Free cash flow","Profit margin %","Revenue growth %","Current ratio","Forward P/E","Sector"]].astype(str))

        st.subheader("4-hour chart (last 60 days)")
        h = yf.Ticker(pick).history(period="60d", interval="1h")
        if not h.empty:
            h4 = h["Close"].resample("4h").last().dropna()
            st.line_chart(h4)

        st.subheader("Why is it down? Latest news")
        for n in (yf.Ticker(pick).news or [])[:8]:
            c = n.get("content", n)
            title = c.get("title")
            link = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else c.get("link")
            src = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher")
            if title:
                st.markdown(f"- [{title}]({link}) — {src or ''}")
else:
    st.info("Tap 'Run screen' to start.")
