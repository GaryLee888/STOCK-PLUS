import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import twstock
import time

# --- 1. 核心邏輯：2026 台股價格修約 ---
def round_stock_price(price):
    if price < 10: return np.round(price, 2)
    elif price < 50: return np.round(price * 20) / 20
    elif price < 100: return np.round(price, 1)
    elif price < 500: return np.round(price * 2) / 2
    elif price < 1000: return np.round(price, 0)
    else: return np.round(price / 5) * 5

# --- 2. 核心分析引擎 ---
class StockEngine:
    def fetch_data(self, sid):
        for suffix in [".TW", ".TWO"]:
            try:
                df = yf.download(f"{sid}{suffix}", period="1y", progress=False)
                if df is not None and not df.empty and len(df) > 60:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    return df, f"{sid}{suffix}"
            except: continue
        return None, None

    def calculate_all_indicators(self, df):
        df = df.copy()
        # 均線群
        for m in [5, 10, 20, 60]: df[f'MA{m}'] = df['Close'].rolling(m).mean()
        # 布林
        std = df['Close'].rolling(20).std()
        df['BB_up'] = df['MA20'] + (std * 2)
        df['BB_low'] = df['MA20'] - (std * 2)
        df['BB_width'] = (df['BB_up'] - df['BB_low']) / df['MA20'].replace(0, 1)
        # KD
        low_9, high_9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
        df['K'] = ((df['Close'] - low_9) / (high_9 - low_9).replace(0, 1) * 100).ewm(com=2).mean()
        df['D'] = df['K'].ewm(com=2).mean()
        # MACD
        ema12 = df['Close'].ewm(span=12).mean()
        ema26 = df['Close'].ewm(span=26).mean()
        df['MACD'] = ema12 - ema26
        df['Signal'] = df['MACD'].ewm(span=9).mean()
        df['Hist'] = df['MACD'] - df['Signal']
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss).replace(0, 1)))
        # 其他
        df['VMA20'] = df['Volume'].rolling(20).mean()
        df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
        return df.ffill().bfill()

    def get_comprehensive_score(self, df):
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        # --- 完整 25 項指標邏輯 ---
        checks = [
            curr['Close'] > curr['MA20'], curr['MA5'] > curr['MA10'], curr['MA10'] > curr['MA20'],
            curr['Close'] > curr['BB_up'], curr['BB_width'] > prev['BB_width'], curr['K'] > curr['D'],
            curr['K'] > 50, curr['Hist'] > 0, curr['Hist'] > prev['Hist'], curr['RSI'] > 50,
            curr['RSI'] < 80, curr['Volume'] > curr['VMA20'], curr['Volume'] > prev['Volume'],
            curr['Close'] > curr['MA5'], curr['OBV'] > prev['OBV'], curr['Close'] > prev['Close'],
            (curr['Close']-curr['MA20'])/curr['MA20'] < 0.1, (curr['Close']-curr['MA20'])/curr['MA20'] > 0,
            curr['Close'] > curr['MA60'], curr['MA20'] > curr['MA60'], curr['K'] < 80,
            curr['D'] < 80, curr['MACD'] > 0, curr['Low'] > curr['MA5'], curr['High'] > prev['High']
        ]
        score = sum([1 for c in checks if c])
        return int((score / 25) * 100)

# --- 3. 介面設定 ---
st.set_page_config(page_title="2026 終極台股分析系統", layout="wide")
engine = StockEngine()

@st.cache_data(ttl=3600)
def get_all_codes():
    """獲取上市、上櫃、興櫃所有代碼"""
    codes = []
    for c, info in twstock.codes.items():
        if info.type in ['股票', 'ETF']: codes.append(c)
    return codes

# --- 4. Sidebar 控制 ---
with st.sidebar:
    st.title("🛡️ 系統控制台")
    mode = st.selectbox("功能模式", ["個股深度診斷", "全市場 >80分 掃描"])
    
    if mode == "個股深度診斷":
        target = st.text_input("輸入股票代碼", "2330")
        btn = st.button("開始診斷")
    else:
        scan_limit = st.slider("掃描數量 (建議先測100)", 50, 1000, 100)
        scan_btn = st.button("啟動全市場掃描")

# --- 5. 主程式邏輯 ---
if mode == "個股深度診斷" and 'target' in locals():
    df_raw, ticker = engine.fetch_data(target)
    if df_raw is not None:
        df = engine.calculate_all_indicators(df_raw)
        score = engine.get_comprehensive_score(df)
        curr = df.iloc[-1]
        
        # 顯示儀表板
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("診斷總分", f"{score} 分")
        c2.metric("最新股價", f"{curr['Close']:.2f}")
        c3.metric("建議買點", f"{round_stock_price(curr['MA20'])}")
        c4.metric("布林寬度", f"{curr['BB_width']:.2%}")

        # K線圖
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name="月線"), row=1, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量"), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("查無資料")

elif mode == "全市場 >80分 掃描":
    if scan_btn:
        all_codes = get_all_codes()[:scan_limit]
        results = []
        bar = st.progress(0)
        status_text = st.empty()
        
        for i, code in enumerate(all_codes):
            status_text.text(f"正在掃描: {code} ({i+1}/{len(all_codes)})")
            df_raw, _ = engine.fetch_data(code)
            if df_raw is not None:
                df = engine.calculate_all_indicators(df_raw)
                score = engine.get_comprehensive_score(df)
                if score >= 80:
                    results.append({"代碼": code, "名稱": twstock.codes[code].name, "分數": score, "現價": df.iloc[-1]['Close']})
            bar.progress((i + 1) / len(all_codes))
        
        st.success(f"掃描完成！共發現 {len(results)} 檔優質標的。")
        if results:
            st.table(pd.DataFrame(results).sort_values(by="分數", ascending=False))
        else:
            st.info("目前市場中暫無 80 分以上標的。")

st.caption("2026 AI Stock Analyzer | GitHub Deployment Ready")
