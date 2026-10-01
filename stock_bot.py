import os
import sqlite3
import telebot
import yfinance as yf
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

import os
import json
from dotenv import load_dotenv
import telebot

load_dotenv()

# ១. ទាញយក Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ រកមិនឃើញ BOT_TOKEN! សូមពិនិត្យមើល File .env ឬ Environment Variables លើ Cloud")

bot = telebot.TeleBot(BOT_TOKEN)

# ២. ប្រព័ន្ធគ្រប់គ្រង Database (JSON File)
DB_FILE = "alerts.json"

def load_alerts():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}
# --- ១. ប្រព័ន្ធគ្រប់គ្រង SQLite Database ---
def init_db():
    """បង្កើត Table Alerts ប្រសិនបើមិនទាន់មាន"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            fair_value REAL NOT NULL,
            set_price REAL NOT NULL,
            UNIQUE(chat_id, ticker)
        )
    ''')
    conn.commit()
    conn.close()

def add_alert(chat_id, ticker, fair_value, set_price):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO alerts (chat_id, ticker, fair_value, set_price)
        VALUES (?, ?, ?, ?)
    ''', (str(chat_id), ticker.upper(), fair_value, set_price))
    conn.commit()
    conn.close()

def get_all_alerts():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id, chat_id, ticker, fair_value FROM alerts')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_alerts(chat_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT ticker, fair_value FROM alerts WHERE chat_id = ?', (str(chat_id),))
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_alert(chat_id, ticker):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM alerts WHERE chat_id = ? AND ticker = ?', (str(chat_id), ticker.upper()))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count > 0

def delete_alert_by_id(alert_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM alerts WHERE id = ?', (alert_id,))
    conn.commit()
    conn.close()

# បង្កើត Database នៅពេលរត់ Program ដំបូង
init_db()

# --- ២. BACKGROUND JOB ពិនិត្យតម្លៃ ---
def check_price_alerts():
    alerts = get_all_alerts()
    if not alerts:
        return

    print("🔍 កំពុងពិនិត្យមើល Price Alerts ក្នុង SQLite Database...")
    for alert_id, chat_id, ticker, fair_value in alerts:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            current_p = info.get('currentPrice') or info.get('regularMarketPrice', 0)

            if current_p > 0 and current_p <= fair_value:
                discount_percent = ((fair_value - current_p) / fair_value) * 100
                alert_msg = f"""
🚨 <b><u>PRICE ALERT! ភាគហ៊ុនធ្លាក់មកដល់ FAIR VALUE</u></b> 🚨

📈 <b>Ticker:</b> {ticker}
💵 <b>តម្លៃបច្ចុប្បន្ន:</b> <code>${current_p:.2f}</code>
💡 <b>Fair Value:</b> <code>${fair_value:.2f}</code>
📉 <b>ចុះថោកជាង Fair Value:</b> <code>-{discount_percent:.1f}%</code>
"""
                bot.send_message(chat_id, alert_msg, parse_mode='HTML')
                delete_alert_by_id(alert_id) # លុបចេញបន្ទាប់ពីជូនដំណឹងរួច
        except Exception as e:
            print(f"Error checking {ticker}: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(check_price_alerts, 'interval', hours=1)
scheduler.start()

# --- ៣. TELEGRAM COMMANDS ---
@bot.message_handler(commands=['setalert'])
def set_alert_cmd(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ សូមបញ្ចូល Ticker! ឧទាហរណ៍៖ `/setalert AAPL`", parse_mode='Markdown')
        return

    ticker = args[1].strip().upper()
    chat_id = message.chat.id
    
    # គណនា Fair Value
    stock = yf.Ticker(ticker)
    info = stock.info
    current_p = info.get('currentPrice', 0)
    eps = info.get('trailingEps', 0)
    pe = info.get('trailingPE', 15)
    
    fair_v = eps * pe if eps > 0 else current_p
    
    add_alert(chat_id, ticker, fair_v, current_p)
    bot.reply_to(message, f"✅ បានរក្សាទុក Alert សម្រាប់ **{ticker}** ក្នុង SQLite ជោគជ័យ! (Fair Value: ${fair_v:.2f})", parse_mode='Markdown')

@bot.message_handler(commands=['myalerts'])
def my_alerts_cmd(message):
    alerts = get_user_alerts(message.chat.id)
    if not alerts:
        bot.reply_to(message, "📭 អ្នកមិនទាន់មាន Alert ណាមួយឡើយ។")
        return

    msg = "🔔 <b><u>បញ្ជី Price Alert របស់អ្នក៖</u></b>\n\n"
    for ticker, fair_v in alerts:
        msg += f"• <b>{ticker}</b> — Fair Value: <code>${fair_v:.2f}</code>\n"
    bot.reply_to(message, msg, parse_mode='HTML')

@bot.message_handler(commands=['removealert'])
def remove_alert_cmd(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ ឧទាហរណ៍៖ `/removealert AAPL`", parse_mode='Markdown')
        return

    ticker = args[1].strip().upper()
    if delete_alert(message.chat.id, ticker):
        bot.reply_to(message, f"🗑️ បានលុប **{ticker}** ចេញពី Database រួចរាល់។", parse_mode='Markdown')
    else:
        bot.reply_to(message, f"⚠️ រកមិនឃើញ **{ticker}** ក្នុងបញ្ជីរបស់អ្នកឡើយ។", parse_mode='Markdown')

bot.infinity_polling()
