import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# យក Redis URL ពី Environment Variable (Render ផ្តល់ជូន ឬប្រើ localhost ពេលរត់ក្នុងเครื่อง)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "stock_bot_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# ឧទាហរណ៍ Task សម្រាប់ដំណើរការផ្ទុកទិន្នន័យ Background
@celery_app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
