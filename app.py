import os
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import logging
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

# إعداد الـ Logging لمراقبة السيرفر بدقة
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# سيرفر وهمي لتفادي إغلاق منصة Render (Port Binding)
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running smoothly.")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), DummyHandler)
        logger.info(f"السيرفر المساعد يعمل بنجاح على المنفذ: {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"فشل تشغيل السيرفر المساعد: {e}")

# جلب المتغيرات السرية من البيئة
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# تهيئة عميل جيميناي
try:
    ai_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
except Exception as e:
    logger.error(f"فشل تفعيل عميل جيميناي: {e}")
    ai_client = None

AVAILABLE_MODELS = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-2.5-pro', 'gemini-1.5-pro']
WORKING_MODEL = None

def ask_gemini_with_fallback(text: str) -> str:
    global WORKING_MODEL
    if not ai_client:
        return "خطأ: لم يتم تهيئة مفتاح جيميناي (GEMINI_API_KEY) في السيرفر."
        
    if WORKING_MODEL:
        try:
            response = ai_client.models.generate_content(model=WORKING_MODEL, contents=text)
            return response.text
        except Exception:
            WORKING_MODEL = None

    for model_name in AVAILABLE_MODELS:
        try:
            response = ai_client.models.generate_content(model=model_name, contents=text)
            WORKING_MODEL = model_name
            return response.text
        except Exception:
            continue
    raise Exception("جميع نماذج جيميناي فشلت في الاستجابة.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! البوت يعمل الآن بشكل مستقر ومحمي ضد التوقف.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    try:
        bot_response = ask_gemini_with_fallback(update.message.text)
        await update.message.reply_text(bot_response)
    except Exception as e:
        await update.message.reply_text(f"خطأ مؤقت في المعالجة:\n{str(e)}")

def main():
    # 1. التحقق من وجود التوكن
    if not TOKEN:
        logger.critical("خطأ حرج: متغير TELEGRAM_TOKEN غير موجود في إعدادات البيئة!")
        sys.exit(1)

    # 2. تشغيل السيرفر المساعد في الخلفية لتجاوز فحص المنافذ في Render
    threading.Thread(target=run_dummy_server, daemon=True).start()

    try:
        # 3. بناء تطبيق تليجرام وإعداد الأوامر
        application = Application.builder().token(TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("جاري بدء استعراض الرسائل من تليجرام (Polling)...")
        application.run_polling()
    except Exception as e:
        logger.critical(f"انهار التطبيق أثناء التشغيل بسبب: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
