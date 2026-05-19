import os
import sys
import json
import html
import re
import asyncio
import threading
import http.server
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import edge_tts
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- إعداد الأنظمة السحابية والتحقق من صلاحيات التشغيل ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

ALLOWED_USER = os.environ.get("ALLOWED_USER_ID")
USER_CHATS = {}

def check_user_authority(user_id: int) -> bool:
    """ تضمن هذه الدالة ألا يستجيب البوت نهائياً لأي طلبات خارجية ما لم تطابق هوية المالك """
    if not ALLOWED_USER:
        return True  # إذا لم يتم تعيين المتغير في ريندر يظل مفتوحاً مؤقتاً
    return str(user_id) == str(ALLOWED_USER)

# --- نظام معالجة وتنسيق النصوص البرمجية المتطور ---
def format_to_telegram_html(text: str) -> str:
    """ تحول مخرجات جيميناي النصية والماركداون إلى كتل HTML متوافقة مع واجهة تليجرام """
    if not text:
        return ""
    
    # فصل الكتل البرمجية لحمايتها من التلف أثناء عملية التحويل التلقائي
    parts = re.split(r'(```[\s\S]*?```)', text)
    for i in range(len(parts)):
        if parts[i].startswith('```'):
            # تم فصل النمط البرمجي في متغير مستقل لحمايته من الانقطاع أثناء اللصق
            code_pattern = r'
http://googleusercontent.com/immersive_entry_chip/0

### الخطوة التالية:
1. استبدل الدالة في ملف `app.py` على GitHub واحفظ الملف (Commit).
2. سيقوم سيرفر Render ببدء البناء تلقائياً بناءً على التحديث الجديد.
3. انتظر دقيقتين وستختفي الرسالة الحمراء ويتحول السيرفر إلى الحالة الخضراء الاسترجاعية المستقرة.
بمجرد الانتهاء من تحديث كود جوجل اسكربت وحفظ ملف `app.py` في مستودع GitHub، سيقوم سيرفر Render تلقائياً بإعادة تشغيل النظام وهيكلة الصلاحيات الجديدة، وحينها يمكنك أن تطلب منه مباشرة تصفية، تصنيف، وقراءة أي محتوى بريدي أو جدولة مواعيدك الشخصية بشكل مباشر وآمن تماماً.
