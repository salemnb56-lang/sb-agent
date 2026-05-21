import os
import sys
import html
import re
import asyncio
import logging
import requests
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import google.generativeai as genai
import edge_tts
from telegram import Update, constants, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

ALLOWED_USER = os.environ.get("ALLOWED_USER_ID")
USER_CHATS = {}

def check_user_authority(user_id: int) -> bool:
    if not ALLOWED_USER: return True
    return str(user_id) == str(ALLOWED_USER).strip()

def format_to_telegram_html(text: str) -> str:
    if not text: return ""
    b_ticks = chr(96) * 3
    parts = re.split(r'(' + b_ticks + r'[\s\S]*?' + b_ticks + r')', text)
    for i in range(len(parts)):
        if parts[i].startswith(b_ticks):
            match = re.match(b_ticks + r'(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)\n' + b_ticks, parts[i])
            content = match.group(1) if match else parts[i].replace(b_ticks, '').strip()
            parts[i] = f"<pre>{html.escape(content)}</pre>"
        else:
            parts[i] = html.escape(parts[i])
            parts[i] = re.sub(r'\*\*([\s\S]*?)\*\*', r'<b>\1</b>', parts[i])
            parts[i] = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', parts[i])
            parts[i] = re.sub(r'#+\s*(.+)', r'<b>\1</b>', parts[i])
    return ''.join(parts)

# ==========================================
# الأدوات الأساسية والسابقة (أدوات النظام والويب)
# ==========================================
def execute_code(code: str, language: str = "python") -> str:
    try:
        res = requests.post("https://emkc.org/api/v2/piston/execute", json={"language": language, "version": "*", "files": [{"content": code}]}, timeout=12)
        return res.json().get("run", {}).get("output", "") if res.status_code == 200 else f"خطأ تنفيذ: {res.status_code}"
    except Exception as e: return str(e)

def search_duckduckgo(query: str) -> str:
    try:
        res = requests.get(f"https://html.duckduckgo.com/html/?q={query}", headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")
        snippets = [a.get_text(strip=True) for a in soup.find_all('a', class_='result__snippet')[:5]]
        return "\n".join(snippets) if snippets else "لا توجد نتائج."
    except Exception as e: return f"خطأ الشبكة: {str(e)}"

def get_webpage_content(url: str) -> str:
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text(separator='\n', strip=True)
        return text[:15000] + "\n...[تم قص النص لحماية الذاكرة]" if len(text) > 15000 else text
    except Exception as e: return f"فشل قراءة الرابط: {str(e)}"

def get_global_news(topic: str) -> str:
    try:
        url = f"https://news.google.com/rss/search?q={topic}&hl=ar&gl=EG&ceid=EG:ar"
        res = requests.get(url, timeout=8)
        root = ET.fromstring(res.content)
        news = [f"- {item.find('title').text}\n  الرابط: {item.find('link').text}" for item in root.findall('./channel/item')[:6]]
        return "\n\n".join(news) if news else "لم أجد أخباراً حديثة."
    except Exception as e: return f"خطأ: {str(e)}"

def generate_image(prompt: str) -> str:
    encoded_prompt = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
    return f"IMAGE_URL:{url}"

def inspect_archive_or_apk(file_path: str) -> str:
    try:
        if not zipfile.is_zipfile(file_path): return "الملف ليس أرشيفاً مدعوماً."
        with zipfile.ZipFile(file_path, 'r') as z:
            files = z.namelist()
            manifest = "موجود" if "AndroidManifest.xml" in files else "غير موجود"
            return f"التحليل:\nالملفات: {len(files)}\nبيانات AndroidManifest: {manifest}\nعينة:\n" + "\n".join(files[:20])
    except Exception as e: return f"خطأ: {str(e)}"

def get_current_datetime() -> str:
    import datetime
    return f"توقيت السيرفر الحالي: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# ==========================================
# أداة جديدة: بناء المشاريع وضغطها (للكوتلين والويب)
# ==========================================
def create_project_zip(files_dict: dict, project_name: str = "project") -> str:
    """
    تقوم هذه الأداة بإنشاء ملف ZIP يحتوي على مجلدات وملفات المشروع المطلوبة (مثل تطبيق أندرويد أو موقع ويب).
    files_dict: قاموس يحتوي على مسار الملف كـ Key ومحتوى الملف كـ Value.
    مثال: {"app/src/main/AndroidManifest.xml": "<manifest>...", "build.yml": "name: CI..."}
    """
    try:
        zip_filename = f"{project_name}.zip"
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filepath, content in files_dict.items():
                zipf.writestr(filepath, content)
        return f"PROJECT_ZIP_CREATED:{zip_filename}"
    except Exception as e:
        return f"فشل إنشاء المشروع: {str(e)}"

# ==========================================
# أدوات Google Apps Script الشاملة
# ==========================================
def google_apps_script_core(action: str, payload: dict) -> str:
    url = os.environ.get("GOOGLE_SCRIPT_URL")
    if not url: return "بوابة جوجل (Apps Script URL) غير مدمجة."
    try:
        res = requests.post(url, json={"action": action, "payload": payload}, timeout=20)
        return res.text if res.status_code == 200 else f"خطأ البوابة: {res.status_code}"
    except Exception as e: return f"فشل الاتصال: {str(e)}"

# أدوات Gmail والتقويم (القديمة)
def gmail_search_emails(query: str, limit: int = 5) -> str: return google_apps_script_core("gmail_search", {"query": query, "limit": limit})
def gmail_send_email(to: str, subject: str, body: str) -> str: return google_apps_script_core("gmail_send", {"to": to, "subject": subject, "body": body})
def gmail_draft_email(to: str, subject: str, body: str) -> str: return google_apps_script_core("gmail_draft", {"to": to, "subject": subject, "body": body})
def calendar_add_event(title: str, start_time: str, end_time: str, description: str = "") -> str: return google_apps_script_core("calendar_create", {"title": title, "start_time": start_time, "end_time": end_time, "description": description})

# أدوات Google Drive & Docs & Sheets (الجديدة)
def drive_search_files(query: str) -> str: 
    """البحث عن ملفات في جوجل درايف"""
    return google_apps_script_core("drive_search", {"query": query})
def drive_create_folder(folder_name: str) -> str: 
    """إنشاء مجلد جديد في جوجل درايف"""
    return google_apps_script_core("drive_create_folder", {"folder_name": folder_name})
def docs_create_document(title: str, content: str) -> str: 
    """إنشاء مستند جوجل (Google Docs) جديد وكتابة محتوى فيه"""
    return google_apps_script_core("docs_create", {"title": title, "content": content})
def sheets_create_spreadsheet(title: str) -> str: 
    """إنشاء جدول بيانات (Google Sheets) جديد"""
    return google_apps_script_core("sheets_create", {"title": title})
def sheets_append_row(sheet_id: str, row_data: list) -> str: 
    """إضافة صف من البيانات إلى جدول جوجل شيتس (يجب توفير ID الجدول)"""
    return google_apps_script_core("sheets_append", {"sheet_id": sheet_id, "row_data": row_data})

# ==========================================
# إعداد الذكاء الاصطناعي والشخصية
# ==========================================
SYSTEM_INSTRUCTION = """أنت السكرتير التنفيذي والوكيل الذكي فائق القدرات لمديرك 'سالم'.
صلاحياتك وقوانينك:
1. تملك أدوات تحكم بكامل منظومة Google (Gmail, Calendar, Drive, Docs, Sheets)، استخدمها بذكاء.
2. تملك القدرة على بناء المشاريع (مواقع، تطبيقات Kotlin، ملفات GitHub Actions YAML). لإنشاء مشروع متكامل وإرساله كملف مضغوط للمدير، استخدم أداة `create_project_zip` وضع فيها هيكل المجلدات والأكواد الدقيقة.
3. تحدث دائماً باللغة العربية الفصحى، بأسلوب عملي، تقني، مباشر، ومحترف.
4. استخدم generate_image لتوليد الصور إن طلب منك ذلك."""

ALL_TOOLS = [
    execute_code, search_duckduckgo, get_webpage_content, get_global_news, generate_image, inspect_archive_or_apk,
    create_project_zip, get_current_datetime, 
    gmail_search_emails, gmail_send_email, gmail_draft_email, calendar_add_event,
    drive_search_files, drive_create_folder, docs_create_document, sheets_create_spreadsheet, sheets_append_row
]

model = genai.GenerativeModel(model_name='gemini-2.5-flash', tools=ALL_TOOLS, system_instruction=SYSTEM_INSTRUCTION)

# ==========================================
# معالجة الردود الشاملة (صور، نصوص، ملفات مضغوطة)
# ==========================================
async def process_and_send_response(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_response: str):
    if not raw_response: return
    
    # معالجة توليد الصور
    if "IMAGE_URL:" in raw_response:
        url = raw_response.split("IMAGE_URL:")[-1].strip()
        try:
            await update.message.reply_photo(photo=url, caption="⚡ تم توليد الصورة بنجاح:")
            return
        except Exception as e: logging.error(f"خطأ الصورة: {e}")

    # معالجة تصدير المشاريع كـ ZIP
    if "PROJECT_ZIP_CREATED:" in raw_response:
        match = re.search(r"PROJECT_ZIP_CREATED:(.*?\.zip)", raw_response)
        if match:
            zip_filename = match.group(1).strip()
            if os.path.exists(zip_filename):
                try:
                    await update.message.reply_document(document=open(zip_filename, 'rb'), caption="📦 تم بناء المشروع وهيكلته بالكامل كما طلبت. يمكنك رفعه لـ GitHub الآن.")
                    os.remove(zip_filename)
                    return
                except Exception as e: logging.error(f"خطأ إرسال ZIP: {e}")
            
    # إرسال النصوص الطويلة
    cleaned_text = re.sub(r'IMAGE_URL:.*', '', raw_response).strip()
    cleaned_text = re.sub(r'PROJECT_ZIP_CREATED:.*', '', cleaned_text).strip()
    if not cleaned_text: return

    chunks = [cleaned_text[i:i+3500] for i in range(0, len(cleaned_text), 3500)]
    for chunk in chunks:
        try:
            await update.message.reply_text(format_to_telegram_html(chunk), parse_mode=constants.ParseMode.HTML)
        except Exception:
            await update.message.reply_text(chunk)
        await asyncio.sleep(0.4)

async def keep_typing_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, stop_event: asyncio.Event):
    try:
        while not stop_event.is_set():
            await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError: pass

# ==========================================
# مستقبلات الأوامر والوسائط
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    USER_CHATS[update.effective_user.id] = model.start_chat(enable_automatic_function_calling=True)
    await update.message.reply_text("مرحباً بك يا مدير سالم. جميع بوابات جوجل والمطورين مفعلة، وأداة تصدير المشاريع تعمل بكفاءة.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    if user_id not in USER_CHATS: USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
        
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing_loop(context, update.effective_chat.id, stop_typing))
    
    try:
        response = await asyncio.to_thread(USER_CHATS[user_id].send_message, update.message.text)
        stop_typing.set()
        typing_task.cancel()
        await process_and_send_response(update, context, response.text)
    except Exception as e:
        stop_typing.set()
        typing_task.cancel()
        await update.message.reply_text(f"⚙️ خطأ: {str(e)}")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    if user_id not in USER_CHATS: USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
        
    doc = update.message.document
    file_name = doc.file_name.lower()
    status_msg = await update.message.reply_text("📥 <i>جاري الاستقبال...</i>", parse_mode="HTML")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as tmp: local_path = tmp.name
        
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(local_path)
        
        if file_name.endswith(('.apk', '.zip', '.rar', '.jar')):
            result = await asyncio.to_thread(inspect_archive_or_apk, local_path)
            prompt = f"فحص أرشيف:\n{result}\nحلل أمنياً."
            await status_msg.delete()
            res = await asyncio.to_thread(USER_CHATS[user_id].send_message, prompt)
            await process_and_send_response(update, context, res.text)
        elif file_name.endswith(('.py', '.txt', '.js', '.html', '.css', '.json', '.xml', '.yml')):
            with open(local_path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
            prompt = f"هذا محتوى الملف ({file_name}):\n\n{content[:18000]}\n\nحلله أو صحح أخطاءه."
            await status_msg.delete()
            res = await asyncio.to_thread(USER_CHATS[user_id].send_message, prompt)
            await process_and_send_response(update, context, res.text)
        else:
            uploaded_media = await asyncio.to_thread(genai.upload_file, local_path)
            await status_msg.delete()
            res = await asyncio.to_thread(USER_CHATS[user_id].send_message, [uploaded_media, update.message.caption or "حلل هذا."])
            await process_and_send_response(update, context, res.text)
    finally:
        if os.path.exists(local_path): os.remove(local_path)

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    if user_id not in USER_CHATS: USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
    
    photo_file = update.message.photo[-1]
    status_msg = await update.message.reply_text("📥 <i>جاري الفحص البصري...</i>", parse_mode="HTML")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp: local_path = tmp.name
    try:
        tg_file = await context.bot.get_file(photo_file.file_id)
        await tg_file.download_to_drive(local_path)
        uploaded_media = await asyncio.to_thread(genai.upload_file, local_path)
        res = await asyncio.to_thread(USER_CHATS[user_id].send_message, [uploaded_media, update.message.caption or "حلل الصورة."])
        await status_msg.delete()
        await process_and_send_response(update, context, res.text)
    finally:
        if os.path.exists(local_path): os.remove(local_path)

async def handle_render_health_check(reader, writer):
    try:
        await reader.read(1024)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
    except Exception: pass
    finally: writer.close()

async def main():
    port = int(os.environ.get("PORT", 10000))
    server = await asyncio.start_server(handle_render_health_check, '0.0.0.0', port)
    app = Application.builder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    async with server:
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
