import os
import json
import telebot
import yfinance as yf
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# 🔐 1. ទាញយក Environment Variables (ពី .env ពេល Local ឬពី Cloud Settings)
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ រកមិនឃើញ BOT_TOKEN! សូមពិនិត្យមើល File .env ឬ Environment Variables លើ Cloud។")

bot = telebot.TeleBot(BOT_TOKEN)
DB_FILE = "alerts.json"

# --- ២. ប្រព័ន្ធគ្រប់គ្រង Database (JSON File) ---
def load_alerts():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_alerts(alerts):
    with open(DB_FILE, "w") as f:
        json.dump(alerts, f, indent=4)

# --- ៣. អនុគមន៍គណនា Fair Value ---
def get_fair_value_info(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        
        name = info.get('longName') or info.get('shortName')
        if not name:
            return None

        current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
        pe_ratio = info.get('trailingPE', 0)
        forward_pe = info.get('forwardPE', 0)
        eps = info.get('trailingEps', 0)
        growth_rate = info.get('earningsGrowth') or 0.10
        
        if eps > 0 and pe_ratio > 0:
            target_pe = forward_pe if forward_pe > 0 else pe_ratio
            fair_value = eps * (1 + growth_rate) * target_pe
        else:
            book_value = info.get('bookValue', 0)
            fair_value = book_value * 1.5 if book_value > 0 else current_price

        return {
            "name": name,
            "current_price": current_price,
            "fair_value": fair_value,
            "pe_ratio": pe_ratio,
            "eps": eps
        }
    except Exception:
        return None

# --- ៤. BACKGROUND JOB: ពិនិត្យមើលតម្លៃភាគហ៊ុនជាទៀងទាត់ ---
def check_price_alerts():
    alerts = load_alerts()
    if not alerts:
        return

    print("🔍 កំពុងពិនិត្យមើល Price Alerts...")
    updated_alerts = alerts.copy()

    for chat_id, tickers in alerts.items():
        for ticker, data in list(tickers.items()):
            stock_data = get_fair_value_info(ticker)
            if not stock_data:
                continue

            current_p = stock_data["current_price"]
            fair_v = stock_data["fair_value"]

            if current_p <= fair_v:
                discount_percent = ((fair_v - current_p) / fair_v) * 100
                alert_msg = f"""
🚨 <b><u>PRICE ALERT! ភាគហ៊ុនធ្លាក់មកដល់ FAIR VALUE</u></b> 🚨

📈 <b>Ticker:</b> {ticker.upper()} ({stock_data['name']})
💵 <b>តម្លៃបច្ចុប្បន្ន:</b> <code>${current_p:.2f}</code>
💡 <b>Fair Value:</b> <code>${fair_v:.2f}</code>
📉 <b>ចុះថោកជាង Fair Value:</b> <code>-{discount_percent:.1f}%</code>

🎯 នេះជាឱកាសសមរម្យក្នុងការពិចារណាទិញ (Under-valued)!
"""
                try:
                    bot.send_message(chat_id, alert_msg, parse_mode='HTML')
                    del updated_alerts[chat_id][ticker]
                except Exception as e:
                    print(f"មិនអាចផ្ញើសារទៅ {chat_id}: {e}")

    save_alerts(updated_alerts)

scheduler = BackgroundScheduler()
scheduler.add_job(check_price_alerts, 'interval', hours=1)
scheduler.start()

# --- ៥. TELEGRAM BOT COMMANDS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
👋 **សួស្តី! ខ្ញុំជា Stock Analyzer & Price Alert Bot**

📌 **ពាក្យបញ្ជាដែលអ្នកអាចប្រើបាន៖**
• ផ្ញើឈ្មោះ Ticker (ឧ. `AAPL`, `NVDA`) ដើម្បទទួលបានការវិភាគ Fair Value
• `/setalert <TICKER>` - បង្កើត Alert ពេលតម្លៃធ្លាក់មកដល់ Fair Value
• `/myalerts` - មើលបញ្ជី Alert ទាំងអស់របស់អ្នក
• `/removealert <TICKER>` - លុប Alert ចេញ
"""
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['setalert'])
def set_alert(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ សូមបញ្ចូល Ticker! ឧទាហរណ៍៖ `/setalert AAPL`", parse_mode='Markdown')
        return

    ticker = args[1].strip().upper()
    chat_id = str(message.chat.id)

    bot.send_chat_action(message.chat.id, 'typing')
    stock_data = get_fair_value_info(ticker)

    if not stock_data:
        bot.reply_to(message, f"❌ រកមិនឃើញ Stock Ticker **'{ticker}'** ឡើយ។")
        return

    alerts = load_alerts()
    if chat_id not in alerts:
        alerts[chat_id] = {}

    alerts[chat_id][ticker] = {
        "fair_value": stock_data["fair_value"],
        "set_price": stock_data["current_price"]
    }
    save_alerts(alerts)

    msg = f"""
✅ <b>បានបង្កើត Alert ជោគជ័យ!</b>

📈 <b>Ticker:</b> {ticker}
💵 <b>តម្លៃបច្ចុប្បន្ន:</b> ${stock_data['current_price']:.2f}
💡 <b>Target Fair Value:</b> ${stock_data['fair_value']:.2f}

🔔 Bot នឹងផ្ញើសារប្រាប់អ្នកភ្លាមៗ ពេលតម្លៃធ្លាក់មកដល់ ឬទាបជាង <b>${stock_data['fair_value']:.2f}</b>!
"""
    bot.reply_to(message, msg, parse_mode='HTML')

@bot.message_handler(commands=['myalerts'])
def my_alerts(message):
    chat_id = str(message.chat.id)
    alerts = load_alerts()

    user_alerts = alerts.get(chat_id, {})
    if not user_alerts:
        bot.reply_to(message, "📭 អ្នកមិនទាន់មាន Price Alert ណាមួយឡើយ។")
        return

    msg = "🔔 <b><u>បញ្ជី Price Alert របស់អ្នក៖</u></b>\n\n"
    for ticker, info in user_alerts.items():
        msg += f"• <b>{ticker}</b> — Fair Value: <code>${info['fair_value']:.2f}</code>\n"
    
    msg += "\n💡 ប្រើ `/removealert <TICKER>` ប្រសិនបើចង់លុប Alert ចេញ។"
    bot.reply_to(message, msg, parse_mode='HTML')

@bot.message_handler(commands=['removealert'])
def remove_alert(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ សូមបញ្ចូល Ticker! ឧទាហរណ៍៖ `/removealert AAPL`", parse_mode='Markdown')
        return

    ticker = args[1].strip().upper()
    chat_id = str(message.chat.id)

    alerts = load_alerts()
    if chat_id in alerts and ticker in alerts[chat_id]:
        del alerts[chat_id][ticker]
        save_alerts(alerts)
        bot.reply_to(message, f"🗑️ បានលុប Price Alert សម្រាប់ **{ticker}** រួចរាល់។", parse_mode='Markdown')
    else:
        bot.reply_to(message, f"⚠️️ មិនឃើញមាន Alert សម្រាប់ **{ticker}** ក្នុងបញ្ជីរបស់អ្នកឡើយ។", parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def analyze(message):
    ticker = message.text.strip().upper()
    if ticker.startswith('/'):
        return

    bot.send_chat_action(message.chat.id, 'typing')
    stock_data = get_fair_value_info(ticker)
    
    if not stock_data:
        bot.reply_to(message, f"❌ រកមិនឃើញ Stock Ticker <b>'{ticker}'</b> ឡើយ។", parse_mode='HTML')
        return

    curr_p = stock_data["current_price"]
    fair_v = stock_data["fair_value"]
    status = "🟢 Under-valued" if curr_p < fair_v else "🔴 Over-valued"

    msg = f"""
📊 <b><u>របាយការណ៍វិភាគ៖ {ticker}</u></b>

🏢 <b>ក្រុមហ៊ុន៖</b> {stock_data['name']}
💵 <b>តម្លៃបច្ចុប្បន្ន៖</b> <code>${curr_p:.2f}</code>
💡 <b>តម្លៃសមរម្យ (Fair Value)៖</b> <code>${fair_v:.2f}</code>
លោកអ្នកគួរដឹង៖ {status}

🔔 ចង់ឱ្យ Bot ប្រាប់ដំណឹងពេលតម្លៃធ្លាក់ចុះដល់ Fair Value?
វាយ៖ `/setalert {ticker}`
"""
    bot.reply_to(message, msg, parse_mode='HTML')

print("🤖 Bot កំពុងដំណើរការដោយសុវត្ថិភាព...")
bot.infinity_polling()