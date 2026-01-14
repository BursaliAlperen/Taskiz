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

# Database Sınıfı - Tam Gerçek
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
                ('Telegram Kanalına Katıl', '@TaskizLive kanalımıza katılın ve ekran görüntüsü gönderin', 0.05, 1000, 'channel_join', 1),
                ('Botumuzu Beğenin', 'Botu favorilere ekleyin ve yıldız verin', 0.03, 500, 'like', 1),
                ('Gönderi Paylaşımı', 'Belirtilen gönderiyi paylaşın ve link gönderin', 0.08, 300, 'share', 1),
                ('YouTube Video İzleme', 'Belirtilen videoyu 1 dakika izleyin', 0.02, 2000, 'watch', 1),
                ('Referans Kazanç', '3 arkadaşınızı davet edin', 0.10, 1000, 'referral', 1),
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
    
    # GENEL FONKSİYONLAR
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
            
            # Admin onayı bekleniyor - GERÇEK SİSTEM
            # Ödül hemen verilmez, admin onayı gerekir
            
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
👥 Toplam: {self.db.cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]}
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
    
    def handle_callback_query(self, callback_query):
        data = callback_query['data']
        user_id = callback_query['from']['id']
        callback_id = callback_query['id']
        
        try:
            # Admin callback'leri
            if str(user_id) in ADMIN_IDS and data.startswith("admin_"):
                self.handle_admin_callback(user_id, data, callback_id)
                return
            
            # Normal kullanıcı callback'leri
            if data.startswith('lang_'):
                lang = data.split('_')[1]
                self.db.cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (lang, user_id))
                self.db.connection.commit()
                answer_callback_query(callback_id, "✅ Dil seçildi")
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
                answer_callback_query(callback_id, "🔄 Yenilendi")
            
            elif data == 'start_withdrawal':
                self.start_withdrawal_process(user_id, callback_id)
            
            elif data == 'copy_ref':
                user = self.db.get_user(user_id)
                if user:
                    answer_callback_query(callback_id, f"📋 Kod: {user['referral_code']}", True)
            
        except Exception as e:
            print(f"Callback error: {e}")
            answer_callback_query(callback_id, "❌ Hata")
    
    # ADMIN PANELİ FONKSİYONLARI
    def show_admin_panel(self, admin_id):
        """Admin panelini göster"""
        stats = self.db.admin_get_stats()
        
        text = f"""
⚡ *ADMIN PANEL - {BOT_NAME}*

📊 *İSTATİSTİKLER*
👥 Toplam Kullanıcı: `{stats['total_users']}`
📈 Aktif (24s): `{stats['active_users']}`
🆕 Yeni (24s): `{stats['new_users']}`
💰 Toplam Bakiye: `${stats['total_balance']:.2f}`
🏧 Bekleyen Çekim: `{stats['pending_withdrawals']}`
💵 Bekleyen Tutar: `${stats['pending_amount']:.2f}`
🎯 Aktif Görev: `{stats['active_tasks']}`
💸 Toplam Çekilen: `${stats['total_withdrawn']:.2f}`

🛠️ *ADMIN ARAÇLARI*
        """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': "👤 Kullanıcı Ara", 'callback_data': 'admin_search_user'},
                    {'text': "💰 Bakiye Ekle", 'callback_data': 'admin_add_balance'}
                ],
                [
                    {'text': "🎯 Görev Oluştur", 'callback_data': 'admin_create_task'},
                    {'text': "📋 Görev Onayları", 'callback_data': 'admin_pending_tasks'}
                ],
                [
                    {'text': "🏧 Çekim Talepleri", 'callback_data': 'admin_withdrawals'},
                    {'text': "📊 Detaylı İstatistik", 'callback_data': 'admin_detailed_stats'}
                ],
                [
                    {'text': "🔍 Son İşlemler", 'callback_data': 'admin_recent_logs'},
                    {'text': "📋 Tüm Kullanıcılar", 'callback_data': 'admin_all_users'}
                ],
                [
                    {'text': "🔄 Yenile", 'callback_data': 'admin_refresh'},
                    {'text': "❌ Kapat", 'callback_data': 'admin_close'}
                ]
            ]
        }
        
        send_message(admin_id, text, reply_markup=keyboard)
    
    def handle_admin_callback(self, admin_id, data, callback_id):
        """Admin callback'lerini işle"""
        if data == 'admin_refresh':
            self.show_admin_panel(admin_id)
            answer_callback_query(callback_id, "🔄 Yenilendi")
        
        elif data == 'admin_close':
            delete_message(callback_query['message']['chat']['id'], callback_query['message']['message_id'])
            answer_callback_query(callback_id, "❌ Panel kapatıldı")
        
        elif data == 'admin_search_user':
            self.ask_admin_search_user(admin_id)
            answer_callback_query(callback_id, "👤 ID veya kullanıcı adı girin")
        
        elif data == 'admin_add_balance':
            self.ask_admin_add_balance(admin_id)
            answer_callback_query(callback_id, "💰 Kullanıcı ID ve miktar girin")
        
        elif data == 'admin_create_task':
            self.ask_admin_create_task(admin_id)
            answer_callback_query(callback_id, "🎯 Görev bilgilerini girin")
        
        elif data == 'admin_pending_tasks':
            self.show_pending_task_completions(admin_id)
            answer_callback_query(callback_id, "📋 Onay bekleyen görevler")
        
        elif data == 'admin_withdrawals':
            self.show_pending_withdrawals(admin_id)
            answer_callback_query(callback_id, "🏧 Bekleyen çekimler")
        
        elif data == 'admin_detailed_stats':
            self.show_detailed_stats(admin_id)
            answer_callback_query(callback_id, "📊 Detaylı istatistikler")
        
        elif data == 'admin_all_users':
            self.show_all_users(admin_id)
            answer_callback_query(callback_id, "📋 Tüm kullanıcılar")
        
        elif data == 'admin_recent_logs':
            self.show_recent_logs(admin_id)
            answer_callback_query(callback_id, "🔍 Son işlemler")
        
        elif data.startswith('admin_approve_task_'):
            parts = data.split('_')
            if len(parts) >= 4:
                task_id = int(parts[3])
                self.approve_task_completion_admin(admin_id, task_id, callback_id)
        
        elif data.startswith('admin_reject_task_'):
            parts = data.split('_')
            if len(parts) >= 4:
                task_id = int(parts[3])
                self.reject_task_completion_admin(admin_id, task_id, callback_id)
        
        elif data.startswith('admin_approve_withdrawal_'):
            parts = data.split('_')
            if len(parts) >= 4:
                withdrawal_id = int(parts[3])
                self.approve_withdrawal_admin(admin_id, withdrawal_id, callback_id)
        
        elif data.startswith('admin_reject_withdrawal_'):
            parts = data.split('_')
            if len(parts) >= 4:
                withdrawal_id = int(parts[3])
                self.reject_withdrawal_admin(admin_id, withdrawal_id, callback_id)
    
    def ask_admin_search_user(self, admin_id):
        """Admin kullanıcı arama"""
        send_message(admin_id, "👤 *Kullanıcı Ara*\n\nKullanıcı ID veya kullanıcı adı girin:\n\nÖrnek: `123456789` veya `@kullaniciadi`")
    
    def ask_admin_add_balance(self, admin_id):
        """Admin bakiye ekleme"""
        send_message(admin_id, "💰 *Bakiye Ekle*\n\nFormat: `ID MİKTAR NEDEN`\n\nÖrnek: `123456789 10.50 Görev bonusu`")
    
    def ask_admin_create_task(self, admin_id):
        """Admin görev oluşturma"""
        send_message(admin_id, """
🎯 *Görev Oluştur*

Format:
