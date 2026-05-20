import os
import sys
import html
import re
import asyncio
import requests
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import google.generativeai as genai
import edge_tts
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
    return str(user_id) == str(ALLOWED_USER)

# ==========================================
# 2. أنظمة الحماية والتنسيق
# ==========================================
def format_to_telegram_html(text: str) -> str:
    """تنسيق النصوص بشكل صارم لمنع انهيار تليجرام بسبب رموز HTML الخاطئة"""
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
# 3. ترسانة الأدوات المتقدمة للسكرتير
# ==========================================
def execute_code(code: str, language: str = "python") -> str:
    """تنفيذ الأكواد البرمجية في بيئة معزولة"""
    try:
        res = requests.post("https://emkc.org/api/v2/piston/execute", json={"language": language, "version": "*", "files": [{"content": code}]}, timeout=12)
        return res.json().get("run", {}).get("output", "") if res.status_code == 200 else f"خطأ تنفيذ: {res.status_code}"
    except Exception as e: return str(e)

def search_duckduckgo(query: str) -> str:
    """البحث السريع في الويب"""
    try:
        res = requests.get(f"https://html.duckduckgo.com/html/?q={query}", headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")
        snippets = [a.get_text(strip=True) for a in soup.find_all('a', class_='result__snippet')[:5]]
        return "\n".join(snippets) if snippets else "لا توجد نتائج."
    except Exception as e: return f"خطأ الشبكة: {str(e)}"

def get_webpage_content(url: str) -> str:
    """استخراج محتوى الروابط وتلخيصها مع حماية من الملفات الضخمة"""
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text(separator='\n', strip=True)
        return text[:15000] + "\n...[تم قص الباقي لحماية الذاكرة]" if len(text) > 15000 else text
    except Exception as e: return f"فشل قراءة الرابط: {str(e)}"

def get_global_news(topic: str) -> str:
    """جلب أحدث الأخبار العالمية أو التقنية عبر RSS مجاني"""
    try:
        url = f"https://news.google.com/rss/search?q={topic}&hl=ar&gl=EG&ceid=EG:ar"
        res = requests.get(url, timeout=8)
        root = ET.fromstring(res.content)
        news = []
        for item in root.findall('./channel/item')[:7]:
            news.append(f"- {item.find('title').text}\n  رابط: {item.find('link').text}")
        return "\n\n".join(news) if news else "لم أجد أخباراً حول هذا الموضوع."
    except Exception as e: return f"فشل جلب الأخبار: {str(e)}"

def inspect_archive_or_apk(file_path: str) -> str:
    """فحص محتويات ملفات ZIP و APK برمجياً"""
    try:
        if not zipfile.is_zipfile(file_path): return "الملف ليس بصيغة أرشيف مدعومة."
        with zipfile.ZipFile(file_path, 'r') as z:
            files = z.namelist()
            total_size = sum([z.getinfo(f).file_size for f in files]) / (1024 * 1024)
            manifest_info = "موجود" if "AndroidManifest.xml" in files else "غير موجود"
            output = f"تفاصيل الأرشيف:\n- عدد الملفات: {len(files)}\n- الحجم الإجمالي: {total_size:.2f} MB\n- ملف AndroidManifest: {manifest_info}\n\nأول 30 ملف:\n"
            output += "\n".join(files[:30])
            return output
    except Exception as e: return f"خطأ أثناء فحص الأرشيف: {str(e)}"

# أدوات مساعدة إضافية
def get_weather(city: str) -> str: pass # (تم الحفاظ عليها من الكود السابق، يمكنك دمج محتواها أو تركها تتصرف بذكاء عبر البحث)
def get_current_datetime() -> str:
    import datetime
    return f"توقيت السيرفر الحالي: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# ==========================================
# 4. بناء النموذج وتعريف شخصية السكرتير
# ==========================================
SYSTEM_INSTRUCTION = """أنت سكرتير تنفيذي ذكي فائق القدرات. مديرك هو 'سالم'، طالب ثانوي (16 عاماً)، مبرمج ومهتم جداً بالأمن السيبراني، تطوير الأندرويد، استخراج الـ APKs، الأتمتة (Termux, MacroDroid)، والتصميم المظلم (Dark Theme).
مهمتك:
1. تنفيذ المهام بكفاءة واحترافية.
2. إذا كان الطلب يتطلب أدوات متعددة، خطط للأمر ونفذه بهدوء.
3. التحدث باللغة العربية دائماً، بأسلوب عملي، تقني، مباشر، وصريح.
4. استخدم الأدوات المتاحة لك لتحليل الملفات والروابط وتلخيصها."""

TOOLS_LIST = [execute_code, search_duckduckgo, get_webpage_content, get_global_news, get_current_datetime]

model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=TOOLS_LIST,
    system_instruction=SYSTEM_INSTRUCTION
)

# ==========================================
# 5. محرك التفكير الشفاف (The "Thinking" Engine)
# ==========================================
async def handle_tool_calls(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_input: list):
    chat_id = update.effective_chat.id
    chat = USER_CHATS[user_id]
    
    # 1. إرسال رسالة التفكير الأولية
    status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>يتم الآن تحليل الطلب وتجهيز خطة العمل...</i>", parse_mode="HTML")
    
    try:
        # إرسال الطلب لنموذج جيميناي (بدون استدعاء تلقائي لنتمكن من التحكم بواجهة المستخدم)
        response = await asyncio.to_thread(chat.send_message, user_input)
        
        while response.function_calls:
            # 2. تحديث رسالة التفكير بالخطوة الحالية
            tools_used = [fc.name for fc in response.function_calls]
            thought_text = f"⚙️ <b>خطوات التنفيذ الحالية:</b>\n"
            for t in tools_used:
                thought_text += f"▪️ تشغيل أداة: <code>{t}</code>\n"
            await status_msg.edit_text(thought_text, parse_mode="HTML")
            
            # 3. تنفيذ الأدوات فعلياً في الخلفية
            function_responses = []
            for fc in response.function_calls:
                func_name = fc.name
                args = {k: v for k, v in fc.args.items()}
                
                # توجيه الاستدعاء للأداة المناسبة
                try:
                    if func_name == "execute_code": res = await asyncio.to_thread(execute_code, **args)
                    elif func_name == "search_duckduckgo": res = await asyncio.to_thread(search_duckduckgo, **args)
                    elif func_name == "get_webpage_content": res = await asyncio.to_thread(get_webpage_content, **args)
                    elif func_name == "get_global_news": res = await asyncio.to_thread(get_global_news, **args)
                    elif func_name == "get_current_datetime": res = get_current_datetime()
                    else: res = "أداة غير معروفة."
                except Exception as e: res = f"فشل تشغيل الأداة: {e}"
                
                # تجميع الردود لإرسالها لجيميناي
                function_responses.append(genai.protos.Part(function_response=genai.protos.FunctionResponse(name=func_name, response={"result": str(res)})))
            
            # 4. إرسال نتائج الأدوات لجيميناي ليقرر الخطوة القادمة (تحديث الرد)
            response = await asyncio.to_thread(chat.send_message, function_responses)
            await asyncio.sleep(1) # تأخير بسيط لمنع حظر تليجرام لرسائل التعديل
            
        # 5. المهمة اكتملت، حذف رسالة التفكير وإرسال الرد النهائي
        await status_msg.delete()
        await send_final_response(update, context, response.text)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>حدث خطأ تنفيذي:</b>\n<code>{str(e)}</code>", parse_mode="HTML")

async def send_final_response(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if not text: return
    chunks = [text[i:i+3500] for i in range(0, len(text), 3500)]
    for chunk in chunks:
        html_formatted = format_to_telegram_html(chunk)
        try:
            await update.message.reply_text(html_formatted, parse_mode=constants.ParseMode.HTML)
        except Exception:
            await update.message.reply_text(chunk) # خطة طوارئ في حال فشل التنسيق
        await asyncio.sleep(0.5)

# ==========================================
# 6. معالجات تليجرام (النصوص والملفات الشاملة)
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    USER_CHATS[update.effective_user.id] = model.start_chat(enable_automatic_function_calling=False)
    await update.message.reply_text("مرحباً بك يا سالم. السكرتير التنفيذي في الخدمة وبأقصى طاقة.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    if user_id not in USER_CHATS:
        USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=False)
    
    # إرسال النص إلى محرك التفكير لمعالجته
    await handle_tool_calls(update, context, user_id, [update.message.text])

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج شامل للملفات (صور، أكواد، APK، ZIP، مستندات)"""
    if not check_user_authority(update.effective_user.id): return
    user_id = update.effective_user.id
    if user_id not in USER_CHATS:
        USER_CHATS[user_id] = model.start_chat(enable_automatic_function_calling=False)
        
    doc = update.message.document
    file_name = doc.file_name.lower()
    
    status_msg = await update.message.reply_text("📥 <i>جاري تحميل الملف لتحليله...</i>", parse_mode="HTML")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as tmp_file:
        local_path = tmp_file.name
        
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(local_path)
        
        # إذا كان الملف أرشيف أو APK نقوم بفحصه بأداة بايثون محلياً
        if file_name.endswith(('.apk', '.zip', '.rar', '.jar')):
            await status_msg.edit_text("🔍 <i>جاري الهندسة العكسية وفحص الأرشيف...</i>", parse_mode="HTML")
            inspection_result = await asyncio.to_thread(inspect_archive_or_apk, local_path)
            prompt = f"لقد قمت بإرسال ملف أرشيف/APK إليك، وهذا تقرير الفحص الداخلي له:\n{inspection_result}\n\nما هو تحليلك له؟"
            await status_msg.delete()
            await handle_tool_calls(update, context, user_id, [prompt])
            
        # إذا كان كود برمجي أو ملف نصي، نقرأه كنص
        elif file_name.endswith(('.py', '.txt', '.js', '.html', '.css', '.json', '.xml')):
            with open(local_path, 'r', encoding='utf-8') as f:
                content = f.read()
            prompt = f"إليك محتوى الملف البرمجي/النصي ({file_name}):\n\n{content[:20000]}\n\nحلله أو نفذ ما طلبته منك بشأنه."
            await status_msg.delete()
            await handle_tool_calls(update, context, user_id, [prompt])
            
        # لباقي الملفات (PDF, صور، إلخ) نرفعها مباشرة لذكاء جيميناي
        else:
            await status_msg.edit_text("📤 <i>جاري رفع الملف لشبكة الذكاء الاصطناعي للتحليل العميق...</i>", parse_mode="HTML")
            uploaded_media = await asyncio.to_thread(genai.upload_file, local_path)
            caption = update.message.caption or "حلل هذا الملف."
            await status_msg.delete()
            await handle_tool_calls(update, context, user_id, [uploaded_media, caption])
            
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>فشل معالجة الملف:</b>\n<code>{str(e)}</code>", parse_mode="HTML")
    finally:
        if os.path.exists(local_path): os.remove(local_path)

# ==========================================
# 7. خادم الاستقرار (Render Keep-Alive)
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
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    # يمكنك إضافة معالج الصوت (Voice) بنفس الآلية لو أردت لاحقاً
    
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
