import os
import logging
from fastapi import FastAPI, Request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yfinance as yf
from dotenv import load_dotenv
from db import add_alert

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://telegram-stock-bot-8j9u.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = FastAPI()

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 **ជម្រាបសួរ! ខ្ញុំជា Stock Analyzer Bot**\n\n"
        "📈 **របៀបប្រើប្រាស់៖**\n"
        "- វាយបញ្ចូល Stock Ticker (ឧ. `AAPL`, `PLTR`, `AMD`)"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['alert'])
def set_alert_command(message):
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "⚠️ សូមផ្ញើតាមទម្រង់៖ `/alert <TICKER> <TARGET_PRICE>`", parse_mode="Markdown")
            return
        
        ticker = parts[1].upper()
        target_price = float(parts[2])
        stock = yf.Ticker(ticker)
        current_price = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        
        success = add_alert(message.chat.id, ticker, target_price, current_price)
        if success:
            bot.reply_to(message, f"✅ Alert set for **{ticker}** at **${target_price:.2f}**", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ មានបញ្ហាក្នុងการរក្សាទុក Alert!")
    except Exception as e:
        bot.reply_to(message, "⚠️ មានបញ្ហាក្នុងការរក្សាទុក!")

@bot.message_handler(func=lambda message: True)
def handle_stock_ticker(message):
    try:
        ticker = message.text.strip().upper()
        if ticker.startswith('/'): return

        stock = yf.Ticker(ticker)
        price = getattr(stock.fast_info, 'last_price', None)
        
        if not price:
            bot.reply_to(message, f"❌ រកមិនឃើញទិន្នន័យ Stock សម្រាប់ `{ticker}` ទេ!", parse_mode="Markdown")
            return

        markup = InlineKeyboardMarkup(row_width=2)
        btn_info = InlineKeyboardButton("🏢 ព័ត៌មានក្រុមហ៊ុន", callback_data=f"info_{ticker}")
        btn_graph = InlineKeyboardButton("📊 មើល Graph", callback_data=f"graph_{ticker}")
        markup.add(btn_info, btn_graph)

        bot.reply_to(
            message,
            f"📈 **Stock Ticker: {ticker}**\n💵 តម្លៃបច្ចុប្បន្ន៖ **${price:.2f}**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error: {e}")

@app.post("/webhook")
async def receive_telegram_webhook(request: Request):
    json_str = await request.json()
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return {"status": "ok"}

@app.get("/healthz")
def health_check():
    return {"status": "healthy", "service": "telegram-stock-bot"}

@app.on_event("startup")
def on_startup():
    if WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
