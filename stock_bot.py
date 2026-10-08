import os
import time
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yfinance as yf
# នាំចូល Supabase helper functions របស់អ្នក (ឧទាហរណ៍៖ get_alerts, update_alert_current_price, delete_alert)
# from database import get_alerts, update_alert_current_price, delete_alert

# ==========================================
# 1. Configuration & Initializations
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://your-streamlit-app.render.com")

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 2. Telegram Bot Command Handlers
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 **សូមស្វាគមន៍មកកាន់ Stock Analysis Bot!**\n\n"
        "សូមផ្ញើឈ្មោះ Ticker នៃភាគហ៊ុន (ឧទាហរណ៍៖ `AAPL`, `CSCO`, `NET`) "
        "ដើម្បីមើលព័ត៌មាន និងកំណត់ Price Alert។"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_stock_ticker(message):
    try:
        ticker = message.text.strip().upper()
        if ticker.startswith('/'): 
            return

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

# ==========================================
# 3. Alert Response Helper (Line 121 Fix)
# ==========================================
def send_alert_success_message(message, ticker, target_price, current_price, fair_value):
    # កែប្រែក្បៀស (comma) ត្រង់បន្ទាត់ reply_to ការពារ SyntaxError[cite: 8]
    bot.reply_to(
        message,
        f"✅ បានកំណត់ Alert សម្រាប់ **{ticker}** ត្រឹម **${target_price:.2f}**\n"
        f"💵 តម្លៃបច្ចុប្បន្ន៖ **${current_price:.2f}** \vert{} Fair Value: **${fair_value:.2f}**",
        parse_mode="Markdown"
    )

# ==========================================
# 4. Safe Background Worker Thread
# ==========================================
def check_price_alerts():
    while True:
        try:
            # ជំនួសដោយ function ទាញយក alerts ពី Supabase របស់អ្នក
            alerts = [] # get_alerts()
            for alert in alerts:
                try:
                    alert_id = alert.get('id')
                    chat_id = alert.get('chat_id')
                    ticker = alert.get('ticker')
                    target_price = float(alert.get('target_price', 0))
                    fair_val = alert.get('fair_value')
                    
                    if not ticker or not target_price: 
                        continue
                        
                    stock = yf.Ticker(ticker)
                    current_price = getattr(stock.fast_info, 'last_price', None)
                    
                    if current_price:
                        # update_alert_current_price(alert_id, current_price)
                        
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
                            # delete_alert(alert_id)
                except Exception as inner_e:
                    print(f"Error processing alert for {alert}: {inner_e}")
        except Exception as e:
            print(f"Alert Check Loop Error: {e}")
        
        time.sleep(300) # រង់ចាំ 5 នាទីត្រួតពិនិត្យម្តង

# ==========================================
# 5. Main Execution (Safe Polling)
# ==========================================
if __name__ == "__main__":
    # ចាប់ផ្តើម Background Thread សម្រាប់ត្រួតពិនិត្យ Alert
    alert_thread = threading.Thread(target=check_price_alerts, daemon=True)
    alert_thread.start()

    print("🤖 Bot is starting...")
    
    # លុប Pending Webhook/Updates ចាស់ៗចោល ការពារការគាំង
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Webhook remove note: {e}")

    # Polling Loop ជាមួយការការពារ Crash
    while True:
        try:
            print("🟢 Bot polling started successfully!")
            bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"⚠️ Polling Error occurred: {e}")
            time.sleep(5)  # រង់ចាំ ៥ វិនាទី រួចរត់ Polling ឡើងវិញដោយស្វ័យប្រវត្តិ
