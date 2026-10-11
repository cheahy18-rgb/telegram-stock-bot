import os
import logging
from fastapi import FastAPI, Request
import telebot
from dotenv import load_dotenv

load_dotenv()

# Setup Structured Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # ឧ. https://your-render-app.onrender.com

bot = telebot.TeleBot(BOT_TOKEN)
app = FastAPI()

# នាំយក Handlers មកភ្ជាប់
from handlers.commands import register_handlers
register_handlers(bot)

@app.post("/webhook")
async def receive_telegram_webhook(request: Request):
    try:
        json_str = await request.json()
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}

# ៥. Health Check Endpoint សម្រាប់ Render & UptimeRobot
@app.get("/healthz")
def health_check():
    return {"status": "healthy", "service": "telegram-stock-bot"}

@app.on_event("startup")
def on_startup():
    if WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"Webhook successfully set to {WEBHOOK_URL}/webhook")
    else:
        logger.warning("WEBHOOK_URL is not set! Bot may not receive updates.")