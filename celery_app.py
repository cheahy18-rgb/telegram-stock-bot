import os
from celery import Celery
import yfinance as yf
import telebot
from dotenv import load_dotenv
from db import get_alerts, update_alert_current_price, delete_alert

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

bot = telebot.TeleBot(BOT_TOKEN)
celery_app = Celery("celery_app", broker=REDIS_URL, backend=REDIS_URL)

@celery_app.task(name="celery_app.check_price_alerts_task")
def check_price_alerts_task():
    alerts = get_alerts()
    for alert in alerts:
        try:
            alert_id = alert.get('id')
            chat_id = alert.get('chat_id')
            ticker = alert.get('ticker')
            target_price = float(alert.get('target_price', 0))
            
            stock = yf.Ticker(ticker)
            current_price = getattr(stock.fast_info, 'last_price', None)
            
            if current_price:
                update_alert_current_price(alert_id, current_price)
                if current_price >= target_price:
                    bot.send_message(chat_id, f"🚨 **PRICE ALERT!** {ticker} hit ${current_price:.2f}", parse_mode="Markdown")
                    delete_alert(alert_id)
        except Exception as e:
            print(f"Error: {e}")
