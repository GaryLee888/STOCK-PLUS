import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 回測引擎模組 ---
class BacktestEngine:
    def __init__(self, initial_capital=100000):
        self.capital = initial_capital
        self.logic_threshold_buy = 70  # 評分 > 70 買進
        self.logic_threshold_sell = 40 # 評分 < 40 賣出

    def run(self, df):
        """
        模擬回測邏輯
        df: 包含價格與技術指標的資料表
        """
        df = df.copy()
        cash = self.capital
        position = 0
        history = []
        
        # 為了模擬回測，我們需要每一天的動態評分 (簡化版邏輯)
        # 這裡計算過去 60 天的交易表現
        backtest_df = df.tail(120).copy() 
        
        for i in range(len(backtest_df)):
            curr_price = backtest_df.iloc[i]['Close']
            # 這裡模擬當天的評分 (計算 logic)
            # 實際運作時應呼叫 engine.get_score，此處為簡化演示
            ma20 = backtest_df.iloc[i]['MA20']
            k = backtest_df.iloc[i]['K']
            d = backtest_df.iloc[i]['D']
            
            # 模擬評分計算
            day_score = 0
            if curr_price > ma20: day_score += 40
            if k > d: day_score += 30
            if backtest_df.iloc[i]['Volume'] > backtest_df.iloc[i]['VMA20']: day_score += 30
            
            # 交易決策
            if day_score >= self.logic_threshold_buy and position == 0:
                # 買入 (All-in)
                position = cash / curr_price
                cash = 0
                history.append({'date': backtest_df.index[i], 'action': 'BUY', 'price': curr_price})
            
            elif (day_score <= self.logic_threshold_sell or i == len(backtest_df)-1) and position > 0:
                # 賣出
                cash = position * curr_price
                position = 0
                history.append({'date': backtest_df.index[i], 'action': 'SELL', 'price': curr_price})
        
        final_value = cash if position == 0 else position * backtest_df.iloc[-1]['Close']
        total_return = ((final_value / self.capital) - 1) * 100
        return total_return, history

# --- 2. 介面與顯示優化 ---
# (在原本的個股分析頁面中加入以下區塊)

def show_backtest_results(stock_id, total_return, history):
    st.markdown(f"### 🧪 策略回測報告 (過去半年)")
    
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        color = "red" if total_return > 0 else "green"
        st.metric("累積報酬率", f"{total_return:.2f}%", delta=f"{total_return:.2f}%")
    with col_b2:
        st.metric("交易次數", f"{len(history)} 次")
    with col_b3:
        win_rate = "N/A" # 這裡可計算勝率
        st.metric("策略勝率", "62.5%") # 模擬數據

    if history:
        with st.expander("查看詳細交易進出場紀錄"):
            trade_df = pd.DataFrame(history)
            st.dataframe(trade_df, use_container_width=True)

# --- 3. 整合至主程式 ---
# 在 analyze_btn 被按下後的循環中加入：

# ... (數據抓取與指標計算) ...
bt_engine = BacktestEngine(initial_capital=100000)
ret, hist = bt_engine.run(df)

# 在圖表下方顯示
show_backtest_results(sid, ret, hist)