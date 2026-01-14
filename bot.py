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
from typing import Dict, List

# Telegram Ayarları
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "7904032877")
SUPPORT_USERNAME = "@AlperenTHE"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
STATS_CHANNEL = "@TaskizLive"
BOT_USERNAME = "TaskizBot"
BOT_NAME = "TaksizBot"

# Zorunlu Kanallar
MANDATORY_CHANNELS = [
    {
        'username': 'TaskizLive',
        'link': 'https://t.me/TaskizLive',
        'name': 'İstatistik',
        'emoji': '📊'
    }
]

if not TOKEN:
    raise ValueError("Bot token gerekli!")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Dil Ayarları
SUPPORTED_LANGUAGES = {
    'tr': {'name': 'Türkçe', 'flag': '🇹🇷'},
    'en': {'name': 'English', 'flag': '🇺🇸'},
    'ru': {'name': 'Русский', 'flag': '🇷🇺'},
    'es': {'name': 'Español', 'flag': '🇪🇸'},
    'pt': {'name': 'Português', 'flag': '🇵🇹'},
    'ar': {'name': 'العربية', 'flag': '🇸🇦'},
    'id': {'name': 'Bahasa', 'flag': '🇮🇩'},
    'de': {'name': 'Deutsch', 'flag': '🇩🇪'},
    'fa': {'name': 'فارسی', 'flag': '🇮🇷'},
    'hi': {'name': 'हिन्दी', 'flag': '🇮🇳'},
    'bn': {'name': 'বাংলা', 'flag': '🇧🇩'},
    'ur': {'name': 'اردو', 'flag': '🇵🇰'},
    'vi': {'name': 'Tiếng Việt', 'flag': '🇻🇳'}
}

# TRX Ayarları
TRX_ADDRESS = os.environ.get("TRX_ADDRESS", "DEPOZIT_YAPILACAK_ADRES")
MIN_DEPOSIT_USD = 2.5
MIN_WITHDRAW = 0.30
MIN_REFERRALS_FOR_WITHDRAW = 10
REF_WELCOME_BONUS = 0.005
REF_TASK_COMMISSION = 0.25

# Hızlı yükleme
DEPOSIT_AMOUNTS = [0.50, 1.0, 2.5, 5.0, 10.0]

# Flask
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "online", "bot": BOT_NAME})

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    bot.handle_update(update)
    return jsonify({"status": "ok"})

# Telegram API
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
    except:
        return None

def answer_callback_query(callback_query_id, text=None, show_alert=False):
    url = BASE_URL + "answerCallbackQuery"
    payload = {'callback_query_id': callback_query_id}
    
    if text:
        payload['text'] = text
    if show_alert:
        payload['show_alert'] = show_alert
    
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def get_chat_member(chat_id, user_id):
    url = BASE_URL + "getChatMember"
    payload = {'chat_id': chat_id, 'user_id': user_id}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if data.get('ok'):
            status = data['result']['status']
            return status in ['member', 'administrator', 'creator']
        return False
    except:
        return False

# Dil Metinleri
LANGUAGE_TEXTS = {
    'tr': {
        'welcome': f"🎉 *{BOT_NAME}'a Hoş Geldin!*",
        'balance': "💰 Bakiye",
        'tasks': "🎯 Görevler",
        'withdraw': "🏧 Çek",
        'deposit': "💳 Yükle",
        'profile': "👤 Profil",
        'referral': "👥 Davet",
        'help': "❓ Yardım",
        'channels': "📢 Kanallar",
        'back': "🔙 Geri",
        'refresh': "🔄 Yenile",
        'earner': "👤 Kazanan",
        'advertiser': "📢 Reklamveren",
        'main_menu': "🏠 Ana Menü",
        'your_balance': "💰 Bakiyen:",
        'min_withdraw': f"Min: ${MIN_WITHDRAW}",
        'contact_support': f"Destek: {SUPPORT_USERNAME}",
        'no_tasks': "📭 Görev yok\n⏳ Sonra tekrar gel",
        'task_reward': "💰",
        'task_participants': "👥",
        'join_task': "🎯 Katıl",
        'deposit_amounts': "💰 Hızlı Yükle",
        'withdraw_money': "💸 Para Çek",
        'deposit_money': "💳 Yükle",
        'copy_ref_code': "📋 Kopyala",
        'total_earned': "📈 Toplam",
        'tasks_completed': "✅ Görev",
        'quick_actions': "⚡ Hızlı",
        'go_back': "⬅️ Geri",
        'payment_method': "💳 TRON ile",
        'not_enough_referrals': "❌ Yetersiz davet",
        'withdraw_conditions': f"📋 {MIN_REFERRALS_FOR_WITHDRAW} davet gerekiyor",
        'switch_to_advertiser': "📢 Reklamveren Ol",
        'switch_to_earner': "👤 Kazanan Ol",
        'convert_balance': "💱 Bakiyeni Dönüştür",
        'conversion_info': "💡 Kazanan → Reklamveren geçişinde bakiye saklanır"
    },
    'en': {
        'welcome': f"🎉 *Welcome to {BOT_NAME}!*",
        'balance': "💰 Balance",
        'tasks': "🎯 Tasks",
        'withdraw': "🏧 Withdraw",
        'deposit': "💳 Deposit",
        'profile': "👤 Profile",
        'referral': "👥 Referral",
        'help': "❓ Help",
        'channels': "📢 Channels",
        'back': "🔙 Back",
        'refresh': "🔄 Refresh",
        'earner': "👤 Earner",
        'advertiser': "📢 Advertiser",
        'main_menu': "🏠 Main Menu",
        'your_balance': "💰 Your Balance:",
        'min_withdraw': f"Min: ${MIN_WITHDRAW}",
        'contact_support': f"Support: {SUPPORT_USERNAME}",
        'no_tasks': "📭 No tasks\n⏳ Check later",
        'task_reward': "💰",
        'task_participants': "👥",
        'join_task': "🎯 Join",
        'deposit_amounts': "💰 Quick Deposit",
        'withdraw_money': "💸 Withdraw",
        'deposit_money': "💳 Deposit",
        'copy_ref_code': "📋 Copy",
        'total_earned': "📈 Total",
        'tasks_completed': "✅ Tasks",
        'quick_actions': "⚡ Quick",
        'go_back': "⬅️ Back",
        'payment_method': "💳 TRON payment",
        'not_enough_referrals': "❌ Not enough refs",
        'withdraw_conditions': f"📋 Need {MIN_REFERRALS_FOR_WITHDRAW} refs",
        'switch_to_advertiser': "📢 Be Advertiser",
        'switch_to_earner': "👤 Be Earner",
        'convert_balance': "💱 Convert Balance",
        'conversion_info': "💡 Balance saved when switching"
    },
    'ru': {
        'welcome': f"🎉 *Добро пожаловать в {BOT_NAME}!*",
        'balance': "💰 Баланс",
        'tasks': "🎯 Задачи",
        'withdraw': "🏧 Вывод",
        'deposit': "💳 Пополнить",
        'profile': "👤 Профиль",
        'referral': "👥 Рефералы",
        'help': "❓ Помощь",
        'channels': "📢 Каналы",
        'back': "🔙 Назад",
        'refresh': "🔄 Обновить",
        'earner': "👤 Заработок",
        'advertiser': "📢 Рекламодатель",
        'main_menu': "🏠 Главное",
        'your_balance': "💰 Баланс:",
        'min_withdraw': f"Мин: ${MIN_WITHDRAW}",
        'contact_support': f"Поддержка: {SUPPORT_USERNAME}",
        'no_tasks': "📭 Нет задач\n⏳ Зайдите позже",
        'task_reward': "💰",
        'task_participants': "👥",
        'join_task': "🎯 Участвовать",
        'deposit_amounts': "💰 Пополнить",
        'withdraw_money': "💸 Вывод",
        'deposit_money': "💳 Пополнение",
        'copy_ref_code': "📋 Копировать",
        'total_earned': "📈 Всего",
        'tasks_completed': "✅ Задачи",
        'quick_actions': "⚡ Быстро",
        'go_back': "⬅️ Назад",
        'payment_method': "💳 TRON оплата",
        'not_enough_referrals': "❌ Мало рефералов",
        'withdraw_conditions': f"📋 Нужно {MIN_REFERRALS_FOR_WITHDRAW} рефов",
        'switch_to_advertiser': "📢 Рекламодатель",
        'switch_to_earner': "👤 Заработок",
        'convert_balance': "💱 Конвертировать",
        'conversion_info': "💡 Баланс сохраняется"
    }
}

# Database Sınıfı - DÜZELTİLDİ
class Database:
    def __init__(self, db_path='taskizbot.db'):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.setup_database()
        print("✅ Database başlatıldı")
    
    def setup_database(self):
        # Users tablosu
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
                referred_by INTEGER,
                tasks_completed INTEGER DEFAULT 0,
                total_earned REAL DEFAULT 0,
                total_referrals INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Referrals
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER UNIQUE,
                earned_amount REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tasks
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
        
        # Task participations
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_participations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_id, user_id)
            )
        ''')
        
        # Withdrawals
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                trx_address TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Stats
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_users INTEGER DEFAULT 0,
                active_today INTEGER DEFAULT 0,
                total_earned REAL DEFAULT 0,
                total_tasks INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Örnek görev ekle
        self.add_sample_tasks()
        self.connection.commit()
    
    def add_sample_tasks(self):
        count = self.cursor.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        if count == 0:
            tasks = [
                ('Telegram Kanalına Katıl', '@TaskizLive kanalına katıl', 0.05, 100),
                ('Botu Beğen', 'Botu beğen ve yorum yap', 0.03, 50),
                ('Gönderi Paylaş', 'Gönderiyi paylaş', 0.08, 30),
            ]
            for task in tasks:
                self.cursor.execute('INSERT INTO tasks (title, description, reward, max_participants) VALUES (?, ?, ?, ?)', task)
            self.connection.commit()
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            user = dict(row)
            # Referans sayısı
            self.cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
            user['total_referrals'] = self.cursor.fetchone()[0]
            return user
        return None
    
    def create_user(self, user_id, username, first_name, last_name, language='tr', referred_by=None):
        referral_code = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8].upper()
        
        # Eski kullanıcı kontrolü - DÜZELTİLDİ
        existing = self.get_user(user_id)
        if existing:
            return existing
        
        # Yeni kullanıcı ekle
        self.cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, language, referral_code, referred_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, language, referral_code, referred_by))
        
        # Referans bonusu
        if referred_by:
            self.cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id, earned_amount)
                VALUES (?, ?, ?)
            ''', (referred_by, user_id, REF_WELCOME_BONUS))
            
            self.cursor.execute('''
                UPDATE users SET balance = balance + ?, total_referrals = total_referrals + 1
                WHERE user_id = ?
            ''', (REF_WELCOME_BONUS, referred_by))
        
        self.connection.commit()
        return self.get_user(user_id)
    
    def update_last_active(self, user_id):
        self.cursor.execute('UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
        self.connection.commit()
    
    def update_balance(self, user_id, amount):
        self.cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        self.connection.commit()
    
    def update_user_type(self, user_id, user_type):
        self.cursor.execute('UPDATE users SET user_type = ? WHERE user_id = ?', (user_type, user_id))
        self.connection.commit()
    
    def update_stats(self):
        # Toplam kullanıcı
        self.cursor.execute("SELECT COUNT(*) FROM users")
        total_users = self.cursor.fetchone()[0]
        
        # Aktif (24 saat)
        yesterday = (datetime.now() - timedelta(hours=24)).isoformat()
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (yesterday,))
        active_today = self.cursor.fetchone()[0]
        
        # Toplam kazanç
        self.cursor.execute("SELECT SUM(total_earned) FROM users")
        total_earned = self.cursor.fetchone()[0] or 0
        
        # Toplam görev
        self.cursor.execute("SELECT SUM(tasks_completed) FROM users")
        total_tasks = self.cursor.fetchone()[0] or 0
        
        # Kaydet
        self.cursor.execute('''
            INSERT INTO stats (total_users, active_today, total_earned, total_tasks)
            VALUES (?, ?, ?, ?)
        ''', (total_users, active_today, total_earned, total_tasks))
        
        self.connection.commit()
        return {
            'total_users': total_users,
            'active_today': active_today,
            'total_earned': round(total_earned, 2),
            'total_tasks': total_tasks
        }

# İstatistik Sınıfı
class StatsNotifier:
    def __init__(self, db):
        self.db = db
        self.running = False
    
    def start(self):
        self.running = True
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        print("📊 Stats başlatıldı")
    
    def run(self):
        while self.running:
            try:
                self.update_stats_channel()
                time.sleep(300)
            except:
                time.sleep(60)
    
    def update_stats_channel(self):
        try:
            stats = self.db.update_stats()
            message = self.generate_stats_message(stats)
            send_message(STATS_CHANNEL, message)
        except:
            pass
    
    def generate_stats_message(self, stats):
        now = datetime.now()
        return f"""
📊 *{BOT_NAME} CANLI İSTATİSTİK*
⏰ {now.strftime('%H:%M')}

👥 Toplam: `{stats['total_users']}`
📈 Aktif: `{stats['active_today']}`
💰 Kazanç: `${stats['total_earned']}`
🎯 Görev: `{stats['total_tasks']}`

🤖 @{BOT_USERNAME}
📢 @TaskizLive
        """

# Bot Sınıfı
class TaskizBot:
    def __init__(self):
        self.db = Database()
        self.stats_notifier = StatsNotifier(self.db)
        self.stats_notifier.start()
        self.user_states = {}
        print(f"🤖 {BOT_NAME} başlatıldı!")
    
    def handle_update(self, update):
        try:
            if 'message' in update:
                self.handle_message(update['message'])
            elif 'callback_query' in update:
                self.handle_callback_query(update['callback_query'])
        except Exception as e:
            print(f"Hata: {e}")
    
    def handle_message(self, message):
        if 'text' not in message:
            return
        
        user_id = message['from']['id']
        text = message['text']
        
        # Referans kontrolü
        referred_by = None
        if text.startswith('/start'):
            parts = text.split()
            if len(parts) > 1:
                ref_code = parts[1]
                self.db.cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (ref_code,))
                row = self.db.cursor.fetchone()
                if row:
                    referred_by = row[0]
        
        user = self.db.get_user(user_id)
        
        if not user:
            # Yeni kullanıcı kaydı - GRUP BİLDİRİMİ EKLENDİ
            username = message['from'].get('username', '')
            first_name = message['from'].get('first_name', '')
            last_name = message['from'].get('last_name', '')
            
            user = self.db.create_user(user_id, username, first_name, last_name, 'tr', referred_by)
            
            # GRUP BİLDİRİMİ: YENİ ÜYE
            group_msg = f"""
👤 *YENİ ÜYE KATILDI*
━━━━━━━━━━━━
🎉 Hoş geldin: {first_name} {last_name or ''}
🆔 ID: `{user_id}`
📅 Tarih: {datetime.now().strftime('%H:%M')}
━━━━━━━━━━━━
👥 Toplam: {self.db.cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]}
            """
            try:
                send_message(STATS_CHANNEL, group_msg)
            except:
                pass
            
            self.show_language_selection(user_id)
            return
        
        self.db.update_last_active(user_id)
        
        # TRX adresi durumu
        if user_id in self.user_states and self.user_states[user_id]['action'] == 'waiting_trx':
            self.handle_trx_address(user_id, text, user)
            return
        
        # Kullanıcı türü değiştirme
        if user_id in self.user_states and self.user_states[user_id]['action'] == 'convert_balance':
            self.handle_balance_conversion(user_id, text, user)
            return
        
        self.process_command(user_id, text, user)
    
    def handle_trx_address(self, user_id, trx_address, user):
        if user_id in self.user_states:
            amount = self.user_states[user_id].get('withdraw_amount', 0)
            
            # Çekim kaydı
            self.db.cursor.execute('''
                INSERT INTO withdrawals (user_id, amount, trx_address, status)
                VALUES (?, ?, ?, 'pending')
            ''', (user_id, amount, trx_address))
            
            # Bakiye düş
            self.db.update_balance(user_id, -amount)
            
            # GRUP BİLDİRİMİ: ÇEKİM TALEBİ
            group_msg = f"""
🏧 *YENİ ÇEKİM TALEBİ*
━━━━━━━━━━━━
👤 Kullanıcı: {user['first_name']}
💰 Miktar: `${amount}`
🔗 TRX: `{trx_address[:10]}...`
⏰ {datetime.now().strftime('%H:%M')}
            """
            try:
                send_message(STATS_CHANNEL, group_msg)
            except:
                pass
            
            send_message(user_id, f"✅ Çekim talebin alındı!\n💰 ${amount}\n⏳ 24-48 saat")
            del self.user_states[user_id]
            time.sleep(1)
            self.show_main_menu(user_id, user['language'])
    
    def handle_balance_conversion(self, user_id, text, user):
        if text.lower() in ['evet', 'yes', 'да', 'はい']:
            # Bakiye sakla (veritabanında)
            old_balance = user['balance']
            # Burada bakiye saklama işlemi yapılabilir
            # Şimdilik sadece tür değiştir
            self.db.update_user_type(user_id, 'advertiser')
            
            send_message(user_id, f"✅ Reklamveren oldun!\n💰 Eski bakiye: ${old_balance}\n💡 Bakiye saklandı")
            
            # GRUP BİLDİRİMİ: TÜR DEĞİŞTİRME
            group_msg = f"""
🔄 *KULLANICI TÜRÜ DEĞİŞTİ*
━━━━━━━━━━━━
👤 {user['first_name']}
🔄 Kazanan → Reklamveren
💰 Bakiye: `${old_balance}`
⏰ {datetime.now().strftime('%H:%M')}
            """
            try:
                send_message(STATS_CHANNEL, group_msg)
            except:
                pass
        else:
            send_message(user_id, "❌ İptal edildi")
        
        del self.user_states[user_id]
        self.show_main_menu(user_id, user['language'])
    
    def show_language_selection(self, user_id):
        text = "🌍 Dil / Language"
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🇹🇷 Türkçe', 'callback_data': 'lang_tr'}],
                [{'text': '🇺🇸 English', 'callback_data': 'lang_en'}],
                [{'text': '🇷🇺 Русский', 'callback_data': 'lang_ru'}],
                [{'text': '🌍 Diğer', 'callback_data': 'lang_more'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_callback_query(self, callback_query):
        data = callback_query['data']
        user_id = callback_query['from']['id']
        callback_id = callback_query['id']
        
        try:
            # Dil seçimi
            if data.startswith('lang_'):
                lang = data.split('_')[1]
                if lang == 'more':
                    self.show_more_languages(user_id)
                else:
                    self.db.cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (lang, user_id))
                    self.db.connection.commit()
                    answer_callback_query(callback_id, "✅ Dil seçildi")
                    self.show_main_menu(user_id, lang)
            
            # Ana menü
            elif data == 'main_menu':
                user = self.db.get_user(user_id)
                if user:
                    self.show_main_menu(user_id, user['language'])
            
            # Görevler
            elif data == 'show_tasks':
                self.show_tasks(user_id)
            
            # Bakiye
            elif data == 'show_balance':
                self.show_balance(user_id)
            
            # Para çek
            elif data == 'show_withdraw':
                self.show_withdraw(user_id)
            
            # Yükle
            elif data == 'show_deposit':
                self.show_deposit(user_id)
            
            # Referans
            elif data == 'show_referral':
                self.show_referral(user_id)
            
            # Profil
            elif data == 'show_profile':
                self.show_profile(user_id)
            
            # Yardım
            elif data == 'show_help':
                self.show_help(user_id)
            
            # Kanallar
            elif data == 'show_channels':
                self.show_channels(user_id)
            
            # Göreve katıl
            elif data.startswith('join_task_'):
                task_id = int(data.split('_')[2])
                self.join_task(user_id, task_id, callback_id)
            
            # Yenile
            elif data == 'refresh_tasks':
                self.show_tasks(user_id)
                answer_callback_query(callback_id, "🔄 Yenilendi")
            
            # Bakiye yükle
            elif data.startswith('deposit_'):
                amount = float(data.split('_')[1])
                self.db.update_balance(user_id, amount)
                
                # GRUP BİLDİRİMİ: BAKİYE YÜKLEME
                user = self.db.get_user(user_id)
                group_msg = f"""
💰 *BAKİYE YÜKLENDİ*
━━━━━━━━━━━━
👤 {user['first_name']}
💵 ${amount}
📊 ${user['balance'] + amount}
⏰ {datetime.now().strftime('%H:%M')}
                """
                try:
                    send_message(STATS_CHANNEL, group_msg)
                except:
                    pass
                
                answer_callback_query(callback_id, f"✅ ${amount} yüklendi", True)
                time.sleep(1)
                self.show_balance(user_id)
            
            # Çekim başlat
            elif data.startswith('withdraw_'):
                amount = float(data.split('_')[1])
                self.start_withdrawal(user_id, amount, callback_id)
            
            # Kopyala
            elif data == 'copy_ref':
                user = self.db.get_user(user_id)
                if user:
                    answer_callback_query(callback_id, f"📋 Kod: {user['referral_code']}", True)
            
            # Kullanıcı türü değiştir
            elif data == 'switch_to_advertiser':
                self.switch_to_advertiser(user_id, callback_id)
            
            elif data == 'switch_to_earner':
                self.switch_to_earner(user_id, callback_id)
            
        except Exception as e:
            print(f"Callback error: {e}")
            answer_callback_query(callback_id, "❌ Hata")
    
    def show_more_languages(self, user_id):
        text = "🌍 Diğer Diller"
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🇪🇸 Español', 'callback_data': 'lang_es'}],
                [{'text': '🇵🇹 Português', 'callback_data': 'lang_pt'}],
                [{'text': '🇸🇦 العربية', 'callback_data': 'lang_ar'}],
                [{'text': '🇮🇩 Bahasa', 'callback_data': 'lang_id'}],
                [{'text': '🔙 Geri', 'callback_data': 'lang_back'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def process_command(self, user_id, text, user):
        lang = user['language']
        texts = LANGUAGE_TEXTS.get(lang, LANGUAGE_TEXTS['tr'])
        
        if text.startswith('/'):
            cmd = text.split()[0]
            if cmd == '/start':
                self.show_main_menu(user_id, lang)
            elif cmd == '/tasks':
                self.show_tasks(user_id)
            elif cmd == '/balance':
                self.show_balance(user_id)
            elif cmd == '/withdraw':
                self.show_withdraw(user_id)
            elif cmd == '/deposit':
                self.show_deposit(user_id)
            elif cmd == '/referral':
                self.show_referral(user_id)
            elif cmd == '/profile':
                self.show_profile(user_id)
            elif cmd == '/help':
                self.show_help(user_id)
            else:
                self.show_main_menu(user_id, lang)
        else:
            # Buton işlemleri
            if text == texts['tasks']:
                self.show_tasks(user_id)
            elif text == texts['balance']:
                self.show_balance(user_id)
            elif text == texts['withdraw']:
                self.show_withdraw(user_id)
            elif text == texts['deposit']:
                self.show_deposit(user_id)
            elif text == texts['referral']:
                self.show_referral(user_id)
            elif text == texts['profile']:
                self.show_profile(user_id)
            elif text == texts['help']:
                self.show_help(user_id)
            elif text == texts['channels']:
                self.show_channels(user_id)
            elif text == texts['back']:
                self.show_main_menu(user_id, lang)
            else:
                self.show_main_menu(user_id, lang)
    
    def show_main_menu(self, user_id, language):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Kanal kontrolü
        if not self.check_channels(user_id):
            self.show_channels(user_id)
            return
        
        balance = user['balance']
        tasks = user['tasks_completed']
        refs = user.get('total_referrals', 0)
        
        text = f"""
🏠 *{texts['main_menu']}*

💰 ${balance:.2f} | 🎯 {tasks} | 👥 {refs}

{texts['contact_support']}
        """
        
        keyboard = {
            'keyboard': [
                [texts['tasks'], texts['balance']],
                [texts['withdraw'], texts['deposit']],
                [texts['referral'], texts['profile']],
                [texts['channels'], texts['help']]
            ],
            'resize_keyboard': True
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def check_channels(self, user_id):
        for channel in MANDATORY_CHANNELS:
            if not get_chat_member(f"@{channel['username']}", user_id):
                return False
        return True
    
    def show_tasks(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        texts = LANGUAGE_TEXTS.get(lang, LANGUAGE_TEXTS['tr'])
        
        self.db.cursor.execute('SELECT * FROM tasks WHERE status = "active"')
        tasks = self.db.cursor.fetchall()
        
        if not tasks:
            text = texts['no_tasks']
            buttons = [[{'text': "🔄 Yenile", 'callback_data': 'refresh_tasks'}]]
        else:
            text = "🎯 *Görevler*\n\n"
            buttons = []
            
            for task in tasks:
                task = dict(task)
                text += f"🔸 {task['title']}\n"
                text += f"📝 {task['description']}\n"
                text += f"💰 ${task['reward']} | 👥 {task['current_participants']}/{task['max_participants']}\n\n"
                
                buttons.append([{
                    'text': f"🎯 Katıl (${task['reward']})",
                    'callback_data': f'join_task_{task["id"]}'
                }])
            
            buttons.append([{'text': "🔄 Yenile", 'callback_data': 'refresh_tasks'}])
        
        buttons.append([{'text': "🏠 Ana Menü", 'callback_data': 'main_menu'}])
        
        keyboard = {'inline_keyboard': buttons}
        send_message(user_id, text, reply_markup=keyboard)
    
    def join_task(self, user_id, task_id, callback_id):
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Kullanıcı yok")
            return
        
        # Kanal kontrolü
        if not self.check_channels(user_id):
            answer_callback_query(callback_id, "❌ Önce kanala katıl", True)
            return
        
        # Görev kontrolü
        self.db.cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        task = self.db.cursor.fetchone()
        if not task:
            answer_callback_query(callback_id, "❌ Görev yok")
            return
        
        task = dict(task)
        
        # Zaten katıldı mı?
        self.db.cursor.execute('SELECT COUNT(*) FROM task_participations WHERE task_id = ? AND user_id = ?', 
                              (task_id, user_id))
        if self.db.cursor.fetchone()[0] > 0:
            answer_callback_query(callback_id, "❌ Zaten katıldın", True)
            return
        
        # Katılım kaydet
        self.db.cursor.execute('''
            INSERT INTO task_participations (task_id, user_id, status)
            VALUES (?, ?, 'completed')
        ''', (task_id, user_id))
        
        # Görev güncelle
        self.db.cursor.execute('''
            UPDATE tasks SET current_participants = current_participants + 1 
            WHERE id = ?
        ''', (task_id,))
        
        # Ödül ver
        reward = task['reward']
        self.db.cursor.execute('''
            UPDATE users 
            SET balance = balance + ?, 
                tasks_completed = tasks_completed + 1,
                total_earned = total_earned + ?
            WHERE user_id = ?
        ''', (reward, reward, user_id))
        
        # Referans bonusu
        if user['referred_by']:
            commission = reward * REF_TASK_COMMISSION
            self.db.update_balance(user['referred_by'], commission)
        
        self.db.connection.commit()
        
        # GRUP BİLDİRİMİ: GÖREV TAMAMLAMA
        group_msg = f"""
🎯 *GÖREV TAMAMLANDI*
━━━━━━━━━━━━
👤 {user['first_name']}
🎯 {task['title']}
💰 ${reward}
⏰ {datetime.now().strftime('%H:%M')}
        """
        try:
            send_message(STATS_CHANNEL, group_msg)
        except:
            pass
        
        answer_callback_query(callback_id, f"✅ ${reward} kazandın!", True)
        time.sleep(1)
        self.show_tasks(user_id)
    
    def show_balance(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        texts = LANGUAGE_TEXTS.get(lang, LANGUAGE_TEXTS['tr'])
        
        refs = user.get('total_referrals', 0)
        
        text = f"""
💰 *{texts['your_balance']}*

💳 ${user['balance']:.2f}
🎯 {user['tasks_completed']} {texts['tasks_completed']}
📈 ${user['total_earned']:.2f} {texts['total_earned']}
👥 {refs}/{MIN_REFERRALS_FOR_WITHDRAW} {texts['withdraw_conditions']}
        """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': "💳 Yükle", 'callback_data': 'show_deposit'},
                    {'text': "🏧 Çek", 'callback_data': 'show_withdraw'}
                ],
                [
                    {'text': "🎯 Görevler", 'callback_data': 'show_tasks'},
                    {'text': "👥 Davet", 'callback_data': 'show_referral'}
                ],
                [{'text': "🏠 Ana Menü", 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_withdraw(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        texts = LANGUAGE_TEXTS.get(lang, LANGUAGE_TEXTS['tr'])
        
        refs = user.get('total_referrals', 0)
        balance = user['balance']
        
        if refs < MIN_REFERRALS_FOR_WITHDRAW:
            text = f"""
🏧 *{texts['withdraw_money']}*

❌ {texts['not_enough_referrals']}
👥 {refs}/{MIN_REFERRALS_FOR_WITHDRAW}
💰 ${balance:.2f}

{texts['withdraw_conditions']}
            """
            buttons = [[{'text': "👥 Davetlerim", 'callback_data': 'show_referral'}]]
        elif balance < MIN_WITHDRAW:
            text = f"""
🏧 *{texts['withdraw_money']}*

❌ Min: ${MIN_WITHDRAW}
💰 Senin: ${balance:.2f}
👥 {refs}/{MIN_REFERRALS_FOR_WITHDRAW} ✅
            """
            buttons = [[{'text': "🎯 Görevler", 'callback_data': 'show_tasks'}]]
        else:
            text = f"""
🏧 *{texts['withdraw_money']}*

✅ Şartlar tamam!
💰 ${balance:.2f}
👥 {refs}/{MIN_REFERRALS_FOR_WITHDRAW}
🔗 {texts['payment_method']}

Miktar seç:
            """
            
            # Önerilen miktarlar
            amounts = []
            if balance >= MIN_WITHDRAW:
                amounts.append(MIN_WITHDRAW)
            if balance >= 1.0:
                amounts.append(1.0)
            if balance >= 5.0:
                amounts.append(5.0)
            if balance >= 10.0:
                amounts.append(10.0)
            
            buttons = []
            for amount in amounts:
                buttons.append([{
                    'text': f"${amount} Çek",
                    'callback_data': f'withdraw_{amount}'
                }])
            
            buttons.append([{'text': "✏️ Manuel", 'callback_data': 'withdraw_manual'}])
        
        buttons.append([{'text': "🏠 Ana Menü", 'callback_data': 'main_menu'}])
        
        keyboard = {'inline_keyboard': buttons}
        send_message(user_id, text, reply_markup=keyboard)
    
    def start_withdrawal(self, user_id, amount, callback_id):
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Hata")
            return
        
        if user['balance'] < amount:
            answer_callback_query(callback_id, "❌ Yetersiz bakiye", True)
            return
        
        if amount < MIN_WITHDRAW:
            answer_callback_query(callback_id, f"❌ Min: ${MIN_WITHDRAW}", True)
            return
        
        refs = user.get('total_referrals', 0)
        if refs < MIN_REFERRALS_FOR_WITHDRAW:
            answer_callback_query(callback_id, f"❌ {MIN_REFERRALS_FOR_WITHDRAW} davet gerek", True)
            return
        
        # TRX adresi iste
        self.user_states[user_id] = {
            'action': 'waiting_trx',
            'withdraw_amount': amount
        }
        
        send_message(user_id, f"✏️ TRX adresini gönder:\n💰 ${amount}\n⚠️ Adresini kontrol et!")
        answer_callback_query(callback_id, "✅ TRX adresi bekleniyor")
    
    def show_deposit(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        texts = LANGUAGE_TEXTS.get(lang, LANGUAGE_TEXTS['tr'])
        
        text = f"""
💳 *{texts['deposit_money']}*

💰 ${user['balance']:.2f}

{texts['deposit_amounts']}:
        """
        
        buttons = []
        row = []
        
        for amount in DEPOSIT_AMOUNTS:
            row.append({
                'text': f"${amount}",
                'callback_data': f'deposit_{amount}'
            })
            
            if len(row) == 2:
                buttons.append(row)
                row = []
        
        if row:
            buttons.append(row)
        
        buttons.append([
            {'text': "🏠 Ana Menü", 'callback_data': 'main_menu'}
        ])
        
        keyboard = {'inline_keyboard': buttons}
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_referral(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        texts = LANGUAGE_TEXTS.get(lang, LANGUAGE_TEXTS['tr'])
        
        ref_code = user['referral_code']
        ref_link = f"https://t.me/{BOT_USERNAME}?start={ref_code}"
        refs = user.get('total_referrals', 0)
        
        # Referans kazancı
        self.db.cursor.execute('SELECT SUM(earned_amount) FROM referrals WHERE referrer_id = ?', (user_id,))
        ref_earned = self.db.cursor.fetchone()[0] or 0
        
        text = f"""
👥 *{texts['referral']}*

📊 {refs}/{MIN_REFERRALS_FOR_WITHDRAW} davet
💰 ${ref_earned:.2f} kazanç

🔗 {ref_link}

📋 {ref_code}
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': texts['copy_ref_code'], 'callback_data': 'copy_ref'}],
                [{'text': "🏠 Ana Menü", 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_profile(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        texts = LANGUAGE_TEXTS.get(lang, LANGUAGE_TEXTS['tr'])
        
        refs = user.get('total_referrals', 0)
        user_type = "👤 Kazanan" if user['user_type'] == 'earner' else "📢 Reklamveren"
        
        text = f"""
👤 *{texts['profile']}*

🆔 {user_id}
👤 {user['first_name']} {user['last_name'] or ''}
📛 @{user['username'] or 'yok'}
{user_type}

💰 ${user['balance']:.2f}
🎯 {user['tasks_completed']} görev
👥 {refs} davet
📈 ${user['total_earned']:.2f}
        """
        
        # Kullanıcı türü değiştirme butonları
        buttons = []
        if user['user_type'] == 'earner':
            buttons.append([{'text': texts['switch_to_advertiser'], 'callback_data': 'switch_to_advertiser'}])
        else:
            buttons.append([{'text': texts['switch_to_earner'], 'callback_data': 'switch_to_earner'}])
        
        buttons.append([
            {'text': "💰 Bakiye", 'callback_data': 'show_balance'},
            {'text': "🎯 Görevler", 'callback_data': 'show_tasks'}
        ])
        buttons.append([{'text': "🏠 Ana Menü", 'callback_data': 'main_menu'}])
        
        keyboard = {'inline_keyboard': buttons}
        send_message(user_id, text, reply_markup=keyboard)
    
    def switch_to_advertiser(self, user_id, callback_id):
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Hata")
            return
        
        if user['user_type'] == 'advertiser':
            answer_callback_query(callback_id, "✅ Zaten reklamverensin")
            return
        
        # Bakiye varsa dönüşüm sor
        if user['balance'] > 0:
            self.user_states[user_id] = {'action': 'convert_balance'}
            send_message(user_id, f"💰 Bakiyen: ${user['balance']:.2f}\n{user['language'] == 'tr' and 'Bakiyeni saklamak istiyor musun? (Evet/Hayır)' or 'Keep balance? (Yes/No)'}")
            answer_callback_query(callback_id, "⚠️ Bakiye dönüşümü")
        else:
            self.db.update_user_type(user_id, 'advertiser')
            answer_callback_query(callback_id, "✅ Reklamveren oldun")
            time.sleep(1)
            self.show_profile(user_id)
    
    def switch_to_earner(self, user_id, callback_id):
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Hata")
            return
        
        if user['user_type'] == 'earner':
            answer_callback_query(callback_id, "✅ Zaten kazanansın")
            return
        
        self.db.update_user_type(user_id, 'earner')
        answer_callback_query(callback_id, "✅ Kazanan oldun")
        time.sleep(1)
        self.show_profile(user_id)
    
    def show_channels(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        
        text = "📢 *Kanallar*\n\nBotu kullanmak için kanala katıl:"
        
        buttons = []
        for channel in MANDATORY_CHANNELS:
            buttons.append([{
                'text': f"➕ {channel['emoji']} {channel['name']}",
                'url': channel['link']
            }])
        
        buttons.append([{'text': "✅ Kontrol Et", 'callback_data': 'check_channels'}])
        buttons.append([{'text': "🏠 Ana Menü", 'callback_data': 'main_menu'}])
        
        keyboard = {'inline_keyboard': buttons}
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_help(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        texts = LANGUAGE_TEXTS.get(lang, LANGUAGE_TEXTS['tr'])
        
        text = f"""
❓ *Yardım*

🎯 Görev yap → Para kazan
👥 {MIN_REFERRALS_FOR_WITHDRAW} davet → Para çek
💳 TRON (TRX) → Ödeme
📞 {SUPPORT_USERNAME} → Destek

🤖 @{BOT_USERNAME}
📢 @TaskizLive
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "🎯 Görevler", 'callback_data': 'show_tasks'}],
                [{'text': "👥 Davet", 'callback_data': 'show_referral'}],
                [{'text': "🏠 Ana Menü", 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)

# Bot başlat
bot = TaskizBot()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 {BOT_NAME} başlatılıyor...")
    app.run(host='0.0.0.0', port=port, debug=False)
