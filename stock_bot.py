import os
import time
import io
import threading
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from supabase import Client, create_client

# ==========================================
# ១. ទាញយក Environment Variables & Setup
# ==========================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://telegram-stock-bot-8j9u.onrender.com")

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ សូមពិនិត្យមើល Environment Variables (BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY)!")

bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# ២. Supabase Database Functions
# ==========================================
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

def update_alert_current_price(alert_id, new_price):
    try:
        supabase.table("alerts").update({"current_price": float(new_price)}).eq("id", alert_id).execute()
    except Exception as e:
        print(f"❌ Supabase Update Error: {e}")

# ==========================================
# ៣. Helper Function: បង្កើត Chart Image
# ==========================================
def generate_chart_image(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if hist.empty:
            return None
        
        fig = go.Figure(data=[go.Candlestick(
            x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close']
        )])
        fig.update_layout(
            title=f"{ticker} 1-Year Candlestick Chart",
            yaxis_title="Price (USD)",
            template="plotly_dark",
            xaxis_rangeslider_visible=False
        )
        img_bytes = fig.to_image(format="png", engine="kaleido")
        return io.BytesIO(img_bytes)
    except Exception as e:
        print(f"❌ Error generating chart image for {ticker}: {e}")
        return None

# ==========================================
# ៤. Telegram Bot Handlers
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 **ជម្រាបសួរ! ខ្ញុំជា Stock Analyzer Bot**\n\n"
        "📈 **របៀបប្រើប្រាស់៖**\n"
        "- វាយបញ្ចូល Stock Ticker (ឧ. `PLTR`, `AAPL`, `SOUN`)\n"
        "- ប្រើប្រាស់ Inline Keyboard ដើម្បីមើលព័ត៌មាន, Graph, Alert ឬបើក Web Dashboard"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['alert'])
def set_alert_command(message):
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "⚠️ សូមផ្ញើតាមទម្រង់៖ `/alert <TICKER> <TARGET_PRICE>`\nឧទាហរណ៍៖ `/alert AAPL 230`", parse_mode="Markdown")
            return
        
        ticker, target_price = parts[1].upper(), float(parts[2])
        stock = yf.Ticker(ticker)
        current_price = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        target_sell = stock.info.get('targetMeanPrice') or (current_price * 1.2 if current_price else target_price)
        fair_value = target_sell * 0.833
        
        if add_alert(message.chat.id, ticker, target_price, current_price, fair_value):
            bot.reply_to(
                message, 
                f"✅ បានកំណត់ Alert សម្រាប់ **{ticker}** ត្រឹម **${target_price:.2f}**\n"
                f"💵 តម្លៃបច្ចុប្បន្ន៖ **${current_price:.2f}** \vert{} Fair Value: **${fair_value:.2f}**", 
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, "❌ មានបញ្ហាក្នុងការរក្សាទុក Alert!")
    except Exception as e:
        bot.reply_to(message, "⚠️ មានបញ្ហាក្នុងការរក្សាទុក! សូមពិនិត្យមើល Ticker ឬលេខតម្លៃ។")

@bot.message_handler(func=lambda message: True)
def handle_stock_ticker(message):
    try:
        ticker = message.text.strip().upper()
        if ticker.startswith('/'): return

        stock = yf.Ticker(ticker)
        fast_info = stock.fast_info
        price = getattr(fast_info, 'last_price', None)
        
        if not price:
            bot.reply_to(message, f"❌ រកមិនឃើញទិន្នន័យ Stock សម្រាប់ `{ticker}` ទេ!", parse_mode="Markdown")
            return

        markup = InlineKeyboardMarkup(row_width=2)
        btn_info = InlineKeyboardButton("🏢 ព័ត៌មានក្រុមហ៊ុន", callback_data=f"info_{ticker}")
        btn_graph = InlineKeyboardButton("📊 មើល Graph", callback_data=f"graph_{ticker}")
        btn_alert = InlineKeyboardButton("🔔 កំណត់ Price Alert", callback_data=f"alert_{ticker}")
        
        user_chat_id = message.chat.id
        dynamic_dashboard_url = f"{DASHBOARD_URL}?ticker={ticker}&chat_id={user_chat_id}"
        btn_web = InlineKeyboardButton("🌐 Web Dashboard", url=dynamic_dashboard_url)
        
        markup.add(btn_info, btn_graph, btn_alert, btn_web)

        bot.reply_to(
            message,
            f"📈 **Stock Ticker Selected: {ticker}**\n"
            f"💵 តម្លៃបច្ចុប្បន្ន៖ **${price:.2f}**\n\n"
            f"👇 សូមជ្រើសរើសមុខងារខាងក្រោម៖",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error handling message: {e}")
        bot.reply_to(message, "⚠️ មានបញ្ហាក្នុងការទាញយកទិន្នន័យ! សូមព្យាយាមម្តងទៀត។")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    data = call.data
    chat_id = call.message.chat.id

    if data.startswith("info_"):
        ticker = data.split("_")[1]
        stock = yf.Ticker(ticker)
        info = stock.info
        current_price = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        
        target_sell = info.get('targetMeanPrice') or (current_price * 1.2)
        fair_value = target_sell * 0.833
        status = "🟢 Under-valued" if current_price < fair_value else ("🔴 Over-valued" if current_price > target_sell else "🟡 Fairly-valued")
        
        response_msg = (
            f"🏢 **[ព័ត៌មានក្រុមហ៊ុន៖ {info.get('longName', ticker)}](https://finance.yahoo.com/quote/{ticker})**\n\n"
            f"🏭 **វិស័យ៖** {info.get('sector', 'N/A')}\n"
            f"💵 **តម្លៃបច្ចុប្បន្ន៖** ${current_price:.2f}\n"
            f"📈 **P/E Ratio:** {info.get('trailingPE', 0):.2f} | **EPS:** ${info.get('trailingEps', 0):.2f}\n\n"
            f"-----------------------------------\n"
            f"🎯 **Valuation**\n"
            f"-----------------------------------\n"
            f"💡 **Fair Value៖** ${fair_value:.2f}\n"
            f"📊 **ស្ថានភាព៖** {status}\n"
            f"🚀 **Target Sell៖** ${target_sell:.2f}"
        )
        bot.send_message(chat_id, response_msg, parse_mode="Markdown", disable_web_page_preview=True)

    elif data.startswith("graph_"):
        ticker = data.split("_")[1]
        status_msg = bot.send_message(chat_id, f"⏳ កំពុងបង្កើត Graph សម្រាប់ `{ticker}`...", parse_mode="Markdown")
        
        try:
            img_stream = generate_chart_image(ticker)
            if img_stream:
                bot.send_photo(chat_id, photo=img_stream, caption=f"📊 1-Year Candlestick Chart សម្រាប់ **{ticker}**", parse_mode="Markdown")
                bot.delete_message(chat_id, status_msg.message_id)
            else:
                bot.edit_message_text(f"❌ មិនអាចទាញយក Graph សម្រាប់ `{ticker}` បានទេ!", chat_id, status_msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"⚠️ មានបញ្ហាក្នុងការបង្កើត Graph សម្រាប់ `{ticker}`!", chat_id, status_msg.message_id)

    elif data.startswith("alert_"):
        ticker = data.split("_")[1]
        stock = yf.Ticker(ticker)
        curr_p = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        sug_p = round(curr_p * 1.1, 2)
        
        msg = (
            f"🔔 **របៀបកំណត់ Price Alert សម្រាប់ {ticker}**\n\n"
            f"សូម វាយបញ្ជា៖\n"
            f"`/alert {ticker} {sug_p}`\n\n"
            f"*(ចំណាំ៖ អាចប្តូរលេខ `{sug_p}` ទៅជាតម្លៃដែលចង់ឱ្យ Alert បាន)*"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")

    bot.answer_callback_query(call.id)

# ==========================================
# ៥. Background Worker Thread (Alert Checker)
# ==========================================
def check_price_alerts():
    while True:
        try:
            alerts = get_alerts()
            for alert in alerts:
                try:
                    alert_id = alert.get('id')
                    chat_id = alert.get('chat_id')
                    ticker = alert.get('ticker')
                    target_price = float(alert.get('target_price', 0))
                    fair_val = alert.get('fair_value')
                    
                    if not ticker or not target_price: continue
                    stock = yf.Ticker(ticker)
                    current_price = getattr(stock.fast_info, 'last_price', None)
                    
                    if current_price:
                        update_alert_current_price(alert_id, current_price)
                        
                        if current_price >= target_price:
                            fv_info = f"\n💡 តម្លៃ Fair Value៖ **${float(fair_val):.2f}**" if fair_val else ""
                            alert_msg = (
                                f"🚨 **PRICE ALERT TRIGGERED!** 🚨\n\n"
                                f"📈 **{ticker}** បានឡើងដល់ Target ហើយ!\n"
                                f"💵 តម្លៃបច្ចុប្បន្ន៖ **${current_price:.2f}**\n"
                                f"🎯 តម្លៃ Target៖ **${target_price:.2f}**"
                                f"{fv_info}"
                            )
                            bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                            delete_alert(alert_id)
                except Exception as inner_e:
                    print(f"Error processing alert for {alert}: {inner_e}")
        except Exception as e:
            print(f"Alert Check Loop Error: {e}")
        
        time.sleep(300)

# ==========================================
# ៦. Streamlit Dashboard & Main Execution
# ==========================================
if "bot_started" not in st.session_state:
    st.session_state["bot_started"] = True

    def run_polling_safe():
        try:
            bot.remove_webhook()
            time.sleep(1)
        except Exception as e:
            print(f"Webhook note: {e}")

        while True:
            try:
                bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
            except Exception as e:
                print(f"Polling Exception: {e}")
                time.sleep(3)

    threading.Thread(target=run_polling_safe, daemon=True).start()

if "alert_checker_started" not in st.session_state:
    st.session_state["alert_checker_started"] = True
    threading.Thread(target=check_price_alerts, daemon=True).start()

# --- UI Interface Streamlit ---
st.set_page_config(page_title="Stock Analytics Dashboard", page_icon="📈", layout="wide")

st.title("📈 Stock Analytics & Price Alert Dashboard")

# ចាប់យក query parameters (ticker និង chat_id)
url_params = st.query_params
default_ticker = url_params.get("ticker", "PLTR").upper()
auto_chat_id = url_params.get("chat_id", "")

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
            
            # ផ្តល់ប្រអប់បញ្ចូល Chat ID ដោយស្វ័យប្រវត្តិ (ដកសារ Warning ចោល)
            input_chat_id = st.text_input("Telegram Chat ID:", value=auto_chat_id, placeholder="ឧ. 123456789")
            target_alert_ដើម្បីដោះស្រាយទាំង ២ ចំណុចនេះឱ្យបានស្អាត និងដើរ ១០០%៖

---

### ១. លុបសារ "គ្មាន Chat ID..." ចេញពី Web Dashboard

ដើម្បីឱ្យ Dashboard មើលទៅ Clean គ្មានសារ Warning ញ៉ញ៉ៃ ហើយអនុញ្ញាតឱ្យបញ្ចូល Alert បានស្រួល លោក Chy គ្រាន់តែអនុវត្តកូដក្នុង `app.py` ខាងក្រោម៖

* លុបប្រអប់ `st.warning("⚠️ គ្មាន Chat ID...")` ចោល[cite: 12]
* កំណត់ `chat_id` ជា Option ដោយស្វ័យប្រវត្តិ (បើទាញបានពី URL គឺប្រើ URL បើអត់ទេគឺកំណត់ `chat_id = "default"` ឬមិនទាមទារឱ្យមាន)[cite: 12]

---

### ២. ដំណោះស្រាយបញ្ហា Bot នៅតែមិនឆ្លើយតប (No Response)

ការដែលផ្ញើ `/start` ឬ Ticker ទៅហើយ Bot នៅតែស្ងាត់ឈឹង[cite: 13] គឺមកពី ** Render Start Command រត់តែ Streamlit តែមួយមុខ (ភ្លេចរត់ `bot.py`)** ឬ **`BOT_TOKEN` ក្នុង Render Environment Variables មិនទាន់ត្រូវ**[cite: 2]។

#### ជំហានទី ១៖ ពិនិត្យ Start Command លើ Render Dashboard
1. ចូលទៅ **Render Dashboard** -> ចុចលើ Service របស់អ្នក -> **Settings**[cite: 2]
2. ត្រង់ប្រអប់ **Start Command** ត្រូវតែដាក់កូដនេះដាច់ខាត (ដើម្បីឱ្យវាដំណើរការទាំង Bot និង Dashboard ព្រមគ្នា)៖
   ```bash
   python stock_bot.py & streamlit run webdashboard.py --server.port $PORT --server.address 0.0.0.0
