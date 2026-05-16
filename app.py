import os
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

# إعداد الـ Logging لمتابعة الأداء في Render بدقة
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. إعداد السيرفر الوهمي لمنصة Render
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running smoothly.")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

# 2. جلب المتغيرات السرية
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# 3. إعداد عميل جيميناي
ai_client = genai.Client(api_key=GEMINI_KEY)

# قائمة النماذج المتاحة للتجربة بالترتيب حسب الأحدث والأكثر استقراراً
AVAILABLE_MODELS = [
    'gemini-2.5-flash',
    'gemini-1.5-flash',
    'gemini-2.5-pro',
    'gemini-1.5-pro'
]

# متغير عالمي لحفظ النموذج الذي نجح الاتصال به لتجنب إعادة الحلقة في كل رسالة
WORKING_MODEL = None

def ask_gemini_with_fallback(text: str) -> str:
    global WORKING_MODEL
    
    # إذا كان هناك نموذج تم اعتماده بنجاح سابقاً، جربه أولاً
    if WORKING_MODEL:
        try:
            response = ai_client.models.generate_content(model=WORKING_MODEL, contents=text)
            return response.text
        except Exception as e:
            logger.warning(f"النموذج المعتمد {WORKING_MODEL} فشل الآن. سأعيد فحص القائمة. الخطأ: {e}")
            WORKING_MODEL = None

    # حلقة التراجع (Fallback Loop) لتجربة النماذج المتاحة بالترتيب
    collected_errors = []
    for model_name in AVAILABLE_MODELS:
        try:
            logger.info(f"جاري محاولة الاتصال بالنموذج: {model_name}")
            response = ai_client.models.generate_content(model=model_name, contents=text)
            
            # إذا نجح الاتصال، احفظ النموذج للاستخدام المستقبلي واخرج من الحلقة
            WORKING_MODEL = model_name
            logger.info(f"تم بنجاح اعتماد النموذج المستقر: {model_name}")
            return response.text
        except Exception as e:
            collected_errors.append(f"{model_name}: {str(e)}")
            continue
    
    # في حال فشلت جميع النماذج في القائمة
    raise Exception("فشلت جميع النماذج المتاحة في الاستجابة. تفاصيل الأخطاء:\n" + "\n".join(collected_errors))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! تم تفعيل نظام الفحص الذاتي للنماذج بنجاح. أرسل رسالتك الآن وسأقوم بالرد فوراً.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        # استدعاء الدالة ذاتية الإصلاح
        bot_response = ask_gemini_with_fallback(user_text)
        await update.message.reply_text(bot_response)
    except Exception as e:
        await update.message.reply_text(f"خطأ في الاتصال بالذكاء الاصطناعي:\n{str(e)}")

def main():
    # تشغيل السيرفر المساعد في الخلفية
    threading.Thread(target=run_dummy_server, daemon=True).start()

    # بناء تطبيق تليجرام
    application = Application.builder().token(TOKEN).build()

    # ربط الأوامر والرسائل بالدوال الخاصة بها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # بدء تشغيل البوت واستقبال البيانات
    logger.info("جاري بدء تشغيل تطبيق تليجرام...")
    application.run_polling()

if __name__ == "__main__":
    main()
