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
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://your-streamlit-app.onrender.com")

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
    img_bytes = fig.to_image(format="png")
    return io.BytesIO(img_bytes)

# ==========================================
# ៤. Telegram Bot Handlers
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 **ជម្រាបសួរ! ខ្ញុំជា Stock Analyzer Bot**\n\n"
        "📈 **របៀបប្រើប្រាស់៖**\n"
        "- វាយបញ្ចូល Stock Ticker (ឧ. `PLTR`, `AAPL`, `NVDA`)\n"
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
            # កែប្រែត្រង់នេះដោយប្រើ | ជំនួស \vert{} ការពារ SyntaxError
            bot.reply_to(
                message, 
                f"✅ បានកំណត់ Alert សម្រាប់ **{ticker}** ត្រឹម **${target_price:.2f}**\n"
                # ✅ ត្រូវ (ដូរទៅជាសញ្ញា | )
                f"💵 តម្លៃបច្ចុប្បន្ន៖ **${current_price:.2f}** | Fair Value: **${fair_value:.2f}**",
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
        btn_web = InlineKeyboardButton("🌐 Web Dashboard", url=DASHBOARD_URL)
        
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
        bot.send_message(chat_id, f"⏳ កំពុងបង្កើត Graph សម្រាប់ `{ticker}`...", parse_mode="Markdown")
        img_stream = generate_chart_image(ticker)
        if img_stream:
            bot.send_photo(chat_id, photo=img_stream, caption=f"📊 1-Year Candlestick Chart សម្រាប់ **{ticker}**", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, f"❌ មិនអាចទាញយក Graph សម្រាប់ `{ticker}` បានទេ!")

    elif data.startswith("alert_"):
        ticker = data.split("_")[1]
        stock = yf.Ticker(ticker)
        curr_p = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        sug_p = round(curr_p * 1.1, 2)
        
        msg = (
            f"🔔 **របៀបកំណត់ Price Alert សម្រាប់ {ticker}**\n\n"
            f"សូម វាយបញ្ជា៖\n"
            f"`/alert {ticker} {sug_p}`\n\n"
            f"*(ចំណាំ៖ Chy អាចប្តូរលេខ `{sug_p}` ទៅជាតម្លៃដែលចង់ឱ្យ Alert បាន)*"
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
    
    # លុប Pending Webhooks ចាស់ៗចោលមុនរត់ Polling
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Webhook note: {e}")

    def run_polling_safe():
        while True:
            try:
                bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)
            except Exception as e:
                print(f"Polling Exception: {e}")
                time.sleep(5)

    threading.Thread(target=run_polling_safe, daemon=True).start()

if "alert_checker_started" not in st.session_state:
    st.session_state["alert_checker_started"] = True
    threading.Thread(target=check_price_alerts, daemon=True).start()

# --- UI Interface Streamlit ---
st.set_page_config(page_title="Stock Analytics Dashboard", page_icon="📈", layout="wide")

st.sidebar.title("🔍 Stock Search")
selected_ticker = st.sidebar.text_input("បញ្ចូល Ticker:", value="PLTR").upper().strip()

st.title("📈 Stock Analytics & Price Alert Dashboard")

if selected_ticker:
    try:
        stock = yf.Ticker(selected_ticker)
        info = stock.info
        curr_p = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        
        target_sell = info.get('targetMeanPrice') or (curr_p * 1.2 if curr_p else 0)
        fair_val = target_sell * 0.833
        
        st.subheader(f"🏢 {info.get('longName', selected_ticker)}")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Current Price", f"${curr_p:.2f}")
        m2.metric("Target Sell", f"${target_sell:.2f}")
        m3.metric("Fair Value", f"${fair_val:.2f}")
        m4.metric("P/E Ratio", f"{info.get('trailingPE', 0):.2f}" if info.get('trailingPE') else "N/A")

        col_graph, col_alert = st.columns([2, 1])

        with col_graph:
            hist = stock.history(period="1y")
            if not hist.empty:
                fig = go.Figure(data=[go.Candlestick(
                    x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close']
                )])
                fig.update_layout(template="plotly_dark", height=400, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

        with col_alert:
            st.subheader("🔔 កំណត់ Price Alert")
            web_chat_id = st.text_input("Telegram Chat ID:", value="", placeholder="ឧ. 123456789")
            target_alert_price = st.number_input("Target Price ($):", value=float(round(curr_p * 1.1, 2)))
            
            if st.button("💾 រក្សាទុក Alert", type="primary", use_container_width=True):
                if not web_chat_id:
                    st.error("⚠️ សូមបញ្ចូល Telegram Chat ID!")
                else:
                    if add_alert(web_chat_id, selected_ticker, target_alert_price, curr_p, fair_val):
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
    st.dataframe(df_alerts[display_cols], use_container_width=True)
else:
    st.info("មិនទាន់មាន Alert កំពុងសកម្មឡើយ។")
