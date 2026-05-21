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
from telegram import Update, constants
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
# 1. أدوات النظام والويب والبحث
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
        return text[:15000] + "\n...[تم قص النص]" if len(text) > 15000 else text
    except Exception as e: return f"فشل قراءة الرابط: {str(e)}"

def get_global_news(topic: str) -> str:
    try:
        url = f"https://news.google.com/rss/search?q={topic}&hl=ar&gl=EG&ceid=EG:ar"
        res = requests.get(url, timeout=8)
        root = ET.fromstring(res.content)
        news = [f"- {item.find('title').text}\n  الرابط: {item.find('link').text}" for item in root.findall('./channel/item')[:6]]
        return "\n\n".join(news) if news else "لم أجد أخباراً."
    except Exception as e: return f"خطأ: {str(e)}"

def generate_image(prompt: str) -> str:
    encoded_prompt = requests.utils.quote(prompt)
    return f"IMAGE_URL:https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"

def inspect_archive_or_apk(file_path: str) -> str:
    try:
        if not zipfile.is_zipfile(file_path): return "الملف ليس أرشيفاً."
        with zipfile.ZipFile(file_path, 'r') as z:
            files = z.namelist()
            manifest = "موجود" if "AndroidManifest.xml" in files else "غير موجود"
            return f"الملفات: {len(files)}\nAndroidManifest: {manifest}\nعينة:\n" + "\n".join(files[:20])
    except Exception as e: return f"خطأ: {str(e)}"

def get_current_datetime() -> str:
    import datetime
    return f"توقيت السيرفر: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def create_project_zip(files_dict: dict, project_name: str = "project") -> str:
    try:
        zip_filename = f"{project_name}.zip"
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filepath, content in files_dict.items():
                zipf.writestr(filepath, content)
        return f"PROJECT_ZIP_CREATED:{zip_filename}"
    except Exception as e: return f"فشل إنشاء المشروع: {str(e)}"

# ==========================================
# 2. أدوات بوابات جوجل (Apps Script)
# ==========================================
def google_apps_script_core(action: str, payload: dict) -> str:
    url = os.environ.get("GOOGLE_SCRIPT_URL")
    if not url: return "بوابة جوجل (Apps Script URL) غير مدمجة."
    try:
        res = requests.post(url, json={"action": action, "payload": payload}, timeout=20)
        return res.text if res.status_code == 200 else f"خطأ البوابة: {res.status_code}"
    except Exception as e: return f"فشل الاتصال: {str(e)}"

def gmail_search_emails(query: str, limit: int = 5) -> str: return google_apps_script_core("gmail_search", {"query": query, "limit": limit})
def gmail_send_email(to: str, subject: str, body: str) -> str: return google_apps_script_core("gmail_send", {"to": to, "subject": subject, "body": body})
def gmail_draft_email(to: str, subject: str, body: str) -> str: return google_apps_script_core("gmail_draft", {"to": to, "subject": subject, "body": body})
def calendar_add_event(title: str, start_time: str, end_time: str, description: str = "") -> str: return google_apps_script_core("calendar_create", {"title": title, "start_time": start_time, "end_time": end_time, "description": description})
def drive_search_files(query: str) -> str: return google_apps_script_core("drive_search", {"query": query})
def drive_create_folder(folder_name: str) -> str: return google_apps_script_core("drive_create_folder", {"folder_name": folder_name})
def docs_create_document(title: str, content: str) -> str: return google_apps_script_core("docs_create", {"title": title, "content": content})
def sheets_create_spreadsheet(title: str) -> str: return google_apps_script_core("sheets_create", {"title": title})
def sheets_append_row(sheet_id: str, row_data: list) -> str: return google_apps_script_core("sheets_append", {"sheet_id": sheet_id, "row_data": row_data})

# ==========================================
# 3. العقل المدبر والتعليمات الصارمة (Agent Core)
# ==========================================
SYSTEM_INSTRUCTION = """أنت وكيل ذكاء اصطناعي (AI Agent) تنفيذي ومبرمج محترف، لست مجرد روبوت دردشة. 
مديرك يعتمد عليك لإنجاز مهام معقدة، ويجب أن تعمل وفق بروتوكول صارم:

1. قانون حظر الهلوسة: يُمنع منعاً باتاً اختلاق معلومات، أسماء شركات، أو استخدام نصوص توضيحية (مثل Lorem Ipsum). إذا طلب منك معلومات عن مشروع حقيقي، يجب أن تستخدم أداة `search_duckduckgo` للبحث، ثم `get_webpage_content` لقرائة التفاصيل واستخراج بيانات حقيقية 100%. إذا لم تجد، أخبر المدير أنك لم تجد بدلاً من اختلاق الأكاذيب.
2. الشفافية والتخطيط (Agentic Workflow): عند تلقي طلب ضخم، لا تعطِ النتيجة مباشرة. اكتب للمدير أولاً رسالة توضح فيها خطتك (مثال: "سأقوم أولاً بالبحث عن المحل.. ثم سأقرأ موقعه.. ثم سأبني الكود"). شارك المدير بتفكيرك.
3. إنشاء المشاريع: إذا قمت ببناء موقع أو تطبيق، يجب عليك إلزامياً استدعاء أداة `create_project_zip` وتمرير الأكواد لها لتكوين ملف حقيقي. مجرد كتابة "تم إنشاء الملف" دون استخدام الأداة يُعتبر فشلاً ذريعاً.
4. الذكاء في الأخطاء: إذا فشلت أداة، قم بتحليل الخطأ وجرب طريقة أخرى للبحث أو التنفيذ قبل الاستسلام.
5. تحدث دائماً باحترافية، بأسلوب مباشر، وباللغة العربية الفصحى."""

ALL_TOOLS = [
    execute_code, search_duckduckgo, get_webpage_content, get_global_news, generate_image, inspect_archive_or_apk,
    create_project_zip, get_current_datetime, 
    gmail_search_emails, gmail_send_email, gmail_draft_email, calendar_add_event,
    drive_search_files, drive_create_folder, docs_create_document, sheets_create_spreadsheet, sheets_append_row
]

model = genai.GenerativeModel(model_name='gemini-2.5-flash', tools=ALL_TOOLS, system_instruction=SYSTEM_INSTRUCTION)

# ==========================================
# 4. معالجة الردود وإدارة المحادثة (مع الحماية من التعليق)
# ==========================================
async def process_and_send_response(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_response: str):
    if not raw_response: return
    
    # معالجة الصور
    if "IMAGE_URL:" in raw_response:
        url = raw_response.split("IMAGE_URL:")[-1].strip()
        try:
            await update.message.reply_photo(photo=url, caption="⚡ تم توليد الصورة.")
        except Exception as e: logging.error(f"خطأ الصورة: {e}")
        raw_response = re.sub(r'IMAGE_URL:.*', '', raw_response)

    # معالجة الملفات المضغوطة (ZIP)
    if "PROJECT_ZIP_CREATED:" in raw_response:
        match = re.search(r"PROJECT_ZIP_CREATED:(.*?\.zip)", raw_response)
        if match:
            zip_filename = match.group(1).strip()
            if os.path.exists(zip_filename):
                try:
                    await update.message.reply_document(document=open(zip_filename, 'rb'), caption="📦 مشروعك جاهز بالكامل.")
                    os.remove(zip_filename)
                except Exception as e: logging.error(f"خطأ ZIP: {e}")
        raw_response = re.sub(r'PROJECT_ZIP_CREATED:.*', '', raw_response)

    # إرسال النص المتبقي
    cleaned_text = raw_response.strip()
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
# 5. أوامر التحكم (Start / Reset / Text)
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    USER_CHATS[update.effective_user.id] = model.start_chat(enable_automatic_function_calling=True)
    await update.message.reply_text("مرحباً بك يا مدير. نظام الوكيل الذكي (Agent) يعمل بكامل أدواته. تم تفعيل بروتوكول التخطيط والبحث الحقيقي.")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر جديد لإعادة تهيئة المحادثة في حال صمت البوت أو تعليقه"""
    if not check_user_authority(update.effective_user.id): return
    USER_CHATS[update.effective_user.id] = model.start_chat(enable_automatic_function_calling=True)
    await update.message.reply_text("🔄 تم مسح الذاكرة المؤقتة وإعادة ضبط العقل المدبر. أنا مستعد لتلقي الأوامر من الصفر.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    if user_id not in USER_CHATS: USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
        
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing_loop(context, update.effective_chat.id, stop_typing))
    
    try:
        # هنا نقطة الاتصال مع Gemini، مضاف إليها حماية من التعليق
        response = await asyncio.to_thread(USER_CHATS[user_id].send_message, update.message.text)
        stop_typing.set()
        typing_task.cancel()
        await process_and_send_response(update, context, response.text)
    except Exception as e:
        stop_typing.set()
        typing_task.cancel()
        # إذا حدث خطأ، نخبر المدير وننصحه باستخدام أمر إعادة الضبط
        await update.message.reply_text(f"⚠️ واجهت عطلاً داخلياً أثناء التفكير: {str(e)}\n\n💡 نصيحة: إذا تكرر هذا الخطأ أو توقفت عن الرد، أرسل أمر /reset لتنظيف ذاكرتي المزدحمة.")

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
    except Exception as e:
        await status_msg.delete()
        await update.message.reply_text(f"⚠️ خطأ أثناء معالجة الملف: {str(e)}")
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
    except Exception as e:
        await status_msg.delete()
        await update.message.reply_text(f"⚠️ خطأ في معالجة الصورة: {str(e)}")
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
    app.add_handler(CommandHandler("reset", reset_command)) # الأمر الجديد لحل التعليق
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
