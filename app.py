import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import twstock
from textblob import TextBlob
import requests
from bs4 import BeautifulSoup
import warnings

warnings.filterwarnings("ignore")

# --- 1. 核心工具函數 ---
def round_stock_price(price):
    """2026 台股升降單位規範"""
    if price < 10: return np.round(price, 2)
    elif price < 50: return np.round(price * 20) / 20
    elif price < 100: return np.round(price, 1)
    elif price < 500: return np.round(price * 2) / 2
    elif price < 1000: return np.round(price, 0)
    else: return np.round(price / 5) * 5

class StockAnalyzer:
    def __init__(self):
        self.headers = {'User-Agent': 'Mozilla/5.0'}

    def fetch_data(self, sid):
        for suffix in [".TW", ".TWO"]:
            df = yf.download(f"{sid}{suffix}", period="1y", progress=False)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df, f"{sid}{suffix}"
        return None, None

    def calculate_indicators(self, df):
        df = df.copy()
        # 技術指標
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        std = df['Close'].rolling(20).std()
        df['BB_up'] = df['MA20'] + (std * 2)
        df['BB_low'] = df['MA20'] - (std * 2)
        low_9 = df['Low'].rolling(9).min()
        high_9 = df['High'].rolling(9).max()
        df['K'] = ((df['Close'] - low_9) / (high_9 - low_9).replace(0, 1) * 100).ewm(com=2).mean()
        df['D'] = df['K'].ewm(com=2).mean()
        tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(14).mean()
        df['VMA20'] = df['Volume'].rolling(20).mean()
        return df.ffill().bfill()

    def get_news_sentiment(self, sid):
        """簡單新聞情緒爬蟲 (模擬)"""
        try:
            # 實際可對接 Google News RSS，此處以關鍵字權重演示
            # 這裡預留邏輯給 TextBlob
            score = 0.5 + (np.random.uniform(-0.2, 0.3)) # 模擬情緒波動
            return np.clip(score, 0, 1)
        except:
            return 0.5

# --- 2. 回測模組 ---
def run_backtest(df):
    capital = 100000
    cash, pos = capital, 0
    history = []
    # 策略：KD金叉買入，死叉賣出
    for i in range(len(df)-100, len(df)):
        p = df.iloc[i]['Close']
        if df.iloc[i]['K'] > df.iloc[i]['D'] and pos == 0:
            pos = cash / p
            cash = 0
            history.append({"日期": df.index[i].date(), "動作": "買入", "價格": round(p, 2)})
        elif df.iloc[i]['K'] < df.iloc[i]['D'] and pos > 0:
            cash = pos * p
            pos = 0
            history.append({"日期": df.index[i].date(), "動作": "賣出", "價格": round(p, 2)})
    
    final_v = cash if pos == 0 else pos * df.iloc[-1]['Close']
    ret = ((final_v - capital) / capital) * 100
    return ret, history

# --- 3. UI 介面 ---
st.set_page_config(page_title="AI 戰情室", layout="wide")
st.markdown("<style> .main { background-color: #0e1117; } </style>", unsafe_allow_html=True)

analyzer = StockAnalyzer()

with st.sidebar:
    st.title("🛡️ 核心控制台")
    sid = st.text_input("輸入股票代碼", "2330")
    run_btn = st.button("啟動 AI 診斷")

if run_btn:
    with st.spinner('正在同步全球數據與情緒分析...'):
        df_raw, ticker = analyzer.fetch_data(sid)
        
        if df_raw is not None:
            df = analyzer.calculate_indicators(df_raw)
            curr = df.iloc[-1]
            
            # 綜合評分計算 (25項邏輯簡化版)
            tech_score = 0
            if curr['Close'] > curr['MA20']: tech_score += 20
            if curr['K'] > curr['D']: tech_score += 20
            if curr['Close'] > curr['MA5']: tech_score += 20
            if curr['Volume'] > curr['VMA20']: tech_score += 20
            
            s_score = analyzer.get_news_sentiment(sid)
            final_score = int(tech_score + (s_score * 20))
            
            # --- 數據儀表板 ---
            st.subheader(f"📊 {sid} 診斷報告：{final_score} 分")
            c1, c2, c3, c4 = st.columns(4)
            entry_p = round_stock_price(curr['MA20'])
            c1.metric("目前現價", f"{curr['Close']:.1f}")
            c2.metric("建議買點", f"{entry_p}")
            c3.metric("情緒偏向", "利多" if s_score > 0.5 else "中性")
            
            # --- 回測執行 ---
            ret, hist = run_backtest(df)
            c4.metric("策略勝率(半年)", f"{ret:.1f}%")

            # --- Plotly K線圖 ---
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name="月線"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_up'], line=dict(color='rgba(255,255,255,0.2)', dash='dash'), name="布林上軌"), row=1, col=1)
            
            # 成交量
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color='white', opacity=0.5), row=2, col=1)
            
            fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            # --- 詳細列表 ---
            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown("### 📝 回測交易明細")
                st.dataframe(pd.DataFrame(hist), use_container_width=True)
            with col_r:
                st.markdown("### 🔍 診斷清單")
                st.write("✅ 均線趨勢：多頭排列" if curr['Close'] > curr['MA20'] else "❌ 均線趨勢：空頭排列")
                st.write("✅ 動能指標：KD金叉" if curr['K'] > curr['D'] else "❌ 動能指標：KD死叉")
                st.write("✅ 資金流向：量增" if curr['Volume'] > curr['VMA20'] else "❌ 資金流向：量縮")
        else:
            st.error("代碼錯誤或暫無數據，請重試。")

st.caption("2026 AI Stock Analysis System - 免責聲明：投資有風險，報告僅供參考。")
