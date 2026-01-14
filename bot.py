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
import uuid
import random

# Telegram Ayarları
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = os.environ.get("ADMIN_ID", "7904032877").split(",")  # Birden fazla admin
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
        'name': 'İstatistik Kanalı',
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
}

# Sistem Ayarları
MIN_WITHDRAW = 0.30
MIN_REFERRALS_FOR_WITHDRAW = 10
REF_WELCOME_BONUS = 0.005
REF_TASK_COMMISSION = 0.25

# Flask App
app = Flask(__name__)

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

def delete_message(chat_id, message_id):
    url = BASE_URL + "deleteMessage"
    payload = {'chat_id': chat_id, 'message_id': message_id}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

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

# Database Sınıfı
class Database:
    def __init__(self, db_path='taskizbot_real.db'):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.setup_database()
        print("✅ Veritabanı başlatıldı")
    
    def setup_database(self):
        # Kullanıcılar
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
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        # Bakiye İşlemleri
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS balance_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                transaction_type TEXT,
                description TEXT,
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Görevler
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
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Görev Katılımları
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_participations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                proof_url TEXT,
                reviewed_by INTEGER,
                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_id, user_id)
            )
        ''')
        
        # Çekim Talepleri
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                trx_address TEXT,
                status TEXT DEFAULT 'pending',
                tx_hash TEXT,
                admin_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        ''')
        
        # Referanslar
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
        
        # İstatistikler
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                total_users INTEGER DEFAULT 0,
                active_users INTEGER DEFAULT 0,
                new_users INTEGER DEFAULT 0,
                tasks_completed INTEGER DEFAULT 0,
                withdrawals_pending INTEGER DEFAULT 0,
                withdrawals_paid REAL DEFAULT 0,
                total_volume REAL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Admin İşlem Logları
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                target_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Örnek görevler ekle
        self.add_sample_tasks()
        self.connection.commit()
    
    def add_sample_tasks(self):
        count = self.cursor.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        if count == 0:
            sample_tasks = [
                ('Telegram Kanalına Katıl', '@TaskizLive kanalımıza katılın', 0.05, 1000, 'channel_join', 1),
                ('Botu Beğenin', 'Botu favorilere ekleyin', 0.03, 500, 'like', 1),
                ('Gönderi Paylaşımı', 'Belirtilen gönderiyi paylaşın', 0.08, 300, 'share', 1),
            ]
            for task in sample_tasks:
                self.cursor.execute('''
                    INSERT INTO tasks (title, description, reward, max_participants, task_type, created_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', task)
            self.connection.commit()
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            user = dict(row)
            # Aktif referans sayısı
            self.cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND status = ?', 
                              (user_id, 'active'))
            user['total_referrals'] = self.cursor.fetchone()[0]
            return user
        return None
    
    def create_user(self, user_id, username, first_name, last_name, language='tr', referred_by=None):
        # Kullanıcı var mı kontrol et
        existing = self.get_user(user_id)
        if existing:
            return existing
        
        # Referans kodu oluştur
        referral_code = str(uuid.uuid4())[:8].upper()
        
        # Yeni kullanıcı ekle
        self.cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, language, referral_code, referred_by, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        ''', (user_id, username, first_name, last_name, language, referral_code, referred_by))
        
        # Referans bonusu
        if referred_by:
            # Referans kaydı
            self.cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id, earned_amount, status)
                VALUES (?, ?, ?, 'active')
            ''', (referred_by, user_id, REF_WELCOME_BONUS))
            
            # Bakiye güncelle
            self.cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, 
                    total_referrals = total_referrals + 1
                WHERE user_id = ?
            ''', (REF_WELCOME_BONUS, referred_by))
            
            # Bakiye işlemi logu
            self.cursor.execute('''
                INSERT INTO balance_transactions (user_id, amount, transaction_type, description)
                VALUES (?, ?, 'referral_bonus', ?)
            ''', (referred_by, REF_WELCOME_BONUS, f'Yeni üye bonusu: {user_id}'))
        
        self.connection.commit()
        return self.get_user(user_id)
    
    # ADMIN FONKSİYONLARI
    def admin_add_balance(self, user_id, amount, admin_id, reason=""):
        """Admin bakiye ekler"""
        try:
            # Bakiye güncelle
            self.cursor.execute('''
                UPDATE users SET balance = balance + ? WHERE user_id = ?
            ''', (amount, user_id))
            
            # İşlem logu
            self.cursor.execute('''
                INSERT INTO balance_transactions (user_id, amount, transaction_type, admin_id, description)
                VALUES (?, ?, 'admin_add', ?, ?)
            ''', (user_id, amount, admin_id, reason or "Admin tarafından eklendi"))
            
            # Admin log
            self.cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_id, details)
                VALUES (?, 'add_balance', ?, ?)
            ''', (admin_id, user_id, f"Amount: ${amount}, Reason: {reason}"))
            
            self.connection.commit()
            return True
        except Exception as e:
            print(f"Admin bakiye ekleme hatası: {e}")
            return False
    
    def admin_create_task(self, title, description, reward, max_participants, task_type, admin_id):
        """Admin görev oluşturur"""
        try:
            self.cursor.execute('''
                INSERT INTO tasks (title, description, reward, max_participants, task_type, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title, description, reward, max_participants, task_type, admin_id))
            
            task_id = self.cursor.lastrowid
            
            # Admin log
            self.cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_id, details)
                VALUES (?, 'create_task', ?, ?)
            ''', (admin_id, task_id, f"Title: {title}, Reward: ${reward}"))
            
            self.connection.commit()
            return task_id
        except Exception as e:
            print(f"Görev oluşturma hatası: {e}")
            return None
    
    def admin_process_withdrawal(self, withdrawal_id, status, admin_id, tx_hash=None, note=""):
        """Admin çekim işlemini işler"""
        try:
            # Çekim bilgilerini al
            self.cursor.execute('SELECT * FROM withdrawals WHERE id = ?', (withdrawal_id,))
            withdrawal = self.cursor.fetchone()
            if not withdrawal:
                return False
            
            withdrawal = dict(withdrawal)
            
            if status == 'approved':
                # Onaylandı
                self.cursor.execute('''
                    UPDATE withdrawals 
                    SET status = 'completed', 
                        tx_hash = ?,
                        admin_note = ?,
                        processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (tx_hash, note, withdrawal_id))
                
                # İstatistik güncelle
                self.cursor.execute('''
                    INSERT OR REPLACE INTO stats (date, withdrawals_paid)
                    VALUES (DATE('now'), COALESCE((SELECT withdrawals_paid FROM stats WHERE date = DATE('now')), 0) + ?)
                ''', (withdrawal['amount'],))
                
            elif status == 'rejected':
                # Reddedildi - bakiye iade
                self.cursor.execute('''
                    UPDATE withdrawals SET status = 'rejected', admin_note = ? WHERE id = ?
                ''', (note, withdrawal_id))
                
                # Bakiye iade
                self.cursor.execute('''
                    UPDATE users SET balance = balance + ? WHERE user_id = ?
                ''', (withdrawal['amount'], withdrawal['user_id']))
                
                # Bakiye işlemi logu
                self.cursor.execute('''
                    INSERT INTO balance_transactions (user_id, amount, transaction_type, admin_id, description)
                    VALUES (?, ?, 'withdrawal_refund', ?, ?)
                ''', (withdrawal['user_id'], withdrawal['amount'], admin_id, f"Çekim reddi iadesi: #{withdrawal_id}"))
            
            # Admin log
            self.cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_id, details)
                VALUES (?, 'process_withdrawal', ?, ?)
            ''', (admin_id, withdrawal_id, f"Status: {status}, Amount: ${withdrawal['amount']}"))
            
            self.connection.commit()
            return True
        except Exception as e:
            print(f"Çekim işleme hatası: {e}")
            return False
    
    def admin_get_stats(self):
        """Admin istatistikleri"""
        stats = {}
        
        # Genel istatistikler
        self.cursor.execute('SELECT COUNT(*) FROM users')
        stats['total_users'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('SELECT COUNT(*) FROM users WHERE last_active > datetime("now", "-1 day")')
        stats['active_users'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('SELECT COUNT(*) FROM users WHERE created_at > datetime("now", "-1 day")')
        stats['new_users'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('SELECT SUM(balance) FROM users')
        stats['total_balance'] = self.cursor.fetchone()[0] or 0
        
        self.cursor.execute('SELECT COUNT(*) FROM withdrawals WHERE status = "pending"')
        stats['pending_withdrawals'] = self.cursor.fetchone()[0]
        
        self.cursor.execute('SELECT SUM(amount) FROM withdrawals WHERE status = "pending"')
        stats['pending_amount'] = self.cursor.fetchone()[0] or 0
        
        self.cursor.execute('SELECT SUM(amount) FROM withdrawals WHERE status = "completed"')
        stats['total_withdrawn'] = self.cursor.fetchone()[0] or 0
        
        self.cursor.execute('SELECT COUNT(*) FROM tasks WHERE status = "active"')
        stats['active_tasks'] = self.cursor.fetchone()[0]
        
        return stats
    
    def admin_get_recent_withdrawals(self, limit=10):
        """Son çekim talepleri"""
        self.cursor.execute('''
            SELECT w.*, u.username, u.first_name 
            FROM withdrawals w
            LEFT JOIN users u ON w.user_id = u.user_id
            ORDER BY w.created_at DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in self.cursor.fetchall()]
    
    def admin_get_user_by_id_or_username(self, search_term):
        """Kullanıcı ara"""
        try:
            user_id = int(search_term)
            self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        except:
            self.cursor.execute('SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ?', 
                              (f"%{search_term}%", f"%{search_term}%"))
        
        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def admin_get_all_users(self, limit=50, offset=0):
        """Tüm kullanıcılar"""
        self.cursor.execute('''
            SELECT * FROM users 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        return [dict(row) for row in self.cursor.fetchall()]
    
    # GENEL FONKSİYONLARI
    def update_last_active(self, user_id):
        self.cursor.execute('UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
        self.connection.commit()
    
    def get_active_tasks(self, user_id=None):
        """Aktif görevleri getir"""
        if user_id:
            # Kullanıcının katılmadığı görevler
            self.cursor.execute('''
                SELECT t.* FROM tasks t
                WHERE t.status = 'active' 
                AND t.current_participants < t.max_participants
                AND NOT EXISTS (
                    SELECT 1 FROM task_participations tp 
                    WHERE tp.task_id = t.id AND tp.user_id = ?
                )
                ORDER BY t.created_at DESC
            ''', (user_id,))
        else:
            self.cursor.execute('''
                SELECT * FROM tasks 
                WHERE status = 'active' 
                AND current_participants < max_participants
                ORDER BY created_at DESC
            ''')
        return [dict(row) for row in self.cursor.fetchall()]
    
    def complete_task(self, user_id, task_id, proof_url=None):
        """Görevi tamamla"""
        try:
            # Görevi al
            self.cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
            task = self.cursor.fetchone()
            if not task:
                return None
            task = dict(task)
            
            # Zaten katıldı mı?
            self.cursor.execute('SELECT COUNT(*) FROM task_participations WHERE task_id = ? AND user_id = ?', 
                              (task_id, user_id))
            if self.cursor.fetchone()[0] > 0:
                return None
            
            # Katılım kaydı oluştur
            self.cursor.execute('''
                INSERT INTO task_participations (task_id, user_id, status, proof_url)
                VALUES (?, ?, 'pending', ?)
            ''', (task_id, user_id, proof_url))
            
            # Görev katılımcı sayısını artır
            self.cursor.execute('''
                UPDATE tasks SET current_participants = current_participants + 1 
                WHERE id = ?
            ''', (task_id,))
            
            self.connection.commit()
            return task['reward']
        except Exception as e:
            print(f"Görev tamamlama hatası: {e}")
            return None
    
    def approve_task_completion(self, participation_id, admin_id):
        """Admin görev tamamlamayı onaylar"""
        try:
            # Katılım bilgilerini al
            self.cursor.execute('''
                SELECT tp.*, t.reward, t.title 
                FROM task_participations tp
                JOIN tasks t ON tp.task_id = t.id
                WHERE tp.id = ?
            ''', (participation_id,))
            participation = self.cursor.fetchone()
            if not participation:
                return False
            
            participation = dict(participation)
            
            # Onayla
            self.cursor.execute('''
                UPDATE task_participations 
                SET status = 'approved', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (admin_id, participation_id))
            
            # Kullanıcıya ödül ver
            reward = participation['reward']
            self.cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, 
                    tasks_completed = tasks_completed + 1,
                    total_earned = total_earned + ?
                WHERE user_id = ?
            ''', (reward, reward, participation['user_id']))
            
            # Bakiye işlemi logu
            self.cursor.execute('''
                INSERT INTO balance_transactions (user_id, amount, transaction_type, description)
                VALUES (?, ?, 'task_reward', ?)
            ''', (participation['user_id'], reward, f"Görev: {participation['title']}"))
            
            # Referans komisyonu
            user = self.get_user(participation['user_id'])
            if user and user['referred_by']:
                commission = reward * REF_TASK_COMMISSION
                self.cursor.execute('''
                    UPDATE users SET balance = balance + ? WHERE user_id = ?
                ''', (commission, user['referred_by']))
                
                # Referans kazancı güncelle
                self.cursor.execute('''
                    UPDATE referrals SET earned_amount = earned_amount + ? 
                    WHERE referred_id = ?
                ''', (commission, participation['user_id']))
                
                # Bakiye log
                self.cursor.execute('''
                    INSERT INTO balance_transactions (user_id, amount, transaction_type, description)
                    VALUES (?, ?, 'referral_commission', ?)
                ''', (user['referred_by'], commission, f"Referans komisyonu: {participation['user_id']}"))
            
            # Admin log
            self.cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_id, details)
                VALUES (?, 'approve_task', ?, ?)
            ''', (admin_id, participation_id, f"Reward: ${reward}, User: {participation['user_id']}"))
            
            self.connection.commit()
            return True
        except Exception as e:
            print(f"Görev onaylama hatası: {e}")
            return False
    
    def reject_task_completion(self, participation_id, admin_id, reason=""):
        """Admin görev tamamlamayı reddeder"""
        try:
            self.cursor.execute('''
                UPDATE task_participations 
                SET status = 'rejected', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (admin_id, participation_id))
            
            # Admin log
            self.cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_id, details)
                VALUES (?, 'reject_task', ?, ?)
            ''', (admin_id, participation_id, f"Reason: {reason}"))
            
            self.connection.commit()
            return True
        except Exception as e:
            print(f"Görev reddetme hatası: {e}")
            return False
    
    def get_pending_task_completions(self):
        """Onay bekleyen görev tamamlamaları"""
        self.cursor.execute('''
            SELECT tp.*, u.username, u.first_name, t.title, t.reward
            FROM task_participations tp
            JOIN users u ON tp.user_id = u.user_id
            JOIN tasks t ON tp.task_id = t.id
            WHERE tp.status = 'pending'
            ORDER BY tp.created_at DESC
        ''')
        return [dict(row) for row in self.cursor.fetchall()]

# Bot Sınıfı
class TaskizBot:
    def __init__(self):
        self.db = Database()
        self.user_states = {}  # EKSİK OLAN SATIR - EKLENDİ
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
        
        # Admin paneli kontrolü
        if str(user_id) in ADMIN_IDS and text == "/admin":
            self.show_admin_panel(user_id)
            return
        
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
            # Yeni kullanıcı
            username = message['from'].get('username', '')
            first_name = message['from'].get('first_name', '')
            last_name = message['from'].get('last_name', '')
            
            user = self.db.create_user(user_id, username, first_name, last_name, 'tr', referred_by)
            
            # Grup bildirimi
            group_msg = f"""
👤 *YENİ ÜYE*
━━━━━━━━━━━━
🎉 {first_name} {last_name or ''}
🆔 `{user_id}`
📅 {datetime.now().strftime('%H:%M')}
            """
            try:
                send_message(STATS_CHANNEL, group_msg)
            except:
                pass
            
            self.show_language_selection(user_id)
            return
        
        self.db.update_last_active(user_id)
        
        # Admin mesajları
        if str(user_id) in ADMIN_IDS:
            if text.startswith("/addbalance"):
                self.handle_admin_add_balance(user_id, text)
                return
            elif text.startswith("/createtask"):
                self.handle_admin_create_task(user_id, text)
                return
        
        # TRX adresi bekleniyor
        if user_id in self.user_states and self.user_states[user_id]['action'] == 'waiting_trx':
            self.handle_trx_address(user_id, text, user)
            return
        
        # Normal komutlar
        self.process_command(user_id, text, user)
    
    def handle_trx_address(self, user_id, text, user):
        """TRX adresi alındığında"""
        if user_id in self.user_states:
            amount = self.user_states[user_id].get('withdraw_amount', 0)
            
            # Çekim kaydı
            self.db.cursor.execute('''
                INSERT INTO withdrawals (user_id, amount, trx_address, status)
                VALUES (?, ?, ?, 'pending')
            ''', (user_id, amount, text, 'pending'))
            
            # Bakiye düş
            self.db.cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
            self.db.connection.commit()
            
            # GRUP BİLDİRİMİ: ÇEKİM TALEBİ
            group_msg = f"""
🏧 *YENİ ÇEKİM TALEBİ*
━━━━━━━━━━━━
👤 {user['first_name']}
💰 ${amount}
🔗 TRX: `{text[:10]}...`
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
    
    def process_command(self, user_id, text, user):
        """Normal komutları işle"""
        lang = user['language']
        
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
            # Basit buton işlemleri
            if text in ["🎯 Görevler", "Tasks"]:
                self.show_tasks(user_id)
            elif text in ["💰 Bakiye", "Balance"]:
                self.show_balance(user_id)
            elif text in ["🏧 Çek", "Withdraw"]:
                self.show_withdraw(user_id)
            elif text in ["💳 Yükle", "Deposit"]:
                self.show_deposit(user_id)
            elif text in ["👥 Davet", "Referral"]:
                self.show_referral(user_id)
            elif text in ["👤 Profil", "Profile"]:
                self.show_profile(user_id)
            elif text in ["❓ Yardım", "Help"]:
                self.show_help(user_id)
            else:
                self.show_main_menu(user_id, lang)
    
    def show_language_selection(self, user_id):
        """Dil seçimi göster"""
        text = """
🌍 *DİL SEÇİMİ / LANGUAGE SELECTION*

Lütfen kullanmak istediğiniz dili seçiniz. Bu seçim botun tüm mesajlarında kullanılacaktır.

Please select your preferred language. This choice will be used for all bot messages.
        """
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🇹🇷 Türkçe - Türk Dili', 'callback_data': 'lang_tr'}],
                [{'text': '🇺🇸 English - English Language', 'callback_data': 'lang_en'}],
                [{'text': '🇷🇺 Русский - Русский язык', 'callback_data': 'lang_ru'}],
                [{'text': '🇪🇸 Español - Español', 'callback_data': 'lang_es'}],
                [{'text': '🇵🇹 Português - Português', 'callback_data': 'lang_pt'}],
                [{'text': '🏠 Ana Menüye Dön / Back to Main Menu', 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_callback_query(self, callback_query):
        data = callback_query['data']
        user_id = callback_query['from']['id']
        callback_id = callback_query['id']
        
        try:
            # Admin callback'leri
            if str(user_id) in ADMIN_IDS and data.startswith("admin_"):
                self.handle_admin_callback(user_id, data, callback_id, callback_query)
                return
            
            # Normal kullanıcı callback'leri
            if data.startswith('lang_'):
                lang = data.split('_')[1]
                self.db.cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (lang, user_id))
                self.db.connection.commit()
                answer_callback_query(callback_id, "✅ Dil seçildi / Language selected")
                self.show_main_menu(user_id, lang)
            
            elif data == 'main_menu':
                user = self.db.get_user(user_id)
                if user:
                    self.show_main_menu(user_id, user['language'])
            
            elif data == 'show_tasks':
                self.show_tasks(user_id)
            
            elif data == 'show_balance':
                self.show_balance(user_id)
            
            elif data == 'show_withdraw':
                self.show_withdraw(user_id)
            
            elif data == 'show_deposit':
                self.show_deposit(user_id)
            
            elif data == 'show_referral':
                self.show_referral(user_id)
            
            elif data == 'show_profile':
                self.show_profile(user_id)
            
            elif data.startswith('join_task_'):
                task_id = int(data.split('_')[2])
                self.join_task(user_id, task_id, callback_id)
            
            elif data == 'refresh_tasks':
                self.show_tasks(user_id)
                answer_callback_query(callback_id, "🔄 Görevler yenilendi / Tasks refreshed")
            
            elif data == 'start_withdrawal':
                self.start_withdrawal_process(user_id, callback_id)
            
            elif data == 'copy_ref':
                user = self.db.get_user(user_id)
                if user:
                    answer_callback_query(callback_id, f"📋 Referans Kodunuz: {user['referral_code']}\nBu kodu kopyalayıp paylaşabilirsiniz.", True)
            
        except Exception as e:
            print(f"Callback error: {e}")
            answer_callback_query(callback_id, "❌ Bir hata oluştu / An error occurred")
    
    # ANA MENÜ GÖSTERİMİ
    def show_main_menu(self, user_id, lang='tr'):
        """Ana menüyü göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        welcome_texts = {
            'tr': f"""
🌟 *HOŞ GELDİN {user['first_name']}!* 🌟

🚀 **{BOT_NAME}** - Telegram'ın en kazançlı görev botu! 
Kolay görevler tamamlayarak para kazanmaya hemen başla!

📊 *Hızlı Bilgiler:*
├ 💰 Bakiyen: `${user['balance']:.2f}`
├ 🎯 Tamamlanan Görev: `{user['tasks_completed']}`
├ 👥 Referansların: `{user['total_referrals']}`
└ 📈 Toplam Kazanç: `${user['total_earned']:.2f}`

💡 *Nasıl Çalışır?*
1. 🎯 Görevler bölümünden bir görev seç
2. 📋 Görevin talimatlarını uygula
3. ✅ Tamamlandığını onayla
4. 💰 Hemen ödülünü al!

⚡ *Hızlı Başlangıç İçin:*
- Her gün yeni görevler ekleniyor
- Referanslarınla ekstra kazan
- Düzenli bonuslar ve promosyonlar
            """,
            'en': f"""
🌟 *WELCOME {user['first_name']}!* 🌟

🚀 **{BOT_NAME}** - The most profitable task bot on Telegram!
Start earning money right away by completing simple tasks!

📊 *Quick Info:*
├ 💰 Your Balance: `${user['balance']:.2f}`
├ 🎯 Tasks Completed: `{user['tasks_completed']}`
├ 👥 Your Referrals: `{user['total_referrals']}`
└ 📈 Total Earned: `${user['total_earned']:.2f}`

💡 *How It Works?*
1. 🎯 Select a task from Tasks section
2. 📋 Follow the task instructions
3. ✅ Confirm completion
4. 💰 Get your reward instantly!

⚡ *For Quick Start:*
- New tasks added daily
- Earn extra with referrals
- Regular bonuses and promotions
            """,
            'ru': f"""
🌟 *ДОБРО ПОЖАЛОВАТЬ {user['first_name']}!* 🌟

🚀 **{BOT_NAME}** - Самый прибыльный бот задач в Telegram!
Начните зарабатывать деньги прямо сейчас, выполняя простые задачи!

📊 *Быстрая информация:*
├ 💰 Ваш баланс: `${user['balance']:.2f}`
├ 🎯 Выполненные задачи: `{user['tasks_completed']}`
├ 👥 Ваши рефералы: `{user['total_referrals']}`
└ 📈 Всего заработано: `${user['total_earned']:.2f}`

💡 *Как это работает?*
1. 🎯 Выберите задачу из раздела Задачи
2. 📋 Выполните инструкции задачи
3. ✅ Подтвердите выполнение
4. 💰 Получите вознаграждение мгновенно!

⚡ *Для быстрого старта:*
- Новые задачи добавляются ежедневно
- Зарабатывайте дополнительно с рефералами
- Регулярные бонусы и акции
            """
        }
        
        text = welcome_texts.get(lang, welcome_texts['tr'])
        
        keyboard = {
            'keyboard': [
                ["🎯 Görevler", "💰 Bakiye"],
                ["🏧 Çek", "💳 Yükle"],
                ["👥 Davet", "👤 Profil"],
                ["❓ Yardım", "⚙️ Ayarlar"]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False
        } if lang == 'tr' else {
            'keyboard': [
                ["🎯 Tasks", "💰 Balance"],
                ["🏧 Withdraw", "💳 Deposit"],
                ["👥 Referral", "👤 Profile"],
                ["❓ Help", "⚙️ Settings"]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    # GÖREVLER SAYFASI
    def show_tasks(self, user_id):
        """Görevleri göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        tasks = self.db.get_active_tasks(user_id)
        lang = user['language']
        
        if not tasks:
            no_tasks_texts = {
                'tr': """
📭 *GÖREV BULUNAMADI*

Şu anda mevcut görev bulunmuyor. 
Lütfen daha sonra tekrar kontrol edin.

⏰ *Yakında:*
- Yeni görevler ekleniyor
- Özel bonus görevleri
- Limitli süreli promosyonlar

💡 **Öneri:** Referanslarınızı davet ederek ekstra kazanmaya devam edebilirsiniz!
                """,
                'en': """
📭 *NO TASKS AVAILABLE*

There are currently no available tasks.
Please check back later.

⏰ *Coming Soon:*
- New tasks being added
- Special bonus tasks
- Limited time promotions

💡 **Tip:** You can continue earning extra by inviting your referrals!
                """,
                'ru': """
📭 *ЗАДАЧИ НЕ НАЙДЕНЫ*

В настоящее время нет доступных задач.
Пожалуйста, проверьте позже.

⏰ *Скоро:*
- Добавляются новые задачи
- Специальные бонусные задачи
- Ограниченные по времени акции

💡 **Совет:** Вы можете продолжать зарабатывать дополнительно, приглашая своих рефералов!
                """
            }
            
            text = no_tasks_texts.get(lang, no_tasks_texts['tr'])
            keyboard = {
                'inline_keyboard': [
                    [{'text': '🔄 Yenile', 'callback_data': 'refresh_tasks'}],
                    [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
                ]
            }
            send_message(user_id, text, reply_markup=keyboard)
            return
        
        text = {
            'tr': f"""
🎯 *MEVCUT GÖREVLER* ({len(tasks)})

Aşağıdaki görevleri tamamlayarak ödül kazanabilirsiniz. Her görevin kendi talimatları ve ödül miktarı bulunmaktadır.

📋 *Talimatlar:*
1. Katılmak istediğiniz görevi seçin
2. Görevin açıklamasını dikkatlice okuyun
3. Talimatları eksiksiz uygulayın
4. Tamamlandığında onay için bekleyin
            """,
            'en': f"""
🎯 *AVAILABLE TASKS* ({len(tasks)})

You can earn rewards by completing the tasks below. Each task has its own instructions and reward amount.

📋 *Instructions:*
1. Select the task you want to join
2. Read the task description carefully
3. Follow the instructions completely
4. Wait for approval when completed
            """,
            'ru': f"""
🎯 *ДОСТУПНЫЕ ЗАДАЧИ* ({len(tasks)})

Вы можете зарабатывать награды, выполняя задачи ниже. Каждая задача имеет свои инструкции и сумму вознаграждения.

📋 *Инструкции:*
1. Выберите задачу, к которой хотите присоединиться
2. Внимательно прочитайте описание задачи
3. Полностью следуйте инструкциям
4. Дождитесь подтверждения по завершении
            """
        }.get(lang)
        
        keyboard = {'inline_keyboard': []}
        
        for task in tasks[:10]:  # İlk 10 görevi göster
            btn_text = f"{task['title']} - ${task['reward']:.2f} ({task['current_participants']}/{task['max_participants']})"
            keyboard['inline_keyboard'].append([
                {'text': btn_text, 'callback_data': f'join_task_{task["id"]}'}
            ])
        
        keyboard['inline_keyboard'].extend([
            [{'text': '🔄 Yenile / Refresh', 'callback_data': 'refresh_tasks'}],
            [{'text': '🏠 Ana Menü / Main Menu', 'callback_data': 'main_menu'}]
        ])
        
        send_message(user_id, text, reply_markup=keyboard)
    
    # BAKİYE SAYFASI
    def show_balance(self, user_id):
        """Bakiyeyi göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        
        balance_texts = {
            'tr': f"""
💰 *BAKİYE DURUMU*

━━━━━━━━━━━━━━━━
💵 **Mevcut Bakiye:** `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━

📊 *Detaylı Bilgiler:*
├ 🎯 Tamamlanan Görev: `{user['tasks_completed']}`
├ 💰 Toplam Kazanç: `${user['total_earned']:.2f}`
├ 👥 Aktif Referans: `{user['total_referrals']}`
└ 📈 Referans Kazancı: `${(user['total_earned'] * REF_TASK_COMMISSION):.2f}`

🏧 *Çekim Koşulları:*
- Minimum çekim: `${MIN_WITHDRAW}`
- Minimum referans: `{MIN_REFERRALS_FOR_WITHDRAW}` aktif referans
- Çekim süresi: 24-48 saat
- Komisyon: %0 (Komisyonsuz!)

💡 *Bakiye Artırma Yolları:*
1. Görevleri tamamlayarak
2. Referanslarını davet ederek
3. Günlük bonuslardan yararlanarak
4. Özel promosyonlara katılarak

⚡ *Hızlı İşlemler:*
            """,
            'en': f"""
💰 *BALANCE STATUS*

━━━━━━━━━━━━━━━━
💵 **Current Balance:** `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━

📊 *Detailed Information:*
├ 🎯 Tasks Completed: `{user['tasks_completed']}`
├ 💰 Total Earned: `${user['total_earned']:.2f}`
├ 👥 Active Referrals: `{user['total_referrals']}`
└ 📈 Referral Earnings: `${(user['total_earned'] * REF_TASK_COMMISSION):.2f}`

🏧 *Withdrawal Conditions:*
- Minimum withdrawal: `${MIN_WITHDRAW}`
- Minimum referrals: `{MIN_REFERRALS_FOR_WITHDRAW}` active referrals
- Withdrawal time: 24-48 hours
- Commission: 0% (No commission!)

💡 *Ways to Increase Balance:*
1. By completing tasks
2. By inviting your referrals
3. By taking advantage of daily bonuses
4. By participating in special promotions

⚡ *Quick Actions:*
            """,
            'ru': f"""
💰 *СТАТУС БАЛАНСА*

━━━━━━━━━━━━━━━━
💵 **Текущий баланс:** `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━

📊 *Подробная информация:*
├ 🎯 Выполненные задачи: `{user['tasks_completed']}`
├ 💰 Всего заработано: `${user['total_earned']:.2f}`
├ 👥 Активные рефералы: `{user['total_referrals']}`
└ 📈 Заработок с рефералов: `${(user['total_earned'] * REF_TASK_COMMISSION):.2f}`

🏧 *Условия вывода:*
- Минимальный вывод: `${MIN_WITHDRAW}`
- Минимальные рефералы: `{MIN_REFERRALS_FOR_WITHDRAW}` активных рефералов
- Время вывода: 24-48 часов
- Комиссия: 0% (Без комиссии!)

💡 *Способы увеличения баланса:*
1. Выполняя задачи
2. Приглашая своих рефералов
3. Используя ежедневные бонусы
4. Участвуя в специальных акциях

⚡ *Быстрые действия:*
            """
        }
        
        text = balance_texts.get(lang, balance_texts['tr'])
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🏧 Para Çek', 'callback_data': 'show_withdraw'}],
                [{'text': '💳 Bakiye Yükle', 'callback_data': 'show_deposit'}],
                [{'text': '🎯 Görevlere Git', 'callback_data': 'show_tasks'}],
                [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    # PARA ÇEKME SAYFASI
    def show_withdraw(self, user_id):
        """Para çekme sayfasını göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        
        # Minimum şartları kontrol et
        can_withdraw = True
        reasons = []
        
        if user['balance'] < MIN_WITHDRAW:
            can_withdraw = False
            reasons.append(f"Minimum çekim: ${MIN_WITHDRAW}")
        
        if user['total_referrals'] < MIN_REFERRALS_FOR_WITHDRAW:
            can_withdraw = False
            reasons.append(f"Minimum referans: {MIN_REFERRALS_FOR_WITHDRAW}")
        
        if can_withdraw:
            withdraw_texts = {
                'tr': f"""
🏧 *PARA ÇEKME*

━━━━━━━━━━━━━━━━
💰 **Kullanılabilir Bakiye:** `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━

📋 *Çekim Bilgileri:*
├ 💰 Minimum Tutar: `${MIN_WITHDRAW}`
├ 👥 Gerekli Referans: `{MIN_REFERRALS_FOR_WITHDRAW}`
├ ⏰ İşlem Süresi: 24-48 saat
├ 📝 Komisyon: %0
└ 🔗 Desteklenen Ağ: Tron (TRX)

💡 *Talimatlar:*
1. Tron (TRX) cüzdan adresinizi hazırlayın
2. Çekmek istediğiniz tutarı girin
3. Cüzdan adresinizi doğru şekilde yazın
4. Talebinizi onaylayın

⚠️ *Önemli Uyarılar:*
- Sadece TRON (TRX) ağı desteklenmektedir
- Yanlış adres gönderimlerinden sorumlu değiliz
- Her çekim talebi manuel olarak kontrol edilir
                """,
                'en': f"""
🏧 *WITHDRAWAL*

━━━━━━━━━━━━━━━━
💰 **Available Balance:** `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━

📋 *Withdrawal Information:*
├ 💰 Minimum Amount: `${MIN_WITHDRAW}`
├ 👥 Required Referrals: `{MIN_REFERRALS_FOR_WITHDRAW}`
├ ⏰ Processing Time: 24-48 hours
├ 📝 Commission: 0%
└ 🔗 Supported Network: Tron (TRX)

💡 *Instructions:*
1. Prepare your Tron (TRX) wallet address
2. Enter the amount you want to withdraw
3. Write your wallet address correctly
4. Confirm your request

⚠️ *Important Warnings:*
- Only TRON (TRX) network is supported
- We are not responsible for wrong address transfers
- Each withdrawal request is manually checked
                """,
                'ru': f"""
🏧 *ВЫВОД СРЕДСТВ*

━━━━━━━━━━━━━━━━
💰 **Доступный баланс:** `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━

📋 *Информация о выводе:*
├ 💰 Минимальная сумма: `${MIN_WITHDRAW}`
├ 👥 Требуемые рефералы: `{MIN_REFERRALS_FOR_WITHDRAW}`
├ ⏰ Время обработки: 24-48 часов
├ 📝 Комиссия: 0%
└ 🔗 Поддерживаемая сеть: Tron (TRX)

💡 *Инструкции:*
1. Подготовьте адрес вашего кошелька Tron (TRX)
2. Введите сумму, которую хотите вывести
3. Правильно напишите адрес вашего кошелька
4. Подтвердите ваш запрос

⚠️ *Важные предупреждения:*
- Поддерживается только сеть TRON (TRX)
- Мы не несем ответственности за переводы на неправильный адрес
- Каждый запрос на вывод проверяется вручную
                """
            }
            
            text = withdraw_texts.get(lang, withdraw_texts['tr'])
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': f'💰 Çekim Yap (${user["balance"]:.2f})', 'callback_data': 'start_withdrawal'}],
                    [{'text': '💰 Bakiye', 'callback_data': 'show_balance'}],
                    [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
                ]
            }
        else:
            # Çekim yapamıyor
            reasons_text = "\n".join([f"• {reason}" for reason in reasons])
            
            cannot_withdraw_texts = {
                'tr': f"""
⛔ *ÇEKİM YAPAMAZSINIZ*

━━━━━━━━━━━━━━━━
💵 Mevcut Bakiye: `${user['balance']:.2f}`
👥 Referans Sayınız: `{user['total_referrals']}`
━━━━━━━━━━━━━━━━

❌ *Eksik Koşullar:*
{reasons_text}

📈 *Hedefleriniz:*
├ 💰 Minimum Bakiye: `${MIN_WITHDRAW}`
└ 👥 Minimum Referans: `{MIN_REFERRALS_FOR_WITHDRAW}`

💡 *Öneriler:*
1. Daha fazla görev tamamlayarak bakiye artır
2. Arkadaşlarını davet et, her davet sana ${REF_WELCOME_BONUS} kazandırır
3. Günlük bonusları takip et
4. Özel promosyonlardan yararlan
                """,
                'en': f"""
⛔ *CANNOT WITHDRAW*

━━━━━━━━━━━━━━━━
💵 Current Balance: `${user['balance']:.2f}`
👥 Your Referrals: `{user['total_referrals']}`
━━━━━━━━━━━━━━━━

❌ *Missing Conditions:*
{reasons_text}

📈 *Your Targets:*
├ 💰 Minimum Balance: `${MIN_WITHDRAW}`
└ 👥 Minimum Referrals: `{MIN_REFERRALS_FOR_WITHDRAW}`

💡 *Suggestions:*
1. Increase balance by completing more tasks
2. Invite friends, each invite earns you ${REF_WELCOME_BONUS}
3. Follow daily bonuses
4. Take advantage of special promotions
                """,
                'ru': f"""
⛔ *НЕ МОЖЕТЕ ВЫВЕСТИ*

━━━━━━━━━━━━━━━━
💵 Текущий баланс: `${user['balance']:.2f}`
👥 Ваши рефералы: `{user['total_referrals']}`
━━━━━━━━━━━━━━━━

❌ *Отсутствующие условия:*
{reasons_text}

📈 *Ваши цели:*
├ 💰 Минимальный баланс: `${MIN_WITHDRAW}`
└ 👥 Минимальные рефералы: `{MIN_REFERRALS_FOR_WITHDRAW}`

💡 *Предложения:*
1. Увеличьте баланс, выполняя больше задач
2. Приглашайте друзей, каждое приглашение приносит вам ${REF_WELCOME_BONUS}
3. Следите за ежедневными бонусами
4. Воспользуйтесь специальными акциями
                """
            }
            
            text = cannot_withdraw_texts.get(lang, cannot_withdraw_texts['tr'])
            
            keyboard = {
                'inline_keyboard': [
                    [{'text': '🎯 Görevlere Git', 'callback_data': 'show_tasks'}],
                    [{'text': '👥 Referans Sistemine Git', 'callback_data': 'show_referral'}],
                    [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
                ]
            }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    # REFERANS SAYFASI
    def show_referral(self, user_id):
        """Referans sistemini göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        
        # Referans istatistiklerini getir
        self.db.cursor.execute('''
            SELECT COUNT(*) as active_refs, 
                   SUM(earned_amount) as total_earned 
            FROM referrals 
            WHERE referrer_id = ? AND status = 'active'
        ''', (user_id,))
        stats = self.db.cursor.fetchone()
        
        active_refs = stats['active_refs'] if stats else 0
        ref_earned = stats['total_earned'] if stats and stats['total_earned'] else 0
        
        referral_link = f"https://t.me/{BOT_USERNAME}?start={user['referral_code']}"
        
        referral_texts = {
            'tr': f"""
👥 *REFERANS SİSTEMİ*

━━━━━━━━━━━━━━━━
💰 **Referans Kazancınız:** `${ref_earned:.2f}`
👥 **Aktif Referanslarınız:** `{active_refs}`
━━━━━━━━━━━━━━━━

🎯 *Referans Programı Detayları:*

1. **Hoş Geldin Bonusu:**
   • Her yeni referans: `${REF_WELCOME_BONUS}`
   • Anında ödeme

2. **Görev Komisyonu:**
   • Referanslarının her görev kazancından: `%{REF_TASK_COMMISSION * 100}`
   • Otomatik ödeme

3. **Minimum Çekim:**
   • Çekim için en az `{MIN_REFERRALS_FOR_WITHDRAW}` aktif referans gereklidir

📊 *Referans İstatistikleriniz:*
├ 👥 Toplam Referans: `{user['total_referrals']}`
├ 💰 Referans Kazancı: `${ref_earned:.2f}`
└ 🎯 Hedef: `{MIN_REFERRALS_FOR_WITHDRAW}` referans

🔗 *Referans Linkiniz:*
`{referral_link}`

📋 *Referans Kodunuz:*
`{user['referral_code']}`

💡 *Nasıl Daha Fazla Kazanırsınız?*
1. Linkinizi sosyal medyada paylaşın
2. Arkadaşlarınıza özel mesaj atın
3. Gruplarda paylaşım yapın
4. Kanalınız varsa açıklamaya ekleyin

⚡ *Hızlı Paylaşım Butonları:*
            """,
            'en': f"""
👥 *REFERRAL SYSTEM*

━━━━━━━━━━━━━━━━
💰 **Your Referral Earnings:** `${ref_earned:.2f}`
👥 **Your Active Referrals:** `{active_refs}`
━━━━━━━━━━━━━━━━

🎯 *Referral Program Details:*

1. **Welcome Bonus:**
   • Each new referral: `${REF_WELCOME_BONUS}`
   • Instant payment

2. **Task Commission:**
   • From each task earning of your referrals: `%{REF_TASK_COMMISSION * 100}`
   • Automatic payment

3. **Minimum Withdrawal:**
   • At least `{MIN_REFERRALS_FOR_WITHDRAW}` active referrals required for withdrawal

📊 *Your Referral Statistics:*
├ 👥 Total Referrals: `{user['total_referrals']}`
├ 💰 Referral Earnings: `${ref_earned:.2f}`
└ 🎯 Target: `{MIN_REFERRALS_FOR_WITHDRAW}` referrals

🔗 *Your Referral Link:*
`{referral_link}`

📋 *Your Referral Code:*
`{user['referral_code']}`

💡 *How to Earn More?*
1. Share your link on social media
2. Send private messages to friends
3. Make shares in groups
4. Add to your channel description if you have one

⚡ *Quick Share Buttons:*
            """,
            'ru': f"""
👥 *РЕФЕРАЛЬНАЯ СИСТЕМА*

━━━━━━━━━━━━━━━━
💰 **Ваш реферальный заработок:** `${ref_earned:.2f}`
👥 **Ваши активные рефералы:** `{active_refs}`
━━━━━━━━━━━━━━━━

🎯 *Детали реферальной программы:*

1. **Бонус за регистрацию:**
   • Каждый новый реферал: `${REF_WELCOME_BONUS}`
   • Мгновенная оплата

2. **Комиссия за задачи:**
   • От каждого заработка с задач ваших рефералов: `%{REF_TASK_COMMISSION * 100}`
   • Автоматическая оплата

3. **Минимальный вывод:**
   • Для вывода требуется не менее `{MIN_REFERRALS_FOR_WITHDRAW}` активных рефералов

📊 *Ваша реферальная статистика:*
├ 👥 Всего рефералов: `{user['total_referrals']}`
├ 💰 Реферальный заработок: `${ref_earned:.2f}`
└ 🎯 Цель: `{MIN_REFERRALS_FOR_WITHDRAW}` рефералов

🔗 *Ваша реферальная ссылка:*
`{referral_link}`

📋 *Ваш реферальный код:*
`{user['referral_code']}`

💡 *Как заработать больше?*
1. Поделитесь своей ссылкой в социальных сетях
2. Отправьте личные сообщения друзьям
3. Делайте публикации в группах
4. Добавьте в описание вашего канала, если он есть

⚡ *Кнопки быстрого обмена:*
            """
        }
        
        text = referral_texts.get(lang, referral_texts['tr'])
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '📋 Referans Kodunu Kopyala', 'callback_data': 'copy_ref'}],
                [{'text': '💰 Bakiye', 'callback_data': 'show_balance'}],
                [{'text': '🎯 Görevler', 'callback_data': 'show_tasks'}],
                [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    # PROFİL SAYFASI
    def show_profile(self, user_id):
        """Kullanıcı profilini göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        
        # Referans kazancını hesapla
        self.db.cursor.execute('SELECT SUM(earned_amount) FROM referrals WHERE referrer_id = ?', (user_id,))
        ref_earned = self.db.cursor.fetchone()[0] or 0
        
        # Son aktiviteyi formatla
        last_active = datetime.strptime(user['last_active'], '%Y-%m-%d %H:%M:%S') if isinstance(user['last_active'], str) else user['last_active']
        days_active = (datetime.now() - last_active).days
        
        profile_texts = {
            'tr': f"""
👤 *PROFİL BİLGİLERİ*

━━━━━━━━━━━━━━━━
🆔 **Kullanıcı ID:** `{user['user_id']}`
👤 **Ad Soyad:** {user['first_name']} {user['last_name'] or ''}
🌍 **Dil:** {SUPPORTED_LANGUAGES[lang]['flag']} {SUPPORTED_LANGUAGES[lang]['name']}
━━━━━━━━━━━━━━━━

📊 *İstatistikleriniz:*
├ 💰 Mevcut Bakiye: `${user['balance']:.2f}`
├ 📈 Toplam Kazanç: `${user['total_earned']:.2f}`
├ 🎯 Tamamlanan Görev: `{user['tasks_completed']}`
├ 👥 Aktif Referans: `{user['total_referrals']}`
├ 💸 Referans Kazancı: `${ref_earned:.2f}`
└ 📅 Son Aktivite: `{days_active}` gün önce

🎯 *Hedefleriniz:*
├ 💰 Minimum Çekim: `${MIN_WITHDRAW}`
├ 👥 Minimum Referans: `{MIN_REFERRALS_FOR_WITHDRAW}`
└ 🏆 Kalan Referans: `{max(0, MIN_REFERRALS_FOR_WITHDRAW - user['total_referrals'])}`

⭐ *Başarı Durumu:*
{self.get_achievement_status(user, lang)}

💡 *Profilinizi Geliştirin:*
1. Daha fazla görev tamamlayın
2. Referanslarınızı artırın
3. Günlük bonusları takip edin
4. Özel etkinliklere katılın
            """,
            'en': f"""
👤 *PROFILE INFORMATION*

━━━━━━━━━━━━━━━━
🆔 **User ID:** `{user['user_id']}`
👤 **Full Name:** {user['first_name']} {user['last_name'] or ''}
🌍 **Language:** {SUPPORTED_LANGUAGES[lang]['flag']} {SUPPORTED_LANGUAGES[lang]['name']}
━━━━━━━━━━━━━━━━

📊 *Your Statistics:*
├ 💰 Current Balance: `${user['balance']:.2f}`
├ 📈 Total Earnings: `${user['total_earned']:.2f}`
├ 🎯 Tasks Completed: `{user['tasks_completed']}`
├ 👥 Active Referrals: `{user['total_referrals']}`
├ 💸 Referral Earnings: `${ref_earned:.2f}`
└ 📅 Last Active: `{days_active}` days ago

🎯 *Your Targets:*
├ 💰 Minimum Withdrawal: `${MIN_WITHDRAW}`
├ 👥 Minimum Referrals: `{MIN_REFERRALS_FOR_WITHDRAW}`
└ 🏆 Remaining Referrals: `{max(0, MIN_REFERRALS_FOR_WITHDRAW - user['total_referrals'])}`

⭐ *Achievement Status:*
{self.get_achievement_status(user, lang)}

💡 *Improve Your Profile:*
1. Complete more tasks
2. Increase your referrals
3. Follow daily bonuses
4. Participate in special events
            """,
            'ru': f"""
👤 *ИНФОРМАЦИЯ О ПРОФИЛЕ*

━━━━━━━━━━━━━━━━
🆔 **ID пользователя:** `{user['user_id']}`
👤 **Полное имя:** {user['first_name']} {user['last_name'] or ''}
🌍 **Язык:** {SUPPORTED_LANGUAGES[lang]['flag']} {SUPPORTED_LANGUAGES[lang]['name']}
━━━━━━━━━━━━━━━━

📊 *Ваша статистика:*
├ 💰 Текущий баланс: `${user['balance']:.2f}`
├ 📈 Всего заработано: `${user['total_earned']:.2f}`
├ 🎯 Выполненные задачи: `{user['tasks_completed']}`
├ 👥 Активные рефералы: `{user['total_referrals']}`
├ 💸 Реферальный заработок: `${ref_earned:.2f}`
└ 📅 Последняя активность: `{days_active}` дней назад

🎯 *Ваши цели:*
├ 💰 Минимальный вывод: `${MIN_WITHDRAW}`
├ 👥 Минимальные рефералы: `{MIN_REFERRALS_FOR_WITHDRAW}`
└ 🏆 Оставшиеся рефералы: `{max(0, MIN_REFERRALS_FOR_WITHDRAW - user['total_referrals'])}`

⭐ *Статус достижений:*
{self.get_achievement_status(user, lang)}

💡 *Улучшите свой профиль:*
1. Выполняйте больше задач
2. Увеличивайте количество рефералов
3. Следите за ежедневными бонусами
4. Участвуйте в специальных мероприятиях
            """
        }
        
        text = profile_texts.get(lang, profile_texts['tr'])
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '💰 Bakiye', 'callback_data': 'show_balance'}],
                [{'text': '👥 Referanslar', 'callback_data': 'show_referral'}],
                [{'text': '🎯 Görevler', 'callback_data': 'show_tasks'}],
                [{'text': '⚙️ Dil Değiştir', 'callback_data': 'change_language'}],
                [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def get_achievement_status(self, user, lang):
        """Başarı durumunu döndür"""
        achievements = []
        
        if user['tasks_completed'] >= 10:
            achievements.append("✅ 10+ Görev Tamamlandı")
        elif user['tasks_completed'] >= 5:
            achievements.append("🟡 5 Görev Tamamlandı")
        else:
            achievements.append("🔴 Görev Başlatılmadı")
        
        if user['total_referrals'] >= MIN_REFERRALS_FOR_WITHDRAW:
            achievements.append(f"✅ {MIN_REFERRALS_FOR_WITHDRAW}+ Referans")
        else:
            achievements.append(f"🔴 {user['total_referrals']}/{MIN_REFERRALS_FOR_WITHDRAW} Referans")
        
        if user['balance'] >= MIN_WITHDRAW:
            achievements.append(f"✅ ${MIN_WITHDRAW}+ Bakiye")
        else:
            achievements.append(f"🔴 ${user['balance']:.2f}/{MIN_WITHDRAW} Bakiye")
        
        if lang == 'tr':
            return "\n".join([f"• {ach}" for ach in achievements])
        elif lang == 'en':
            return "\n".join([f"• {ach}" for ach in achievements])
        else:
            return "\n".join([f"• {ach}" for ach in achievements])
    
    # YARDIM SAYFASI
    def show_help(self, user_id):
        """Yardım sayfasını göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        lang = user['language']
        
        help_texts = {
            'tr': f"""
❓ *YARDIM VE DESTEK*

━━━━━━━━━━━━━━━━
🤖 **Bot:** {BOT_NAME}
👤 **Destek:** {SUPPORT_USERNAME}
🌍 **Resmi Kanal:** @TaskizLive
━━━━━━━━━━━━━━━━

📚 *Sıkça Sorulan Sorular:*

1. **Nasıl para kazanırım?**
   • Görevler bölümünden görev seçin
   • Talimatları uygulayın
   • Tamamlandığında onay için bekleyin
   • Ödülünüz otomatik olarak bakiyenize eklenecek

2. **Para çekme şartları nelerdir?**
   • Minimum bakiye: `${MIN_WITHDRAW}`
   • Minimum referans: `{MIN_REFERRALS_FOR_WITHDRAW}` aktif referans
   • İşlem süresi: 24-48 saat
   • Desteklenen ağ: Tron (TRX)

3. **Referans sisteminden nasıl kazanırım?**
   • Her yeni referans: `${REF_WELCOME_BONUS}` bonus
   • Referanslarınızın her görev kazancından: `%{REF_TASK_COMMISSION * 100}` komisyon
   • Ödemeler otomatik ve anlıktır

4. **Görev onay süresi ne kadar?**
   • Normal görevler: 1-12 saat
   • Özel görevler: 24 saate kadar
   • Her görev manuel olarak kontrol edilir

5. **Bakiye neden artmıyor?**
   • Görev tamamlamaları onay bekliyor olabilir
   • Sistemde teknik bir sorun olabilir
   • Lütfen destek ekibiyle iletişime geçin

🔧 *Teknik Sorunlar:*
• Bot cevap vermiyorsa: /start yazın
• Görevler görünmüyorsa: /tasks yazın
• Bakiye güncellenmiyorsa: /balance yazın

📞 *İletişim:*
• Destek: {SUPPORT_USERNAME}
• Resmi Kanal: @TaskizLive
• Güncellemeler: @TaskizLive

⚠️ *Önemli Uyarılar:*
• Asla şifrenizi veya özel bilgilerinizi paylaşmayın
• Sadece resmi kanallardan gelen mesajlara güvenin
• Şüpheli linklere tıklamayın
            """,
            'en': f"""
❓ *HELP AND SUPPORT*

━━━━━━━━━━━━━━━━
🤖 **Bot:** {BOT_NAME}
👤 **Support:** {SUPPORT_USERNAME}
🌍 **Official Channel:** @TaskizLive
━━━━━━━━━━━━━━━━

📚 *Frequently Asked Questions:*

1. **How do I earn money?**
   • Select tasks from Tasks section
   • Follow the instructions
   • Wait for approval when completed
   • Your reward will be automatically added to your balance

2. **What are the withdrawal conditions?**
   • Minimum balance: `${MIN_WITHDRAW}`
   • Minimum referrals: `{MIN_REFERRALS_FOR_WITHDRAW}` active referrals
   • Processing time: 24-48 hours
   • Supported network: Tron (TRX)

3. **How do I earn from referral system?**
   • Each new referral: `${REF_WELCOME_BONUS}` bonus
   • From each task earning of your referrals: `%{REF_TASK_COMMISSION * 100}` commission
   • Payments are automatic and instant

4. **How long does task approval take?**
   • Normal tasks: 1-12 hours
   • Special tasks: up to 24 hours
   • Each task is manually checked

5. **Why isn't my balance increasing?**
   • Task completions may be pending approval
   • There may be a technical issue in the system
   • Please contact the support team

🔧 *Technical Issues:*
• If bot doesn't respond: type /start
• If tasks aren't showing: type /tasks
• If balance isn't updating: type /balance

📞 *Contact:*
• Support: {SUPPORT_USERNAME}
• Official Channel: @TaskizLive
• Updates: @TaskizLive

⚠️ *Important Warnings:*
• Never share your password or private information
• Trust only messages from official channels
• Don't click suspicious links
            """,
            'ru': f"""
❓ *ПОМОЩЬ И ПОДДЕРЖКА*

━━━━━━━━━━━━━━━━
🤖 **Бот:** {BOT_NAME}
👤 **Поддержка:** {SUPPORT_USERNAME}
🌍 **Официальный канал:** @TaskizLive
━━━━━━━━━━━━━━━━

📚 *Часто задаваемые вопросы:*

1. **Как я могу зарабатывать деньги?**
   • Выбирайте задачи из раздела Задачи
   • Следуйте инструкциям
   • Дождитесь подтверждения по завершении
   • Ваша награда будет автоматически добавлена на ваш баланс

2. **Каковы условия вывода?**
   • Минимальный баланс: `${MIN_WITHDRAW}`
   • Минимальные рефералы: `{MIN_REFERRALS_FOR_WITHDRAW}` активных рефералов
   • Время обработки: 24-48 часов
   • Поддерживаемая сеть: Tron (TRX)

3. **Как зарабатывать с реферальной системы?**
   • Каждый новый реферал: `${REF_WELCOME_BONUS}` бонус
   • От каждого заработка с задач ваших рефералов: `%{REF_TASK_COMMISSION * 100}` комиссия
   • Выплаты автоматические и мгновенные

4. **Сколько времени занимает подтверждение задачи?**
   • Обычные задачи: 1-12 часов
   • Специальные задачи: до 24 часов
   • Каждая задача проверяется вручную

5. **Почему не увеличивается мой баланс?**
   • Завершения задач могут ожидать подтверждения
   • Возможна техническая проблема в системе
   • Пожалуйста, свяжитесь со службой поддержки

🔧 *Технические проблемы:*
• Если бот не отвечает: напишите /start
• Если задачи не отображаются: напишите /tasks
• Если баланс не обновляется: напишите /balance

📞 *Контакты:*
• Поддержка: {SUPPORT_USERNAME}
• Официальный канал: @TaskizLive
• Обновления: @TaskizLive

⚠️ *Важные предупреждения:*
• Никогда не делитесь паролем или личной информацией
• Доверяйте только сообщениям из официальных каналов
• Не нажимайте на подозрительные ссылки
            """
        }
        
        text = help_texts.get(lang, help_texts['tr'])
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '📞 Destekle İletişim', 'url': f'tg://resolve?domain={SUPPORT_USERNAME[1:]}'}],
                [{'text': '📢 Resmi Kanal', 'url': 'https://t.me/TaskizLive'}],
                [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    # ADMIN FONKSİYONLARI DEVAMI...
    def handle_admin_add_balance(self, admin_id, text):
        """Admin bakiye ekleme"""
        try:
            parts = text.split()
            if len(parts) < 3:
                send_message(admin_id, "❌ Format: /addbalance USER_ID AMOUNT [REASON]")
                return
            
            user_id = int(parts[1])
            amount = float(parts[2])
            reason = " ".join(parts[3:]) if len(parts) > 3 else ""
            
            if amount <= 0:
                send_message(admin_id, "❌ Miktar pozitif olmalıdır")
                return
            
            user = self.db.get_user(user_id)
            if not user:
                send_message(admin_id, "❌ Kullanıcı bulunamadı")
                return
            
            if self.db.admin_add_balance(user_id, amount, admin_id, reason):
                send_message(admin_id, f"✅ Bakiye eklendi!\n👤 Kullanıcı: {user_id}\n💰 Miktar: ${amount}\n📝 Nedeni: {reason}")
                
                # Kullanıcıya bildirim
                send_message(user_id, f"🎉 Bakiyenize ${amount} eklendi!\n📝 Nedeni: {reason or 'Admin bonusu'}")
            else:
                send_message(admin_id, "❌ Bakiye eklenemedi")
        except Exception as e:
            send_message(admin_id, f"❌ Hata: {e}")
    
    def handle_admin_create_task(self, admin_id, text):
        """Admin görev oluşturma"""
        try:
            parts = text.split(maxsplit=5)
            if len(parts) < 5:
                send_message(admin_id, "❌ Format: /createtask TITLE REWARD MAX_PARTICIPANTS TYPE DESCRIPTION")
                return
            
            title = parts[1]
            reward = float(parts[2])
            max_parts = int(parts[3])
            task_type = parts[4]
            description = parts[5] if len(parts) > 5 else ""
            
            task_id = self.db.admin_create_task(title, description, reward, max_parts, task_type, admin_id)
            
            if task_id:
                send_message(admin_id, f"""
✅ Görev oluşturuldu!

🎯 **Başlık:** {title}
💰 **Ödül:** ${reward}
👥 **Katılımcı:** {max_parts}
📝 **Tip:** {task_type}
🆔 **ID:** {task_id}
                """)
            else:
                send_message(admin_id, "❌ Görev oluşturulamadı")
        except Exception as e:
            send_message(admin_id, f"❌ Hata: {e}")
    
    def start_withdrawal_process(self, user_id, callback_id):
        """Para çekme sürecini başlat"""
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Kullanıcı bulunamadı")
            return
        
        if user['balance'] < MIN_WITHDRAW:
            answer_callback_query(callback_id, f"❌ Minimum çekim: ${MIN_WITHDRAW}", True)
            return
        
        if user['total_referrals'] < MIN_REFERRALS_FOR_WITHDRAW:
            answer_callback_query(callback_id, f"❌ Minimum referans: {MIN_REFERRALS_FOR_WITHDRAW}", True)
            return
        
        # Kullanıcı durumunu güncelle
        self.user_states[user_id] = {
            'action': 'waiting_trx',
            'withdraw_amount': user['balance']
        }
        
        answer_callback_query(callback_id, "💰 Çekim başlatıldı")
        
        # TRX adresi iste
        send_message(user_id, f"""
🏧 *ÇEKİM TALEBİ*

━━━━━━━━━━━━━━━━
💰 **Çekilecek Tutar:** `${user['balance']:.2f}`
━━━━━━━━━━━━━━━━

🔗 Lütfen TRON (TRX) cüzdan adresinizi gönderin:

⚠️ **ÖNEMLİ:**
- Sadece TRON ağı desteklenmektedir
- Yanlış adres gönderimlerinden sorumlu değiliz
- Adresi doğru kopyaladığınızdan emin olun

✍️ **Format:** `T...` şeklinde TRX adresiniz
        """)
    
    def join_task(self, user_id, task_id, callback_id):
        """Göreve katıl"""
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Kullanıcı bulunamadı")
            return
        
        # Kanallara üyelik kontrolü
        for channel in MANDATORY_CHANNELS:
            if not get_chat_member(f"@{channel['username']}", user_id):
                answer_callback_query(callback_id, f"❌ Önce @{channel['username']} kanalına katılmalısın", True)
                return
        
        # Görevi tamamla
        reward = self.db.complete_task(user_id, task_id)
        
        if reward:
            answer_callback_query(callback_id, f"✅ Göreve katıldın!\n💰 Ödül: ${reward}\n⏳ Onay bekleniyor...")
            
            # Adminlere bildirim
            for admin in ADMIN_IDS:
                try:
                    send_message(admin, f"""
🎯 *YENİ GÖREV KATILIMI*

👤 Kullanıcı: {user['first_name']} (@{user['username'] or 'N/A'})
🆔 ID: `{user_id}`
💰 Ödül: `${reward}`
⏰ Zaman: {datetime.now().strftime('%H:%M:%S')}
                    """)
                except:
                    pass
        else:
            answer_callback_query(callback_id, "❌ Göreve zaten katıldın veya görev bulunamadı", True)

# Flask Routes
@app.route('/')
def home():
    return "🤖 TaskizBot Aktif!"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        bot.handle_update(update)
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    if not WEBHOOK_URL:
        return "WEBHOOK_URL ayarlanmamış", 400
    
    url = f"{BASE_URL}setWebhook?url={WEBHOOK_URL}/webhook"
    response = requests.get(url)
    return response.json()

# Bot Başlatma
bot = TaskizBot()

if __name__ == '__main__':
    # Webhook ayarla
    if WEBHOOK_URL:
        try:
            url = f"{BASE_URL}setWebhook?url={WEBHOOK_URL}/webhook"
            response = requests.get(url)
            print(f"Webhook ayarlandı: {response.json()}")
        except Exception as e:
            print(f"Webhook ayarlama hatası: {e}")
    
    # Flask'ı başlat
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
