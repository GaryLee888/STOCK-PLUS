import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import twstock
import time

# --- 1. 核心工具與修約 ---
def round_stock_price(price):
    """2026 台股最新升降單位規範"""
    if price < 10: return np.round(price, 2)
    elif price < 50: return np.round(price * 20) / 20
    elif price < 100: return np.round(price, 1)
    elif price < 500: return np.round(price * 2) / 2
    elif price < 1000: return np.round(price, 0)
    else: return np.round(price / 5) * 5

class StockEngine:
    def __init__(self):
        # 獲取全市場 4 位數純股票代碼 (剔除權證、認購售等)
        self.all_codes = [c for c, info in twstock.codes.items() 
                          if len(c) == 4 and c.isdigit() and info.type in ['股票', 'ETF']]

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

    def calculate_indicators(self, df):
        df = df.copy()
        # 25 項診斷指標所需基礎數據
        for m in [5, 10, 20, 60]: df[f'MA{m}'] = df['Close'].rolling(m).mean()
        std = df['Close'].rolling(20).std()
        df['BB_up'], df['BB_low'] = df['MA20'] + (std * 2), df['MA20'] - (std * 2)
        df['BB_width'] = (df['BB_up'] - df['BB_low']) / df['MA20'].replace(0, 1)
        low_9, high_9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
        df['K'] = ((df['Close'] - low_9) / (high_9 - low_9).replace(0, 1) * 100).ewm(com=2).mean()
        df['D'] = df['K'].ewm(com=2).mean()
        ema12, ema26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
        df['MACD_h'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
        delta = df['Close'].diff()
        gain, loss = (delta.where(delta > 0, 0)).rolling(14).mean(), (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss).replace(0, 1)))
        df['VMA20'] = df['Volume'].rolling(20).mean()
        df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
        return df.ffill().bfill()

    def get_score(self, df):
        """完整 25 項診斷指標"""
        c = df.iloc[-1]; p = df.iloc[-2]
        checks = [
            c['Close'] > c['MA20'], c['MA5'] > c['MA10'], c['MA10'] > c['MA20'],
            c['Close'] > c['BB_up'], c['BB_width'] > p['BB_width'], c['K'] > c['D'],
            c['K'] > 50, c['MACD_h'] > 0, c['MACD_h'] > p['MACD_h'], c['RSI'] > 50,
            c['RSI'] < 80, c['Volume'] > c['VMA20'], c['Volume'] > p['Volume'],
            c['Close'] > c['MA5'], c['OBV'] > p['OBV'], c['Close'] > p['Close'],
            (c['Close']-c['MA20'])/c['MA20'] < 0.1, (c['Close']-c['MA20'])/c['MA20'] > 0,
            c['Close'] > c['MA60'], c['MA20'] > c['MA60'], c['K'] < 80,
            c['D'] < 80, c['Close'] > c['MA10'], c['Low'] > c['MA5'], c['High'] > p['High']
        ]
        return int((sum(checks) / 25) * 100)

# --- 2. 回測引擎 ---
def run_backtest(df):
    capital = 100000
    cash, pos = capital, 0
    history = []
    # 策略：KD金叉買入，死叉賣出
    for i in range(len(df)-120, len(df)):
        price = df.iloc[i]['Close']
        if df.iloc[i]['K'] > df.iloc[i]['D'] and pos == 0:
            pos = cash / price
            cash = 0
            history.append({"日期": df.index[i].date(), "動作": "買入", "價格": f"{price:.2f}"})
        elif df.iloc[i]['K'] < df.iloc[i]['D'] and pos > 0:
            cash = pos * price
            pos = 0
            history.append({"日期": df.index[i].date(), "動作": "賣出", "價格": f"{price:.2f}"})
    
    final_v = cash if pos == 0 else pos * df.iloc[-1]['Close']
    return ((final_v - capital) / capital) * 100, history

# --- 3. UI 介面 ---
st.set_page_config(page_title="AI 終極台股系統", layout="wide")
engine = StockEngine()

with st.sidebar:
    st.title("🛡️ 核心控制台")
    mode = st.radio("功能選擇", ["個股診斷與回測", "全市場 >80分 掃描器"])
    st.info(f"當前監控標的：{len(engine.all_codes)} 檔股票")

if mode == "個股診斷與回測":
    sid = st.text_input("輸入股票代碼 (例如 2330)", "2330")
    if st.button("啟動分析"):
        df_raw, ticker = engine.fetch_data(sid)
        if df_raw is not None:
            df = engine.calculate_indicators(df_raw)
            score = engine.get_score(df)
            ret, trades = run_backtest(df)
            
            # 指標顯示
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("診斷分數", f"{score} 分")
            c2.metric("最新股價", f"{df.iloc[-1]['Close']:.2f}")
            c3.metric("策略回測報酬", f"{ret:.1f}%")
            c4.metric("建議買點", f"{round_stock_price(df.iloc[-1]['MA20'])}")

            # K線圖
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name="月線"), row=1, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="量"), row=2, col=1)
            fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📝 查看半年詳細回測紀錄"):
                st.table(pd.DataFrame(trades))
        else:
            st.error("找不到該股票代碼資料。")

else:
    st.subheader(f"🕵️ 全市場自動偵測 (篩選 4 位數純股票)")
    if st.button("啟動全市場掃描 (可能需要 2-5 分鐘)"):
        results = []
        progress_bar = st.progress(0)
        status = st.empty()
        
        # 掃描邏輯 (針對全部 4 位數股票)
        total = len(engine.all_codes)
        for i, code in enumerate(engine.all_codes):
            status.text(f"掃描中: {code} ({i+1}/{total})")
            df_raw, _ = engine.fetch_data(code)
            if df_raw is not None:
                df = engine.calculate_indicators(df_raw)
                score = engine.get_score(df)
                if score >= 80:
                    ret, _ = run_backtest(df)
                    results.append({"代碼": code, "名稱": twstock.codes[code].name, "分數": score, "策略報酬": f"{ret:.1f}%"})
            progress_bar.progress((i + 1) / total)
        
        st.success(f"掃描完畢！發現 {len(results)} 檔優質標的。")
        if results:
            st.table(pd.DataFrame(results).sort_values(by="分數", ascending=False))

st.caption("2026 AI Stock Engine | 數據來源: Yahoo Finance | 本系統僅供參考")
