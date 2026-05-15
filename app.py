import os
import logging
import threading
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from google import genai

# إعداد السجلات لمراقبة الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(message)s', level=logging.INFO)

# دالة لتشغيل سيرفر وهمي في الخلفية لإرضاء منصة Hugging Face ومنع إغلاق البوت
def run_dummy_server():
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"SB Agent is Online and Running!")
            
    try:
        with TCPServer(("0.0.0.0", 7860), Handler) as httpd:
            logging.info("Dummy server started on port 7860")
            httpd.serve_forever()
    except Exception as e:
        logging.error(f"Server error: {e}")

# تشغيل السيرفر الوهمي في مسار منفصل (Thread) قبل بدء البوت
threading.Thread(target=run_dummy_server, daemon=True).start()

# إعداد عميل جيميناي بالمكتبة الحديثة لعام 2026
# تقرأ المكتبة تلقائياً المفتاح المسمى GEMINI_API_KEY من إعدادات الـ Secrets
client = genai.Client()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    chat_id = update.message.chat_id
    
    # إرسال حركة "جاري الكتابة..." في تليجرام
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        # صياغة التوجيه للوكيل
        prompt = f"أنت وكيل ذكاء اصطناعي خبير تقني ومبرمج محترف. اسمك SB Agent. أجب دائماً باللغة العربية بوضوح واختصار مفيد. المستخدم يطلب منك: {user_text}"
        
        # استدعاء النموذج الحديث
        response = client.models.generate_content(
            model='gemini-1.5-pro',
            contents=prompt,
        )
        
        # الرد على المستخدم
        await update.message.reply_text(response.text)

    except Exception as e:
        logging.error(f"Error while generating content: {e}")
        await update.message.reply_text(f"عذراً، واجهت مشكلة في معالجة طلبك: {str(e)}")

if __name__ == '__main__':
    # الحصول على التوكن وتشغيل البوت
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logging.error("TELEGRAM_TOKEN is missing!")
    else:
        application = ApplicationBuilder().token(token).build()
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        logging.info("Starting Telegram Bot application...")
        application.run_polling()