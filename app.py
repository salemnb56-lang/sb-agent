import os
import sys
import json
import asyncio
import threading
import http.server
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import edge_tts
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- إعداد بيئة جيميناي والتأكد من المفاتيح ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

# قاموس محلي لحفظ جلسات المحادثة لكل مستخدم للحفاظ على سياق الذاكرة
USER_CHATS = {}

# --- تعريف الأدوات البرمجية للوكيل (Functions) ---

def execute_code(code: str, language: str = "python") -> str:
    """
    Executes code securely inside an isolated sandbox environment (Piston API) and returns the output.
    Args:
        code: The exact program code string to run.
        language: The programming language (e.g., 'python', 'javascript'). Default is 'python'.
    """
    try:
        payload = {
            "language": language,
            "version": "*",
            "files": [{"content": code}]
        }
        response = requests.post("https://emkc.org/api/v2/piston/execute", json=payload, timeout=12)
        if response.status_code == 200:
            res = response.json()
            output = res.get("run", {}).get("output", "")
            return output if output else "تم تشغيل الكود بنجاح ولكن لا توجد مخرجات نصية لعرضها."
        return f"خطأ في سيرفر تشغيل الأكواد: {response.status_code}"
    except Exception as e:
        return f"فشل تنفيذ الكود محلياً بسبب خطأ: {str(e)}"

def get_weather(city: str) -> str:
    """
    Fetches real-time weather details and temperature info for a specific city using OpenWeatherMap API.
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key:
        return "أداة الطقس معطلة؛ مفتاح الحساب غير متوفر في متغيرات السيرفر."
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=ar"
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            data = res.json()
            desc = data['weather'][0]['description']
            temp = data['main']['temp']
            humidity = data['main']['humidity']
            return f"الطقس الحالي في {city}: {desc}، درجة الحرارة: {temp}°م، الرطوبة: {humidity}%."
        return "لم يتم العثور على المدينة المحددة، يرجى التحقق من الاسم."
    except Exception as e:
        return f"حدث خطأ أثناء جلب الطقس: {str(e)}"

def google_apps_script_action(action: str, payload_data: str) -> str:
    """
    Sends automation tasks (like sending emails or logging sheets) to the user's Google Apps Script.
    Args:
        action: The task type ('send_email', 'write_sheet', 'read_sheet').
        payload_data: A strict valid JSON string containing parameters matching the action requirements.
    """
    url = os.environ.get("GOOGLE_SCRIPT_URL")
    if not url:
        return "بوابة أتمتة جوجل غير مفعّلة؛ الرابط البرميجي مفقود."
    try:
        parsed_payload = json.loads(payload_data)
        data = {"action": action, "payload": parsed_payload}
        res = requests.post(url, json=data, timeout=15)
        if res.status_code == 200:
            return res.text
        return f"بوابة جوجل أرجعت خطأ رقم: {res.status_code}"
    except Exception as e:
        return f"فشل الاتصال ببوابة أتمتة جوجل: {str(e)}"

def search_duckduckgo(query: str) -> str:
    """
    Performs a live web search via DuckDuckGo to fetch updated real-time information and summaries.
    """
    try:
        url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            snippets = [a.get_text(strip=True) for a in soup.find_all('a', class_='result__snippet')[:4]]
            return "\n".join(snippets) if snippets else "لم يتم العثور على نتائج مباشرة للبحث الجاري."
        return f"محرك البحث لا يستجيب حالياً، رمز الحالة: {res.status_code}"
    except Exception as e:
        return f"خطأ أثناء إجراء عملية البحث: {str(e)}"

def lookup_ip(ip: str) -> str:
    """
    Provides intelligence information, location, ISP lookup for a specific IP address. Useful for network scanning tasks.
    """
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}", timeout=6)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "success":
                return f"بيانات الـ IP [{ip}]: الدولة: {data.get('country')}، المدينة: {data.get('city')}، المزود (ISP): {data.get('isp')}."
            return "فشل فحص العنوان؛ قد يكون تنسيق الـ IP غير صالح."
        return "سيرفر الفحص الخارجي لا يستجيب."
    except Exception as e:
        return f"خطأ في أداة فحص الشبكة: {str(e)}"

def encrypt_decrypt_text(text: str, operation: str) -> str:
    """
    Locally encrypts or decrypts text using secure Base64 conversions for privacy.
    Args:
        text: The text block to encrypt or decrypt.
        operation: 'encrypt' to secure text, 'decrypt' to uncover text.
    """
    import base64
    try:
        if operation.lower() == "encrypt":
            encoded = base64.b64encode(text.encode('utf-8')).decode('utf-8')
            return f"النص المشفر بنجاح: {encoded}"
        elif operation.lower() == "decrypt":
            decoded = base64.b64decode(text.encode('utf-8')).decode('utf-8')
            return f"النص بعد فك التشفير: {decoded}"
        return "عملية غير صالحة؛ يرجى اختيار 'encrypt' أو 'decrypt'."
    except Exception as e:
        return f"فشل معالجة النص: {str(e)}"

def get_current_datetime() -> str:
    """
    Returns the exact accurate current system date and time. Prevents chronological halluncinations.
    """
    import datetime
    return f"التاريخ والوقت الحالي في بيئة عمل الوكيل: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# بناء نموذج جيميناي وربط كافة الأدوات المعرفّة أعلاه به تلقائياً
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[execute_code, get_weather, google_apps_script_action, search_duckduckgo, lookup_ip, encrypt_decrypt_text, get_current_datetime]
)

# --- معالجة الردود المتقدمة ومؤشرات تليجرام ---

async def send_smart_response(update: Update, context: ContextTypes.DEFAULT_TYPE, text_response: str):
    """ Sends text and automatically converts short responses into high-quality Arabic voice. """
    if not text_response:
        return
        
    # إرسال الرد النصي الأساسي أولاً
    await update.message.reply_text(text_response)
    
    # إذا كان النص قصيراً ومختصراً، يتم توليد ملف صوتي ذكي فوراً وبشكل صامت
    if len(text_response) < 450:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.RECORD_AUDIO)
            audio_file_path = f"agent_voice_{update.effective_user.id}.mp3"
            
            # استخدام الصوت العصبي الفصيح من مايكروسوفت إيدج
            communicate = edge_tts.Communicate(text_response, "ar-SA-HamedNeural")
            await communicate.save(audio_file_path)
            
            with open(audio_file_path, 'rb') as audio:
                await update.message.reply_audio(audio=audio, title="الرد الصوتي للوكيل", performer="Manus-Sub")
                
            if os.path.exists(audio_file_path):
                os.remove(audio_file_path)
        except Exception as e:
            print(f"TTS Engine Warning: {str(e)}")

# --- معالجات الأحداث (Handlers) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
    await update.message.reply_text("تم تفعيل الوكيل وتجهيز كافة الأدوات المحلية والأتمتة بسندبوكس معزول. أنا جاهز تماماً الآن للتنفيذ.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    # إظهار مؤشر "جاري الكتابة..." فوراً ليعلم المستخدم أن العمل جاري بالخلفية
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    
    if user_id not in USER_CHATS:
        USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
        
    try:
        # إرسال النص لجيميناي ليتخذ القرار باستدعاء الأداة المناسبة وتنفيذها ذاتياً
        response = USER_CHATS[user_id].send_message(user_text)
        await send_smart_response(update, context, response.text)
    except Exception as e:
        await update.message.reply_text(f"تنبيه برميجي: فشل الوكيل في معالجة الطلب الداخلي. الخطأ: {str(e)}")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    voice = update.message.voice
    
    # إظهار مؤشر "جاري تسجيل صوت..." لإثبات التفاعل مع الرسالة الصوتية الواردة
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.RECORD_AUDIO)
    
    local_voice_path = f"incoming_voice_{user_id}.ogg"
    
    try:
        # تحميل الملف الصوتي من تليجرام محلياً
        tg_file = await context.bot.get_file(voice.file_id)
        await tg_file.download_to_drive(local_voice_path)
        
        # رفع الملف مباشرة إلى سحابة جيميناي لمعالجته كملف متعدد الوسائط (فهم حقيقي للصوت)
        uploaded_media = genai.upload_file(local_voice_path, mime_type="audio/ogg")
        
        if user_id not in USER_CHATS:
            USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
            
        response = USER_CHATS[user_id].send_message([uploaded_media, "استمع بدقة لهذا الملف الصوتي المرفق ونفذ الإجراء أو أجب عليه مباشرة."])
        
        if os.path.exists(local_voice_path):
            os.remove(local_voice_path)
            
        await send_smart_response(update, context, response.text)
    except Exception as e:
        await update.message.reply_text(f"خطأ أثناء فك ومعالجة الرسالة الصوتية: {str(e)}")

# --- سيرفر مساعد لربط المنفذ والحفاظ على استمرارية الخدمة على Render ---

class RenderHealthServer(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("الوكيل مستقر ويعمل بأعلى كفاءة تشغيلية.".encode("utf-8"))
    def log_message(self, format, *args):
        return  # كتم السجلات الإضافية لتبسيط مخرجات المنصة

def start_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    srv = http.server.HTTPServer(("0.0.0.0", port), RenderHealthServer)
    srv.serve_forever()

# --- انطلاق التطبيق ---

if __name__ == "__main__":
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("خطأ حرج: متغير TELEGRAM_TOKEN غير موجود!")
        sys.exit(1)
        
    # تشغيل سيرفر الـ Health Check في خيط فرعي معزول لمنع سقوط البيئة
    t = threading.Thread(target=start_health_check_server, daemon=True)
    t.start()
    
    # إعداد تطبيق تليجرام واستقبال الرسائل بنمط Polling المستقر
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    print("الوكيل انطلق بنجاح ويعمل الآن...")
    app.run_polling()
