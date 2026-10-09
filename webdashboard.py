import os
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def add_alert(chat_id, ticker, target_price, current_price=None, fair_value=None):
    try:
        data = {
            "chat_id": str(chat_id),
            "ticker": ticker.upper(),
            "target_price": float(target_price),
            "current_price": float(current_price) if current_price is not None else None,
            "fair_value": float(fair_value) if fair_value is not None else None
        }
        supabase.table("alerts").insert(data).execute()
        return True
    except Exception as e:
        return False

def get_alerts():
    try:
        res = supabase.table("alerts").select("*").execute()
        return res.data
    except Exception as e:
        return []

st.set_page_config(page_title="Stock Analytics Dashboard", page_icon="📈", layout="wide")

st.title("📈 Stock Analytics & Price Alert Dashboard")

# ចាប់យក query parameters ពី URL (ticker និង chat_id ស្វ័យប្រវត្តិ)
url_params = st.query_params
default_ticker = url_params.get("ticker", "PLTR").upper()
auto_chat_id = url_params.get("chat_id", None)

col_left, col_right = st.columns([2, 1])

with col_right:
    st.subheader("🔍 Stock Search")
    selected_ticker = st.text_input("បញ្ចូល Ticker:", value=default_ticker).upper().strip()

if selected_ticker:
    try:
        stock = yf.Ticker(selected_ticker)
        info = stock.info
        curr_p = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        
        target_sell = info.get('targetMeanPrice') or (curr_p * 1.2 if curr_p else 0)
        fair_val = target_sell * 0.833
        
        with col_left:
            st.subheader(f"🏢 {info.get('longName', selected_ticker)}")
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Current Price", f"${curr_p:.2f}")
            m2.metric("Target Sell", f"${target_sell:.2f}")
            m3.metric("Fair Value", f"${fair_val:.2f}")
            m4.metric("P/E Ratio", f"{info.get('trailingPE', 0):.2f}" if info.get('trailingPE') else "N/A")

            hist = stock.history(period="1y")
            if not hist.empty:
                fig = go.Figure(data=[go.Candlestick(
                    x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close']
                )])
                fig.update_layout(template="plotly_dark", height=400, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, width="stretch")

        with col_right:
            st.divider()
            st.subheader("🔔 កំណត់ Price Alert")
            
            # បង្ហាញ Chat ID ដែលចាប់បានស្វ័យប្រវត្តិពី Telegram
            if auto_chat_id:
                st.info(f"👤 **Telegram ID:** `{auto_chat_id}`")
            else:
               # st.warning("⚠️ គ្មាន Chat ID! សូមបើក Dashboard នេះចេញពី Telegram Bot។")

            target_alert_price = st.number_input("Target Price ($):", value=float(round(curr_p * 1.1, 2)))
            
            if st.button("💾 រក្សាទុក Alert", type="primary", width="stretch"):
                if not auto_chat_id:
                    st.error("❌ មិនអាចរក្សាទុកបានទេ! សូមចុចបើក Web Dashboard ពី Telegram Bot ម្តងទៀត។")
                else:
                    if add_alert(auto_chat_id, selected_ticker, target_alert_price, curr_p, fair_val):
                        st.success(f"✅ បានរក្សាទុក Alert សម្រាប់ {selected_ticker}!")
                        st.rerun()
                    else:
                        st.error("❌ បរាជ័យក្នុងការរក្សាទុក Alert!")
    except Exception as e:
        st.error(f"Error loading stock data: {e}")

st.divider()

st.subheader("📋 Active Price Alerts (Supabase)")
alerts_data = get_alerts()
if alerts_data:
    df_alerts = pd.DataFrame(alerts_data)
    display_cols = [c for c in ['chat_id', 'ticker', 'current_price', 'target_price', 'fair_value', 'created_at'] if c in df_alerts.columns]
    st.dataframe(df_alerts[display_cols], width="stretch")
else:
    st.info("មិនទាន់មាន Alert កំពុងសកម្មឡើយ។")
