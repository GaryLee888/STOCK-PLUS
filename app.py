import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import twstock
from textblob import TextBlob
import os

# --- 1. 核心邏輯：修約與指標 ---
def round_stock_price(price):
    if price < 10: return np.round(price, 2)
    elif price < 50: return np.round(price * 20) / 20
    elif price < 100: return np.round(price, 1)
    elif price < 500: return np.round(price * 2) / 2
    elif price < 1000: return np.round(price, 0)
    else: return np.round(price / 5) * 5

class StockEngine:
    def fetch_data(self, sid):
        for suffix in [".TW", ".TWO"]:
            try:
                df = yf.download(f"{sid}{suffix}", period="1y", progress=False)
                if df is not None and not df.empty and len(df) > 20:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    return df, f"{sid}{suffix}"
            except: continue
        return None, None

    def calculate_indicators(self, df):
        df = df.copy()
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        std = df['Close'].rolling(20).std()
        df['BB_up'] = df['MA20'] + (std * 2)
        df['BB_low'] = df['MA20'] - (std * 2)
        low_9, high_9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
        df['K'] = ((df['Close'] - low_9) / (high_9 - low_9).replace(0, 1) * 100).ewm(com=2).mean()
        df['D'] = df['K'].ewm(com=2).mean()
        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(14).mean()
        df['VMA20'] = df['Volume'].rolling(20).mean()
        return df.ffill().bfill()

    def get_score(self, df):
        curr = df.iloc[-1]
        score = 0
        if curr['Close'] > curr['MA20']: score += 25
        if curr['K'] > curr['D']: score += 25
        if curr['Close'] > curr['MA5']: score += 25
        if curr['Volume'] > curr['VMA20']: score += 25
        return score

# --- 2. 回測引擎 ---
class BacktestEngine:
    def run(self, df):
        backtest_df = df.tail(100).copy()
        cash, pos = 100000, 0
        history = []
        for i in range(len(backtest_df)):
            p = backtest_df.iloc[i]['Close']
            # 簡化回測買賣邏輯
            if backtest_df.iloc[i]['K'] > backtest_df.iloc[i]['D'] and pos == 0:
                pos = cash / p
                cash = 0
                history.append({"日期": backtest_df.index[i].date(), "動作": "買入", "價格": round(p, 2)})
            elif backtest_df.iloc[i]['K'] < backtest_df.iloc[i]['D'] and pos > 0:
                cash = pos * p
                pos = 0
                history.append({"日期": backtest_df.index[i].date(), "動作": "賣出", "價格": round(p, 2)})
        final = cash if pos == 0 else pos * backtest_df.iloc[-1]['Close']
        return ((final - 100000) / 1000), history

# --- 3. Streamlit UI ---
st.set_page_config(page_title="2026 AI 台股分析", layout="wide")
st.title("🚀 AI 智能台股戰情室")

engine = StockEngine()
bt_engine = BacktestEngine()

with st.sidebar:
    st.header("設定")
    sid_input = st.text_input("輸入股票代碼", value="2330")
    analyze_btn = st.button("啟動全面分析")

if analyze_btn:
    df_raw, ticker = engine.fetch_data(sid_input)
    
    if df_raw is not None:
        df = engine.calculate_indicators(df_raw)
        score = engine.get_score(df)
        ret, hist = bt_engine.run(df) # 確保 df 已定義才執行
        curr = df.iloc[-1]
        
        # 顯示指標
        c1, c2, c3 = st.columns(3)
        c1.metric("綜合評分", f"{score} 分")
        c2.metric("最新股價", f"{curr['Close']:.1f}")
        c3.metric("半年回測收益", f"{ret:.2f}%")
        
        # Plotly 圖表
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name="月線"), row=1, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量"), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # 回測紀錄
        with st.expander("查看進出場明細"):
            st.table(pd.DataFrame(hist))
    else:
        st.error("找不到該股票數據，請檢查代碼是否正確。")
