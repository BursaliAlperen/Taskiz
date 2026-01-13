import os
import time
import json
import requests
from datetime import datetime, timedelta
import threading
import sqlite3
from flask import Flask, jsonify, request
import hashlib
import pytz
import re
from typing import Optional, Dict, List, Tuple, Any

# Telegram Ayarları
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "7904032877")
SUPPORT_USERNAME = "@AlperenTHE"

# Zorunlu Kanallar
MANDATORY_CHANNELS = [
    {
        'username': 'EarnTether2026',
        'link': 'https://t.me/EarnTether2026',
        'name': 'Ana Kanal'
    },
    {
        'username': 'instagramNewsBrazil',
        'link': 'https://t.me/instagramNewsBrazil',
        'name': 'Instagram Haberleri'
    },
    {
        'username': 'BinanceBrazilNews',
        'link': 'https://t.me/BinanceBrazilNews',
        'name': 'Binance Haberleri'
    },
    {
        'username': 'TaskizLive',
        'link': 'https://t.me/TaskizLive',
        'name': 'Canlı İstatistik'
    }
]

# İstatistik kanalı
STATS_CHANNEL = "TaskizLive"

if not TOKEN:
    raise ValueError("Bot token gerekli!")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Dil ve Para Birimi Ayarları
SUPPORTED_LANGUAGES = {
    'tr': {'name': 'Türkçe', 'flag': '🇹🇷', 'currency': 'TRY'},
    'en': {'name': 'English', 'flag': '🇺🇸', 'currency': 'USD'},
    'ru': {'name': 'Русский', 'flag': '🇷🇺', 'currency': 'RUB'},
    'bn': {'name': 'বাংলা', 'flag': '🇧🇩', 'currency': 'BDT'}
}

# Türkiye saati için
TURKEY_TZ = pytz.timezone('Europe/Istanbul')

# TRX Ayarları
TRX_ADDRESS = os.environ.get("TRX_ADDRESS", "DEPOZIT_YAPILACAK_ADRES")
MIN_DEPOSIT_USD = 2.5
MAX_DEPOSIT_USD = 10.0

# Görev Ücretleri (USD cinsinden)
CHANNEL_TASK_PRICE = 0.03
GROUP_TASK_PRICE = 0.02
BOT_TASK_PRICE = 0.01

# Minimum çekim (USD)
MIN_WITHDRAW = 1.0

# Referans bonusları
REF_WELCOME_BONUS = 0.005
REF_TASK_COMMISSION = 0.25

# Flask App
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "online", "bot": "TaskizBot v3.1"})

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    bot.handle_update(update)
    return jsonify({"status": "ok"})

def get_turkey_time():
    """Türkiye saatini döndür"""
    return datetime.now(TURKEY_TZ)

# Dil Metinleri (Sadeleştirilmiş)
LANGUAGE_TEXTS = {
    'tr': {
        'welcome': "🤖 *TaskizBot'a Hoş Geldiniz!*\n\nPara kazanmak için kanallara katılın ve görevleri tamamlayın.",
        'balance': "💰 Bakiye",
        'tasks': "🎯 Görevler",
        'withdraw': "🏧 Para Çek",
        'deposit': "💳 Bakiye Yükle",
        'profile': "👤 Profil",
        'referral': "👥 Referans",
        'stats': "📊 İstatistik",
        'help': "❓ Yardım",
        'channels': "📢 Kanallar",
        'back': "🔙 Geri",
        'check_channels': "✅ Kanalları Kontrol Et",
        'join_channels': "📢 Kanallara Katıl",
        'earner': "👤 Para Kazanan",
        'advertiser': "📢 Reklamveren",
        'select_type': "Hangi tür kullanıcı olmak istiyorsunuz?",
        'choose_lang': "🌐 Dilinizi seçin:",
        'mandatory_channels': "📋 *Zorunlu Kanallar*\n\nBotu kullanmak için aşağıdaki kanallara katılmalısınız:",
        'all_channels_joined': "✅ *Tebrikler!*\n\nTüm kanallara katıldınız. Şimdi görev yapmaya başlayabilirsiniz.",
        'not_joined_all': "❌ *Hala Bazı Kanallara Katılmadınız!*\n\nLütfen aşağıdaki kanallara katılın:",
        'main_menu': "🏠 *Ana Menü*",
        'your_balance': "💰 *Bakiyeniz:*",
        'min_withdraw': f"Minimum çekim: ${MIN_WITHDRAW}",
        'min_deposit': f"Minimum yükleme: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 Destek: {SUPPORT_USERNAME}",
        'error': "❌ Hata",
        'success': "✅ Başarılı"
    },
    'en': {
        'welcome': "🤖 *Welcome to TaskizBot!*\n\nJoin channels and complete tasks to earn money.",
        'balance': "💰 Balance",
        'tasks': "🎯 Tasks",
        'withdraw': "🏧 Withdraw",
        'deposit': "💳 Deposit",
        'profile': "👤 Profile",
        'referral': "👥 Referral",
        'stats': "📊 Statistics",
        'help': "❓ Help",
        'channels': "📢 Channels",
        'back': "🔙 Back",
        'check_channels': "✅ Check Channels",
        'join_channels': "📢 Join Channels",
        'earner': "👤 Earner",
        'advertiser': "📢 Advertiser",
        'select_type': "What type of user do you want to be?",
        'choose_lang': "🌐 Choose your language:",
        'mandatory_channels': "📋 *Mandatory Channels*\n\nTo use the bot, you must join the channels below:",
        'all_channels_joined': "✅ *Congratulations!*\n\nYou have joined all channels. You can now start doing tasks.",
        'not_joined_all': "❌ *You Still Haven't Joined Some Channels!*\n\nPlease join the following channels:",
        'main_menu': "🏠 *Main Menu*",
        'your_balance': "💰 *Your Balance:*",
        'min_withdraw': f"Minimum withdrawal: ${MIN_WITHDRAW}",
        'min_deposit': f"Minimum deposit: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 Support: {SUPPORT_USERNAME}",
        'error': "❌ Error",
        'success': "✅ Success"
    },
    'ru': {
        'welcome': "🤖 *Добро пожаловать в TaskizBot!*\n\nПрисоединяйтесь к каналам и выполняйте задания, чтобы зарабатывать деньги.",
        'balance': "💰 Баланс",
        'tasks': "🎯 Задания",
        'withdraw': "🏧 Вывести",
        'deposit': "💳 Пополнить",
        'profile': "👤 Профиль",
        'referral': "👥 Рефералы",
        'stats': "📊 Статистика",
        'help': "❓ Помощь",
        'channels': "📢 Каналы",
        'back': "🔙 Назад",
        'check_channels': "✅ Проверить каналы",
        'join_channels': "📢 Присоединиться",
        'earner': "👤 Зарабатывающий",
        'advertiser': "📢 Рекламодатель",
        'select_type': "Каким типом пользователя вы хотите быть?",
        'choose_lang': "🌐 Выберите язык:",
        'mandatory_channels': "📋 *Обязательные каналы*\n\nЧтобы использовать бота, вы должны присоединиться к каналам ниже:",
        'all_channels_joined': "✅ *Поздравляем!*\n\nВы присоединились ко всем каналам. Теперь вы можете начать выполнять задания.",
        'not_joined_all': "❌ *Вы еще не присоединились к некоторым каналам!*\n\nПожалуйста, присоединитесь к следующим каналам:",
        'main_menu': "🏠 *Главное меню*",
        'your_balance': "💰 *Ваш баланс:*",
        'min_withdraw': f"Минимальный вывод: ${MIN_WITHDRAW}",
        'min_deposit': f"Минимальный депозит: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 Поддержка: {SUPPORT_USERNAME}",
        'error': "❌ Ошибка",
        'success': "✅ Успешно"
    },
    'bn': {
        'welcome': "🤖 *TaskizBot-এ স্বাগতম!*\n\nটাকা উপার্জন করতে চ্যানেলে যোগ দিন এবং টাস্ক সম্পন্ন করুন।",
        'balance': "💰 ব্যালেন্স",
        'tasks': "🎯 টাস্ক",
        'withdraw': "🏧 উত্তোলন",
        'deposit': "💳 ডিপোজিট",
        'profile': "👤 প্রোফাইল",
        'referral': "👥 রেফারেল",
        'stats': "📊 পরিসংখ্যান",
        'help': "❓ সাহায্য",
        'channels': "📢 চ্যানেল",
        'back': "🔙 পিছনে",
        'check_channels': "✅ চ্যানেল চেক",
        'join_channels': "📢 যোগ দিন",
        'earner': "👤 আয়কারী",
        'advertiser': "📢 বিজ্ঞাপনদাতা",
        'select_type': "আপনি কি ধরণের ব্যবহারকারী হতে চান?",
        'choose_lang': "🌐 ভাষা নির্বাচন করুন:",
        'mandatory_channels': "📋 *বাধ্যতামূলক চ্যানেল*\n\nবট ব্যবহার করতে, আপনাকে নিচের চ্যানেলে যোগ দিতে হবে:",
        'all_channels_joined': "✅ *অভিনন্দন!*\n\nআপনি সব চ্যানেলে যোগ দিয়েছেন। এখন আপনি টাস্ক করা শুরু করতে পারেন।",
        'not_joined_all': "❌ *আপনি এখনও কিছু চ্যানেলে যোগ দেননি!*\n\nঅনুগ্রহ করে নিচের চ্যানেলে যোগ দিন:",
        'main_menu': "🏠 *প্রধান মেনু*",
        'your_balance': "💰 *আপনার ব্যালেন্স:*",
        'min_withdraw': f"ন্যূনতম উত্তোলন: ${MIN_WITHDRAW}",
        'min_deposit': f"ন্যূনতম ডিপোজিট: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 সমর্থন: {SUPPORT_USERNAME}",
        'error': "❌ ত্রুটি",
        'success': "✅ সফল"
    }
}

# Telegram API Fonksiyonları
def send_message(chat_id, text, reply_markup=None, parse_mode='Markdown'):
    """Telegram mesaj gönder"""
    url = BASE_URL + "sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': True
    }
    
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"❌ Mesaj gönderme hatası: {e}")
        return None

def edit_message_text(chat_id, message_id, text, reply_markup=None, parse_mode='Markdown'):
    """Telegram mesajını düzenle"""
    url = BASE_URL + "editMessageText"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': parse_mode
    }
    
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"❌ Mesaj düzenleme hatası: {e}")
        return None

def answer_callback_query(callback_query_id, text=None, show_alert=False):
    """Callback query'yi yanıtla"""
    url = BASE_URL + "answerCallbackQuery"
    payload = {
        'callback_query_id': callback_query_id
    }
    
    if text:
        payload['text'] = text
    if show_alert:
        payload['show_alert'] = show_alert
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"❌ Callback yanıtlama hatası: {e}")

def get_chat_member(chat_id, user_id):
    """Kullanıcının kanal üyeliğini kontrol et"""
    url = BASE_URL + "getChatMember"
    payload = {
        'chat_id': chat_id,
        'user_id': user_id
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        
        if data.get('ok'):
            status = data['result']['status']
            return status in ['member', 'administrator', 'creator']
        return False
    except Exception as e:
        print(f"❌ Üyelik kontrol hatası {chat_id}: {e}")
        return False

def delete_message(chat_id, message_id):
    """Mesaj sil"""
    url = BASE_URL + "deleteMessage"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id
    }
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"❌ Mesaj silme hatası: {e}")

# Database Sınıfı
class Database:
    def __init__(self, db_path='taskizbot.db'):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.setup_database()
    
    def setup_database(self):
        """Veritabanı tablolarını oluştur"""
        # Kullanıcılar tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT DEFAULT 'tr',
                balance REAL DEFAULT 0,
                user_type TEXT DEFAULT 'earner',
                referral_code TEXT UNIQUE,
                tasks_completed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Kanal kontrol kayıtları
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_username TEXT,
                joined INTEGER DEFAULT 0,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.connection.commit()
    
    def get_user(self, user_id):
        """Kullanıcı bilgilerini getir"""
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def create_user(self, user_id, username, first_name, last_name, language='tr'):
        """Yeni kullanıcı oluştur"""
        referral_code = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8].upper()
        
        self.cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, language, referral_code)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, language, referral_code))
        
        self.connection.commit()
        return self.get_user(user_id)
    
    def update_user_language(self, user_id, language):
        """Kullanıcı dilini güncelle"""
        self.cursor.execute('''
            UPDATE users SET language = ? WHERE user_id = ?
        ''', (language, user_id))
        self.connection.commit()
    
    def update_user_type(self, user_id, user_type):
        """Kullanıcı türünü güncelle"""
        self.cursor.execute('''
            UPDATE users SET user_type = ? WHERE user_id = ?
        ''', (user_type, user_id))
        self.connection.commit()
    
    def update_user_balance(self, user_id, amount):
        """Kullanıcı bakiyesini güncelle"""
        self.cursor.execute('''
            UPDATE users SET balance = balance + ? WHERE user_id = ?
        ''', (amount, user_id))
        self.connection.commit()
    
    def update_last_active(self, user_id):
        """Son aktif zamanını güncelle"""
        now = datetime.now().isoformat()
        self.cursor.execute('''
            UPDATE users SET last_active = ? WHERE user_id = ?
        ''', (now, user_id))
        self.connection.commit()
    
    def save_channel_check(self, user_id, channel_username, joined):
        """Kanal kontrol sonucunu kaydet"""
        self.cursor.execute('''
            INSERT OR REPLACE INTO channel_checks 
            (user_id, channel_username, joined, checked_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, channel_username, joined))
        self.connection.commit()
    
    def get_last_channel_check(self, user_id, channel_username):
        """Son kanal kontrolünü getir"""
        self.cursor.execute('''
            SELECT * FROM channel_checks 
            WHERE user_id = ? AND channel_username = ?
            ORDER BY checked_at DESC LIMIT 1
        ''', (user_id, channel_username))
        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None

# Bot Sınıfı
class TaskizBot:
    def __init__(self):
        self.db = Database()
        self.user_states = {}
        print("🤖 TaskizBot başlatıldı!")
    
    def handle_update(self, update):
        """Gelen update'i işle"""
        try:
            if 'message' in update:
                self.handle_message(update['message'])
            elif 'callback_query' in update:
                self.handle_callback_query(update['callback_query'])
        except Exception as e:
            print(f"❌ Update işleme hatası: {e}")
    
    def handle_message(self, message):
        """Gelen mesajı işle"""
        if 'text' not in message:
            return
        
        user_id = message['from']['id']
        text = message['text']
        
        # Kullanıcıyı veritabanında ara veya oluştur
        user = self.db.get_user(user_id)
        
        if not user:
            # Yeni kullanıcı kayıt akışı
            self.start_registration(message)
            return
        
        # Son aktif zamanını güncelle
        self.db.update_last_active(user_id)
        
        # Komutları işle
        self.process_command(user_id, text, user)
    
    def start_registration(self, message):
        """Yeni kullanıcı kaydı başlat"""
        user_id = message['from']['id']
        username = message['from'].get('username', '')
        first_name = message['from'].get('first_name', '')
        last_name = message['from'].get('last_name', '')
        
        # Kullanıcıyı oluştur
        user = self.db.create_user(user_id, username, first_name, last_name)
        
        # Dil seçimi göster
        self.show_language_selection(user_id)
    
    def show_language_selection(self, user_id):
        """Dil seçimini göster"""
        text = "🌐 *Please select your language / Lütfen dilinizi seçin*"
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '🇹🇷 Türkçe', 'callback_data': 'lang_tr'},
                    {'text': '🇺🇸 English', 'callback_data': 'lang_en'}
                ],
                [
                    {'text': '🇷🇺 Русский', 'callback_data': 'lang_ru'},
                    {'text': '🇧🇩 বাংলা', 'callback_data': 'lang_bn'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_callback_query(self, callback_query):
        """Callback query'leri işle"""
        data = callback_query['data']
        user_id = callback_query['from']['id']
        
        try:
            if data.startswith('lang_'):
                language = data.split('_')[1]
                self.handle_language_selection(user_id, language, callback_query['id'])
                
            elif data == 'check_channels':
                self.check_user_channels(user_id, callback_query['id'])
                
            elif data == 'show_main_menu':
                user = self.db.get_user(user_id)
                if user:
                    self.show_main_menu(user_id, user['language'])
                answer_callback_query(callback_query['id'])
                
            elif data == 'show_profile':
                self.show_profile(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data == 'show_balance':
                self.show_balance(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data == 'show_tasks':
                self.show_tasks(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data == 'show_withdraw':
                self.show_withdraw(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data == 'show_deposit':
                self.show_deposit(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data == 'show_referral':
                self.show_referral(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data == 'show_channels':
                self.show_channels(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data == 'show_help':
                self.show_help(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data.startswith('user_type_'):
                user_type = data.split('_')[2]
                self.handle_user_type_selection(user_id, user_type, callback_query['id'])
        
        except Exception as e:
            print(f"❌ Callback işleme hatası: {e}")
            answer_callback_query(callback_query['id'], "❌ Bir hata oluştu!")
    
    def handle_language_selection(self, user_id, language, callback_id):
        """Dil seçimini işle"""
        # Dili kaydet
        self.db.update_user_language(user_id, language)
        
        # Kullanıcı tipi seçimine geç
        self.show_user_type_selection(user_id, language)
        
        answer_callback_query(callback_id, "✅ Dil seçildi / Language selected!")
    
    def show_user_type_selection(self, user_id, language):
        """Kullanıcı tipi seçimini göster"""
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
{texts['select_type']}

👤 {texts['earner']} - Görev yaparak para kazan
📢 {texts['advertiser']} - Görev oluşturarak reklam ver
        """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': texts['earner'], 'callback_data': 'user_type_earner'},
                    {'text': texts['advertiser'], 'callback_data': 'user_type_advertiser'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_user_type_selection(self, user_id, user_type, callback_id):
        """Kullanıcı tipi seçimini işle"""
        # Kullanıcı tipini kaydet
        self.db.update_user_type(user_id, user_type)
        
        # Kanal kontrol ekranını göster
        user = self.db.get_user(user_id)
        self.show_channels(user_id)
        
        answer_callback_query(callback_id, "✅ Kullanıcı türü seçildi!")
    
    def check_user_channels(self, user_id, callback_id=None):
        """Kullanıcının kanallara katılımını kontrol et"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        not_joined = []
        all_joined = True
        
        for channel in MANDATORY_CHANNELS:
            joined = get_chat_member(f"@{channel['username']}", user_id)
            self.db.save_channel_check(user_id, channel['username'], joined)
            
            if not joined:
                not_joined.append(channel)
                all_joined = False
        
        if all_joined:
            text = texts['all_channels_joined']
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': texts['check_channels'], 'callback_data': 'check_channels'}],
                    [{'text': texts['main_menu'], 'callback_data': 'show_main_menu'}]
                ]
            }
            
            if callback_id:
                answer_callback_query(callback_id, "✅ Tüm kanallara katıldınız!")
                time.sleep(0.5)
            
            send_message(user_id, text, reply_markup=keyboard)
            
            # İlk kez tüm kanallara katıldıysa ana menüyü göster
            if 'first_channel_check' not in self.user_states.get(user_id, {}):
                self.user_states[user_id] = {'first_channel_check': True}
                time.sleep(1)
                self.show_main_menu(user_id, language)
        else:
            text = texts['not_joined_all'] + "\n\n"
            
            for channel in not_joined:
                text += f"• {channel['name']}: @{channel['username']}\n"
            
            text += f"\n{texts['contact_support']}"
            
            buttons = []
            for channel in not_joined:
                buttons.append([
                    {'text': f"✅ {channel['name']}'na katıl", 'url': channel['link']}
                ])
            
            buttons.append([
                {'text': texts['check_channels'], 'callback_data': 'check_channels'}
            ])
            
            keyboard = {'inline_keyboard': buttons}
            
            if callback_id:
                answer_callback_query(callback_id, "❌ Hala bazı kanallara katılmadınız!")
            
            send_message(user_id, text, reply_markup=keyboard)
    
    def show_channels(self, user_id):
        """Zorunlu kanalları göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = texts['mandatory_channels'] + "\n\n"
        
        for channel in MANDATORY_CHANNELS:
            text += f"• {channel['name']}: @{channel['username']}\n"
        
        text += f"\n{texts['contact_support']}"
        
        buttons = []
        for channel in MANDATORY_CHANNELS:
            buttons.append([
                {'text': f"✅ {channel['name']}'na katıl", 'url': channel['link']}
            ])
        
        buttons.append([
            {'text': texts['check_channels'], 'callback_data': 'check_channels'}
        ])
        
        keyboard = {'inline_keyboard': buttons}
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def process_command(self, user_id, text, user):
        """Komutları işle"""
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        if text == '/start':
            # Önce kanal kontrolü yap
            if not self.check_all_channels(user_id):
                self.show_channels(user_id)
            else:
                self.show_main_menu(user_id, language)
        
        elif text == texts['check_channels']:
            self.check_user_channels(user_id)
        
        elif text == texts['channels']:
            self.show_channels(user_id)
        
        elif text == texts['balance']:
            self.show_balance(user_id)
        
        elif text == texts['tasks']:
            self.show_tasks(user_id)
        
        elif text == texts['withdraw']:
            self.show_withdraw(user_id)
        
        elif text == texts['deposit']:
            self.show_deposit(user_id)
        
        elif text == texts['profile']:
            self.show_profile(user_id)
        
        elif text == texts['referral']:
            self.show_referral(user_id)
        
        elif text == texts['help']:
            self.show_help(user_id)
        
        elif text == texts['back']:
            self.show_main_menu(user_id, language)
        
        else:
            # Özel durumlar
            if user_id in self.user_states:
                state = self.user_states[user_id]
                # State işlemleri burada
                pass
            else:
                # Ana menüyü göster
                self.show_main_menu(user_id, language)
    
    def check_all_channels(self, user_id):
        """Tüm kanallara katılıp katılmadığını kontrol et"""
        for channel in MANDATORY_CHANNELS:
            if not get_chat_member(f"@{channel['username']}", user_id):
                return False
        return True
    
    def show_main_menu(self, user_id, language):
        """Ana menüyü göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Önce kanal kontrolü yap
        if not self.check_all_channels(user_id):
            self.show_channels(user_id)
            return
        
        # Kullanıcı bilgileri
        balance = user['balance']
        tasks_completed = user['tasks_completed']
        
        text = f"""
{texts['main_menu']}

{texts['your_balance']} ${balance:.2f}
🎯 Tamamlanan Görev: {tasks_completed}

{texts['contact_support']}
        """
        
        keyboard = {
            'keyboard': [
                [texts['tasks'], texts['balance']],
                [texts['withdraw'], texts['deposit']],
                [texts['referral'], texts['profile']],
                [texts['channels'], texts['help']]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_balance(self, user_id):
        """Bakiye bilgisini göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        balance = user['balance']
        
        text = f"""
{texts['your_balance']} ${balance:.2f}

{texts['min_withdraw']}
{texts['min_deposit']}

{texts['contact_support']}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': texts['deposit'], 'callback_data': 'show_deposit'}],
                [{'text': texts['withdraw'], 'callback_data': 'show_withdraw'}],
                [{'text': texts['back'], 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_tasks(self, user_id):
        """Görevleri göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
🎯 *Görevler*

Şu anda mevcut görev bulunmuyor.

Yakında yeni görevler eklenecek!

{texts['contact_support']}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': texts['check_channels'], 'callback_data': 'check_channels'}],
                [{'text': texts['back'], 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_withdraw(self, user_id):
        """Para çekme ekranını göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        balance = user['balance']
        
        text = f"""
🏧 *Para Çekme*

Mevcut bakiye: ${balance:.2f}
{texts['min_withdraw']}

Para çekmek için destekle iletişime geçin:
{SUPPORT_USERNAME}

{texts['contact_support']}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': texts['back'], 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_deposit(self, user_id):
        """Bakiye yükleme ekranını göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
💳 *Bakiye Yükleme*

{texts['min_deposit']}

Bakiye yüklemek için destekle iletişime geçin:
{SUPPORT_USERNAME}

TRX adresiniz hazırsa gönderebilirsiniz:
`{TRX_ADDRESS}`

⚠️ Sadece TRX (Tron) gönderin!
⚠️ Farklı coin gönderirseniz kaybolur!

{texts['contact_support']}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': texts['back'], 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_profile(self, user_id):
        """Profil ekranını göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        lang_info = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES['tr'])
        
        text = f"""
👤 *Profil*

🆔 ID: {user_id}
👤 Ad: {user['first_name']} {user['last_name'] or ''}
📛 Kullanıcı adı: @{user['username'] or 'Yok'}
🌐 Dil: {lang_info['name']} {lang_info['flag']}
💰 Bakiye: ${user['balance']:.2f}
🎯 Görev: {user['tasks_completed']}
📅 Kayıt: {user['created_at'][:10] if user['created_at'] else '-'}

{texts['contact_support']}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': texts['back'], 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_referral(self, user_id):
        """Referans ekranını göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        referral_code = user['referral_code']
        bot_username = TOKEN.split(':')[0] if ':' in TOKEN else 'taskizbot'
        referral_link = f"https://t.me/{bot_username}?start={referral_code}"
        
        text = f"""
👥 *Referans Programı*

🔗 Referans Linkiniz:
`{referral_link}`

📋 Referans Kodunuz:
`{referral_code}`

💡 *Nasıl Çalışır?*
1. Linkinizi paylaşın
2. Arkadaşlarınız botu kullanmaya başlasın
3. Onlar görev yaptıkça siz kazanın!

{texts['contact_support']}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': texts['back'], 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_help(self, user_id):
        """Yardım ekranını göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
❓ *Yardım*

🤖 *TaskizBot Nedir?*
Görev tamamlayarak para kazanabileceğiniz bir platform.

🎯 *Nasıl Para Kazanırım?*
1. Zorunlu kanallara katılın
2. Görevleri tamamlayın
3. Kazandığınız parayı çekin

💰 *Ödemeler:*
• Minimum çekim: ${MIN_WITHDRAW}
• TRX (Tron) cüzdanınıza ödeme

⚠️ *Kurallar:*
• Sahte görev yapmak yasaktır
• Kurallara uymayanlar banlanır

📞 *Destek:*
Sorularınız için iletişime geçin:
{SUPPORT_USERNAME}

{texts['contact_support']}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': texts['channels'], 'callback_data': 'show_channels'}],
                [{'text': texts['back'], 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)

# Botu başlat
bot = TaskizBot()

# Flask server'ı başlat
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    # Webhook ayarla
    webhook_url = os.environ.get('WEBHOOK_URL', '')
    if webhook_url:
        response = requests.get(f"{BASE_URL}setWebhook?url={webhook_url}/webhook")
        print(f"Webhook ayarlandı: {response.json()}")
    
    app.run(host='0.0.0.0', port=port, debug=False)
