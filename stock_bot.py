import os
from dotenv import load_dotenv
import telebot
from supabase import create_client, Client

load_dotenv()

# ១. ទាញយក Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not BOT_TOKEN:
    raise ValueError("❌ រកមិនឃើញ BOT_TOKEN! សូមពិនិត្យ Environment Variables លើ Render")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ រកមិនឃើញ SUPABASE_URL ឬ SUPABASE_KEY!")

# បង្កើត Client សម្រាប់ Telegram Bot និង Supabase
bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ២. Function សម្រាប់គ្រប់គ្រងទិន្នន័យលើ Supabase Table (ឧទាហរណ៍ Table ឈ្មោះ 'alerts')
def add_alert(chat_id, ticker, target_price):
    try:
        data = {
            "chat_id": str(chat_id),
            "ticker": ticker.upper(),
            "target_price": float(target_price)
        }
        response = supabase.table("alerts").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error adding alert: {e}")
        return False

def get_alerts():
    try:
        response = supabase.table("alerts").select("*").execute()
        return response.data
    except Exception as e:
        print(f"Error fetching alerts: {e}")
        return []
