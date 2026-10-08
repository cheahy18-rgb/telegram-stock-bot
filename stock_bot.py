import os
import time
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

if not BOT_TOKEN:
    raise ValueError("❌ រកមិនឃើញ BOT_TOKEN! សូមពិនិត្យ Environment Variables លើ Render")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ រកមិនឃើញ SUPABASE_URL ឬ SUPABASE_KEY!")

bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# ២. Supabase Database Functions (បន្ថែម fair_value)
# ==========================================
def add_alert(chat_id, ticker, target_price, fair_value=None):
    try:
        data = {
            "chat_id": str(chat_id),
            "ticker": ticker.upper(),
            "target_price": float(target_price),
            "fair_value": float(fair_value) if fair_value is not None else None
        }
        res = supabase.table("alerts").insert(data).execute()
        print(f"✅ Supabase Insert Result: {res}")
        return True
    except Exception as e:
        print(f"❌ Supabase Insert Error: {e}")
        return False

def get_alerts():
    try:
        response = supabase.table("alerts").select("*").execute()
        return response.data
    except Exception as e:
        print(f"❌ Supabase Fetch Error: {e}")
        return []

def delete_alert(alert_id):
    try:
        supabase.table("alerts").delete().eq("id", alert_id).execute()
        return True
    except Exception as e:
        print(f"❌ Supabase Delete Error: {e}")
        return False

# ==========================================
# ៣. Telegram Bot Handlers & Rich Report Logic
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 **ជម្រាបសួរ! ខ្ញុំជា Stock Analyzer Bot**\n\n"
        "📈 **របៀបប្រើប្រាស់៖**\n"
        "- ផ្ញើឈ្មោះ Stock Ticker (ឧទាហរណ៍៖ `PLTR`, `AAPL`, `MSFT`) ដើម្បីទទួលបានរបាយការណ៍វិភាគលម្អិត\n"
        "- កំណត់ Alert៖ `/alert AAPL 200`\n"
        "- មើល Alert របស់អ្នក៖ `/myalerts`"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['myalerts'])
def show_my_alerts(message):
    chat_id = str(message.chat.id)
    alerts = get_alerts()
    user_alerts = [a for a in alerts if str(a.get('chat_id')) == chat_id]
    
    if not user_alerts:
        bot.reply_to(message, "ℹ️ អ្នកមិនទាន់មាន Alert កំពុងសកម្មនៅក្នុងប្រព័ន្ធនៅឡើយទេ។")
        return
        
    msg = "🔔 **បញ្ជី Alert របស់អ្នក៖**\n\n"
    for a in user_alerts:
        fv = a.get('fair_value')
        fv_str = f" | Fair Value: **${float(fv):.2f}**" if fv else ""
        msg += f"• **{a.get('ticker')}** ត្រឹមតម្លៃ Target: **${float(a.get('target_price', 0)):.2f}**{fv_str}\n"
    
    bot.reply_to(message, msg, parse_mode="Markdown")

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
        
        # ទាញយក Fair Value ស្វ័យប្រវត្តិតាម yfinance ពេលសរសេរ /alert
        stock = yf.Ticker(ticker)
        info = stock.info
        target_sell = info.get('targetMeanPrice') or (stock.fast_info.last_price * 1.2 if stock.fast_info.last_price else target_price)
        fair_value = target_sell * 0.833
        
        if add_alert(chat_id, ticker, target_price, fair_value):
            bot.reply_to(
                message, 
                f"✅ បានកំណត់ Alert សម្រាប់ **{ticker}** ត្រឹមតម្លៃ **${target_price:.2f}**\n"
                f"💡 រក្សាទុក Fair Value: **${fair_value:.2f}** ចូលក្នុង Database រួចរាល់!", 
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, "❌ មានបញ្ហាក្នុងការរក្សាទុក alert ទៅក្នុង Database! (សូមពិនិត្យ Column `fair_value` លើ Supabase)")
    except ValueError:
        bot.reply_to(message, "⚠️ តម្លៃ Target Price ត្រូវតែជាលេខ!")

@bot.message_handler(func=lambda message: True)
def get_stock_analysis(message):
    ticker_symbol = message.text.strip().upper()
    
    if ticker_symbol.startswith('/'):
        return

    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        fast_info = stock.fast_info
        
        company_name = info.get('longName', ticker_symbol)
        sector = info.get('sector', 'N/A')
        current_price = fast_info.last_price or info.get('currentPrice', 0.0)
        
        pe_ratio = info.get('trailingPE') or info.get('forwardPE') or 0.0
        eps = info.get('trailingEps') or 0.0
        
        target_sell = info.get('targetMeanPrice')
        if not target_sell or target_sell == 0:
            target_sell = current_price * 1.2
            
        fair_value = target_sell * 0.833
        
        if current_price > 0:
            upside = ((target_sell - current_price) / current_price) * 100
        else:
            upside = 0.0
            
        if current_price < fair_value:
            status_text = "🟢 Under-valued"
        elif current_price > target_sell:
            status_text = "🔴 Over-valued"
        else:
            status_text = "🟡 Fairly-valued"

        response_msg = (
            f"📊 **[របាយការណ៍វិភាគ៖ {ticker_symbol}](https://finance.yahoo.com/quote/{ticker_symbol})**\n\n"
            f"🏢 **ក្រុមហ៊ុន៖** {company_name}\n"
            f"🏭 **វិស័យ៖** {sector}\n"
            f"💵 **តម្លៃបច្ចុប្បន្ន៖** ${current_price:.2f}\n"
            f"📈 **P/E Ratio:** {pe_ratio:.2f} | **EPS:** ${eps:.2f}\n\n"
            f"-----------------------------------\n"
            f"🎯 **ការវាយតម្លៃ (Valuation)**\n"
            f"-----------------------------------\n"
            f"💡 **តម្លៃសមរម្យ (Fair Value)៖** ${fair_value:.2f}\n"
            f"លោកអ្នកគួរដឹង៖ {status_text}\n\n"
            f"🚀 **តម្លៃគួរលក់ (Target Sell)៖** ${target_sell:.2f}\n"
            f"📈 **ឱកាសចំណេញ (Upside)៖** {upside:+.1f}%"
        )
        
        bot.reply_to(message, response_msg, parse_mode="Markdown", disable_web_page_preview=True)
        
    except Exception as e:
        print(f"Error fetching analysis for {ticker_symbol}: {e}")
        bot.reply_to(message, f"❌ មានបញ្ហាក្នុងការទាញយកទិន្នន័យសម្រាប់ `{ticker_symbol}`!", parse_mode="Markdown")

# ==========================================
# ៤. Background Threads (Bot & Price Alert Checker)
# ==========================================
def start_bot():
    print("🤖 Telegram Bot thread is starting...")
    try:
        bot.skip_pending_commits()
    except Exception as e:
        print(f"Skip pending commits info: {e}")
    bot.infinity_polling(none_stop=True)

def check_price_alerts():
    print("🔔 Auto Price Alert Checker Thread started...")
    while True:
        try:
            alerts = get_alerts()
            for alert in alerts:
                alert_id = alert.get('id')
                chat_id = alert.get('chat_id')
                ticker = alert.get('ticker')
                target_price = float(alert.get('target_price', 0))
                fair_val = alert.get('fair_value')
                
                if not ticker or not target_price:
                    continue
                
                stock = yf.Ticker(ticker)
                current_price = stock.fast_info.last_price
                
                if current_price is None:
                    continue
                
                if current_price >= target_price:
                    fv_info = f"\n💡 តម្លៃ Fair Value៖ **${float(fair_val):.2f}**" if fair_val else ""
                    alert_msg = (
                        f"🚨 **PRICE ALERT TRIGGERED!** 🚨\n\n"
                        f"📈 **{ticker}** ពេលនេះបានឡើងដល់តម្លៃ Target ហើយ!\n"
                        f"💵 តម្លៃបច្ចុប្បន្ន៖ **${current_price:.2f}**\n"
                        f"🎯 តម្លៃ Target របស់អ្នក៖ **${target_price:.2f}**"
                        f"{fv_info}"
                    )
                    bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                    delete_alert(alert_id)
                    print(f"✅ Alert Triggered & Deleted for {ticker} (Chat ID: {chat_id})")
                    
        except Exception as e:
            print(f"❌ Error in price alert checker thread: {e}")
            
        time.sleep(300)

if "bot_started" not in st.session_state:
    st.session_state["bot_started"] = True
    threading.Thread(target=start_bot, daemon=True).start()

if "alert_checker_started" not in st.session_state:
    st.session_state["alert_checker_started"] = True
    threading.Thread(target=check_price_alerts, daemon=True).start()

# ==========================================
# ៥. Streamlit Dashboard Web Interface
# ==========================================
st.set_page_config(page_title="Stock Analyzer & Bot Dashboard", page_icon="📈", layout="wide")

st.title("📈 Stock Analyzer Dashboard & Telegram Bot")
st.success("🤖 Telegram Bot & Price Alert Checker ត្រូវបានដាស់ឱ្យដំណើរការ (Active Background Workers)!")

col1, col2 = st.columns([1, 2])

timeframe_map = {
    "1 Day (1D)": {"period": "1d", "interval": "5m"},
    "5 Days (5D)": {"period": "5d", "interval": "15m"},
    "1 Month (1M)": {"period": "1mo", "interval": "1d"},
    "6 Months (6M)": {"period": "6mo", "interval": "1d"},
    "1 Year (1Y)": {"period": "1y", "interval": "1wk"},
    "5 Years (5Y)": {"period": "5y", "interval": "1mo"}
}

with col1:
    st.header("🔍 Stock Query")
    selected_ticker = st.text_input("បញ្ចូល Stock Ticker (ឧ. AAPL, PLTR):", value="PLTR").upper()
    
    selected_timeframe_label = st.selectbox(
        "⏱️ ជ្រើសរើស Timeframe សម្រាប់ Chart:",
        list(timeframe_map.keys()),
        index=2
    )
    
    tf_setting = timeframe_map[selected_timeframe_label]
    
    if selected_ticker:
        try:
            stock = yf.Ticker(selected_ticker)
            hist = stock.history(period=tf_setting["period"], interval=tf_setting["interval"])
            
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
        # បន្ថែម 'fair_value' ចូលក្នុងតារាង Dashboard
        display_cols = [c for c in ['chat_id', 'ticker', 'target_price', 'fair_value', 'created_at'] if c in df_alerts.columns]
        st.dataframe(df_alerts[display_cols], width='stretch')
    else:
        st.info("មិនទាន់មាន Alert ក្នុង Database នៅឡើយទេ។")

with col2:
    st.header(f"📊 {selected_ticker} Stock Price Chart ({selected_timeframe_label})")
    if selected_ticker:
        try:
            stock = yf.Ticker(selected_ticker)
            hist = stock.history(period=tf_setting["period"], interval=tf_setting["interval"])
            
            if not hist.empty:
                fig = go.Figure(data=[go.Candlestick(
                    x=hist.index,
                    open=hist['Open'],
                    high=hist['High'],
                    low=hist['Low'],
                    close=hist['Close']
                )])
                fig.update_layout(
                    title=f"{selected_ticker} Candlestick Chart ({selected_timeframe_label})",
                    yaxis_title="Price (USD)",
                    template="plotly_dark",
                    xaxis_rangeslider_visible=False
                )
                st.plotly_chart(fig, width='stretch')
            else:
                st.error("មិនមានទិន្នន័យសម្រាប់ Timeframe នេះទេ!")
        except Exception as e:
            st.error(f"Cannot generate chart: {e}")
