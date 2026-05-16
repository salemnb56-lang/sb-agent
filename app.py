import os
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

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

# 3. إعداد عميل جيميناي بالصيغة الصحيحة للمكتبة الجديدة
ai_client = genai.Client(api_key=GEMINI_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! أنا جاهز ومستقر الآن على السيرفر الجديد. كيف يمكنني مساعدتك؟")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        # استخدام النموذج الموصى به وبصيغة متوافقة مباشرة
        response = ai_client.models.generate_content(
            model='gemini-1.5-flash',
            contents=user_text
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء معالجة الذكاء الاصطناعي: {str(e)}")

def main():
    # تشغيل السيرفر الوهمي في خلفية النظام
    threading.Thread(target=run_dummy_server, daemon=True).start()

    # بناء تطبيق تليجرام
    application = Application.builder().token(TOKEN).build()

    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # بدء الاستماع للرسائل
    application.run_polling()

if __name__ == "__main__":
    main()
