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
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# Zorunlu Kanallar (Güncellendi - instagram ve binance kaldırıldı)
MANDATORY_CHANNELS = [
    {
        'username': 'EarnTether2026',
        'link': 'https://t.me/EarnTether2026',
        'name': 'Ana Kanal',
        'emoji': '📢'
    },
    {
        'username': 'TaskizLive',
        'link': 'https://t.me/TaskizLive',
        'name': 'Canlı İstatistik',
        'emoji': '📊'
    }
]

if not TOKEN:
    raise ValueError("Bot token gerekli!")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Dil ve Para Birimi Ayarları (Portekizce eklendi)
SUPPORTED_LANGUAGES = {
    'tr': {'name': 'Türkçe', 'flag': '🇹🇷', 'currency': 'TRY'},
    'en': {'name': 'English', 'flag': '🇺🇸', 'currency': 'USD'},
    'ru': {'name': 'Русский', 'flag': '🇷🇺', 'currency': 'RUB'},
    'bn': {'name': 'বাংলা', 'flag': '🇧🇩', 'currency': 'BDT'},
    'pt': {'name': 'Português', 'flag': '🇵🇹', 'currency': 'BRL'}
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
    return jsonify({"status": "online", "bot": "TaskizBot v3.4", "webhook": bool(WEBHOOK_URL)})

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    bot.handle_update(update)
    return jsonify({"status": "ok"})

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    """Webhook'u manuel ayarlama endpoint'i"""
    if not WEBHOOK_URL:
        return jsonify({"error": "WEBHOOK_URL env değişkeni ayarlanmamış"})
    
    url = f"{WEBHOOK_URL}/webhook"
    response = requests.get(f"{BASE_URL}setWebhook?url={url}")
    
    info = requests.get(f"{BASE_URL}getWebhookInfo").json()
    
    return jsonify({
        "set_webhook": response.json(),
        "webhook_info": info
    })

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot": "TaskizBot"
    })

def get_turkey_time():
    return datetime.now(TURKEY_TZ)

# Dil Metinleri (Portekizce eklendi)
LANGUAGE_TEXTS = {
    'tr': {
        'welcome': "🎉 *TaskizBot'a Hoş Geldiniz!*\n\n✨ Görev tamamlayarak para kazanın 💰",
        'balance': "💰 Bakiye",
        'tasks': "🎯 Görevler",
        'withdraw': "🏧 Para Çek",
        'deposit': "💳 Yükle",
        'profile': "👤 Profil",
        'referral': "👥 Referans",
        'stats': "📊 İstatistik",
        'help': "❓ Yardım",
        'channels': "📢 Kanallar",
        'back': "🔙 Geri",
        'check_channels': "🔍 Kontrol Et",
        'join_channels': "➕ Katıl",
        'earner': "👤 Kazanan",
        'advertiser': "📢 Reklamveren",
        'select_type': "🌟 *Hangi tür kullanıcı olmak istiyorsunuz?*",
        'choose_lang': "🌍 *Dilinizi seçin:*",
        'mandatory_channels': "📋 *Zorunlu Kanallar*\n\nBotu kullanmak için tüm kanallara katılmalısınız:",
        'all_channels_joined': "🎊 *Tebrikler!*\n\n✅ Tüm kanallara katıldınız!\n\n🎯 Şimdi görev yapmaya başlayabilirsiniz!",
        'not_joined_all': "⚠️ *Eksik Kanallar*\n\nHenüz bazı kanallara katılmadınız:",
        'main_menu': "🏠 *Ana Menü*",
        'your_balance': "💰 *Bakiyeniz:*",
        'min_withdraw': f"📉 Minimum çekim: ${MIN_WITHDRAW}",
        'min_deposit': f"📈 Minimum yükleme: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 Destek: {SUPPORT_USERNAME}",
        'error': "❌ Hata",
        'success': "✅ Başarılı",
        'loading': "⏳ Yükleniyor...",
        'welcome_back': "👋 Tekrar Hoş Geldiniz!",
        'joined': "✅ Katıldınız",
        'not_joined': "❌ Katılmadınız",
        'channel_status': "📊 *Kanal Durumu*",
        'checking': "🔍 Kontrol ediliyor...",
        'join_now': "🚀 Hemen Katıl",
        'available_tasks': "🎯 *Mevcut Görevler*",
        'no_tasks': "📭 Şu anda mevcut görev bulunmuyor",
        'task_reward': "💰 Ödül",
        'task_participants': "👥 Katılımcı",
        'join_task': "🎯 Göreve Katıl",
        'deposit_info': "💳 *Bakiye Yükleme Bilgileri*",
        'withdraw_info': "🏧 *Para Çekme Bilgileri*",
        'referral_info': "👥 *Referans Programı*",
        'profile_info': "👤 *Profil Bilgileri*",
        'help_info': "❓ *Yardım Merkezi*"
    },
    'en': {
        'welcome': "🎉 *Welcome to TaskizBot!*\n\n✨ Complete tasks and earn money 💰",
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
        'check_channels': "🔍 Check",
        'join_channels': "➕ Join",
        'earner': "👤 Earner",
        'advertiser': "📢 Advertiser",
        'select_type': "🌟 *What type of user do you want to be?*",
        'choose_lang': "🌍 *Choose your language:*",
        'mandatory_channels': "📋 *Mandatory Channels*\n\nTo use the bot, you must join all channels:",
        'all_channels_joined': "🎊 *Congratulations!*\n\n✅ You have joined all channels!\n\n🎯 You can now start doing tasks!",
        'not_joined_all': "⚠️ *Missing Channels*\n\nYou haven't joined some channels yet:",
        'main_menu': "🏠 *Main Menu*",
        'your_balance': "💰 *Your Balance:*",
        'min_withdraw': f"📉 Minimum withdrawal: ${MIN_WITHDRAW}",
        'min_deposit': f"📈 Minimum deposit: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 Support: {SUPPORT_USERNAME}",
        'error': "❌ Error",
        'success': "✅ Success",
        'loading': "⏳ Loading...",
        'welcome_back': "👋 Welcome Back!",
        'joined': "✅ Joined",
        'not_joined': "❌ Not Joined",
        'channel_status': "📊 *Channel Status*",
        'checking': "🔍 Checking...",
        'join_now': "🚀 Join Now",
        'available_tasks': "🎯 *Available Tasks*",
        'no_tasks': "📭 No tasks available at the moment",
        'task_reward': "💰 Reward",
        'task_participants': "👥 Participants",
        'join_task': "🎯 Join Task",
        'deposit_info': "💳 *Deposit Information*",
        'withdraw_info': "🏧 *Withdrawal Information*",
        'referral_info': "👥 *Referral Program*",
        'profile_info': "👤 *Profile Information*",
        'help_info': "❓ *Help Center*"
    },
    'ru': {
        'welcome': "🎉 *Добро пожаловать в TaskizBot!*\n\n✨ Выполняйте задания и зарабатывайте деньги 💰",
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
        'check_channels': "🔍 Проверить",
        'join_channels': "➕ Присоединиться",
        'earner': "👤 Зарабатывающий",
        'advertiser': "📢 Рекламодатель",
        'select_type': "🌟 *Каким типом пользователя вы хотите быть?*",
        'choose_lang': "🌍 *Выберите язык:*",
        'mandatory_channels': "📋 *Обязательные каналы*\n\nЧтобы использовать бота, вы должны присоединиться ко всем каналам:",
        'all_channels_joined': "🎊 *Поздравляем!*\n\n✅ Вы присоединились ко всем каналам!\n\n🎯 Теперь вы можете начать выполнять задания!",
        'not_joined_all': "⚠️ *Отсутствующие каналы*\n\nВы еще не присоединились к некоторым каналам:",
        'main_menu': "🏠 *Главное меню*",
        'your_balance': "💰 *Ваш баланс:*",
        'min_withdraw': f"📉 Минимальный вывод: ${MIN_WITHDRAW}",
        'min_deposit': f"📈 Минимальный депозит: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 Поддержка: {SUPPORT_USERNAME}",
        'error': "❌ Ошибка",
        'success': "✅ Успешно",
        'loading': "⏳ Загрузка...",
        'welcome_back': "👋 С возвращением!",
        'joined': "✅ Присоединились",
        'not_joined': "❌ Не присоединились",
        'channel_status': "📊 *Статус каналов*",
        'checking': "🔍 Проверка...",
        'join_now': "🚀 Присоединиться",
        'available_tasks': "🎯 *Доступные задания*",
        'no_tasks': "📭 В данный момент заданий нет",
        'task_reward': "💰 Награда",
        'task_participants': "👥 Участники",
        'join_task': "🎯 Присоединиться",
        'deposit_info': "💳 *Информация о пополнении*",
        'withdraw_info': "🏧 *Информация о выводе*",
        'referral_info': "👥 *Реферальная программа*",
        'profile_info': "👤 *Информация о профиле*",
        'help_info': "❓ *Центр помощи*"
    },
    'bn': {
        'welcome': "🎉 *TaskizBot-এ স্বাগতম!*\n\n✨ টাস্ক সম্পূর্ণ করে অর্থ উপার্জন করুন 💰",
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
        'check_channels': "🔍 চেক",
        'join_channels': "➕ যোগ দিন",
        'earner': "👤 আয়কারী",
        'advertiser': "📢 বিজ্ঞাপনদাতা",
        'select_type': "🌟 *আপনি কি ধরণের ব্যবহারকারী হতে চান?*",
        'choose_lang': "🌍 *ভাষা নির্বাচন করুন:*",
        'mandatory_channels': "📋 *বাধ্যতামূলক চ্যানেল*\n\nবট ব্যবহার করতে, আপনাকে সব চ্যানেলে যোগ দিতে হবে:",
        'all_channels_joined': "🎊 *অভিনন্দন!*\n\n✅ আপনি সব চ্যানেলে যোগ দিয়েছেন!\n\n🎯 এখন আপনি টাস্ক করা শুরু করতে পারেন!",
        'not_joined_all': "⚠️ *অনুপস্থিত চ্যানেল*\n\nআপনি এখনও কিছু চ্যানেলে যোগ দেননি:",
        'main_menu': "🏠 *প্রধান মেনু*",
        'your_balance': "💰 *আপনার ব্যালেন্স:*",
        'min_withdraw': f"📉 ন্যূনতম উত্তোলন: ${MIN_WITHDRAW}",
        'min_deposit': f"📈 ন্যূনতম ডিপোজিট: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 সমর্থন: {SUPPORT_USERNAME}",
        'error': "❌ ত্রুটি",
        'success': "✅ সফল",
        'loading': "⏳ লোড হচ্ছে...",
        'welcome_back': "👋 পুনরায় স্বাগতম!",
        'joined': "✅ যোগ দিয়েছেন",
        'not_joined': "❌ যোগ দেননি",
        'channel_status': "📊 *চ্যানেল স্ট্যাটাস*",
        'checking': "🔍 চেক করা হচ্ছে...",
        'join_now': "🚀 এখনই যোগ দিন",
        'available_tasks': "🎯 *উপলব্ধ টাস্ক*",
        'no_tasks': "📭 এই মুহূর্তে কোন টাস্ক নেই",
        'task_reward': "💰 পুরস্কার",
        'task_participants': "👥 অংশগ্রহণকারী",
        'join_task': "🎯 টাস্কে যোগ দিন",
        'deposit_info': "💳 *ডিপোজিট তথ্য*",
        'withdraw_info': "🏧 *উত্তোলন তথ্য*",
        'referral_info': "👥 *রেফারেল প্রোগ্রাম*",
        'profile_info': "👤 *প্রোফাইল তথ্য*",
        'help_info': "❓ *সাহায্য কেন্দ্র*"
    },
    'pt': {
        'welcome': "🎉 *Bem-vindo ao TaskizBot!*\n\n✨ Complete tarefas e ganhe dinheiro 💰",
        'balance': "💰 Saldo",
        'tasks': "🎯 Tarefas",
        'withdraw': "🏧 Sacar",
        'deposit': "💳 Depositar",
        'profile': "👤 Perfil",
        'referral': "👥 Indicação",
        'stats': "📊 Estatísticas",
        'help': "❓ Ajuda",
        'channels': "📢 Canais",
        'back': "🔙 Voltar",
        'check_channels': "🔍 Verificar",
        'join_channels': "➕ Entrar",
        'earner': "👤 Ganhador",
        'advertiser': "📢 Anunciante",
        'select_type': "🌟 *Que tipo de usuário você quer ser?*",
        'choose_lang': "🌍 *Escolha seu idioma:*",
        'mandatory_channels': "📋 *Canais Obrigatórios*\n\nPara usar o bot, você deve entrar em todos os canais:",
        'all_channels_joined': "🎊 *Parabéns!*\n\n✅ Você entrou em todos os canais!\n\n🎯 Agora você pode começar a fazer tarefas!",
        'not_joined_all': "⚠️ *Canais Faltantes*\n\nVocê ainda não entrou em alguns canais:",
        'main_menu': "🏠 *Menu Principal*",
        'your_balance': "💰 *Seu Saldo:*",
        'min_withdraw': f"📉 Saque mínimo: ${MIN_WITHDRAW}",
        'min_deposit': f"📈 Depósito mínimo: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 Suporte: {SUPPORT_USERNAME}",
        'error': "❌ Erro",
        'success': "✅ Sucesso",
        'loading': "⏳ Carregando...",
        'welcome_back': "👋 Bem-vindo de volta!",
        'joined': "✅ Entrou",
        'not_joined': "❌ Não entrou",
        'channel_status': "📊 *Status dos Canais*",
        'checking': "🔍 Verificando...",
        'join_now': "🚀 Entrar Agora",
        'available_tasks': "🎯 *Tarefas Disponíveis*",
        'no_tasks': "📭 Nenhuma tarefa disponível no momento",
        'task_reward': "💰 Recompensa",
        'task_participants': "👥 Participantes",
        'join_task': "🎯 Entrar na Tarefa",
        'deposit_info': "💳 *Informações de Depósito*",
        'withdraw_info': "🏧 *Informações de Saque*",
        'referral_info': "👥 *Programa de Indicação*",
        'profile_info': "👤 *Informações do Perfil*",
        'help_info': "❓ *Central de Ajuda*"
    }
}

# Telegram API Fonksiyonları
def send_message(chat_id, text, reply_markup=None, parse_mode='Markdown'):
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
    url = BASE_URL + "answerCallbackQuery"
    payload = {
        'callback_query_id': callback_query_id
    }
    
    if text:
        payload['text'] = text
    if show_alert:
        payload['show_alert'] = show_alert
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        return response
    except Exception as e:
        print(f"❌ Callback yanıtlama hatası: {e}")
        return None

def get_chat_member(chat_id, user_id):
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

# Database Sınıfı
class Database:
    def __init__(self, db_path='taskizbot.db'):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.setup_database()
    
    def setup_database(self):
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
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, channel_username)
            )
        ''')
        
        # Görevler tablosu (basit versiyon)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                reward REAL,
                max_participants INTEGER,
                current_participants INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Görev katılımları
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_participations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (id)
            )
        ''')
        
        # Örnek görevler ekle
        self.add_sample_tasks()
        
        self.connection.commit()
        print("✅ Veritabanı tabloları oluşturuldu")
    
    def add_sample_tasks(self):
        """Örnek görevler ekle"""
        self.cursor.execute('SELECT COUNT(*) FROM tasks')
        if self.cursor.fetchone()[0] == 0:
            sample_tasks = [
                ('Telegram Kanalına Katıl', '@EarnTether2026 kanalına katılın', 0.05, 100),
                ('Botu Beğen', 'Botu beğenin ve yorum yapın', 0.03, 50),
                ('Gönderi Paylaş', 'Belirtilen gönderiyi paylaşın', 0.08, 30),
                ('Yorum Yap', 'Belirtilen gönderiye yorum yapın', 0.02, 200),
                ('Grup Katılımı', 'Özel gruba katılın', 0.10, 20)
            ]
            
            for task in sample_tasks:
                self.cursor.execute('''
                    INSERT INTO tasks (title, description, reward, max_participants)
                    VALUES (?, ?, ?, ?)
                ''', task)
            
            print("✅ Örnek görevler eklendi")
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def create_user(self, user_id, username, first_name, last_name, language='tr'):
        referral_code = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8].upper()
        
        self.cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, language, referral_code)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, language, referral_code))
        
        self.connection.commit()
        return self.get_user(user_id)
    
    def update_user_language(self, user_id, language):
        self.cursor.execute('''
            UPDATE users SET language = ? WHERE user_id = ?
        ''', (language, user_id))
        self.connection.commit()
    
    def update_user_type(self, user_id, user_type):
        self.cursor.execute('''
            UPDATE users SET user_type = ? WHERE user_id = ?
        ''', (user_type, user_id))
        self.connection.commit()
    
    def update_user_balance(self, user_id, amount):
        self.cursor.execute('''
            UPDATE users SET balance = balance + ? WHERE user_id = ?
        ''', (amount, user_id))
        self.connection.commit()
    
    def update_last_active(self, user_id):
        now = datetime.now().isoformat()
        self.cursor.execute('''
            UPDATE users SET last_active = ? WHERE user_id = ?
        ''', (now, user_id))
        self.connection.commit()
    
    def save_channel_check(self, user_id, channel_username, joined):
        self.cursor.execute('''
            INSERT OR REPLACE INTO channel_checks 
            (user_id, channel_username, joined, checked_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, channel_username, joined))
        self.connection.commit()
    
    def get_channel_status(self, user_id, channel_username):
        self.cursor.execute('''
            SELECT joined FROM channel_checks 
            WHERE user_id = ? AND channel_username = ?
            ORDER BY checked_at DESC LIMIT 1
        ''', (user_id, channel_username))
        row = self.cursor.fetchone()
        return row[0] if row else None
    
    def get_active_tasks(self):
        """Aktif görevleri getir"""
        self.cursor.execute('''
            SELECT * FROM tasks 
            WHERE status = 'active' 
            AND current_participants < max_participants
            ORDER BY created_at DESC
            LIMIT 10
        ''')
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows]
    
    def join_task(self, user_id, task_id):
        """Göreve katıl"""
        # Önce katılıp katılmadığını kontrol et
        self.cursor.execute('''
            SELECT COUNT(*) FROM task_participations 
            WHERE task_id = ? AND user_id = ?
        ''', (task_id, user_id))
        
        if self.cursor.fetchone()[0] > 0:
            return False, "already_joined"
        
        # Görev detaylarını al
        self.cursor.execute('''
            SELECT reward, max_participants, current_participants
            FROM tasks WHERE id = ? AND status = 'active'
        ''', (task_id,))
        
        task = self.cursor.fetchone()
        if not task:
            return False, "task_not_found"
        
        if task['current_participants'] >= task['max_participants']:
            return False, "task_full"
        
        # Katılım kaydı oluştur
        self.cursor.execute('''
            INSERT INTO task_participations (task_id, user_id, status)
            VALUES (?, ?, 'pending')
        ''', (task_id, user_id))
        
        # Görev katılımcı sayısını güncelle
        self.cursor.execute('''
            UPDATE tasks SET current_participants = current_participants + 1 
            WHERE id = ?
        ''', (task_id,))
        
        self.connection.commit()
        return True, "success"
    
    def get_task(self, task_id):
        """Görev detaylarını getir"""
        self.cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
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
        try:
            if 'message' in update:
                self.handle_message(update['message'])
            elif 'callback_query' in update:
                self.handle_callback_query(update['callback_query'])
        except Exception as e:
            print(f"❌ Update işleme hatası: {e}")
    
    def handle_message(self, message):
        if 'text' not in message:
            return
        
        user_id = message['from']['id']
        text = message['text']
        
        user = self.db.get_user(user_id)
        
        if not user:
            self.start_registration(message)
            return
        
        self.db.update_last_active(user_id)
        self.process_command(user_id, text, user)
    
    def start_registration(self, message):
        user_id = message['from']['id']
        username = message['from'].get('username', '')
        first_name = message['from'].get('first_name', '')
        last_name = message['from'].get('last_name', '')
        
        user = self.db.create_user(user_id, username, first_name, last_name, 'tr')
        self.show_language_selection(user_id)
    
    def show_language_selection(self, user_id):
        text = """
🌍 *Dil Seçimi / Language Selection*

Lütfen dilinizi seçin / Please select your language:
        """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '🇹🇷 Türkçe', 'callback_data': 'lang_tr'},
                    {'text': '🇺🇸 English', 'callback_data': 'lang_en'},
                    {'text': '🇷🇺 Русский', 'callback_data': 'lang_ru'}
                ],
                [
                    {'text': '🇧🇩 বাংলা', 'callback_data': 'lang_bn'},
                    {'text': '🇵🇹 Português', 'callback_data': 'lang_pt'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_callback_query(self, callback_query):
        data = callback_query['data']
        user_id = callback_query['from']['id']
        callback_id = callback_query['id']
        
        try:
            if data.startswith('lang_'):
                language = data.split('_')[1]
                self.handle_language_selection(user_id, language, callback_id)
                
            elif data == 'check_channels':
                answer_callback_query(callback_id, "🔍 Kontrol ediliyor...")
                time.sleep(0.3)
                self.check_user_channels(user_id, show_detailed=True)
                
            elif data == 'show_main_menu':
                user = self.db.get_user(user_id)
                if user:
                    self.show_main_menu(user_id, user['language'])
                answer_callback_query(callback_id)
                
            elif data == 'show_profile':
                self.show_profile(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'show_balance':
                self.show_balance(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'show_tasks':
                self.show_tasks(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'show_withdraw':
                self.show_withdraw(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'show_deposit':
                self.show_deposit(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'show_referral':
                self.show_referral(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'show_channels':
                self.show_channels_detailed(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'show_help':
                self.show_help(user_id)
                answer_callback_query(callback_id)
                
            elif data.startswith('user_type_'):
                user_type = data.split('_')[2]
                self.handle_user_type_selection(user_id, user_type, callback_id)
                
            elif data == 'refresh_channels':
                answer_callback_query(callback_id, "🔄 Yenileniyor...")
                time.sleep(0.3)
                self.check_user_channels(user_id, show_detailed=True)
                
            elif data.startswith('join_task_'):
                task_id = int(data.split('_')[2])
                self.handle_join_task(user_id, task_id, callback_id)
                
            elif data == 'refresh_tasks':
                answer_callback_query(callback_id, "🔄 Görevler yenileniyor...")
                time.sleep(0.3)
                self.show_tasks(user_id)
                
            elif data == 'copy_ref':
                user = self.db.get_user(user_id)
                if user:
                    referral_code = user['referral_code']
                    answer_callback_query(callback_id, f"📋 Referans kodunuz: {referral_code}\n\nKopyalandı!", show_alert=True)
        
        except Exception as e:
            print(f"❌ Callback işleme hatası: {e}")
            answer_callback_query(callback_id, "❌ Bir hata oluştu!")
    
    def handle_language_selection(self, user_id, language, callback_id):
        self.db.update_user_language(user_id, language)
        self.show_user_type_selection(user_id, language)
        answer_callback_query(callback_id, "✅ Dil seçildi!")
    
    def show_user_type_selection(self, user_id, language):
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
{texts['select_type']}

{texts['earner']} - 🎯 Görev yap, 💰 para kazan
{texts['advertiser']} - 📢 Görev oluştur, 🎯 kitleni bul
        """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': f"{texts['earner']} 👤", 'callback_data': 'user_type_earner'},
                    {'text': f"{texts['advertiser']} 📢", 'callback_data': 'user_type_advertiser'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_user_type_selection(self, user_id, user_type, callback_id):
        self.db.update_user_type(user_id, user_type)
        answer_callback_query(callback_id, "✅ Kullanıcı türü seçildi!")
        time.sleep(0.5)
        
        self.show_channels_detailed(user_id)
    
    def check_user_channels(self, user_id, show_detailed=False):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        channel_status = []
        all_joined = True
        
        for channel in MANDATORY_CHANNELS:
            joined = get_chat_member(f"@{channel['username']}", user_id)
            self.db.save_channel_check(user_id, channel['username'], joined)
            
            channel_status.append({
                'channel': channel,
                'joined': joined
            })
            
            if not joined:
                all_joined = False
        
        if all_joined:
            if show_detailed:
                self.show_channel_status(user_id, channel_status, all_joined)
            else:
                text = f"""
{texts['all_channels_joined']}

✨ *Tebrikler!* Tüm kanallara katıldınız.
🎯 Şimdi görev yapmaya başlayabilirsiniz!
                """
                
                keyboard = {
                    'inline_keyboard': [
                        [{'text': "🎯 Görevlere Başla", 'callback_data': 'show_tasks'}],
                        [{'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}]
                    ]
                }
                
                send_message(user_id, text, reply_markup=keyboard)
                time.sleep(1)
                self.show_main_menu(user_id, language)
        else:
            self.show_channel_status(user_id, channel_status, all_joined)
    
    def show_channel_status(self, user_id, channel_status, all_joined):
        user = self.db.get_user(user_id)
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        if all_joined:
            status_emoji = "✅"
            status_text = "Tüm Kanallara Katıldınız"
        else:
            status_emoji = "⚠️"
            status_text = "Eksik Kanallar Var"
        
        text = f"""
{texts['channel_status']}

{status_emoji} *{status_text}*

"""
        
        for status in channel_status:
            channel = status['channel']
            joined = status['joined']
            
            status_icon = "✅" if joined else "❌"
            text += f"{status_icon} {channel['emoji']} *{channel['name']}*\n"
            text += f"   👉 @{channel['username']}\n\n"
        
        text += f"\n{texts['contact_support']}"
        
        buttons = []
        
        # Katılma butonları (sadece katılmadıkları için)
        for status in channel_status:
            if not status['joined']:
                channel = status['channel']
                buttons.append([
                    {'text': f"➕ {channel['emoji']} {channel['name']}'na katıl", 'url': channel['link']}
                ])
        
        # Kontrol butonları
        buttons.append([
            {'text': "🔄 Yenile", 'callback_data': 'refresh_channels'},
            {'text': "🔍 Detaylı Kontrol", 'callback_data': 'check_channels'}
        ])
        
        if all_joined:
            buttons.append([
                {'text': "🚀 Ana Menüye Git", 'callback_data': 'show_main_menu'}
            ])
        
        keyboard = {'inline_keyboard': buttons}
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_channels_detailed(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
{texts['mandatory_channels']}

Botu kullanmak için *tüm kanallara* katılmanız gerekiyor:

"""
        
        for channel in MANDATORY_CHANNELS:
            text += f"{channel['emoji']} *{channel['name']}*\n"
            text += f"   👉 @{channel['username']}\n\n"
        
        text += f"🎯 *Adımlar:*\n"
        text += f"1️⃣ Aşağıdaki butonlarla kanallara katıl\n"
        text += f"2️⃣ '🔍 Kontrol Et' butonuna tıkla\n"
        text += f"3️⃣ Tüm kanallara katıldıysan görevlere başla!\n\n"
        text += f"{texts['contact_support']}"
        
        buttons = []
        
        # Her kanal için katılma butonu
        for channel in MANDATORY_CHANNELS:
            buttons.append([
                {'text': f"{channel['emoji']} {channel['name']}'na katıl", 'url': channel['link']}
            ])
        
        # Kontrol butonları
        buttons.append([
            {'text': "🔍 Kontrol Et", 'callback_data': 'check_channels'},
            {'text': "🔄 Yenile", 'callback_data': 'refresh_channels'}
        ])
        
        keyboard = {'inline_keyboard': buttons}
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def process_command(self, user_id, text, user):
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Tüm komutları küçük harfe çevir
        text_lower = text.lower().strip()
        
        # Komut eşleştirme
        if text_lower == '/start' or text_lower == 'start':
            self.handle_start(user_id, language)
        
        elif text_lower == '/check' or text_lower == texts['check_channels'].lower():
            self.check_user_channels(user_id, show_detailed=True)
        
        elif text_lower == '/channels' or text_lower == texts['channels'].lower():
            self.show_channels_detailed(user_id)
        
        elif text_lower == '/balance' or text_lower == texts['balance'].lower():
            self.show_balance(user_id)
        
        elif text_lower == '/tasks' or text_lower == texts['tasks'].lower():
            self.show_tasks(user_id)
        
        elif text_lower == '/withdraw' or text_lower == texts['withdraw'].lower():
            self.show_withdraw(user_id)
        
        elif text_lower == '/deposit' or text_lower == texts['deposit'].lower():
            self.show_deposit(user_id)
        
        elif text_lower == '/profile' or text_lower == texts['profile'].lower():
            self.show_profile(user_id)
        
        elif text_lower == '/referral' or text_lower == texts['referral'].lower():
            self.show_referral(user_id)
        
        elif text_lower == '/help' or text_lower == texts['help'].lower():
            self.show_help(user_id)
        
        elif text_lower == '/menu' or text_lower == texts['back'].lower():
            self.show_main_menu(user_id, language)
        
        else:
            # Ana menüyü göster
            self.show_main_menu(user_id, language)
    
    def handle_start(self, user_id, language):
        if not self.check_all_channels(user_id):
            self.show_channels_detailed(user_id)
        else:
            texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
            send_message(user_id, f"👋 {texts['welcome_back']}")
            self.show_main_menu(user_id, language)
    
    def check_all_channels(self, user_id):
        for channel in MANDATORY_CHANNELS:
            if not get_chat_member(f"@{channel['username']}", user_id):
                return False
        return True
    
    def show_main_menu(self, user_id, language):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        if not self.check_all_channels(user_id):
            self.show_channels_detailed(user_id)
            return
        
        balance = user['balance']
        tasks_completed = user['tasks_completed']
        
        text = f"""
{texts['main_menu']}

💰 *Bakiye:* `${balance:.2f}`
🎯 *Tamamlanan Görev:* `{tasks_completed}`
👤 *Durum:* `Aktif`

✨ *Ne yapmak istersiniz?*
        """
        
        keyboard = {
            'keyboard': [
                [f"🎯 {texts['tasks']}", f"💰 {texts['balance']}"],
                [f"🏧 {texts['withdraw']}", f"💳 {texts['deposit']}"],
                [f"👥 {texts['referral']}", f"👤 {texts['profile']}"],
                [f"📢 {texts['channels']}", f"❓ {texts['help']}"]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_tasks(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Aktif görevleri getir
        tasks = self.db.get_active_tasks()
        
        if not tasks:
            text = f"""
{texts['available_tasks']}

{texts['no_tasks']}

🔄 Yeni görevler yakında eklenecek!
            """
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': "🔄 Görevleri Yenile", 'callback_data': 'refresh_tasks'}],
                    [{'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}]
                ]
            }
        else:
            text = f"""
{texts['available_tasks']}

🎯 *Toplam {len(tasks)} görev bulundu:*

"""
            
            buttons = []
            for task in tasks:
                text += f"""
🔸 *{task['title']}*
📝 {task['description']}
💰 {texts['task_reward']}: `${task['reward']:.2f}`
👥 {task['current_participants']}/{task['max_participants']} {texts['task_participants']}

"""
                buttons.append([
                    {'text': f"🎯 {task['title'][:20]}... (${task['reward']:.2f})", 
                     'callback_data': f'join_task_{task["id"]}'}
                ])
            
            buttons.append([
                {'text': "🔄 Görevleri Yenile", 'callback_data': 'refresh_tasks'},
                {'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}
            ])
            
            keyboard = {'inline_keyboard': buttons}
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_join_task(self, user_id, task_id, callback_id):
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Kullanıcı bulunamadı!")
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Önce kanal kontrolü yap
        if not self.check_all_channels(user_id):
            answer_callback_query(callback_id, texts['not_joined_all'], show_alert=True)
            time.sleep(1)
            self.show_channels_detailed(user_id)
            return
        
        # Göreve katıl
        success, message = self.db.join_task(user_id, task_id)
        
        if success:
            # Görev detaylarını al
            task = self.db.get_task(task_id)
            if task:
                # Kullanıcı bakiyesine ödülü ekle
                self.db.update_user_balance(user_id, task['reward'])
                
                # Tamamlanan görev sayısını artır
                self.db.cursor.execute('''
                    UPDATE users SET tasks_completed = tasks_completed + 1 
                    WHERE user_id = ?
                ''', (user_id,))
                self.db.connection.commit()
                
                answer_callback_query(callback_id, 
                    f"✅ Göreve katıldınız!\n\n💰 Kazanç: ${task['reward']:.2f}\n💰 Yeni bakiye: ${user['balance'] + task['reward']:.2f}", 
                    show_alert=True)
                
                # Görevleri yenile
                time.sleep(1)
                self.show_tasks(user_id)
            else:
                answer_callback_query(callback_id, "❌ Görev bulunamadı!", show_alert=True)
        else:
            if message == "already_joined":
                answer_callback_query(callback_id, "❌ Bu göreve zaten katıldınız!", show_alert=True)
            elif message == "task_full":
                answer_callback_query(callback_id, "❌ Görev doldu!", show_alert=True)
            else:
                answer_callback_query(callback_id, "❌ Görev bulunamadı!", show_alert=True)
    
    def show_balance(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        balance = user['balance']
        
        text = f"""
{texts['your_balance']}

┌─────────────────
│ 💰 *Mevcut Bakiye:* `${balance:.2f}`
│ 📊 *Tamamlanan Görev:* `{user['tasks_completed']}`
└─────────────────

{texts['min_withdraw']}
{texts['min_deposit']}

💡 *İpucu:* Görev tamamlayarak bakiyenizi artırabilirsiniz!
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "💳 Bakiye Yükle", 'callback_data': 'show_deposit'}],
                [{'text': "🏧 Para Çek", 'callback_data': 'show_withdraw'}],
                [{'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_withdraw(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        balance = user['balance']
        
        text = f"""
{texts['withdraw_info']}

┌─────────────────
│ 💰 *Mevcut Bakiye:* `${balance:.2f}`
│ 📉 *Minimum Çekim:* `${MIN_WITHDRAW}`
│ ⏱️ *İşlem Süresi:* 24 saat
└─────────────────

💡 *Adımlar:*
1️⃣ Çekim miktarını belirleyin
2️⃣ TRX cüzdan adresinizi girin
3️⃣ Onay bekleyin

⚠️ *Önemli:*
• Sadece TRX (Tron) adresinize gönderim yapılır
• Yanlış adres için sorumluluk kabul edilmez
• İşlemler manuel kontrol edilir

📞 *Destek:* {SUPPORT_USERNAME}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "📞 Destekle İletişime Geç", 'url': f"https://t.me/{SUPPORT_USERNAME[1:]}"}],
                [{'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_deposit(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
{texts['deposit_info']}

┌─────────────────
│ 📈 *Minimum Yükleme:* `${MIN_DEPOSIT_USD}`
│ ⚡ *Ağ:* TRON (TRX)
│ 🔄 *Onay Süresi:* 10-30 dakika
└─────────────────

💎 *TRX Adresi:*
`{TRX_ADDRESS}`

📝 *Talimatlar:*
1. Yukarıdaki adrese TRX gönderin
2. İşlem tamamlanmasını bekleyin
3. Bakiyeniz otomatik güncellenecek

⚠️ *Uyarılar:*
• Sadece TRX (Tron) gönderin!
• Farklı coin gönderirseniz kaybolur!
• Yeterli network ücreti bırakın

📞 *Sorularınız için:* {SUPPORT_USERNAME}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_profile(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        lang_info = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES['tr'])
        
        user_type_emoji = "👤" if user['user_type'] == 'earner' else "📢"
        user_type_text = texts['earner'] if user['user_type'] == 'earner' else texts['advertiser']
        
        text = f"""
{texts['profile_info']}

┌─────────────────
│ 🆔 *ID:* `{user_id}`
│ 👤 *Ad:* `{user['first_name']} {user['last_name'] or ''}`
│ 📛 *Kullanıcı Adı:* `@{user['username'] or 'Belirtilmemiş'}`
│ 🌐 *Dil:* `{lang_info['name']} {lang_info['flag']}`
│ {user_type_emoji} *Tür:* `{user_type_text}`
│ 💰 *Bakiye:* `${user['balance']:.2f}`
│ 🎯 *Görev:* `{user['tasks_completed']}`
│ 📅 *Kayıt:* `{user['created_at'][:10] if user['created_at'] else '-'}`
└─────────────────

📊 *İstatistikler yakında eklenecek!*
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "🔄 Profili Yenile", 'callback_data': 'show_profile'}],
                [{'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_referral(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        referral_code = user['referral_code']
        bot_username = TOKEN.split(':')[0] if ':' in TOKEN else 'taskizbot'
        referral_link = f"https://t.me/{bot_username}?start={referral_code}"
        
        text = f"""
{texts['referral_info']}

┌─────────────────
│ 📊 *Sistem:* Aktif
│ 💰 *Komisyon:* %{REF_TASK_COMMISSION*100}
│ 👥 *Limit:* Sınırsız
└─────────────────

🔗 *Referans Linkiniz:*
`{referral_link}`

📋 *Referans Kodunuz:*
`{referral_code}`

💰 *Nasıl Kazanırsınız:*
1. Linkinizi paylaşın
2. Arkadaşlarınız kayıt olsun
3. Onlar görev yaptıkça siz kazanın!
4. Onlar para çektiğinde komisyon alın

🎯 *Bonuslar:*
• Yeni kayıt bonusu: `${REF_WELCOME_BONUS}`
• Görev komisyonu: %{REF_TASK_COMMISSION*100}

📞 *Destek:* {SUPPORT_USERNAME}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "📋 Kodu Kopyala", 'callback_data': 'copy_ref'}],
                [{'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_help(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
{texts['help_info']}

🤖 *TaskizBot Nedir?*
Görev tamamlayarak para kazanabileceğiniz güvenilir bir platform.

🎯 *Çalışma Prensibi:*
1️⃣ 📢 Kanallara katılın
2️⃣ 🎯 Görevleri tamamlayın
3️⃣ 💰 Ödülünüzü alın
4️⃣ 🏧 Parayı çekin

💰 *Ödeme Sistemi:*
• Minimum çekim: `${MIN_WITHDRAW}`
• Ödeme ağı: TRON (TRX)
• İşlem süresi: 24 saat

⚠️ *Kurallar:*
• Sahte görev yapmak yasak
• Çoklu hesap yasak
• Kurallara uymayanlar banlanır

📞 *Destek & İletişim:*
Sorularınız için iletişime geçin:
{SUPPORT_USERNAME}

✨ *İyi kazançlar dileriz!*
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "📢 Kanalları Kontrol Et", 'callback_data': 'check_channels'}],
                [{'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)

# Botu başlat
bot = TaskizBot()

# Flask server'ı başlat
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    if WEBHOOK_URL:
        try:
            print("🌐 Webhook ayarlanıyor...")
            
            # Mevcut webhook'u sil
            requests.get(f"{BASE_URL}deleteWebhook")
            time.sleep(1)
            
            # Yeni webhook'u ayarla
            url = f"{WEBHOOK_URL}/webhook"
            response = requests.get(f"{BASE_URL}setWebhook?url={url}")
            print(f"✅ Webhook ayarlandı: {response.json()}")
            
            # Webhook bilgilerini kontrol et
            time.sleep(2)
            info = requests.get(f"{BASE_URL}getWebhookInfo").json()
            print(f"📋 Webhook bilgisi: {info}")
            
        except Exception as e:
            print(f"❌ Webhook hatası: {e}")
    else:
        print("⚠️ WEBHOOK_URL ayarlanmamış")
    
    print(f"🚀 Bot {port} portunda başlatılıyor...")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
