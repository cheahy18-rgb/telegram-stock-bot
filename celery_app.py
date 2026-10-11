import os
from celery import Celery
import yfinance as yf
import telebot
from dotenv import load_dotenv
from services.db import get_alerts, update_alert_current_price, delete_alert

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

bot = telebot.TeleBot(BOT_TOKEN)

# កំណត់ Celery App ឱ្យស្គាល់ Module Path ត្រឹមត្រូវ
celery_app = Celery(
    "celery_app",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Optional configuration សម្រាប់ Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

@celery_app.task(name="tasks.celery_app.check_price_alerts_task")
def check_price_alerts_task():
    alerts = get_alerts()
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
                update_alert_current_price(alert_id, current_price)
                if current_price >= target_price:
                    fv_info = f"\n💡 Fair Value: **${float(fv_val):.2f}**" if fv_val else ""
                    alert_msg = (
                        f"🚨 **PRICE ALERT TRIGGERED!** 🚨\n\n"
                        f"📈 **{ticker}** hit target price!\n"
                        f"💵 Current Price: **${current_price:.2f}**\n"
                        f"🎯 Target Price: **${target_price:.2f}**"
                        f"{fv_info}"
                    )
                    bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                    delete_alert(alert_id)
        except Exception as e:
            print(f"Error in background alert task: {e}")
