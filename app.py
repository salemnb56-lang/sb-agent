import os
import sys
import html
import re
import asyncio
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import edge_tts
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- الإعدادات والمصادقة ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

ALLOWED_USER = os.environ.get("ALLOWED_USER_ID")
USER_CHATS = {}

def check_user_authority(user_id: int) -> bool:
    if not ALLOWED_USER:
        return True
    return str(user_id) == str(ALLOWED_USER)

# --- نظام التنسيق المضاد لأخطاء النسخ واللصق ---
def format_to_telegram_html(text: str) -> str:
    if not text:
        return ""
    
    # استخدام التشفير الرقمي لتوليد علامات (```) لتجنب تكسير الأسطر في GitHub
    b_ticks = chr(96) * 3
    split_pattern = r'(' + b_ticks + r'[\s\S]*?' + b_ticks + r')'
    code_pattern = b_ticks + r'(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)\n' + b_ticks
    
    parts = re.split(split_pattern, text)
    for i in range(len(parts)):
        if parts[i].startswith(b_ticks):
            match = re.match(code_pattern, parts[i])
            if match:
                parts[i] = f"<pre>{html.escape(match.group(1))}</pre>"
            else:
                parts[i] = f"<pre>{html.escape(parts[i].replace(b_ticks, '').strip())}</pre>"
        else:
            parts[i] = html.escape(parts[i])
            parts[i] = re.sub(r'\*\*([\s\S]*?)\*\*', r'<b>\1</b>', parts[i])
            parts[i] = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', parts[i])
            
            lines = parts[i].split('\n')
            for j, line in enumerate(lines):
                if line.strip().startswith('#'):
                    cleaned_line = line.replace('#', '').strip()
                    lines[j] = f"<b>{cleaned_line}</b>"
            parts[i] = '\n'.join(lines)
            
    return ''.join(parts)

# --- أدوات السكرتارية التنفيذية ---
def google_apps_script_core(action: str, payload: dict) -> str:
    url = os.environ.get("GOOGLE_SCRIPT_URL")
    if not url: return "بوابة الأتمتة غير مدمجة بالنظام."
    try:
        res = requests.post(url, json={"action": action, "payload": payload}, timeout=20)
        return res.text if res.status_code == 200 else f"فشل الإجراء: {res.status_code}"
    except Exception as e: return f"فشل الاتصال: {str(e)}"

def gmail_search_emails(query: str, limit: int = 10) -> str:
    return google_apps_script_core("gmail_search", {"query": query, "limit": limit})

def gmail_mark_email_as_read(thread_id: str) -> str:
    return google_apps_script_core("gmail_mark_read", {"thread_id": thread_id})

def calendar_add_event(title: str, start_time: str, end_time: str, description: str = "") -> str:
    return google_apps_script_core("calendar_create", {"title": title, "start_time": start_time, "end_time": end_time, "description": description})

def calendar_list_events(start_time: str, end_time: str) -> str:
    return google_apps_script_core("calendar_list", {"start_time": start_time, "end_time": end_time})

def execute_code(code: str, language: str = "python") -> str:
    try:
        payload = {"language": language, "version": "*", "files": [{"content": code}]}
        res = requests.post("[https://emkc.org/api/v2/piston/execute](https://emkc.org/api/v2/piston/execute)", json=payload, timeout=12)
        if res.status_code == 200:
            out = res.json().get("run", {}).get("output", "")
            return out if out else "نُفذ بنجاح دون مخرجات."
        return f"خطأ بيئة التنفيذ: {res.status_code}"
    except Exception as e: return f"فشل المعالج: {str(e)}"

def search_duckduckgo(query: str) -> str:
    try:
        res = requests.get(f"[https://html.duckduckgo.com/html/?q=](https://html.duckduckgo.com/html/?q=){query}", headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            snippets = [a.get_text(strip=True) for a in soup.find_all('a', class_='result__snippet')[:4]]
            return "\n".join(snippets) if snippets else "لا توجد نتائج."
        return f"فشل البحث: {res.status_code}"
    except Exception as e: return f"خطأ الشبكة: {str(e)}"

def get_weather(city: str) -> str:
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key: return "مفتاح الطقس مفقود."
    try:
        res = requests.get(f"[http://api.openweathermap.org/data/2.5/weather?q=](http://api.openweathermap.org/data/2.5/weather?q=){city}&appid={api_key}&units=metric&lang=ar", timeout=6)
        if res.status_code == 200:
            d = res.json()
            return f"الطقس في {city}: {d['weather'][0]['description']}، حرارة: {d['main']['temp']}°م."
        return "فشل تحديد المدينة."
    except Exception as e: return str(e)

def lookup_ip(ip: str) -> str:
    try:
        res = requests.get(f"[http://ip-api.com/json/](http://ip-api.com/json/){ip}", timeout=6)
        if res.status_code == 200 and res.json().get("status") == "success":
            d = res.json()
            return f"الدولة: {d.get('country')}، المدينة: {d.get('city')}، المزود: {d.get('isp')}."
        return "العنوان غير متاح."
    except Exception as e: return str(e)

def encrypt_decrypt_text(text: str, operation: str) -> str:
    import base64
    try:
        if operation.lower() == "encrypt":
            return f"مشفّر: {base64.b64encode(text.encode('utf-8')).decode('utf-8')}"
        elif operation.lower() == "decrypt":
            return f"مفكوك: {base64.b64decode(text.encode('utf-8')).decode('utf-8')}"
        return "عملية غير مدعومة."
    except Exception as e: return str(e)

def get_current_datetime() -> str:
    import datetime
    return f"توقيت السيرفر: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# --- بناء النموذج وربط الأدوات ---
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[
        execute_code, get_weather, search_duckduckgo, lookup_ip, 
        encrypt_decrypt_text, get_current_datetime, gmail_search_emails, 
        gmail_mark_email_as_read, calendar_add_event, calendar_list_events
    ]
)

# --- نظام الاستجابة والصوت ---
async def process_and_send_response(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_response: str):
    if not raw_response: return
    html_formatted = format_to_telegram_html(raw_response)
    try:
        await update.message.reply_text(html_formatted, parse_mode=constants.ParseMode.HTML)
    except Exception:
        await update.message.reply_text(raw_response)
        
    if len(raw_response) < 450:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.RECORD_AUDIO)
            audio_path = f"audio_{update.effective_user.id}.mp3"
            communicate = edge_tts.Communicate(raw_response, "ar-SA-HamedNeural")
            await communicate.save(audio_path)
            with open(audio_path, 'rb') as audio:
                await update.message.reply_audio(audio=audio)
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception: pass

# --- المعالجات ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    USER_CHATS[update.effective_user.id] = model.start_chat(enable_automatic_function_calling=True)
    await update.message.reply_text("النظام جاهز.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    if user_id not in USER_CHATS:
        USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
    try:
        response = USER_CHATS[user_id].send_message(update.message.text)
        await process_and_send_response(update, context, response.text)
    except Exception as e:
        await update.message.reply_text(f"خطأ تنفيذي: {str(e)}")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.RECORD_AUDIO)
    local_path = f"voice_{user_id}.ogg"
    try:
        tg_file = await context.bot.get_file(update.message.voice.file_id)
        await tg_file.download_to_drive(local_path)
        uploaded_media = genai.upload_file(local_path, mime_type="audio/ogg")
        if user_id not in USER_CHATS:
            USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
        response = USER_CHATS[user_id].send_message([uploaded_media, "نفذ المطلوب."])
        if os.path.exists(local_path): os.remove(local_path)
        await process_and_send_response(update, context, response.text)
    except Exception as e:
        await update.message.reply_text(f"خطأ صوتي: {str(e)}")

# --- خادم الفحص الخاص بمنصة Render ---
async def handle_render_health_check(reader, writer):
    try:
        await reader.read(1024)
        body = b"OK"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
    except Exception: pass
    finally: writer.close()

async def main():
    port = int(os.environ.get("PORT", 10000))
    server = await asyncio.start_server(handle_render_health_check, '0.0.0.0', port)
    
    app = Application.builder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(filters.TEXT & ~filters.COMMAND, text_handler)
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    async with server:
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    if not os.environ.get("TELEGRAM_TOKEN"):
        sys.exit(1)
    asyncio.run(main())
