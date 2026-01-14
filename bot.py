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
STATS_CHANNEL = "@TaskizLive"  # İstatistik kanalı

# Zorunlu Kanallar
MANDATORY_CHANNELS = [
    {
        'username': 'TaskizLive',
        'link': 'https://t.me/TaskizLive',
        'name': 'İstatistik Kanalı',
        'emoji': '📊'
    }
]

if not TOKEN:
    raise ValueError("Bot token gerekli!")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Dil Ayarları
SUPPORTED_LANGUAGES = {
    'tr': {'name': 'Türkçe', 'flag': '🇹🇷', 'currency': 'TRY'},
    'en': {'name': 'English', 'flag': '🇺🇸', 'currency': 'USD'},
    'pt': {'name': 'Português', 'flag': '🇵🇹', 'currency': 'BRL'}
}

# TRX Ayarları
TRX_ADDRESS = os.environ.get("TRX_ADDRESS", "DEPOZIT_YAPILACAK_ADRES")
MIN_DEPOSIT_USD = 2.5
MAX_DEPOSIT_USD = 10.0
MIN_WITHDRAW = 0.30  # Minimum çekim miktarı
MIN_REFERRALS_FOR_WITHDRAW = 10  # Çekim için minimum referans sayısı
REF_WELCOME_BONUS = 0.005
REF_TASK_COMMISSION = 0.25

# Hızlı bakiye yükleme miktarları
DEPOSIT_AMOUNTS = [0.50, 1.0, 2.5, 5.0, 10.0, 25.0]

# Flask App
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "online", "bot": "TaskizBot v4.0", "webhook": bool(WEBHOOK_URL)})

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    bot.handle_update(update)
    return jsonify({"status": "ok"})

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
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

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode='Markdown'):
    """Mesajı düzenle"""
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

# Dil Metinleri
LANGUAGE_TEXTS = {
    'tr': {
        'welcome': "🎉 *TaskizBot'a Hoş Geldiniz!*",
        'balance': "💰 Bakiye",
        'tasks': "🎯 Görevler",
        'withdraw': "🏧 Para Çek",
        'deposit': "💳 Yükle",
        'deposit_quick': "🚀 Hızlı Yükle",
        'profile': "👤 Profil",
        'referral': "👥 Referans",
        'help': "❓ Yardım",
        'channels': "📢 Kanallar",
        'back': "🔙 Geri",
        'refresh': "🔄 Yenile",
        'check_channels': "🔍 Kontrol Et",
        'earner': "👤 Kazanan",
        'advertiser': "📢 Reklamveren",
        'select_type': "🌟 *Hangi tür kullanıcı olmak istiyorsunuz?*",
        'choose_lang': "🌍 *Dilinizi seçin:*",
        'mandatory_channels': "📋 *Zorunlu Kanallar*",
        'all_channels_joined': "✅ *Tüm kanallara katıldınız!*",
        'not_joined_all': "⚠️ *Eksik Kanallar*",
        'main_menu': "🏠 *Ana Menü*",
        'your_balance': "💰 *Bakiyeniz:*",
        'min_withdraw': f"📉 Minimum çekim: ${MIN_WITHDRAW}",
        'min_deposit': f"📈 Minimum yükleme: ${MIN_DEPOSIT_USD}",
        'min_referrals_for_withdraw': f"👥 Para çekmek için minimum {MIN_REFERRALS_FOR_WITHDRAW} referans gerekiyor",
        'contact_support': f"📞 Destek: {SUPPORT_USERNAME}",
        'error': "❌ Hata",
        'success': "✅ Başarılı",
        'loading': "⏳ Yükleniyor...",
        'welcome_back': "👋 Tekrar Hoş Geldiniz!",
        'available_tasks': "🎯 *Mevcut Görevler*",
        'no_tasks': "📭 Şu anda mevcut görev bulunmuyor",
        'task_reward': "💰 Ödül",
        'task_participants': "👥 Katılımcı",
        'join_task': "🎯 Katıl",
        'refresh_tasks': "🔄 Görevleri Yenile",
        'deposit_amounts': "💰 Hızlı Yükleme",
        'test_deposit': "⚠️ Test İçin Butonlara Basın",
        'complete_task': "✅ Görevi Tamamla",
        'share_post': "📤 Gönderi Paylaş",
        'like_bot': "🤖 Botu Beğen",
        'join_channel': "➕ Kanala Katıl",
        'atm': "🏧 ATM",
        'withdraw_money': "💸 Para Çek",
        'deposit_money': "💳 Para Yükle",
        'copy_ref_code': "📋 Kodu Kopyala",
        'referral_stats': "📊 Referans İstatistik",
        'total_earned': "💰 Toplam Kazanç",
        'tasks_completed': "✅ Tamamlanan Görev",
        'join_now': "🎯 Hemen Katıl",
        'quick_actions': "⚡ Hızlı İşlemler",
        'go_back': "⬅️ Geri Dön",
        'referral_required': "👥 Referans Gerekiyor",
        'withdraw_conditions': "📋 Çekim Şartları",
        'payment_method': "💳 Ödeme Yöntemi: TRON (TRX)",
        'not_enough_referrals': "❌ Yetersiz Referans",
        'withdraw_conditions_title': "🏧 Para Çekme Şartları",
        'tron_payment': "🔗 TRON ile Ödeme",
        'referrals_count': "👥 Referans Sayısı",
        'referrals_needed': "🎯 Gereken Referans",
        'withdraw_rules': "📜 Çekim Kuralları"
    },
    'en': {
        'welcome': "🎉 *Welcome to TaskizBot!*",
        'balance': "💰 Balance",
        'tasks': "🎯 Tasks",
        'withdraw': "🏧 Withdraw",
        'deposit': "💳 Deposit",
        'deposit_quick': "🚀 Quick Deposit",
        'profile': "👤 Profile",
        'referral': "👥 Referral",
        'help': "❓ Help",
        'channels': "📢 Channels",
        'back': "🔙 Back",
        'refresh': "🔄 Refresh",
        'check_channels': "🔍 Check",
        'earner': "👤 Earner",
        'advertiser': "📢 Advertiser",
        'select_type': "🌟 *What type of user do you want to be?*",
        'choose_lang': "🌍 *Choose your language:*",
        'mandatory_channels': "📋 *Mandatory Channels*",
        'all_channels_joined': "✅ *All channels joined!*",
        'not_joined_all': "⚠️ *Missing Channels*",
        'main_menu': "🏠 *Main Menu*",
        'your_balance': "💰 *Your Balance:*",
        'min_withdraw': f"📉 Minimum withdrawal: ${MIN_WITHDRAW}",
        'min_deposit': f"📈 Minimum deposit: ${MIN_DEPOSIT_USD}",
        'min_referrals_for_withdraw': f"👥 Minimum {MIN_REFERRALS_FOR_WITHDRAW} referrals required for withdrawal",
        'contact_support': f"📞 Support: {SUPPORT_USERNAME}",
        'error': "❌ Error",
        'success': "✅ Success",
        'loading': "⏳ Loading...",
        'welcome_back': "👋 Welcome Back!",
        'available_tasks': "🎯 *Available Tasks*",
        'no_tasks': "📭 No tasks available",
        'task_reward': "💰 Reward",
        'task_participants': "👥 Participants",
        'join_task': "🎯 Join",
        'refresh_tasks': "🔄 Refresh Tasks",
        'deposit_amounts': "💰 Quick Deposit",
        'test_deposit': "⚠️ Click Buttons for Test",
        'complete_task': "✅ Complete Task",
        'share_post': "📤 Share Post",
        'like_bot': "🤖 Like Bot",
        'join_channel': "➕ Join Channel",
        'atm': "🏧 ATM",
        'withdraw_money': "💸 Withdraw Money",
        'deposit_money': "💳 Deposit Money",
        'copy_ref_code': "📋 Copy Code",
        'referral_stats': "📊 Referral Stats",
        'total_earned': "💰 Total Earned",
        'tasks_completed': "✅ Tasks Completed",
        'join_now': "🎯 Join Now",
        'quick_actions': "⚡ Quick Actions",
        'go_back': "⬅️ Go Back",
        'referral_required': "👥 Referral Required",
        'withdraw_conditions': "📋 Withdrawal Conditions",
        'payment_method': "💳 Payment Method: TRON (TRX)",
        'not_enough_referrals': "❌ Not Enough Referrals",
        'withdraw_conditions_title': "🏧 Withdrawal Conditions",
        'tron_payment': "🔗 Payment with TRON",
        'referrals_count': "👥 Referrals Count",
        'referrals_needed': "🎯 Required Referrals",
        'withdraw_rules': "📜 Withdrawal Rules"
    }
}

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
                referred_by TEXT,
                tasks_completed INTEGER DEFAULT 0,
                total_earned REAL DEFAULT 0,
                total_referrals INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Referanslar tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER UNIQUE,
                earned_amount REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Görevler tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                reward REAL,
                max_participants INTEGER,
                current_participants INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                task_type TEXT DEFAULT 'general',
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
                UNIQUE(task_id, user_id)
            )
        ''')
        
        # Para çekme talepleri
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                trx_address TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        ''')
        
        # İstatistik tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_users INTEGER DEFAULT 0,
                active_today INTEGER DEFAULT 0,
                total_earned REAL DEFAULT 0,
                total_tasks INTEGER DEFAULT 0,
                total_withdrawals INTEGER DEFAULT 0,
                total_withdrawal_amount REAL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Örnek görevler ekle
        self.add_sample_tasks()
        self.connection.commit()
        print("✅ Veritabanı tabloları oluşturuldu")
    
    def add_sample_tasks(self):
        self.cursor.execute('SELECT COUNT(*) FROM tasks')
        if self.cursor.fetchone()[0] == 0:
            sample_tasks = [
                ('Telegram Kanalına Katıl', '@TaskizLive kanalına katılın', 0.05, 100, 'channel_join'),
                ('Botu Beğen ve Yorum Yap', 'Botu beğenin ve yorum yapın', 0.03, 50, 'like'),
                ('Gönderi Paylaş', 'Belirtilen gönderiyi paylaşın', 0.08, 30, 'share'),
                ('Günlük Giriş Bonusu', 'Günlük giriş yaparak bonus kazanın', 0.01, 1000, 'daily'),
                ('Arkadaş Davet Et', 'Arkadaşınızı davet edin (10 referans)', 0.10, 500, 'referral'),
            ]
            
            for task in sample_tasks:
                self.cursor.execute('''
                    INSERT INTO tasks (title, description, reward, max_participants, task_type)
                    VALUES (?, ?, ?, ?, ?)
                ''', task)
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            user = dict(row)
            # Toplam referans sayısını hesapla
            self.cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND status = ?', 
                              (user_id, 'active'))
            user['total_referrals'] = self.cursor.fetchone()[0]
            return user
        return None
    
    def create_user(self, user_id, username, first_name, last_name, language='tr', referred_by=None):
        referral_code = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8].upper()
        
        self.cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, language, referral_code, referred_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, language, referral_code, referred_by))
        
        # Referans bonusu
        if referred_by:
            referrer = self.get_user(referred_by)
            if referrer:
                # Referans kaydı oluştur
                self.cursor.execute('''
                    INSERT OR IGNORE INTO referrals (referrer_id, referred_id, earned_amount, status)
                    VALUES (?, ?, ?, ?)
                ''', (referred_by, user_id, REF_WELCOME_BONUS, 'active'))
                
                # Referrer'a bonus ver
                self.cursor.execute('''
                    UPDATE users SET 
                    balance = balance + ?,
                    total_referrals = total_referrals + 1
                    WHERE user_id = ?
                ''', (REF_WELCOME_BONUS, referred_by))
        
        self.connection.commit()
        return self.get_user(user_id)
    
    def update_last_active(self, user_id):
        self.cursor.execute('UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
        self.connection.commit()
    
    def get_user_referrals_count(self, user_id):
        """Kullanıcının aktif referans sayısını getir"""
        self.cursor.execute('''
            SELECT COUNT(*) FROM referrals 
            WHERE referrer_id = ? AND status = 'active'
        ''', (user_id,))
        return self.cursor.fetchone()[0]
    
    def update_stats(self):
        """İstatistikleri güncelle"""
        # Toplam kullanıcı
        self.cursor.execute("SELECT COUNT(*) FROM users")
        total_users = self.cursor.fetchone()[0]
        
        # Aktif kullanıcılar (son 24 saat)
        yesterday = (datetime.now() - timedelta(hours=24)).isoformat()
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (yesterday,))
        active_today = self.cursor.fetchone()[0]
        
        # Toplam kazanç
        self.cursor.execute("SELECT SUM(total_earned) FROM users")
        total_earned = self.cursor.fetchone()[0] or 0
        
        # Toplam görev
        self.cursor.execute("SELECT SUM(tasks_completed) FROM users")
        total_tasks = self.cursor.fetchone()[0] or 0
        
        # Toplam çekim
        self.cursor.execute("SELECT COUNT(*), SUM(amount) FROM withdrawals WHERE status = 'completed'")
        withdrawal_data = self.cursor.fetchone()
        total_withdrawals = withdrawal_data[0] or 0
        total_withdrawal_amount = withdrawal_data[1] or 0
        
        # İstatistikleri kaydet
        self.cursor.execute('''
            INSERT INTO stats (total_users, active_today, total_earned, total_tasks, 
                             total_withdrawals, total_withdrawal_amount, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (total_users, active_today, total_earned, total_tasks, total_withdrawals, total_withdrawal_amount))
        
        self.connection.commit()
        return {
            'total_users': total_users,
            'active_today': active_today,
            'total_earned': round(total_earned, 2),
            'total_tasks': total_tasks,
            'total_withdrawals': total_withdrawals,
            'total_withdrawal_amount': round(total_withdrawal_amount, 2)
        }
    
    def create_withdrawal_request(self, user_id, amount, trx_address):
        """Para çekme talebi oluştur"""
        self.cursor.execute('''
            INSERT INTO withdrawals (user_id, amount, trx_address, status)
            VALUES (?, ?, ?, 'pending')
        ''', (user_id, amount, trx_address))
        
        # Kullanıcı bakiyesini düş
        self.cursor.execute('''
            UPDATE users SET balance = balance - ? 
            WHERE user_id = ?
        ''', (amount, user_id))
        
        self.connection.commit()
        return self.cursor.lastrowid
    
    def get_latest_stats(self):
        """Son istatistikleri getir"""
        self.cursor.execute('''
            SELECT * FROM stats 
            ORDER BY updated_at DESC 
            LIMIT 1
        ''')
        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None

# İstatistik Bildirim Sınıfı
class StatsNotifier:
    def __init__(self, db):
        self.db = db
        self.running = False
        self.last_stats_message_id = None
    
    def start(self):
        self.running = True
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        print("📊 İstatistik bildirim sistemi başlatıldı")
    
    def run(self):
        while self.running:
            try:
                self.update_stats_channel()
                time.sleep(300)  # 5 dakikada bir
            except Exception as e:
                print(f"❌ İstatistik güncelleme hatası: {e}")
                time.sleep(60)
    
    def update_stats_channel(self):
        """İstatistik kanalını güncelle"""
        try:
            stats = self.db.update_stats()
            message = self.generate_stats_message(stats)
            
            if self.last_stats_message_id:
                try:
                    edit_message(STATS_CHANNEL, self.last_stats_message_id, message)
                except:
                    # Mesaj düzenlenemezse yeni mesaj gönder
                    response = send_message(STATS_CHANNEL, message)
                    if response and response.get('ok'):
                        self.last_stats_message_id = response['result']['message_id']
            else:
                response = send_message(STATS_CHANNEL, message)
                if response and response.get('ok'):
                    self.last_stats_message_id = response['result']['message_id']
                    
        except Exception as e:
            print(f"❌ İstatistik kanalı güncelleme hatası: {e}")
    
    def generate_stats_message(self, stats):
        """İstatistik mesajı oluştur"""
        now = datetime.now()
        
        message = f"""
📊 *TASKIZBOT CANLI İSTATİSTİKLER*
⏰ {now.strftime('%d.%m.%Y %H:%M')} (TR)

━━━━━━━━━━━━━━━━
👥 *Toplam Kullanıcı:* `{stats['total_users']}`
📈 *Aktif Kullanıcı (24s):* `{stats['active_today']}`
💰 *Toplam Kazanç:* `${stats['total_earned']:.2f}`
🎯 *Tamamlanan Görev:* `{stats['total_tasks']}`
🏧 *Toplam Çekim:* `${stats['total_withdrawal_amount']:.2f}`
💸 *Çekim Sayısı:* `{stats['total_withdrawals']}`
━━━━━━━━━━━━━━━━

📊 *Son 24 Saat:*
• Yeni kullanıcılar eklendi
• Görev tamamlamaları arttı
• Toplam kazanç yükseldi

💡 *Çekim Şartları:*
• Minimum çekim: `${MIN_WITHDRAW}`
• Minimum referans: `{MIN_REFERRALS_FOR_WITHDRAW}`
• Ödeme yöntemi: `TRON (TRX)`

🤖 @{(TOKEN.split(':')[0])}
📊 @TaskizLive
        """
        
        return message

# Bot Sınıfı
class TaskizBot:
    def __init__(self):
        self.db = Database()
        self.stats_notifier = StatsNotifier(self.db)
        self.stats_notifier.start()
        self.user_states = {}
        print("🤖 TaskizBot v4.0 başlatıldı!")
    
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
        
        # Referans kontrolü
        referred_by = None
        if 'entities' in message:
            for entity in message['entities']:
                if entity['type'] == 'bot_command' and text.startswith('/start'):
                    parts = text.split()
                    if len(parts) > 1:
                        referral_code = parts[1]
                        self.db.cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (referral_code,))
                        row = self.db.cursor.fetchone()
                        if row:
                            referred_by = row[0]
        
        user = self.db.get_user(user_id)
        
        if not user:
            self.start_registration(message, referred_by)
            return
        
        self.db.update_last_active(user_id)
        
        # Kullanıcı durumunu kontrol et
        if user_id in self.user_states:
            state = self.user_states[user_id]
            if state['action'] == 'waiting_for_trx_address':
                self.handle_trx_address(user_id, text, user)
                return
        
        self.process_command(user_id, text, user)
    
    def handle_trx_address(self, user_id, trx_address, user):
        """TRX adresi alındığında"""
        if user_id in self.user_states:
            state = self.user_states[user_id]
            amount = state.get('withdraw_amount', 0)
            
            # TRX adresi doğrulama (basit kontrol)
            if len(trx_address) < 10:
                send_message(user_id, "❌ Geçersiz TRX adresi! Lütfen geçerli bir TRX adresi girin.")
                return
            
            # Para çekme talebi oluştur
            withdrawal_id = self.db.create_withdrawal_request(user_id, amount, trx_address)
            
            # Grup mesajı gönder
            group_message = f"""
🏧 *YENİ PARA ÇEKME TALEBİ*
━━━━━━━━━━━━━━━━
👤 Kullanıcı: {user['first_name']} {user['last_name'] or ''}
🆔 ID: `{user_id}`
💰 Miktar: `${amount:.2f}`
🔗 TRX Adres: `{trx_address[:15]}...`
📅 Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}
━━━━━━━━━━━━━━━━
🎯 Referans: {user['total_referrals']}/{MIN_REFERRALS_FOR_WITHDRAW}
📋 Talep ID: `{withdrawal_id}`
            """
            
            try:
                send_message(STATS_CHANNEL, group_message)
            except Exception as e:
                print(f"❌ Grup mesajı gönderme hatası: {e}")
            
            # Kullanıcıya onay mesajı
            send_message(user_id, f"""
✅ *Para Çekme Talebiniz Alındı!*

━━━━━━━━━━━━━━━━
💰 Çekim Miktarı: `${amount:.2f}`
🔗 TRX Adresiniz: `{trx_address}`
📋 Talep ID: `{withdrawal_id}`
━━━━━━━━━━━━━━━━

⏳ *İşlem Durumu:* Beklemede
📞 *Destek:* {SUPPORT_USERNAME}

💡 Talep durumunu destek ekibinden öğrenebilirsiniz.
            """)
            
            # Kullanıcı durumunu temizle
            del self.user_states[user_id]
            
            # Ana menüye dön
            time.sleep(2)
            self.show_main_menu(user_id, user['language'])
    
    def start_registration(self, message, referred_by=None):
        user_id = message['from']['id']
        username = message['from'].get('username', '')
        first_name = message['from'].get('first_name', '')
        last_name = message['from'].get('last_name', '')
        
        user = self.db.create_user(user_id, username, first_name, last_name, 'tr', referred_by)
        self.show_language_selection(user_id)
    
    def show_language_selection(self, user_id):
        text = "🌍 *Dil Seçimi / Language Selection*\n\nLütfen dilinizi seçin:"
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '🇹🇷 Türkçe', 'callback_data': 'lang_tr'},
                    {'text': '🇺🇸 English', 'callback_data': 'lang_en'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_callback_query(self, callback_query):
        data = callback_query['data']
        user_id = callback_query['from']['id']
        callback_id = callback_query['id']
        message_id = callback_query['message']['message_id'] if 'message' in callback_query else None
        
        try:
            # Dil seçimi
            if data.startswith('lang_'):
                language = data.split('_')[1]
                self.handle_language_selection(user_id, language, callback_id)
                
            # Kanal kontrolü
            elif data == 'check_channels':
                self.check_user_channels(user_id)
                answer_callback_query(callback_id, "📊 Kanallar kontrol ediliyor...")
                
            # Ana menü
            elif data == 'show_main_menu':
                user = self.db.get_user(user_id)
                if user:
                    self.show_main_menu(user_id, user['language'])
                answer_callback_query(callback_id)
                
            # Profil
            elif data == 'show_profile':
                self.show_profile(user_id)
                answer_callback_query(callback_id)
                
            # Bakiye
            elif data == 'show_balance':
                self.show_balance(user_id)
                answer_callback_query(callback_id)
                
            # Görevler
            elif data == 'show_tasks':
                self.show_tasks(user_id)
                answer_callback_query(callback_id)
                
            # Para çekme
            elif data == 'show_withdraw':
                self.show_withdraw(user_id)
                answer_callback_query(callback_id)
                
            # Bakiye yükleme
            elif data == 'show_deposit':
                self.show_deposit_with_buttons(user_id)
                answer_callback_query(callback_id)
                
            # Referans
            elif data == 'show_referral':
                self.show_referral(user_id)
                answer_callback_query(callback_id)
                
            # Kanallar
            elif data == 'show_channels':
                self.show_channels_detailed(user_id)
                answer_callback_query(callback_id)
                
            # Yardım
            elif data == 'show_help':
                self.show_help(user_id)
                answer_callback_query(callback_id)
                
            # Kullanıcı türü seçimi
            elif data.startswith('user_type_'):
                user_type = data.split('_')[2]
                self.handle_user_type_selection(user_id, user_type, callback_id)
                
            # Göreve katılma
            elif data.startswith('join_task_'):
                task_id = int(data.split('_')[2])
                self.handle_join_task(user_id, task_id, callback_id)
                
            # Görevleri yenile
            elif data == 'refresh_tasks':
                self.show_tasks(user_id)
                answer_callback_query(callback_id, "🔄 Görevler yenileniyor...")
                
            # Kanalları yenile
            elif data == 'refresh_channels':
                self.check_user_channels(user_id)
                answer_callback_query(callback_id)
                
            # Referans kodu kopyala
            elif data == 'copy_ref':
                user = self.db.get_user(user_id)
                if user:
                    answer_callback_query(callback_id, 
                        f"📋 Referans kodunuz: {user['referral_code']}\n\nKopyalamak için seçin!", 
                        show_alert=True)
                        
            # Bakiye yükleme butonları
            elif data.startswith('deposit_'):
                amount = float(data.split('_')[1])
                self.handle_deposit_button(user_id, amount, callback_id)
                
            # ATM işlemleri
            elif data == 'atm_withdraw':
                self.show_withdraw(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'atm_deposit':
                self.show_deposit_with_buttons(user_id)
                answer_callback_query(callback_id)
                
            # Hızlı işlemler
            elif data == 'quick_tasks':
                self.show_tasks(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'quick_balance':
                self.show_balance(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'quick_deposit':
                self.show_deposit_with_buttons(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'quick_withdraw':
                self.show_withdraw(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'quick_referral':
                self.show_referral(user_id)
                answer_callback_query(callback_id)
                
            # Para çekme başlatma
            elif data.startswith('withdraw_'):
                amount = float(data.split('_')[1])
                self.start_withdrawal_process(user_id, amount, callback_id)
        
        except Exception as e:
            print(f"❌ Callback işleme hatası: {e}")
            answer_callback_query(callback_id, "❌ Bir hata oluştu!")
    
    def handle_language_selection(self, user_id, language, callback_id):
        self.db.cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (language, user_id))
        self.db.connection.commit()
        self.show_user_type_selection(user_id, language)
        answer_callback_query(callback_id, "✅ Dil seçildi!")
    
    def show_user_type_selection(self, user_id, language):
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"{texts['select_type']}\n\n" \
               f"🎯 {texts['earner']} - Görev yaparak para kazan\n" \
               f"📢 {texts['advertiser']} - Reklam vererek kitle oluştur"
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': f"🎯 {texts['earner']}", 'callback_data': 'user_type_earner'},
                    {'text': f"📢 {texts['advertiser']}", 'callback_data': 'user_type_advertiser'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_user_type_selection(self, user_id, user_type, callback_id):
        self.db.cursor.execute('UPDATE users SET user_type = ? WHERE user_id = ?', (user_type, user_id))
        self.db.connection.commit()
        
        user = self.db.get_user(user_id)
        texts = LANGUAGE_TEXTS.get(user['language'], LANGUAGE_TEXTS['tr'])
        
        answer_callback_query(callback_id, f"✅ {texts['success']}! {user_type.capitalize()} olarak kaydedildiniz!")
        
        time.sleep(1)
        self.show_main_menu(user_id, user['language'])
    
    def check_user_channels(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        not_joined = []
        all_joined = True
        
        for channel in MANDATORY_CHANNELS:
            joined = get_chat_member(f"@{channel['username']}", user_id)
            if not joined:
                not_joined.append(channel)
                all_joined = False
        
        if all_joined:
            text = f"✅ *{texts['all_channels_joined']}*\n\n✨ Tüm kanallara katıldınız! Görev yapmaya başlayabilirsiniz."
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': "🎯 Görevlere Başla", 'callback_data': 'show_tasks'}],
                    [{'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}]
                ]
            }
            
            send_message(user_id, text, reply_markup=keyboard)
        else:
            text = f"⚠️ *{texts['not_joined_all']}*\n\nHenüz katılmadığınız kanallar:\n"
            
            for channel in not_joined:
                text += f"\n❌ {channel['emoji']} {channel['name']}"
            
            text += "\n\n👉 Tüm kanallara katılıp tekrar kontrol edin!"
            
            buttons = []
            for channel in not_joined:
                buttons.append([
                    {'text': f"➕ {channel['emoji']} {channel['name']} Katıl", 'url': channel['link']}
                ])
            
            buttons.append([
                {'text': "🔍 Tekrar Kontrol Et", 'callback_data': 'refresh_channels'}
            ])
            
            keyboard = {'inline_keyboard': buttons}
            send_message(user_id, text, reply_markup=keyboard)
    
    def show_channels_detailed(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"📋 *{texts['mandatory_channels']}*\n\n" \
               f"Botu kullanmak için aşağıdaki kanala katılmanız gerekiyor:\n"
        
        for channel in MANDATORY_CHANNELS:
            text += f"\n{channel['emoji']} *{channel['name']}*"
            text += f"\n   👉 @{channel['username']}\n"
        
        text += f"\n✅ Tüm kanallara katıldıktan sonra 'Kontrol Et' butonuna basın."
        
        buttons = []
        for channel in MANDATORY_CHANNELS:
            buttons.append([
                {'text': f"➕ {channel['emoji']} {channel['name']} Katıl", 'url': channel['link']}
            ])
        
        buttons.append([
            {'text': "🔍 Kontrol Et", 'callback_data': 'check_channels'}
        ])
        
        keyboard = {'inline_keyboard': buttons}
        send_message(user_id, text, reply_markup=keyboard)
    
    def process_command(self, user_id, text, user):
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        if text.startswith('/'):
            if text == '/start':
                self.show_main_menu(user_id, language)
            elif text == '/help':
                self.show_help(user_id)
            elif text == '/profile':
                self.show_profile(user_id)
            elif text == '/balance':
                self.show_balance(user_id)
            elif text == '/tasks':
                self.show_tasks(user_id)
            elif text == '/withdraw':
                self.show_withdraw(user_id)
            elif text == '/deposit':
                self.show_deposit_with_buttons(user_id)
            elif text == '/referral':
                self.show_referral(user_id)
            elif text == '/channels':
                self.show_channels_detailed(user_id)
            else:
                self.show_main_menu(user_id, language)
        else:
            # Buton komutlarını işle
            if text == texts['help']:
                self.show_help(user_id)
            elif text == texts['profile']:
                self.show_profile(user_id)
            elif text == texts['balance']:
                self.show_balance(user_id)
            elif text == texts['tasks']:
                self.show_tasks(user_id)
            elif text == texts['withdraw']:
                self.show_withdraw(user_id)
            elif text == texts['deposit'] or text == texts['deposit_quick']:
                self.show_deposit_with_buttons(user_id)
            elif text == texts['referral']:
                self.show_referral(user_id)
            elif text == texts['channels']:
                self.show_channels_detailed(user_id)
            elif text == texts['check_channels']:
                self.check_user_channels(user_id)
            elif text == texts['back']:
                self.show_main_menu(user_id, language)
            else:
                self.show_main_menu(user_id, language)
    
    def show_main_menu(self, user_id, language):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Kanal kontrolü
        if not self.check_all_channels(user_id):
            self.show_channels_detailed(user_id)
            return
        
        balance = user['balance']
        tasks_completed = user['tasks_completed']
        total_earned = user['total_earned']
        total_referrals = user.get('total_referrals', 0)
        
        text = f"""
🏠 *{texts['main_menu']}*

━━━━━━━━━━━━━━━━
💰 *Bakiye:* `${balance:.2f}`
🎯 *Görev:* `{tasks_completed}`
👥 *Referans:* `{total_referrals}/{MIN_REFERRALS_FOR_WITHDRAW}`
📈 *Toplam:* `${total_earned:.2f}`
━━━━━━━━━━━━━━━━

⚡ *{texts['quick_actions']}*
        """
        
        # Reply keyboard oluştur
        keyboard = {
            'keyboard': [
                [texts['tasks'], texts['balance']],
                [texts['withdraw'], texts['deposit_quick']],
                [texts['referral'], texts['profile']],
                [texts['channels'], texts['help']]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def check_all_channels(self, user_id):
        for channel in MANDATORY_CHANNELS:
            if not get_chat_member(f"@{channel['username']}", user_id):
                return False
        return True
    
    def show_tasks(self, user_id):
        """Görevler sayfası - Güncellenmiş tasarım"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Aktif görevleri getir
        self.db.cursor.execute('''
            SELECT * FROM tasks 
            WHERE status = 'active' 
            AND current_participants < max_participants
            ORDER BY task_type, reward DESC
        ''')
        tasks = self.db.cursor.fetchall()
        
        if not tasks:
            text = f"🎯 *{texts['available_tasks']}*\n\n" \
                   f"📭 {texts['no_tasks']}\n\n" \
                   f"⏳ Yeni görevler için biraz sonra tekrar kontrol edin!"
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': "🔄 Yenile", 'callback_data': 'refresh_tasks'}],
                    [{'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}]
                ]
            }
        else:
            text = f"🎯 *{texts['available_tasks']}*\n\n"
            buttons = []
            
            for task in tasks:
                task_dict = dict(task)
                participants = f"{task_dict['current_participants']}/{task_dict['max_participants']}"
                
                # Görev türüne göre emoji
                emoji = "🎯"
                if task_dict['task_type'] == 'channel_join':
                    emoji = "➕"
                elif task_dict['task_type'] == 'like':
                    emoji = "🤖"
                elif task_dict['task_type'] == 'share':
                    emoji = "📤"
                elif task_dict['task_type'] == 'daily':
                    emoji = "📅"
                elif task_dict['task_type'] == 'referral':
                    emoji = "👥"
                
                text += f"\n{emoji} *{task_dict['title']}*"
                text += f"\n📝 {task_dict['description']}"
                text += f"\n💰 {texts['task_reward']}: `${task_dict['reward']:.2f}`"
                text += f"\n👥 {participants} {texts['task_participants']}\n"
                
                # Katıl butonu
                buttons.append([
                    {'text': f"🎯 Katıl (${task_dict['reward']:.2f})", 
                     'callback_data': f'join_task_{task_dict["id"]}'}
                ])
            
            text += f"\n━━━━━━━━━━━━━━━━\n✅ Tüm görevleri tamamlayarak günlük ${sum(t['reward'] for t in tasks):.2f} kazanabilirsiniz!"
            
            buttons.append([
                {'text': "🔄 Yenile", 'callback_data': 'refresh_tasks'},
                {'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}
            ])
            
            keyboard = {'inline_keyboard': buttons}
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_join_task(self, user_id, task_id, callback_id):
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Kullanıcı bulunamadı!")
            return
        
        # Kanal kontrolü
        if not self.check_all_channels(user_id):
            answer_callback_query(callback_id, "❌ Önce tüm kanallara katılmalısınız!", show_alert=True)
            return
        
        # Göreve zaten katıldı mı?
        self.db.cursor.execute('''
            SELECT COUNT(*) FROM task_participations 
            WHERE task_id = ? AND user_id = ?
        ''', (task_id, user_id))
        
        if self.db.cursor.fetchone()[0] > 0:
            answer_callback_query(callback_id, "❌ Bu göreve zaten katıldınız!", show_alert=True)
            return
        
        # Görev detaylarını al
        self.db.cursor.execute('''
            SELECT * FROM tasks 
            WHERE id = ? AND status = 'active'
        ''', (task_id,))
        
        task = self.db.cursor.fetchone()
        if not task:
            answer_callback_query(callback_id, "❌ Görev bulunamadı!", show_alert=True)
            return
        
        task_dict = dict(task)
        
        # Görev doldu mu?
        if task_dict['current_participants'] >= task_dict['max_participants']:
            answer_callback_query(callback_id, "❌ Görev doldu!", show_alert=True)
            return
        
        # Katılım kaydı oluştur
        self.db.cursor.execute('''
            INSERT OR IGNORE INTO task_participations (task_id, user_id, status)
            VALUES (?, ?, 'completed')
        ''', (task_id, user_id))
        
        # Görev katılımcı sayısını güncelle
        self.db.cursor.execute('''
            UPDATE tasks SET current_participants = current_participants + 1 
            WHERE id = ?
        ''', (task_id,))
        
        # Kullanıcıya ödül ver
        reward = task_dict['reward']
        self.db.cursor.execute('''
            UPDATE users 
            SET balance = balance + ?, 
                tasks_completed = tasks_completed + 1,
                total_earned = total_earned + ?
            WHERE user_id = ?
        ''', (reward, reward, user_id))
        
        # Referans komisyonu
        if user['referred_by']:
            commission = reward * REF_TASK_COMMISSION
            self.db.cursor.execute('''
                UPDATE users SET balance = balance + ? 
                WHERE user_id = ?
            ''', (commission, user['referred_by']))
            
            self.db.cursor.execute('''
                UPDATE referrals SET earned_amount = earned_amount + ? 
                WHERE referred_id = ?
            ''', (commission, user_id))
        
        self.db.connection.commit()
        
        # Yeni kullanıcı bilgilerini al
        user = self.db.get_user(user_id)
        
        # Grup mesajı gönder
        group_message = f"""
🎉 *YENİ GÖREV TAMAMLANDI*
━━━━━━━━━━━━━━━━
👤 Kullanıcı: {user['first_name']} {user['last_name'] or ''}
🆔 ID: `{user_id}`
🎯 Görev: {task_dict['title']}
💰 Kazanç: `${reward:.2f}`
💳 Yeni Bakiye: `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━
⏰ Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        """
        
        try:
            send_message(STATS_CHANNEL, group_message)
        except Exception as e:
            print(f"❌ Grup mesajı gönderme hatası: {e}")
        
        answer_callback_query(callback_id, 
            f"✅ Göreve katıldınız!\n💰 Kazanç: ${reward:.2f}\n💳 Yeni bakiye: ${user['balance']:.2f}", 
            show_alert=True)
        
        # Görevleri yenile
        time.sleep(2)
        self.show_tasks(user_id)
    
    def handle_deposit_button(self, user_id, amount, callback_id):
        """Bakiye yükleme butonuna basıldığında"""
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Kullanıcı bulunamadı!")
            return
        
        # Bakiye yükle
        self.db.cursor.execute('''
            UPDATE users SET balance = balance + ? 
            WHERE user_id = ?
        ''', (amount, user_id))
        self.db.connection.commit()
        
        # Yeni kullanıcıyı al
        user = self.db.get_user(user_id)
        
        # Grup mesajı gönder
        group_message = f"""
💰 *BAKİYE YÜKLENDİ*
━━━━━━━━━━━━━━━━
👤 Kullanıcı: {user['first_name']} {user['last_name'] or ''}
🆔 ID: `{user_id}`
💰 Miktar: `${amount:.2f}`
📈 Yeni Bakiye: `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━
⏰ Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        """
        
        try:
            send_message(STATS_CHANNEL, group_message)
        except Exception as e:
            print(f"❌ Grup mesajı gönderme hatası: {e}")
        
        answer_callback_query(callback_id, 
            f"✅ ${amount:.2f} bakiye yüklendi!\n💰 Yeni bakiyeniz: ${user['balance']:.2f}", 
            show_alert=True)
        
        time.sleep(2)
        self.show_main_menu(user_id, user['language'])
    
    def show_deposit_with_buttons(self, user_id):
        """Butonlu bakiye yükleme ekranı"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
💳 *{texts['deposit_money']}*

━━━━━━━━━━━━━━━━
💰 *Mevcut Bakiye:* `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━

🚀 *{texts['deposit_amounts']}:*
        
{texts['test_deposit']}

💡 *Not:* Gerçek TRX gönderimi için adres:
`{TRX_ADDRESS}`
        """
        
        # Butonları oluştur
        buttons = []
        row = []
        
        for amount in DEPOSIT_AMOUNTS:
            row.append({
                'text': f"${amount}",
                'callback_data': f'deposit_{amount}'
            })
            
            if len(row) == 3:  # Her satırda 3 buton
                buttons.append(row)
                row = []
        
        if row:  # Kalan butonlar
            buttons.append(row)
        
        # Ek butonlar
        buttons.append([
            {'text': "🏧 ATM", 'callback_data': 'atm_deposit'},
            {'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}
        ])
        
        keyboard = {'inline_keyboard': buttons}
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_balance(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        total_referrals = user.get('total_referrals', 0)
        
        text = f"""
💰 *{texts['your_balance']}*

━━━━━━━━━━━━━━━━
💳 *Mevcut Bakiye:* `${user['balance']:.2f}`
🎯 *Tamamlanan Görev:* `{user['tasks_completed']}`
👥 *Referans Sayısı:* `{total_referrals}/{MIN_REFERRALS_FOR_WITHDRAW}`
📈 *Toplam Kazanç:* `${user['total_earned']:.2f}`
━━━━━━━━━━━━━━━━

📋 *{texts['withdraw_conditions']}:*
• {texts['min_withdraw']}
• {texts['min_referrals_for_withdraw']}
• {texts['payment_method']}

⚡ *Hızlı İşlemler:*
        """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': "💳 Bakiye Yükle", 'callback_data': 'quick_deposit'},
                    {'text': "🏧 Para Çek", 'callback_data': 'quick_withdraw'}
                ],
                [
                    {'text': "🎯 Görevlere Git", 'callback_data': 'quick_tasks'},
                    {'text': "👥 Referans", 'callback_data': 'quick_referral'}
                ],
                [
                    {'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_withdraw(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        total_referrals = user.get('total_referrals', 0)
        
        # Minimum referans kontrolü
        has_enough_referrals = total_referrals >= MIN_REFERRALS_FOR_WITHDRAW
        
        if not has_enough_referrals:
            text = f"""
🏧 *{texts['withdraw_money']}*

━━━━━━━━━━━━━━━━
💰 Mevcut Bakiye: `${user['balance']:.2f}`
📉 Minimum Çekim: `${MIN_WITHDRAW}`
👥 Referans Sayınız: `{total_referrals}/{MIN_REFERRALS_FOR_WITHDRAW}`
━━━━━━━━━━━━━━━━

❌ *{texts['not_enough_referrals']}!*

{texts['min_referrals_for_withdraw']}

💡 *Nasıl Daha Fazla Referans Kazanırım?*
1. Referans linkinizi paylaşın
2. Arkadaşlarınızı davet edin
3. Her arkadaşınız için komisyon kazanın

🎯 *Hedef:* {MIN_REFERRALS_FOR_WITHDRAW} referans
📊 *Kalan:* {MIN_REFERRALS_FOR_WITHDRAW - total_referrals} referans
            """
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': "👥 Referans Linkim", 'callback_data': 'show_referral'}],
                    [{'text': "🎯 Görevlere Git", 'callback_data': 'show_tasks'}],
                    [{'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}]
                ]
            }
            
        elif user['balance'] < MIN_WITHDRAW:
            text = f"""
🏧 *{texts['withdraw_money']}*

━━━━━━━━━━━━━━━━
💰 Mevcut Bakiye: `${user['balance']:.2f}`
📉 Minimum Çekim: `${MIN_WITHDRAW}`
👥 Referans Sayınız: `{total_referrals}/{MIN_REFERRALS_FOR_WITHDRAW}`
━━━━━━━━━━━━━━━━

✅ *{texts['referral_required']}:* Tamamlandı! ✓
❌ *Yetersiz Bakiye!*

{texts['min_withdraw']}

💡 *Öneri:* Daha fazla görev yaparak bakiyenizi artırın!
            """
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': "🎯 Görevlere Git", 'callback_data': 'show_tasks'}],
                    [{'text': "💳 Bakiye Yükle", 'callback_data': 'show_deposit'}],
                    [{'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}]
                ]
            }
            
        else:
            # Para çekme butonlarını oluştur
            balance = user['balance']
            suggested_amounts = [
                MIN_WITHDRAW,
                round(balance / 2, 2),
                balance  # Tüm bakiye
            ]
            
            # Benzersiz değerler oluştur
            suggested_amounts = list(dict.fromkeys([round(a, 2) for a in suggested_amounts if a >= MIN_WITHDRAW]))
            
            text = f"""
🏧 *{texts['withdraw_money']}*

━━━━━━━━━━━━━━━━
💰 Çekilebilir Bakiye: `${balance:.2f}`
📉 Minimum Çekim: `${MIN_WITHDRAW}`
👥 Referans Sayınız: `{total_referrals}/{MIN_REFERRALS_FOR_WITHDRAW}`
🔗 Ödeme Yöntemi: `TRON (TRX)`
━━━━━━━━━━━━━━━━

✅ *Tüm şartları karşılıyorsunuz!*

💡 *TRX adresinizi hazırlayın ve miktar seçin:*
            """
            
            # Butonları oluştur
            buttons = []
            row = []
            
            for amount in suggested_amounts:
                if amount <= balance:
                    row.append({
                        'text': f"${amount} Çek",
                        'callback_data': f'withdraw_{amount}'
                    })
                    
                    if len(row) == 2:
                        buttons.append(row)
                        row = []
            
            if row:
                buttons.append(row)
            
            # Manuel miktar butonu
            buttons.append([
                {'text': "📝 Manuel Miktar", 'callback_data': 'withdraw_manual'}
            ])
            
            # Diğer butonlar
            buttons.append([
                {'text': "💳 Bakiye", 'callback_data': 'show_balance'},
                {'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}
            ])
            
            keyboard = {'inline_keyboard': buttons}
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def start_withdrawal_process(self, user_id, amount, callback_id):
        """Para çekme işlemini başlat"""
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Kullanıcı bulunamadı!")
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Kontroller
        total_referrals = user.get('total_referrals', 0)
        
        if total_referrals < MIN_REFERRALS_FOR_WITHDRAW:
            answer_callback_query(callback_id, 
                f"❌ Yetersiz referans! {MIN_REFERRALS_FOR_WITHDRAW} referans gerekiyor.", 
                show_alert=True)
            return
        
        if user['balance'] < amount:
            answer_callback_query(callback_id, 
                f"❌ Yetersiz bakiye! Mevcut bakiye: ${user['balance']:.2f}", 
                show_alert=True)
            return
        
        if amount < MIN_WITHDRAW:
            answer_callback_query(callback_id, 
                f"❌ Minimum çekim miktarı: ${MIN_WITHDRAW}", 
                show_alert=True)
            return
        
        # Kullanıcı durumunu kaydet
        self.user_states[user_id] = {
            'action': 'waiting_for_trx_address',
            'withdraw_amount': amount
        }
        
        # TRX adresi iste
        text = f"""
✅ *Para Çekme İşlemi Başlatıldı*

━━━━━━━━━━━━━━━━
💰 Çekim Miktarı: `${amount:.2f}`
💳 Mevcut Bakiye: `${user['balance']:.2f}`
🔗 Ödeme Yöntemi: `TRON (TRX)`
━━━━━━━━━━━━━━━━

📋 *Lütfen TRX cüzdan adresinizi girin:*

💡 *Örnek:* `TXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`

⚠️ *Dikkat:* Adresi doğru girdiğinizden emin olun!
⏳ *İşlem süresi:* 24-48 saat

✏️ *TRX adresinizi bu mesaja yanıt olarak gönderin:*
        """
        
        send_message(user_id, text)
        answer_callback_query(callback_id, f"✅ ${amount:.2f} çekim başlatıldı! Lütfen TRX adresinizi girin.")
    
    def show_profile(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        lang_info = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES['tr'])
        total_referrals = user.get('total_referrals', 0)
        
        # Son aktiviteyi hesapla
        last_active = user['last_active']
        if last_active:
            try:
                if isinstance(last_active, str):
                    last_active_dt = datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S')
                else:
                    last_active_dt = last_active
                
                time_diff = datetime.now() - last_active_dt
                hours_ago = int(time_diff.total_seconds() / 3600)
                
                if hours_ago < 1:
                    last_active_str = "Az önce"
                elif hours_ago < 24:
                    last_active_str = f"{hours_ago} saat önce"
                else:
                    last_active_str = f"{hours_ago // 24} gün önce"
            except:
                last_active_str = "Bilinmiyor"
        else:
            last_active_str = "Bilinmiyor"
        
        text = f"""
👤 *{texts['profile']}*

━━━━━━━━━━━━━━━━
🆔 *ID:* `{user_id}`
👤 *Ad:* `{user['first_name']} {user['last_name'] or ''}`
📛 *Kullanıcı Adı:* `@{user['username'] or 'Yok'}`
🌐 *Dil:* {lang_info['name']} {lang_info['flag']}
🎯 *Tür:* {user['user_type'].capitalize()}
━━━━━━━━━━━━━━━━

📊 *İstatistikler*
💰 Bakiye: `${user['balance']:.2f}`
🎯 Görev: `{user['tasks_completed']}`
👥 Referans: `{total_referrals}/{MIN_REFERRALS_FOR_WITHDRAW}`
📈 Toplam: `${user['total_earned']:.2f}`
⏰ Son Aktif: `{last_active_str}`
📅 Kayıt: `{user['created_at'][:10] if user['created_at'] else '-'}`
━━━━━━━━━━━━━━━━
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "💰 Bakiye", 'callback_data': 'show_balance'}],
                [{'text': "🎯 Görevler", 'callback_data': 'show_tasks'}],
                [{'text': "👥 Referans", 'callback_data': 'show_referral'}],
                [{'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_referral(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        total_referrals = user.get('total_referrals', 0)
        
        referral_code = user['referral_code']
        bot_username = TOKEN.split(':')[0] if ':' in TOKEN else 'taskizbot'
        referral_link = f"https://t.me/{bot_username}?start={referral_code}"
        
        # Referans kazancı
        self.db.cursor.execute('SELECT SUM(earned_amount) FROM referrals WHERE referrer_id = ?', (user_id,))
        referral_earned = self.db.cursor.fetchone()[0] or 0
        
        # Kalan referans sayısını hesapla
        referrals_needed = max(0, MIN_REFERRALS_FOR_WITHDRAW - total_referrals)
        
        text = f"""
👥 *{texts['referral']}*

━━━━━━━━━━━━━━━━
📊 *{texts['referral_stats']}:*
👥 Toplam Referans: `{total_referrals}/{MIN_REFERRALS_FOR_WITHDRAW}`
💰 Referans Kazancı: `${referral_earned:.2f}`
🎯 Kalan Referans: `{referrals_needed}`
━━━━━━━━━━━━━━━━

🔗 *Referans Linkiniz:*
`{referral_link}`

📋 *Referans Kodunuz:*
`{referral_code}`

💡 *{texts['withdraw_conditions']}:*
• Minimum {MIN_REFERRALS_FOR_WITHDRAW} referans gerekiyor
• Her referans için ${REF_WELCOME_BONUS} bonus
• Arkadaşlarınız görev yaptıkça %{REF_TASK_COMMISSION*100} komisyon

🎯 *Hedef:* {MIN_REFERRALS_FOR_WITHDRAW} referans ile para çekme özelliğini aç!
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "📋 Kodu Kopyala", 'callback_data': 'copy_ref'}],
                [{'text': "💰 Bakiye", 'callback_data': 'show_balance'}],
                [{'text': "🏧 Para Çek", 'callback_data': 'show_withdraw'}],
                [{'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}]
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
❓ *{texts['help']}*

━━━━━━━━━━━━━━━━
🤖 *TaskizBot Nedir?*
Görev tamamlayarak para kazanabileceğiniz bir platform.

🎯 *{texts['how_it_works']}:*
1️⃣ Zorunlu kanallara katılın
2️⃣ Görevleri tamamlayın
3️⃣ {MIN_REFERRALS_FOR_WITHDRAW} referans kazanın
4️⃣ Kazandığınız parayı çekin

━━━━━━━━━━━━━━━━
💰 *Ödemeler:*
• Minimum çekim: `${MIN_WITHDRAW}`
• Minimum referans: `{MIN_REFERRALS_FOR_WITHDRAW}`
• {texts['tron_payment']}
• 24-48 saat içinde ödeme

━━━━━━━━━━━━━━━━
📋 *{texts['withdraw_rules']}:*
• {MIN_REFERRALS_FOR_WITHDRAW} aktif referans zorunludur
• Sadece TRON (TRX) cüzdanına ödeme
• Sahte hesap açmak yasaktır
• Kurallara uymayanlar banlanır

━━━━━━━━━━━━━━━━
📞 *Destek:*
Sorularınız için iletişime geçin:
{SUPPORT_USERNAME}

#️⃣ *Popüler Komutlar:*
/start - Botu başlat
/help - Yardım menüsü
/profile - Profiliniz
/balance - Bakiyeniz
/tasks - Görevler
/withdraw - Para çekme
/referral - Referans linkiniz
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': "📢 Kanallar", 'callback_data': 'show_channels'}],
                [{'text': "🎯 Görevler", 'callback_data': 'show_tasks'}],
                [{'text': "👥 Referans", 'callback_data': 'show_referral'}],
                [{'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)

# Botu başlat
bot = TaskizBot()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    if WEBHOOK_URL:
        try:
            print("🌐 Webhook ayarlanıyor...")
            requests.get(f"{BASE_URL}deleteWebhook")
            time.sleep(1)
            
            url = f"{WEBHOOK_URL}/webhook"
            response = requests.get(f"{BASE_URL}setWebhook?url={url}")
            print(f"✅ Webhook ayarlandı: {response.json()}")
            
        except Exception as e:
            print(f"❌ Webhook hatası: {e}")
    else:
        print("⚠️ WEBHOOK_URL ayarlanmamış")
    
    print(f"🚀 Bot {port} portunda başlatılıyor...")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
