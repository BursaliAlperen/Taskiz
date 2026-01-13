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

# Dil Ayarları
SUPPORTED_LANGUAGES = {
    'tr': {'name': 'Türkçe', 'flag': '🇹🇷', 'currency': 'TRY'},
    'en': {'name': 'English', 'flag': '🇺🇸', 'currency': 'USD'},
    'ru': {'name': 'Русский', 'flag': '🇷🇺', 'currency': 'RUB'},
    'bn': {'name': 'বাংলা', 'flag': '🇧🇩', 'currency': 'BDT'},
    'pt': {'name': 'Português', 'flag': '🇵🇹', 'currency': 'BRL'}
}

# TRX Ayarları
TRX_ADDRESS = os.environ.get("TRX_ADDRESS", "DEPOZIT_YAPILACAK_ADRES")
MIN_DEPOSIT_USD = 2.5
MAX_DEPOSIT_USD = 10.0
MIN_WITHDRAW = 1.0
REF_WELCOME_BONUS = 0.005
REF_TASK_COMMISSION = 0.25

# Flask App
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "online", "bot": "TaskizBot v3.5", "webhook": bool(WEBHOOK_URL)})

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
        'profile': "👤 Profil",
        'referral': "👥 Referans",
        'help': "❓ Yardım",
        'channels': "📢 Kanallar",
        'back': "🔙 Geri",
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
        'contact_support': f"📞 Destek: {SUPPORT_USERNAME}",
        'error': "❌ Hata",
        'success': "✅ Başarılı",
        'loading': "⏳ Yükleniyor...",
        'welcome_back': "👋 Tekrar Hoş Geldiniz!",
        'available_tasks': "🎯 *Mevcut Görevler*",
        'no_tasks': "📭 Şu anda mevcut görev bulunmuyor",
        'task_reward': "💰 Ödül",
        'task_participants': "👥 Katılımcı",
        'join_task': "🎯 Göreve Katıl"
    },
    'en': {
        'welcome': "🎉 *Welcome to TaskizBot!*",
        'balance': "💰 Balance",
        'tasks': "🎯 Tasks",
        'withdraw': "🏧 Withdraw",
        'deposit': "💳 Deposit",
        'profile': "👤 Profile",
        'referral': "👥 Referral",
        'help': "❓ Help",
        'channels': "📢 Channels",
        'back': "🔙 Back",
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
        'contact_support': f"📞 Support: {SUPPORT_USERNAME}",
        'error': "❌ Error",
        'success': "✅ Success",
        'loading': "⏳ Loading...",
        'welcome_back': "👋 Welcome Back!",
        'available_tasks': "🎯 *Available Tasks*",
        'no_tasks': "📭 No tasks available",
        'task_reward': "💰 Reward",
        'task_participants': "👥 Participants",
        'join_task': "🎯 Join Task"
    },
    'pt': {
        'welcome': "🎉 *Bem-vindo ao TaskizBot!*",
        'balance': "💰 Saldo",
        'tasks': "🎯 Tarefas",
        'withdraw': "🏧 Sacar",
        'deposit': "💳 Depositar",
        'profile': "👤 Perfil",
        'referral': "👥 Indicação",
        'help': "❓ Ajuda",
        'channels': "📢 Canais",
        'back': "🔙 Voltar",
        'check_channels': "🔍 Verificar",
        'earner': "👤 Ganhador",
        'advertiser': "📢 Anunciante",
        'select_type': "🌟 *Que tipo de usuário você quer ser?*",
        'choose_lang': "🌍 *Escolha seu idioma:*",
        'mandatory_channels': "📋 *Canais Obrigatórios*",
        'all_channels_joined': "✅ *Todos os canais joined!*",
        'not_joined_all': "⚠️ *Canais Faltantes*",
        'main_menu': "🏠 *Menu Principal*",
        'your_balance': "💰 *Seu Saldo:*",
        'min_withdraw': f"📉 Saque mínimo: ${MIN_WITHDRAW}",
        'min_deposit': f"📈 Depósito mínimo: ${MIN_DEPOSIT_USD}",
        'contact_support': f"📞 Suporte: {SUPPORT_USERNAME}",
        'error': "❌ Erro",
        'success': "✅ Sucesso",
        'loading': "⏳ Carregando...",
        'welcome_back': "👋 Bem-vindo de volta!",
        'available_tasks': "🎯 *Tarefas Disponíveis*",
        'no_tasks': "📭 Nenhuma tarefa disponível",
        'task_reward': "💰 Recompensa",
        'task_participants': "👥 Participantes",
        'join_task': "🎯 Entrar na Tarefa"
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
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                ('Telegram Kanalına Katıl', '@EarnTether2026 kanalına katılın', 0.05, 100),
                ('Botu Beğen', 'Botu beğenin ve yorum yapın', 0.03, 50),
                ('Gönderi Paylaş', 'Belirtilen gönderiyi paylaşın', 0.08, 30),
            ]
            
            for task in sample_tasks:
                self.cursor.execute('''
                    INSERT INTO tasks (title, description, reward, max_participants)
                    VALUES (?, ?, ?, ?)
                ''', task)
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            return dict(row)
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
                self.cursor.execute('''
                    INSERT INTO referrals (referrer_id, referred_id, earned_amount)
                    VALUES (?, ?, ?)
                ''', (referred_by, user_id, REF_WELCOME_BONUS))
                
                self.cursor.execute('''
                    UPDATE users SET balance = balance + ? 
                    WHERE user_id = ?
                ''', (REF_WELCOME_BONUS, referred_by))
        
        self.connection.commit()
        return self.get_user(user_id)
    
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
        
        # İstatistikleri kaydet
        self.cursor.execute('''
            INSERT INTO stats (total_users, active_today, total_earned, total_tasks, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (total_users, active_today, total_earned, total_tasks))
        
        self.connection.commit()
        return {
            'total_users': total_users,
            'active_today': active_today,
            'total_earned': total_earned,
            'total_tasks': total_tasks
        }
    
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

👥 *Toplam Kullanıcı:* `{stats['total_users']}`
📈 *Aktif Kullanıcı (24s):* `{stats['active_today']}`
💰 *Toplam Kazanç:* `${stats['total_earned']:.2f}`
🎯 *Tamamlanan Görev:* `{stats['total_tasks']}`

📊 *Son 24 Saat:*
• Yeni kullanıcılar eklendi
• Görev tamamlamaları arttı
• Toplam kazanç yükseldi

🤖 @{(TOKEN.split(':')[0])}
📢 @EarnTether2026
        """
        
        return message

def edit_message(chat_id, message_id, text, parse_mode='Markdown'):
    """Mesajı düzenle"""
    url = BASE_URL + "editMessageText"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': parse_mode
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"❌ Mesaj düzenleme hatası: {e}")
        return None

# Bot Sınıfı
class TaskizBot:
    def __init__(self):
        self.db = Database()
        self.stats_notifier = StatsNotifier(self.db)
        self.stats_notifier.start()
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
        
        # Referans kontrolü
        referred_by = None
        if 'entities' in message:
            for entity in message['entities']:
                if entity['type'] == 'bot_command' and text.startswith('/start'):
                    parts = text.split()
                    if len(parts) > 1:
                        referral_code = parts[1]
                        # Referans kodundan kullanıcıyı bul
                        self.db.cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (referral_code,))
                        row = self.db.cursor.fetchone()
                        if row:
                            referred_by = row[0]
        
        user = self.db.get_user(user_id)
        
        if not user:
            self.start_registration(message, referred_by)
            return
        
        self.db.update_last_active(user_id)
        self.process_command(user_id, text, user)
    
    def start_registration(self, message, referred_by=None):
        user_id = message['from']['id']
        username = message['from'].get('username', '')
        first_name = message['from'].get('first_name', '')
        last_name = message['from'].get('last_name', '')
        
        user = self.db.create_user(user_id, username, first_name, last_name, 'tr', referred_by)
        self.show_language_selection(user_id)
    
    def show_language_selection(self, user_id):
        text = "🌍 *Dil Seçimi / Language Selection*"
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '🇹🇷 Türkçe', 'callback_data': 'lang_tr'},
                    {'text': '🇺🇸 English', 'callback_data': 'lang_en'},
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
                self.check_user_channels(user_id)
                answer_callback_query(callback_id)
                
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
                
            elif data.startswith('join_task_'):
                task_id = int(data.split('_')[2])
                self.handle_join_task(user_id, task_id, callback_id)
                
            elif data == 'refresh_tasks':
                self.show_tasks(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'refresh_channels':
                self.check_user_channels(user_id)
                answer_callback_query(callback_id)
                
            elif data == 'copy_ref':
                user = self.db.get_user(user_id)
                if user:
                    answer_callback_query(callback_id, 
                        f"📋 Referans kodunuz: {user['referral_code']}\n\nKopyalamak için dokunun!", 
                        show_alert=True)
        
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
        
        text = f"{texts['select_type']}"
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': f"{texts['earner']}", 'callback_data': 'user_type_earner'},
                    {'text': f"{texts['advertiser']}", 'callback_data': 'user_type_advertiser'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_user_type_selection(self, user_id, user_type, callback_id):
        self.db.cursor.execute('UPDATE users SET user_type = ? WHERE user_id = ?', (user_type, user_id))
        self.db.connection.commit()
        answer_callback_query(callback_id, "✅ Kullanıcı türü seçildi!")
        
        user = self.db.get_user(user_id)
        self.show_channels_detailed(user_id)
    
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
            text = f"{texts['all_channels_joined']}\n\n✨ Tüm kanallara katıldınız! Görev yapmaya başlayabilirsiniz."
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': "🎯 Görevlere Başla", 'callback_data': 'show_tasks'}],
                    [{'text': "🏠 Ana Menü", 'callback_data': 'show_main_menu'}]
                ]
            }
            
            send_message(user_id, text, reply_markup=keyboard)
        else:
            text = f"{texts['not_joined_all']}\n\nHenüz katılmadığınız kanallar:"
            
            for channel in not_joined:
                text += f"\n❌ {channel['emoji']} {channel['name']}"
            
            buttons = []
            for channel in not_joined:
                buttons.append([
                    {'text': f"➕ {channel['emoji']} {channel['name']}'na katıl", 'url': channel['link']}
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
        
        text = f"{texts['mandatory_channels']}\n\nBotu kullanmak için tüm kanallara katılmanız gerekiyor:"
        
        for channel in MANDATORY_CHANNELS:
            text += f"\n{channel['emoji']} {channel['name']}"
            text += f"\n   👉 @{channel['username']}\n"
        
        buttons = []
        for channel in MANDATORY_CHANNELS:
            buttons.append([
                {'text': f"{channel['emoji']} {channel['name']}'na katıl", 'url': channel['link']}
            ])
        
        buttons.append([
            {'text': "🔍 Kontrol Et", 'callback_data': 'check_channels'}
        ])
        
        keyboard = {'inline_keyboard': buttons}
        send_message(user_id, text, reply_markup=keyboard)
    
    def process_command(self, user_id, text, user):
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Komutları işle
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
                self.show_deposit(user_id)
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
            elif text == texts['deposit']:
                self.show_deposit(user_id)
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
        
        text = f"""
{texts['main_menu']}

💰 *Bakiye:* `${balance:.2f}`
🎯 *Görev:* `{tasks_completed}`

{texts['contact_support']}
        """
        
        # Reply keyboard oluştur
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
    
    def check_all_channels(self, user_id):
        for channel in MANDATORY_CHANNELS:
            if not get_chat_member(f"@{channel['username']}", user_id):
                return False
        return True
    
    def show_tasks(self, user_id):
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
            ORDER BY created_at DESC
        ''')
        tasks = self.db.cursor.fetchall()
        
        if not tasks:
            text = f"{texts['available_tasks']}\n\n{texts['no_tasks']}"
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': "🔄 Yenile", 'callback_data': 'refresh_tasks'}],
                    [{'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}]
                ]
            }
        else:
            text = f"{texts['available_tasks']}\n\n"
            buttons = []
            
            for task in tasks:
                task_dict = dict(task)
                text += f"\n🔸 *{task_dict['title']}*"
                text += f"\n📝 {task_dict['description']}"
                text += f"\n💰 {texts['task_reward']}: `${task_dict['reward']:.2f}`"
                text += f"\n👥 {task_dict['current_participants']}/{task_dict['max_participants']} {texts['task_participants']}\n"
                
                buttons.append([
                    {'text': f"🎯 Katıl (${task_dict['reward']:.2f})", 
                     'callback_data': f'join_task_{task_dict["id"]}'}
                ])
            
            buttons.append([
                {'text': "🔄 Yenile", 'callback_data': 'refresh_tasks'},
                {'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}
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
            INSERT INTO task_participations (task_id, user_id, status)
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
        
        answer_callback_query(callback_id, 
            f"✅ Göreve katıldınız!\n💰 Kazanç: ${reward:.2f}", 
            show_alert=True)
        
        # Görevleri yenile
        time.sleep(1)
        self.show_tasks(user_id)
    
    def show_balance(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user['language']
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
{texts['your_balance']}

💰 *Mevcut Bakiye:* `${user['balance']:.2f}`
🎯 *Tamamlanan Görev:* `{user['tasks_completed']}`
📈 *Toplam Kazanç:* `${user['total_earned']:.2f}`

{texts['min_withdraw']}
{texts['min_deposit']}

{texts['contact_support']}
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
        
        text = f"""
🏧 *Para Çekme*

Mevcut bakiye: `${user['balance']:.2f}`
Minimum çekim: `${MIN_WITHDRAW}`

Para çekmek için destekle iletişime geçin:
{SUPPORT_USERNAME}

{texts['contact_support']}
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
💳 *Bakiye Yükleme*

Minimum yükleme: `${MIN_DEPOSIT_USD}`

TRX adresiniz hazırsa gönderebilirsiniz:
`{TRX_ADDRESS}`

⚠️ Sadece TRX (Tron) gönderin!
⚠️ Farklı coin gönderirseniz kaybolur!

{texts['contact_support']}
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
        
        text = f"""
👤 *Profil*

🆔 ID: `{user_id}`
👤 Ad: `{user['first_name']} {user['last_name'] or ''}`
📛 Kullanıcı adı: `@{user['username'] or 'Yok'}`
🌐 Dil: `{lang_info['name']} {lang_info['flag']}`
💰 Bakiye: `${user['balance']:.2f}`
🎯 Görev: `{user['tasks_completed']}`
📅 Kayıt: `{user['created_at'][:10] if user['created_at'] else '-'}`

{texts['contact_support']}
        """
        
        keyboard = {
            'inline_keyboard': [
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
        
        # Referans sayısı
        self.db.cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
        referral_count = self.db.cursor.fetchone()[0]
        
        # Referans kazancı
        self.db.cursor.execute('SELECT SUM(earned_amount) FROM referrals WHERE referrer_id = ?', (user_id,))
        referral_earned = self.db.cursor.fetchone()[0] or 0
        
        text = f"""
👥 *Referans Programı*

🔗 *Referans Linkiniz:*
`{referral_link}`

📋 *Referans Kodunuz:*
`{referral_code}`

📊 *İstatistikler:*
👥 Toplam Referans: `{referral_count}`
💰 Referans Kazancı: `${referral_earned:.2f}`

💡 *Nasıl Çalışır?*
1. Linkinizi paylaşın
2. Arkadaşlarınız botu kullanmaya başlasın
3. Onlar görev yaptıkça siz kazanın!

{texts['contact_support']}
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
❓ *Yardım*

🤖 *TaskizBot Nedir?*
Görev tamamlayarak para kazanabileceğiniz bir platform.

🎯 *Nasıl Para Kazanırım?*
1. Zorunlu kanallara katılın
2. Görevleri tamamlayın
3. Kazandığınız parayı çekin

💰 *Ödemeler:*
• Minimum çekim: `${MIN_WITHDRAW}`
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
                [{'text': "📢 Kanalları Kontrol Et", 'callback_data': 'show_channels'}],
                [{'text': "🔙 Ana Menü", 'callback_data': 'show_main_menu'}]
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
