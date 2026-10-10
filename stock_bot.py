import os
import time
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

# ==========================================
# ១. Setup Environment Variables
# ==========================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://telegram-stock-bot-8j9u.onrender.com")

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Missing Environment Variables!")

bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# ២. Supabase Database Helpers
# ==========================================
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
        print(f"❌ Insert Error: {e}")
        return False

def get_alerts():
    try:
        res = supabase.table("alerts").select("*").execute()
        return res.data
    except Exception as e:
        print(f"❌ Fetch Error: {e}")
        return []

def delete_alert(alert_id):
    try:
        supabase.table("alerts").delete().eq("id", alert_id).execute()
        return True
    except Exception as e:
        print(f"❌ Delete Error: {e}")
        return False

def update_alert_current_price(alert_id, new_price):
    try:
        supabase.table("alerts").update({"current_price": float(new_price)}).eq("id", alert_id).execute()
    except Exception as e:
        print(f"❌ Update Error: {e}")

# ==========================================
# ៣. Telegram Bot Message Handlers
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 **ជម្រាបសួរ! ខ្ញុំជា Stock Analyzer Bot**\n\n"
        "📈 **របៀបប្រើប្រាស់៖**\n"
        "- វាយបញ្ចូល Stock Ticker (ឧ. `AAPL`, `PLTR`, `META`)\n"
        "- ប្រើប្រាស់ Inline Keyboard ដើម្បីមើលព័ត៌មាន, Earning, Graph ឬបើក Web Dashboard"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['alert'])
def set_alert_command(message):
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "⚠️ សូមផ្ញើតាមទម្រង់៖ `/alert <TICKER> <TARGET_PRICE>`\nឧទាហរណ៍៖ `/alert AAPL 230`", parse_mode="Markdown")
            return
        
        ticker = parts[1].upper()
        target_price = float(parts[2])
        stock = yf.Ticker(ticker)
        current_price = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        target_sell = stock.info.get('targetMeanPrice') or (current_price * 1.2 if current_price else target_price)
        fair_value = target_sell * 0.833
        
        success = add_alert(message.chat.id, ticker, target_price, current_price, fair_value)
        if success:
            bot.reply_to(
                message, 
                f"✅ បានកំណត់ Alert សម្រាប់ **{ticker}** ត្រឹម **${target_price:.2f}**\n"
                f"💵 តម្លៃបច្ចុប្បន្ន៖ **${current_price:.2f}** | Fair Value: **${fair_value:.2f}**"
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, "❌ មានបញ្ហាក្នុងการរក្សាទុក Alert!")
    except Exception as e:
        bot.reply_to(message, "⚠️ មានបញ្ហាក្នុងការរក្សាទុក! សូមពិនិត្យមើល Ticker ឬលេខតម្លៃ។")

@bot.message_handler(func=lambda message: True)
def handle_stock_ticker(message):
    try:
        ticker = message.text.strip().upper()
        if ticker.startswith('/'): return

        stock = yf.Ticker(ticker)
        fast_info = stock.fast_info
        price = getattr(fast_info, 'last_price', None)
        
        if not price:
            bot.reply_to(message, f"❌ រកមិនឃើញទិន្នន័យ Stock សម្រាប់ `{ticker}` ទេ!", parse_mode="Markdown")
            return

        markup = InlineKeyboardMarkup(row_width=2)
        btn_info = InlineKeyboardButton("🏢 ព័ត៌មានក្រុមហ៊ុន", callback_data=f"info_{ticker}")
        btn_graph = InlineKeyboardButton("📊 មើល Graph", callback_data=f"graph_{ticker}")
        btn_earning = InlineKeyboardButton("💰 Earning", callback_data=f"earning_{ticker}")
        btn_alert = InlineKeyboardButton("🔔 កំណត់ Price Alert", callback_data=f"alert_{ticker}")
        
        user_chat_id = message.chat.id
        dynamic_dashboard_url = f"{DASHBOARD_URL}?ticker={ticker}&chat_id={user_chat_id}"
        btn_web = InlineKeyboardButton("🌐 Web Dashboard", url=dynamic_dashboard_url)
        
        markup.add(btn_info, btn_graph, btn_earning, btn_alert, btn_web)

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

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    data = call.data
    chat_id = call.message.chat.id

    if data.startswith("info_"):
        ticker = data.split("_")[1]
        stock = yf.Ticker(ticker)
        info = stock.info
        current_price = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        
        target_sell = info.get('targetMeanPrice') or (current_price * 1.2)
        fair_value = target_sell * 0.833
        status = "🟢 Under-valued" if current_price < fair_value else ("🔴 Over-valued" if current_price > target_sell else "🟡 Fairly-valued")
        
        response_msg = (
            f"🏢 **[ព័ត៌មានក្រុមហ៊ុន៖ {info.get('longName', ticker)}](https://finance.yahoo.com/quote/{ticker})**\n\n"
            f"🏭 **វិស័យ៖** {info.get('sector', 'N/A')}\n"
            f"💵 **តម្លៃបច្ចុប្បន្ន៖** ${current_price:.2f}\n"
            f"📈 **P/E Ratio:** {info.get('trailingPE', 0):.2f} | **EPS:** ${info.get('trailingEps', 0):.2f}\n\n"
            f"-----------------------------------\n"
            f"🎯 **Valuation**\n"
            f"-----------------------------------\n"
            f"💡 **Fair Value៖** ${fair_value:.2f}\n"
            f"📊 **ស្ថានភាព៖** {status}\n"
            f"🚀 **Target Sell៖** ${target_sell:.2f}"
        )
        bot.send_message(chat_id, response_msg, parse_mode="Markdown", disable_web_page_preview=True)

    elif data.startswith("graph_"):
        ticker = data.split("_")[1]
        tv_link = f"https://www.tradingview.com/chart/?symbol={ticker}"
        dash_link = f"{DASHBOARD_URL}?ticker={ticker}&chat_id={chat_id}"
        
        msg = (
            f"📊 **Interactive Chart សម្រាប់ {ticker}**\n\n"
            f"🔗 [មើលនៅលើ TradingView]({tv_link})\n"
            f"🌐 [មើលនៅលើ Web Dashboard]({dash_link})"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown", disable_web_page_preview=False)

    elif data.startswith("earning_"):
        ticker = data.split("_")[1]
        current_year = 2026
        
        markup = InlineKeyboardMarkup(row_width=2)
        btn_q1 = InlineKeyboardButton(f"Q1 {current_year}", callback_data=f"qtr_{ticker}_Q1_{current_year}")
        btn_q2 = InlineKeyboardButton(f"Q2 {current_year}", callback_data=f"qtr_{ticker}_Q2_{current_year}")
        btn_q3 = InlineKeyboardButton(f"Q3 {current_year}", callback_data=f"qtr_{ticker}_Q3_{current_year}")
        btn_q4 = InlineKeyboardButton(f"Q4 {current_year}", callback_data=f"qtr_{ticker}_Q4_{current_year}")
        markup.add(btn_q1, btn_q2, btn_q3, btn_q4)
        
        bot.send_message(
            chat_id, 
            f"📅 **Earnings Reports សម្រាប់ {ticker} (ឆ្នាំ {current_year})**\n\n👇 សូមជ្រើសរើសត្រីមាស (Quarter) ដែលចង់ពិនិត្យមើល៖", 
            reply_markup=markup, 
            parse_mode="Markdown"
        )

    elif data.startswith("qtr_"):
        parts = data.split("_")
        ticker = parts[1]
        quarter = parts[2]
        year = parts[3]
        
        try:
            stock = yf.Ticker(ticker)
            q_fin = stock.quarterly_financials
            
            if q_fin is not None and not q_fin.empty:
                matched_col = q_fin.columns[0]
                date_str = str(matched_col)[:10]

                def get_val(row_name):
                    try:
                        if row_name in q_fin.index:
                            val = q_fin.loc[row_name, matched_col]
                            if pd.notna(val):
                                return f"${val / 1e9:.2f}B" if abs(val) >= 1e9 else f"${val / 1e6:.2f}M"
                    except Exception:
                        pass
                    return "N/A"

                revenue = get_val("Total Revenue")
                net_income = get_val("Net Income")
                op_income = get_val("Operating Income")

                response_msg = (
                    f"📊 **{ticker} Earnings Overview ({quarter} {year})**\n"
                    f"📅 *របាយការណ៍កាលបរិច្ឆេទ៖ {date_str}*\n\n"
                    f"💵 **ចំណូលសរុប (Revenue):** {revenue}\n"
                    f"📈 **ប្រាក់ចំណេញសុទ្ធ (Net Income):** {net_income}\n"
                    f"⚙️ **ចំណេញពីប្រតិបត្តិការ (Op. Income):** {op_income}\n\n"
                    f"🔗 [មើលលម្អិតលើ Yahoo Finance](https://finance.yahoo.com/quote/{ticker}/financials)"
                )
            else:
                response_msg = f"⚠️ រកមិនឃើញទិន្នន័យ Earning សម្រាប់ **{ticker}** ទេ!"
                
            bot.send_message(chat_id, response_msg, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception as e:
            print(f"Earning Error Details: {e}")
            bot.send_message(chat_id, f"❌ មានបញ្ហាក្នុងការទាញយកទិន្នន័យ Earning សម្រាប់ {ticker}។")

    elif data.startswith("alert_"):
        ticker = data.split("_")[1]
        stock = yf.Ticker(ticker)
        curr_p = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        sug_p = round(curr_p * 1.1, 2)
        
        markup = InlineKeyboardMarkup(row_width=2)
        btn_preset1 = InlineKeyboardButton(f"🎯 +10% (${sug_p})", callback_data=f"setalert_{ticker}_{sug_p}")
        btn_preset2 = InlineKeyboardButton(f"🎯 Web Dashboard", url=f"{DASHBOARD_URL}?ticker={ticker}&chat_id={chat_id}")
        markup.add(btn_preset1, btn_preset2)

        msg = (
            f"🔔 **កំណត់ Price Alert សម្រាប់ {ticker}**\n\n"
            f"💵 តម្លៃបច្ចុប្បន្ន៖ **${curr_p:.2f}**\n"
            f"👇 លោកអ្នកអាចចុចប៊ូតុងខាងក្រោមដើម្បីកំណត់ Target (+10%) ភ្លាមៗ ឬវាយបញ្ជា៖\n"
            f"`/alert {ticker} {sug_p}`"
        )
        bot.send_message(chat_id, msg, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("setalert_"):
        parts = data.split("_")
        ticker = parts[1]
        target_price = float(parts[2])
        
        stock = yf.Ticker(ticker)
        curr_p = getattr(stock.fast_info, 'last_price', 0.0) or 0.0
        target_sell = stock.info.get('targetMeanPrice') or (curr_p * 1.2)
        fair_value = target_sell * 0.833
        
        if add_alert(chat_id, ticker, target_price, curr_p, fair_value):
            bot.send_message(
                chat_id, 
                f"✅ បានកំណត់ Alert ស្វ័យប្រវត្តិសម្រាប់ **{ticker}** ត្រឹម **${target_price:.2f}**!", 
                parse_mode="Markdown"
            )
        else:
            bot.send_message(chat_id, "❌ មានបញ្ហាក្នុងការរក្សាទុក Alert!")

    bot.answer_callback_query(call.id)

# ==========================================
# ៤. Background Price Alert Checker Function
# ==========================================
def check_price_alerts():
    while True:
        try:
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
                            fv_info = f"\n💡 តម្លៃ Fair Value៖ **${float(fair_val):.2f}**" if fair_val else ""
                            alert_msg = (
                                f"🚨 **PRICE ALERT TRIGGERED!** 🚨\n\n"
                                f"📈 **{ticker}** បានឡើងដល់ Target ហើយ!\n"
                                f"💵 តម្លៃបច្ចុប្បន្ន៖ **${current_price:.2f}**\n"
                                f"🎯 តម្លៃ Target៖ **${target_price:.2f}**"
                                f"{fv_info}"
                            )
                            bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                            delete_alert(alert_id)
                except Exception as inner_e:
                    print(f"Error checking alert item: {inner_e}")
        except Exception as e:
            print(f"Alert Check Loop Error: {e}")
        time.sleep(300)

# ==========================================
# ៥. Main Execution Loop
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=check_price_alerts, daemon=True).start()

    print("🤖 Starting Telegram Bot...")

    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"Webhook reset note: {e}")

    while True:
        try:
            print("🟢 Bot is listening for messages...")
            bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except Exception as e:
            print(f"⚠️ Polling Error: {e}")
            time.sleep(3)
