import streamlit as st
import pandas as pd
import os

st.title("📊 當沖雷達績效看板")
daily_f = f"DayTrade_Log_{pd.Timestamp.now().strftime('%Y-%m-%d')}.xlsx"

if os.path.exists(daily_f):
    df = pd.read_excel(daily_f)
    st.dataframe(df, use_container_width=True)
else:
    st.info("今日尚未產生交易紀錄。")
