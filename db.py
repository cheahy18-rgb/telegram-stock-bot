import os
import logging
from supabase import Client, create_client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

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
        logger.error(f"Database Insert Error: {e}")
        return False

def get_alerts():
    try:
        res = supabase.table("alerts").select("*").execute()
        return res.data
    except Exception as e:
        logger.error(f"Database Fetch Error: {e}")
        return []

def delete_alert(alert_id):
    try:
        supabase.table("alerts").delete().eq("id", alert_id).execute()
        return True
    except Exception as e:
        logger.error(f"Database Delete Error: {e}")
        return False

def update_alert_current_price(alert_id, new_price):
    try:
        supabase.table("alerts").update({"current_price": float(new_price)}).eq("id", alert_id).execute()
    except Exception as e:
        logger.error(f"Database Update Error: {e}")