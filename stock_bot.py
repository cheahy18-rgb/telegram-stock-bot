import os
import time
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yfinance as yf
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://telegram-stock-bot-8j9u.onrender.com/")

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Missing Environment Variables!")

bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Supabase Database Functions ---
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
        print(f"❌ Insert Error: {e}")
        return False

def get_alerts():
    try:
        res = supabase.table("alerts").select("*").execute()
        return res.data
    except Exception as e:
        print(f"❌ Fetch Error: {e}")
        return []

def delete_alert(alert_id):
    try:
        supabase.table("alerts").delete().eq("id", alert_id).execute()
        return True
    except Exception as e:
        print(f"❌ Delete Error: {e}")
        return False

def update_alert_current_price(alert_id, new_price):
    try:
        supabase.table("alerts").update({"current_price": float(new_price)}).eq("id", alert_id).execute()
    except Exception as e:
        print(f"❌ Update Error: {e}")

# --- Bot Handlers ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 **ជម្រាបសួរ! ខ្ញុំជា Stock Analyzer Bot**\n\n"
        "📈 **របៀបប្រើប្រាស់៖**\n"
        "- វាយបញ្ចូល Stock Ticker (ឧ. `AAPL`, `PLTR`, `SOUN`)\n"
        "- ប្រើប្រាស់ Inline Keyboard ដើម្បីមើលព័ត៌មាន ឬបើក Web Dashboard"
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
        btn_alert = InlineKeyboardButton("🔔 កំណត់ Price Alert", callback_data=f"alert_{ticker}")
        
        dynamic_dashboard_url = f"{DASHBOARD_URL}?ticker={ticker}"
        btn_web = InlineKeyboardButton("🌐 Web Dashboard", url=dynamic_dashboard_url)
        
        markup.add(btn_info, btn_alert, btn_web)

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

# --- Background Price Alert Checker ---
def check_price_alerts():
    while True:
        try:
            alerts = get_alerts()
            for alert in alerts:
                try:
                    alert_id, chat_id, ticker = alert.get('id'), alert.get('chat_id'), alert.get('ticker')
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
                    print(f"Error checking alert item: {inner_e}")
        except Exception as e:
            print(f"Alert Check Loop Error: {e}")
        time.sleep(300)

# --- Entry Point ---
if __name__ == "__main__":
    threading.Thread(target=check_price_alerts, daemon=True).start()
    
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Webhook note: {e}")
        
    print("🟢 Bot is starting...")
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"⚠️ Polling Error: {e}")
            time.sleep(5)
