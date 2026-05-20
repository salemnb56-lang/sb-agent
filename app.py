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
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# تفعيل سجلات النظام لمراقبة أي خطأ فوراً في Render
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ==========================================
# 1. الإعدادات وتكوين الذكاء الاصطناعي
# ==========================================
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

ALLOWED_USER = os.environ.get("ALLOWED_USER_ID")
USER_CHATS = {}

def check_user_authority(user_id: int) -> bool:
    if not ALLOWED_USER: return True
    is_valid = str(user_id) == str(ALLOWED_USER).strip()
    if not is_valid:
        logging.warning(f"⚠️ محاولة وصول مرفوضة من الرقم: {user_id}")
    return is_valid

# ==========================================
# 2. أنظمة الحماية وتنسيق النصوص للتلغرام
# ==========================================
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
# 3. ترسانة الأدوات الشاملة (القديمة + الحديثة)
# ==========================================
def execute_code(code: str, language: str = "python") -> str:
    """تنفيذ الأكواد البرمجية واختبارها في بيئة معزولة آمنة"""
    try:
        res = requests.post("https://emkc.org/api/v2/piston/execute", json={"language": language, "version": "*", "files": [{"content": code}]}, timeout=12)
        return res.json().get("run", {}).get("output", "") if res.status_code == 200 else f"خطأ تنفيذ: {res.status_code}"
    except Exception as e: return str(e)

def search_duckduckgo(query: str) -> str:
    """البحث السريع في الإنترنت لجلب معلومات فورية وعامة"""
    try:
        res = requests.get(f"https://html.duckduckgo.com/html/?q={query}", headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")
        snippets = [a.get_text(strip=True) for a in soup.find_all('a', class_='result__snippet')[:5]]
        return "\n".join(snippets) if snippets else "لا توجد نتائج."
    except Exception as e: return f"خطأ الشبكة: {str(e)}"

def get_webpage_content(url: str) -> str:
    """الدخول المباشر لأي رابط ويب وقراءة محتواه وتلخيصه"""
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text(separator='\n', strip=True)
        return text[:15000] + "\n...[تم قص النص لحماية الذاكرة]" if len(text) > 15000 else text
    except Exception as e: return f"فشل قراءة الرابط: {str(e)}"

def get_global_news(topic: str) -> str:
    """جلب وتلخيص أحدث الأخبار العالمية أو التقنية عبر محرك بحث RSS مجاني وجامع"""
    try:
        url = f"https://news.google.com/rss/search?q={topic}&hl=ar&gl=EG&ceid=EG:ar"
        res = requests.get(url, timeout=8)
        root = ET.fromstring(res.content)
        news = []
        for item in root.findall('./channel/item')[:6]:
            news.append(f"- {item.find('title').text}\n  الرابط: {item.find('link').text}")
        return "\n\n".join(news) if news else "لم أجد أخباراً حديثة حول هذا الموضوع."
    except Exception as e: return f"فشل جلب الأخبار: {str(e)}"

def generate_image(prompt: str) -> str:
    """توليد ورسم صور إبداعية جديدة بالذكاء الاصطناعي مجاناً بناءً على الوصف"""
    encoded_prompt = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
    return f"IMAGE_URL:{url}"

def inspect_archive_or_apk(file_path: str) -> str:
    """الهندسة العكسية وفحص محتويات ملفات ZIP و APK للأندرويد برمجياً وثغراتها"""
    try:
        if not zipfile.is_zipfile(file_path): return "الملف ليس بصيغة أرشيف مدعومة."
        with zipfile.ZipFile(file_path, 'r') as z:
            files = z.namelist()
            total_size = sum([z.getinfo(f).file_size for f in files]) / (1024 * 1024)
            manifest_info = "موجود (APK نقي)" if "AndroidManifest.xml" in files else "غير موجود"
            output = f"تحليل ملف الأرشيف:\n- عدد الملفات الداخلية: {len(files)}\n- الحجم الكلي مفروداً: {total_size:.2f} MB\n- ملف الـ Manifest الأندرويد: {manifest_info}\n\nأبرز الملفات المكتشفة:\n"
            output += "\n".join(files[:30])
            return output
    except Exception as e: return f"خطأ فحص الأرشيف: {str(e)}"

# --- أدوات السكرتارية التنفيذية لبوابة Google Apps Script ---
def google_apps_script_core(action: str, payload: dict) -> str:
    url = os.environ.get("GOOGLE_SCRIPT_URL")
    if not url: return "بوابة الأتمتة لجوجل (Apps Script URL) غير مدمجة بالسيرفر حالياً."
    try:
        res = requests.post(url, json={"action": action, "payload": payload}, timeout=20)
        return res.text if res.status_code == 200 else f"خطأ البوابة: {res.status_code}"
    except Exception as e: return f"فشل اتصال الأتمتة: {str(e)}"

def gmail_search_emails(query: str, limit: int = 10) -> str:
    """البحث في بريدك الإلكتروني لـ Gmail وقراءة الرسائل الواردة"""
    return google_apps_script_core("gmail_search", {"query": query, "limit": limit})

def gmail_send_email(to: str, subject: str, body: str) -> str:
    """إنشاء وإرسال رسالة بريد إلكتروني جديدة رسمية عبر Gmail لأي شخص"""
    return google_apps_script_core("gmail_send", {"to": to, "subject": subject, "body": body})

def gmail_draft_email(to: str, subject: str, body: str) -> str:
    """إنشاء مسودة إيميل داخل حسابك على Gmail لمراجعتها لاحقاً دون إرسال فوراً"""
    return google_apps_script_core("gmail_draft", {"to": to, "subject": subject, "body": body})

def calendar_add_event(title: str, start_time: str, end_time: str, description: str = "") -> str:
    """إضافة حدث أو منبه جديد لتقويم جوجل الخاص بك تذكيري"""
    return google_apps_script_core("calendar_create", {"title": title, "start_time": start_time, "end_time": end_time, "description": description})

def calendar_list_events(start_time: str, end_time: str) -> str:
    """عرض قائمة بجميع مواعيدك وأحداثك المسجلة في تقويم جوجل لفترة معينة"""
    return google_apps_script_core("calendar_list", {"start_time": start_time, "end_time": end_time})

def calendar_update_event(event_id: str, updates: dict) -> str:
    """تعديل تفاصيل أو وقت حدث مسجل مسبقاً في تقويم جوجل"""
    return google_apps_script_core("calendar_update", {"event_id": event_id, "updates": updates})

def calendar_delete_event(event_id: str) -> str:
    """إلغاء أو أرشفة حدث من تقويم جوجل"""
    return google_apps_script_core("calendar_delete", {"event_id": event_id})

def get_current_datetime() -> str:
    import datetime
    return f"توقيت السيرفر الحالي بدقة: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# ==========================================
# 4. بناء النموذج وإرساء الشخصية
# ==========================================
SYSTEM_INSTRUCTION = """أنت السكرتير التنفيذي والوكيل الذكي فائق القدرات لمديرك 'سالم'. سالم عمره 16 عاماً، مبرمج محترف، يعشق الأمن السيبراني والأتمتة والهندسة العكسية لتطبيقات الأندرويد.
صلاحياتك وقوانينك:
1. أنت تملك أدوات كاملة للتحكم بـ Gmail والتقويم، وفحص ملفات الـ APK، وقراءة صفحات الويب، وتوليد الصور، وتنفيذ الأكواد. استخدمها تلقائياً عند الحاجة.
2. تحدث دائماً باللغة العربية الفصحى، بأسلوب عملي، حاد وذكي، تقني جداً ومباشر كزميل خبير.
3. عند توليد الصور، استخدم أداة generate_image فقط وسيقوم النظام بإرسالها له تلقائياً."""

ALL_TOOLS = [
    execute_code, search_duckduckgo, get_webpage_content, get_global_news, generate_image,
    get_current_datetime, gmail_search_emails, gmail_send_email, gmail_draft_email,
    calendar_add_event, calendar_list_events, calendar_update_event, calendar_delete_event
]

model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=ALL_TOOLS,
    system_instruction=SYSTEM_INSTRUCTION
)

# ==========================================
# 5. محرك الإرسال الذكي والتحكم بالوسائط
# ==========================================
async def process_and_send_response(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_response: str):
    if not raw_response: return
    
    # فحص إذا كان الرد عبارة عن رابط صورة تم توليدها برمجياً
    if "IMAGE_URL:" in raw_response:
        url = raw_response.split("IMAGE_URL:")[-1].strip()
        try:
            await update.message.reply_photo(photo=url, caption="⚡ تم توليد وتصميم الصورة المطلوبة بنجاح بواسطة سكرتيرك الذكي:")
            return
        except Exception as e:
            logging.error(f"فشل إرسال الصورة المنتجة: {e}")
            
    # تقسيم النصوص الطويلة جداً منعاً لانهيار تيليجرام
    chunks = [raw_response[i:i+3500] for i in range(0, len(raw_response), 3500)]
    for chunk in chunks:
        html_formatted = format_to_telegram_html(chunk)
        try:
            await update.message.reply_text(html_formatted, parse_mode=constants.ParseMode.HTML)
        except Exception:
            await update.message.reply_text(chunk)
        await asyncio.sleep(0.4)
        
    # نظام الرد الصوتي الآلي التلقائي للرسائل الوجيزة
    if len(raw_response) < 400 and not "IMAGE_URL:" in raw_response:
        try:
            audio_path = f"audio_{update.effective_user.id}.mp3"
            communicate = edge_tts.Communicate(raw_response, "ar-SA-HamedNeural")
            await communicate.save(audio_path)
            with open(audio_path, 'rb') as audio:
                await update.message.reply_audio(audio=audio)
            if os.path.exists(audio_path): os.remove(audio_path)
        except Exception: pass

async def keep_typing_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, stop_event: asyncio.Event):
    try:
        while not stop_event.is_set():
            await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError: pass

# ==========================================
# 6. المعالجات المركزية المدعمة للوسائط المتعددة
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    USER_CHATS[update.effective_user.id] = model.start_chat(enable_automatic_function_calling=True)
    await update.message.reply_text("مرحباً بك يا مدير سالم. نظام السكرتارية الفسيح تم تفعيله بالكامل وربط كافة بوابات الويب وجوجل والأندرويد بصلاحيات آمنة ومستقرة.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id not in USER_CHATS:
        USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
        
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing_loop(context, chat_id, stop_typing))
    
    try:
        # تشغيل المحرك التلقائي المستقر بنسبة 100% لمنع صمت البوت أو تعليق الجلسة
        response = await asyncio.to_thread(USER_CHATS[user_id].send_message, update.message.text)
        stop_typing.set()
        typing_task.cancel()
        await process_and_send_response(update, context, response.text)
    except Exception as e:
        stop_typing.set()
        typing_task.cancel()
        logging.error(f"خطأ تنفيذ نصي داخلي: {e}")
        await update.message.reply_text(f"⚙️ تم رصد مشكلة معالجة داخلية، تقرير المطور: {str(e)}")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة وفهم محتويات الصور المرفوعة للبوت واستنباط البيانات منها (Vision)"""
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    
    if user_id not in USER_CHATS:
        USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
        
    photo_file = update.message.photo[-1]
    status_msg = await update.message.reply_text("📥 <i>جاري استقبال الصورة وفحص أبعادها برمجياً...</i>", parse_mode="HTML")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        local_path = tmp.name
        
    try:
        tg_file = await context.bot.get_file(photo_file.file_id)
        await tg_file.download_to_drive(local_path)
        
        uploaded_media = await asyncio.to_thread(genai.upload_file, local_path)
        caption = update.message.caption or "حلل وافحص هذه الصورة بدقة واستخرج محتواها."
        
        await status_msg.edit_text("🧠 <i>جاري معالجة الرؤية البصرية للذكاء الاصطناعي...</i>", parse_mode="HTML")
        response = await asyncio.to_thread(USER_CHATS[user_id].send_message, [uploaded_media, caption])
        await status_msg.delete()
        await process_and_send_response(update, context, response.text)
    except Exception as e:
        await status_msg.edit_text(f"❌ خطأ معالجة البصر: {e}")
    finally:
        if os.path.exists(local_path): os.remove(local_path)

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة كافة أنواع الملفات والمستندات والأكواد والـ APK والـ ZIP الأرشيفية"""
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    
    if user_id not in USER_CHATS:
        USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
        
    doc = update.message.document
    file_name = doc.file_name.lower()
    status_msg = await update.message.reply_text("📥 <i>جاري تحميل المستند إلى الذاكرة العزلية...</i>", parse_mode="HTML")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as tmp:
        local_path = tmp.name
        
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(local_path)
        
        if file_name.endswith(('.apk', '.zip', '.rar', '.jar')):
            await status_msg.edit_text("🛠️ <i>جاري تفكيك حزم الأرشيف وفحص الكود الداخلي والـ Manifest...</i>", parse_mode="HTML")
            result = await asyncio.to_thread(inspect_archive_or_apk, local_path)
            prompt = f"لقد قمت برفع ملف حزمة مضغوطة/APK وهذا تقرير الفحص الأولي لها:\n{result}\n\nحلل هذا أمنياً وبنية برمجية."
            await status_msg.delete()
            response = await asyncio.to_thread(USER_CHATS[user_id].send_message, prompt)
            await process_and_send_response(update, context, response.text)
            
        elif file_name.endswith(('.py', '.txt', '.js', '.html', '.css', '.json', '.xml', '.sh')):
            with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            prompt = f"إليك كود ملف برمجي نصي أرفعُه لك ({file_name}):\n\n{content[:18000]}\n\nراجع الكود وافحصه واكتشف ثغراته أو نفذ المطلوب."
            await status_msg.delete()
            response = await asyncio.to_thread(USER_CHATS[user_id].send_message, prompt)
            await process_and_send_response(update, context, response.text)
            
        else:
            await status_msg.edit_text("📤 <i>جاري رفع الملف لبيئة جيميناي السحابية العميقة...</i>", parse_mode="HTML")
            uploaded_media = await asyncio.to_thread(genai.upload_file, local_path)
            caption = update.message.caption or "حلل هذا الملف بدقة واشرح تفاصيله."
            await status_msg.delete()
            response = await asyncio.to_thread(USER_CHATS[user_id].send_message, [uploaded_media, caption])
            await process_and_send_response(update, context, response.text)
            
    except Exception as e:
        await status_msg.edit_text(f"❌ فشل السكرتير في قراءة الملف: {e}")
    finally:
        if os.path.exists(local_path): os.remove(local_path)

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    if user_id not in USER_CHATS:
        USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=True)
        
    local_path = f"voice_{user_id}.ogg"
    try:
        tg_file = await context.bot.get_file(update.message.voice.file_id)
        await tg_file.download_to_drive(local_path)
        uploaded_media = await asyncio.to_thread(genai.upload_file, local_path, mime_type="audio/ogg")
        response = await asyncio.to_thread(USER_CHATS[user_id].send_message, [uploaded_media, "استمع للملف الصوتي بدقة ونفذ المكتوب فيه بالكامل."])
        if os.path.exists(local_path): os.remove(local_path)
        await process_and_send_response(update, context, response.text)
    except Exception as e:
        if os.path.exists(local_path): os.remove(local_path)
        await update.message.reply_text(f"❌ خطأ معالجة الصوت: {e}")

# ==========================================
# 7. خادم الاستقرار والمراقبة السحابية (Render)
# ==========================================
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
    
    # ربط جميع مستمعات الحركة للوسائط لضمان قوة وكيل الشات الشامل
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logging.info("🚀 تم تشغيل البوت بنظام المراقبة والاستماع لجميع أنواع الوسائط بنجاح")
    
    async with server:
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    if not os.environ.get("TELEGRAM_TOKEN"):
        logging.error("TELEGRAM_TOKEN مفقود من متغيرات البيئة!")
        sys.exit(1)
    asyncio.run(main())
