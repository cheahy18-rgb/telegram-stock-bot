import os
import threading
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st
import telebot
from dotenv import load_dotenv
from supabase import Client, create_client

# ==========================================
# ១. ទាញយក Environment Variables & Setup
# ==========================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ការពារ Error ពេលខ្វះ Key លើ Cloud Server
if not BOT_TOKEN:
    raise ValueError("❌ រកមិនឃើញ BOT_TOKEN! សូមពិនិត្យ Environment Variables លើ Render")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ រកមិនឃើញ SUPABASE_URL ឬ SUPABASE_KEY!")

# បង្កើត Clients សម្រាប់ Telegram Bot និង Supabase
bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# ២. Supabase Database Functions
# ==========================================
def add_alert(chat_id, ticker, target_price):
    try:
        data = {
            "chat_id": str(chat_id),
            "ticker": ticker.upper(),
            "target_price": float(target_price)
        }
        supabase.table("alerts").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error adding alert: {e}")
        return False

def get_alerts():
    try:
        response = supabase.table("alerts").select("*").execute()
        return response.data
    except Exception as e:
        print(f"Error fetching alerts: {e}")
        return []

# ==========================================
# ៣. Telegram Bot Handlers & Logic
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 **ជម្រាបសួរ! ខ្ញុំជា Stock Analyzer Bot**\n\n"
        "📈 **របៀបប្រើប្រាស់៖**\n"
        "- ផ្ញើឈ្មោះ Stock Ticker (ឧទាហរណ៍៖ `AAPL`, `PLTR`, `RIOT`) ដើម្បីមើលតម្លៃ និងការវិភាគ\n"
        "- កំណត់ Alert៖ `/alert AAPL 200`\n"
        "- មើល Alert របស់អ្នក៖ `/myalerts`"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['alert'])
def set_alert(message):
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "⚠️ សូមផ្ញើតាមទម្រង់៖ `/alert <TICKER> <TARGET_PRICE>`\nឧទាហរណ៍៖ `/alert AAPL 230`", parse_mode="Markdown")
            return
        
        ticker = parts[1].upper()
        target_price = float(parts[2])
        chat_id = message.chat.id
        
        if add_alert(chat_id, ticker, target_price):
            bot.reply_to(message, f"✅ បានកំណត់ Alert សម្រាប់ **{ticker}** ត្រឹមតម្លៃ **${target_price:.2f}** ដោយជោគជ័យ!", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ មានបញ្ហាក្នុងការរក្សាទុក alert ទៅក្នុង Database!")
    except ValueError:
        bot.reply_to(message, "⚠️ តម្លៃ Target Price ត្រូវតែជាលេខ!")

@bot.message_handler(func=lambda message: True)
def get_stock_info(message):
    ticker_symbol = message.text.strip().upper()
    
    # មិនដំណើរការប្រសិនបើជា Command
    if ticker_symbol.startswith('/'):
        return

    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.fast_info
        
        current_price = info.last_price
        prev_close = info.previous_close
        
        if current_price is None or prev_close is None:
            bot.reply_to(message, f"❌ រកមិនឃើញទិន្នន័យសម្រាប់ Ticker: `{ticker_symbol}` ទេ!", parse_mode="Markdown")
            return
            
        change = current_price - prev_close
        change_pct = (change / prev_close) * 100
        
        status_icon = "🟢" if change >= 0 else "🔴"
        
        response_msg = (
            f"📊 **{ticker_symbol} Stock Info**\n\n"
            f"💵 តម្លៃបច្ចុប្បន្ន៖ **${current_price:.2f}**\n"
            f"{status_icon} បម្រែបម្រួល៖ **${change:+.2f} ({change_pct:+.2f}%)**\n"
            f"📉 តម្លៃបិទម្សិលមិញ៖ **${prev_close:.2f}**"
        )
        bot.reply_to(message, response_msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.reply_to(message, f"❌ មានបញ្ហាក្នុងការទាញយកទិន្នន័យ `{ticker_symbol}`", parse_mode="Markdown")

# ==========================================
# ៤. Running Telegram Bot inside Thread
# ==========================================
def start_bot():
    print("🤖 Telegram Bot thread is starting...")
    try:
        bot.skip_pending_commits()
    except Exception as e:
        print(f"Skip pending commits info: {e}")
    bot.infinity_polling(none_stop=True)

# ការពារ Thread រត់ជាន់គ្នានៅពេល Streamlit Re-run លើ UI
if "bot_started" not in st.session_state:
    st.session_state["bot_started"] = True
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

# ==========================================
# ៥. Streamlit Dashboard Web Interface
# ==========================================
st.set_page_config(page_title="Stock Analyzer & Bot Dashboard", page_icon="📈", layout="wide")

st.title("📈 Stock Analyzer Dashboard & Telegram Bot")
st.success("🤖 Telegram Bot ត្រូវបានដាស់ឱ្យដំណើរការ (Active Background Worker)!")

col1, col2 = st.columns([1, 2])

with col1:
    st.header("🔍 Stock Query")
    selected_ticker = st.text_input("បញ្ចូល Stock Ticker (ឧ. AAPL, PLTR):", value="AAPL").upper()
    
    if selected_ticker:
        try:
            stock = yf.Ticker(selected_ticker)
            hist = stock.history(period="1mo")
            
            if not hist.empty:
                last_price = hist['Close'].iloc[-1]
                st.metric(label=f"{selected_ticker} Current Price", value=f"${last_price:.2f}")
            else:
                st.warning("រកមិនឃើញទិន្នន័យ Chart ឡើយ!")
        except Exception as e:
            st.error(f"Error fetching data: {e}")

    st.divider()
    st.header("🔔 Active Alerts (Supabase)")
    alerts_data = get_alerts()
    if alerts_data:
        df_alerts = pd.DataFrame(alerts_data)
        st.dataframe(df_alerts[['chat_id', 'ticker', 'target_price', 'created_at']], width='stretch')
    else:
        st.info("មិនទាន់មាន Alert ក្នុង Database នៅឡើយទេ។")

with col2:
    st.header(f"📊 {selected_ticker} Stock Price Chart (1 Month)")
    if selected_ticker:
        try:
            stock = yf.Ticker(selected_ticker)
            hist = stock.history(period="1mo")
            
            if not hist.empty:
                fig = go.Figure(data=[go.Candlestick(
                    x=hist.index,
                    open=hist['Open'],
                    high=hist['High'],
                    low=hist['Low'],
                    close=hist['Close']
                )])
                fig.update_layout(title=f"{selected_ticker} Candlestick Chart", yaxis_title="Price (USD)", template="plotly_dark")
                st.plotly_chart(fig, width='stretch')
        except Exception as e:
            st.error(f"Cannot generate chart: {e}")
