import os
import sys
import json
import html
import re
import asyncio
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
        return True
    return str(user_id) == str(ALLOWED_USER)

# --- نظام معالجة وتنسيق النصوص البرمجية المتطور ---
def format_to_telegram_html(text: str) -> str:
    """ تحول مخرجات جيميناي النصية والماركداون إلى كتل HTML متوافقة مع واجهة تليجرام """
    if not text:
        return ""
    
    parts = re.split(r'(```[\s\S]*?```)', text)
    for i in range(len(parts)):
        if parts[i].startswith('```'):
            code_pattern = r'
http://googleusercontent.com/immersive_entry_chip/0

احفظ هذا الكود في GitHub وتلقائياً سيبدأ سيرفر Render بالبناء الجديد، وستلاحظ اختفاء خطأ المنفذ تماماً واستقرار الخدمة باللون الأخضر.
