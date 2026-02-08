import os
import time
import json
import requests
from datetime import datetime
import threading
import sqlite3
from flask import Flask, jsonify, request
import hashlib
import pytz
from typing import Dict, List
import uuid
import random
import firebase_admin
from firebase_admin import credentials, firestore

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

FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")

# Dil Ayarları - SADECE 2 DİL
SUPPORTED_LANGUAGES = {
    'tr': {'name': 'Türkçe', 'flag': '🇹🇷'},
    'en': {'name': 'English', 'flag': '🇺🇸'},
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

def send_photo(chat_id, photo, caption=None, reply_markup=None, parse_mode='Markdown'):
    url = BASE_URL + "sendPhoto"
    payload = {
        'chat_id': chat_id,
        'photo': photo,
        'parse_mode': parse_mode
    }

    if caption:
        payload['caption'] = caption
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"❌ Fotoğraf gönderme hatası: {e}")
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

# Firebase helper
class FirebaseClient:
    def __init__(self):
        self.enabled = False
        self.db = None
        if not FIREBASE_CREDENTIALS_JSON or not FIREBASE_PROJECT_ID:
            return
        try:
            cred = credentials.Certificate(json.loads(FIREBASE_CREDENTIALS_JSON))
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
            self.db = firestore.client()
            self.enabled = True
        except Exception as e:
            print(f"Firebase init hatası: {e}")

    def upsert(self, collection, doc_id, payload):
        if not self.enabled:
            return
        try:
            self.db.collection(collection).document(str(doc_id)).set(payload, merge=True)
        except Exception as e:
            print(f"Firebase yazma hatası ({collection}): {e}")

    def add(self, collection, payload):
        if not self.enabled:
            return
        try:
            self.db.collection(collection).add(payload)
        except Exception as e:
            print(f"Firebase ekleme hatası ({collection}): {e}")

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

        # Yükleme (Deposit) Talepleri - SADECE MANUEL KAYIT İÇİN
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                admin_note TEXT,
                status TEXT DEFAULT 'completed',
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Reklamlar
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                poster TEXT,
                link_url TEXT,
                ad_text TEXT,
                budget REAL DEFAULT 0,
                remaining_budget REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ad_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id INTEGER,
                viewer_id INTEGER,
                reward REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ad_id, viewer_id)
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
                ('Kanal Görevi', 'Belirtilen kanala katılın', 0.0025, 10, 'channel_join', 1),
                ('Grup Görevi', 'Belirtilen gruba katılın', 0.0015, 10, 'group_join', 1),
                ('Post Görevi', 'Belirtilen postu beğen/yorum yap', 0.0005, 10, 'post', 1),
                ('Bot Görevi', 'Belirtilen botu başlat', 0.001, 10, 'bot_start', 1),
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

            try:
                send_message(STATS_CHANNEL, f"""
👥 **YENİ REFERANS**
━━━━━━━━━━━━
👤 Referans: `{referred_by}`
🆕 Yeni Kullanıcı: `{user_id}`
💰 Bonus: `${REF_WELCOME_BONUS}`
                """)
            except Exception as e:
                print(f"Referans bildirim hatası: {e}")
        
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
            
            # Deposit kaydı oluştur (manuel olduğu için)
            self.cursor.execute('''
                INSERT INTO deposits (user_id, amount, admin_note, status, admin_id)
                VALUES (?, ?, ?, 'completed', ?)
            ''', (user_id, amount, reason or "Manuel yükleme", admin_id))
            
            # Admin log
            self.cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_id, details)
                VALUES (?, 'add_balance', ?, ?)
            ''', (admin_id, user_id, f"Amount: ${amount}, Reason: {reason}"))
            
            self.connection.commit()

            try:
                send_message(STATS_CHANNEL, f"""
💳 **MEGA DEPOSIT**
━━━━━━━━━━━━
👤 Kullanıcı: `{user_id}`
💰 Tutar: `${amount}`
📝 Not: {reason or 'Admin yüklemesi'}
                """)
            except Exception as e:
                print(f"Mega deposit bildirim hatası: {e}")

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

                try:
                    send_message(STATS_CHANNEL, f"""
💸 **MEGA PAYOUT**
━━━━━━━━━━━━
🆔 Çekim: `#{withdrawal_id}`
👤 Kullanıcı: `{withdrawal['user_id']}`
💰 Tutar: `${withdrawal['amount']}`
✅ Durum: **Ödendi**
                    """)
                except Exception as e:
                    print(f"Mega payout bildirim hatası: {e}")
                
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

    def admin_get_recent_deposits(self, limit=20):
        """Son yüklemeler"""
        self.cursor.execute('''
            SELECT d.*, u.username, u.first_name
            FROM deposits d
            LEFT JOIN users u ON d.user_id = u.user_id
            ORDER BY d.created_at DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in self.cursor.fetchall()]

    def admin_process_deposit(self, deposit_id, status, admin_id, note=""):
        """Yükleme taleplerini admin onaylar/redi"""
        try:
            self.cursor.execute('SELECT * FROM deposits WHERE id = ?', (deposit_id,))
            deposit = self.cursor.fetchone()
            if not deposit:
                return False

            deposit = dict(deposit)

            if status == 'approved':
                self.cursor.execute('''
                    UPDATE deposits
                    SET status = 'approved',
                        admin_id = ?,
                        admin_note = ?,
                        processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (admin_id, note, deposit_id))

                self.cursor.execute('''
                    UPDATE users SET balance = balance + ? WHERE user_id = ?
                ''', (deposit['amount'], deposit['user_id']))

                self.cursor.execute('''
                    INSERT INTO balance_transactions (user_id, amount, transaction_type, admin_id, description)
                    VALUES (?, ?, 'deposit', ?, ?)
                ''', (deposit['user_id'], deposit['amount'], admin_id, f"Deposit onayı: #{deposit_id}"))

                try:
                    send_message(STATS_CHANNEL, f"""
💳 **MEGA DEPOSIT ONAY**
━━━━━━━━━━━━
🆔 Yükleme: `#{deposit_id}`
👤 Kullanıcı: `{deposit['user_id']}`
💰 Tutar: `${deposit['amount']}`
                    """)
                except Exception as e:
                    print(f"Deposit onay bildirim hatası: {e}")

                send_message(deposit['user_id'], f"✅ Yükleme onaylandı!\n💰 ${deposit['amount']}")
            else:
                self.cursor.execute('''
                    UPDATE deposits
                    SET status = 'rejected',
                        admin_id = ?,
                        admin_note = ?,
                        processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (admin_id, note or "Reddedildi", deposit_id))

                send_message(deposit['user_id'], f"❌ Yükleme reddedildi.\n📝 Not: {note or 'Reddedildi'}")

            self.cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_id, details)
                VALUES (?, 'process_deposit', ?, ?)
            ''', (admin_id, deposit_id, f"Status: {status}, Amount: ${deposit['amount']}"))

            self.connection.commit()
            return True
        except Exception as e:
            print(f"Deposit işleme hatası: {e}")
            return False
    
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

    def create_ad(self, owner_id, poster, link_url, ad_text, budget):
        try:
            self.cursor.execute('''
                INSERT INTO ads (owner_id, poster, link_url, ad_text, budget, remaining_budget, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
            ''', (owner_id, poster, link_url, ad_text, budget, budget))
            self.connection.commit()
            return self.cursor.lastrowid
        except Exception as e:
            print(f"Reklam oluşturma hatası: {e}")
            return None

    def get_random_active_ad(self, viewer_id):
        self.cursor.execute('''
            SELECT * FROM ads
            WHERE status = 'active' AND remaining_budget > 0 AND owner_id != ?
            ORDER BY RANDOM()
            LIMIT 1
        ''', (viewer_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def record_ad_view(self, ad_id, viewer_id, reward):
        try:
            self.cursor.execute('''
                INSERT INTO ad_views (ad_id, viewer_id, reward)
                VALUES (?, ?, ?)
            ''', (ad_id, viewer_id, reward))
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"Reklam görüntüleme hatası: {e}")
            return False

    def refund_ad_budget(self, ad_id, owner_id):
        try:
            self.cursor.execute('SELECT * FROM ads WHERE id = ? AND owner_id = ?', (ad_id, owner_id))
            ad = self.cursor.fetchone()
            if not ad:
                return None
            ad = dict(ad)
            if ad['remaining_budget'] <= 0 or ad['status'] != 'active':
                return None
            refund_amount = ad['remaining_budget']
            self.cursor.execute('''
                UPDATE ads SET remaining_budget = 0, status = 'refunded' WHERE id = ?
            ''', (ad_id,))
            self.cursor.execute('''
                UPDATE users SET balance = balance + ? WHERE user_id = ?
            ''', (refund_amount, owner_id))
            self.connection.commit()
            return refund_amount
        except Exception as e:
            print(f"Reklam iade hatası: {e}")
            return None

    def get_user_ads(self, owner_id):
        self.cursor.execute('''
            SELECT * FROM ads
            WHERE owner_id = ? AND status = 'active' AND remaining_budget > 0
            ORDER BY created_at DESC
        ''', (owner_id,))
        return [dict(row) for row in self.cursor.fetchall()]

    def get_owner_ads(self, owner_id):
        self.cursor.execute('''
            SELECT * FROM ads
            WHERE owner_id = ?
            ORDER BY created_at DESC
        ''', (owner_id,))
        return [dict(row) for row in self.cursor.fetchall()]

    def get_ad_budget_summary(self, owner_id):
        self.cursor.execute('''
            SELECT COUNT(*) as active_ads, COALESCE(SUM(remaining_budget), 0) as remaining_budget
            FROM ads
            WHERE owner_id = ? AND status = 'active' AND remaining_budget > 0
        ''', (owner_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else {'active_ads': 0, 'remaining_budget': 0}
    
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

    def get_post_tasks(self, user_id=None):
        """Sadece post tipindeki görevleri getir"""
        if user_id:
            self.cursor.execute('''
                SELECT t.* FROM tasks t
                WHERE t.status = 'active' 
                AND t.task_type = 'post'
                AND t.current_participants < t.max_participants
                AND NOT EXISTS (
                    SELECT 1 FROM task_participations tp 
                    WHERE tp.task_id = t.id AND tp.user_id = ?
                )
                ORDER BY t.created_at DESC
                LIMIT 1
            ''', (user_id,))
        else:
            self.cursor.execute('''
                SELECT * FROM tasks 
                WHERE status = 'active' 
                AND task_type = 'post'
                AND current_participants < max_participants
                ORDER BY created_at DESC
                LIMIT 1
            ''')
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_all_tasks(self):
        self.cursor.execute('SELECT * FROM tasks ORDER BY created_at DESC')
        return [dict(row) for row in self.cursor.fetchall()]
    
    def complete_task(self, user_id, task_id, proof_url=None):
        """Görevi tamamla (otomatik onay)"""
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
            
            # Katılım kaydı oluştur (otomatik onay)
            self.cursor.execute('''
                INSERT INTO task_participations (task_id, user_id, status, proof_url, reviewed_by, reviewed_at)
                VALUES (?, ?, 'approved', ?, 0, CURRENT_TIMESTAMP)
            ''', (task_id, user_id, proof_url))
            
            # Görev katılımcı sayısını artır
            self.cursor.execute('''
                UPDATE tasks SET current_participants = current_participants + 1 
                WHERE id = ?
            ''', (task_id,))
            
            # Kullanıcıya ödül ver (GÖREVİN ÖDÜLÜNÜN 2/3'Ü kadar)
            original_reward = task['reward']
            actual_reward = original_reward * 0.67  # 0.0015 -> 0.001 (yaklaşık)
            
            self.cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, 
                    tasks_completed = tasks_completed + 1,
                    total_earned = total_earned + ?
                WHERE user_id = ?
            ''', (actual_reward, actual_reward, user_id))

            # Bakiye işlemi logu
            self.cursor.execute('''
                INSERT INTO balance_transactions (user_id, amount, transaction_type, description)
                VALUES (?, ?, 'task_reward', ?)
            ''', (user_id, actual_reward, f"Görev: {task['title']}"))

            # Referans komisyonu
            user = self.get_user(user_id)
            if user and user['referred_by']:
                commission = actual_reward * REF_TASK_COMMISSION
                self.cursor.execute('''
                    UPDATE users SET balance = balance + ? WHERE user_id = ?
                ''', (commission, user['referred_by']))
                self.cursor.execute('''
                    UPDATE referrals SET earned_amount = earned_amount + ? 
                    WHERE referred_id = ?
                ''', (commission, user_id))

            self.connection.commit()

            try:
                send_message(STATS_CHANNEL, f"""
✅ **YENİ GÖREV KATILIMI**
━━━━━━━━━━━━
🆔 Görev: `#{task_id}`
👤 Kullanıcı: `{user_id}`
💰 Ödül: `${actual_reward:.4f}`
✅ Durum: **Otomatik Onay**
                """)
            except Exception as e:
                print(f"Görev katılım bildirim hatası: {e}")

            return actual_reward
        except Exception as e:
            print(f"Görev tamamlama hatası: {e}")
            return None
    
    def complete_post_task(self, user_id):
        """Post görevini tamamla"""
        try:
            # Post tipindeki görevi al
            task = self.get_post_tasks(user_id)
            if not task:
                return None
            
            task_id = task['id']
            
            # Zaten katıldı mı?
            self.cursor.execute('SELECT COUNT(*) FROM task_participations WHERE task_id = ? AND user_id = ?', 
                              (task_id, user_id))
            if self.cursor.fetchone()[0] > 0:
                return None
            
            # Katılım kaydı oluştur (otomatik onay)
            self.cursor.execute('''
                INSERT INTO task_participations (task_id, user_id, status, proof_url, reviewed_by, reviewed_at)
                VALUES (?, ?, 'approved', ?, 0, CURRENT_TIMESTAMP)
            ''', (task_id, user_id, 'post_view'))
            
            # Görev katılımcı sayısını artır
            self.cursor.execute('''
                UPDATE tasks SET current_participants = current_participants + 1 
                WHERE id = ?
            ''', (task_id,))
            
            # Kullanıcıya ödül ver (GÖREVİN ÖDÜLÜNÜN 2/3'Ü kadar)
            original_reward = task['reward']
            actual_reward = original_reward * 0.67  # 0.0015 -> 0.001 (yaklaşık)
            
            self.cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, 
                    tasks_completed = tasks_completed + 1,
                    total_earned = total_earned + ?
                WHERE user_id = ?
            ''', (actual_reward, actual_reward, user_id))

            # Bakiye işlemi logu
            self.cursor.execute('''
                INSERT INTO balance_transactions (user_id, amount, transaction_type, description)
                VALUES (?, ?, 'task_reward', ?)
            ''', (user_id, actual_reward, f"Post Görevi: {task['title']}"))

            # Referans komisyonu
            user = self.get_user(user_id)
            if user and user['referred_by']:
                commission = actual_reward * REF_TASK_COMMISSION
                self.cursor.execute('''
                    UPDATE users SET balance = balance + ? WHERE user_id = ?
                ''', (commission, user['referred_by']))
                self.cursor.execute('''
                    UPDATE referrals SET earned_amount = earned_amount + ? 
                    WHERE referred_id = ?
                ''', (commission, user_id))

            self.connection.commit()

            try:
                send_message(STATS_CHANNEL, f"""
📢 **POST GÖRÜNTÜLEME**
━━━━━━━━━━━━
🆔 Görev: `#{task_id}`
👤 Kullanıcı: `{user_id}`
💰 Ödül: `${actual_reward:.4f}`
✅ Durum: **Post Görüntülendi**
                """)
            except Exception as e:
                print(f"Post görev bildirim hatası: {e}")

            return actual_reward
        except Exception as e:
            print(f"Post görev tamamlama hatası: {e}")
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
            
            # Kullanıcıya ödül ver (2/3'ü kadar)
            original_reward = participation['reward']
            reward = original_reward * 0.67
            
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

            try:
                send_message(STATS_CHANNEL, f"""
🏆 **GÖREV ONAYLANDI**
━━━━━━━━━━━━
🆔 Katılım: `#{participation_id}`
👤 Kullanıcı: `{participation['user_id']}`
🎯 Görev: **{participation['title']}**
💰 Ödül: `${reward:.4f}`
                """)
            except Exception as e:
                print(f"Görev onay bildirim hatası: {e}")

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
        self.firebase = FirebaseClient()
        if self.firebase.enabled:
            self.sync_tasks_to_firebase()
        print(f"🤖 {BOT_NAME} başlatıldı!")

    def sync_tasks_to_firebase(self):
        tasks = self.db.get_all_tasks()
        for task in tasks:
            self.firebase.upsert('tasks', task['id'], {
                'title': task['title'],
                'description': task['description'],
                'reward': task['reward'],
                'max_participants': task['max_participants'],
                'current_participants': task['current_participants'],
                'status': task['status'],
                'task_type': task['task_type'],
                'created_by': task['created_by'],
                'created_at': str(task['created_at'])
            })

    def enforce_mandatory_channels(self, user_id, lang='tr'):
        """Zorunlu kanal kontrolü"""
        missing_channels = []
        for channel in MANDATORY_CHANNELS:
            if not get_chat_member(f"@{channel['username']}", user_id):
                missing_channels.append(channel)

        if not missing_channels:
            return True

        channel_lines = "\n".join([
            f"• {channel['emoji']} **{channel['name']}** → @{channel['username']}"
            for channel in missing_channels
        ])

        texts = {
            'tr': f"""
🚨 **ZORUNLU KANAL KONTROLÜ**

Devam etmek için şu kanallara katıl:
{channel_lines}

✅ Katıldıktan sonra **Kontrol Et** butonuna bas.
            """,
            'en': f"""
🚨 **MANDATORY CHANNEL CHECK**

Please join these channels to continue:
{channel_lines}

✅ After joining, tap **Check**.
            """
        }

        keyboard = {
            'inline_keyboard': [
                [{'text': f"{channel['emoji']} {channel['name']}", 'url': channel['link']}]
                for channel in missing_channels
            ] + [
                [{'text': '✅ Kontrol Et / Check', 'callback_data': 'check_channels'}],
                [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
            ]
        }

        send_message(user_id, texts.get(lang, texts['tr']), reply_markup=keyboard)
        return False

    def cancel_user_action(self, user_id, callback_id=None):
        if user_id in self.user_states:
            del self.user_states[user_id]
        if callback_id:
            answer_callback_query(callback_id, "❌ İşlem iptal edildi")
        send_message(user_id, "❌ İşlem iptal edildi. Ana menüye dönebilirsiniz.")
    
    def handle_update(self, update):
        try:
            if 'message' in update:
                self.handle_message(update['message'])
            elif 'callback_query' in update:
                self.handle_callback_query(update['callback_query'])
        except Exception as e:
            print(f"Hata: {e}")
    
    def handle_message(self, message):
        user_id = message['from']['id']
        if 'text' not in message:
            if user_id in self.user_states and self.user_states[user_id].get('action') == 'waiting_ad_poster':
                photos = message.get('photo', [])
                if photos:
                    file_id = photos[-1].get('file_id')
                    if file_id:
                        user = self.db.get_user(user_id)
                        if user:
                            self.handle_ad_poster(user_id, file_id, user)
                return
            return
        
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
            if self.firebase.enabled:
                self.firebase.upsert('users', user_id, {
                    'user_id': user_id,
                    'username': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'language': 'tr',
                    'created_at': datetime.utcnow().isoformat(),
                    'referred_by': referred_by
                })
            
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
            elif text.startswith("/depositnote"):
                self.handle_admin_deposit_note(user_id, text)
                return

        # Reklam oluşturma süreçleri
        if user_id in self.user_states:
            action = self.user_states[user_id].get('action')
            if action == 'waiting_ad_poster':
                self.handle_ad_poster(user_id, text, user)
                return
            if action == 'waiting_ad_link':
                self.handle_ad_link(user_id, text, user)
                return
            if action == 'waiting_ad_text':
                self.handle_ad_text(user_id, text, user)
                return
            if action == 'waiting_ad_budget':
                self.handle_ad_budget(user_id, text, user)
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
            elif cmd == '/firebase':
                self.show_firebase_guide(user_id)
            elif cmd == '/ads':
                self.show_ads_menu(user_id)
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
            elif text in ["📢 Reklam", "📢 Ads"]:
                self.show_ads_menu(user_id)
            elif text in ["👥 Davet", "Referral"]:
                self.show_referral(user_id)
            elif text in ["👤 Profil", "Profile"]:
                self.show_profile(user_id)
            elif text in ["❓ Yardım", "Help"]:
                self.show_help(user_id)
            elif text in ["🔥 Firebase Rehberi", "Firebase Guide"]:
                self.show_firebase_guide(user_id)
            elif text in ["🛡️ Admin Panel"] and str(user_id) in ADMIN_IDS:
                self.show_admin_panel(user_id)
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
                [{'text': '🏠 Ana Menüye Dön / Back to Main Menu', 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)

    def show_ads_menu(self, user_id):
        """Reklam menüsü"""
        user = self.db.get_user(user_id)
        if not user:
            return

        lang = user['language']
        ads_texts = {
            'tr': """
📢 *POST GÖRÜNTÜLEME*

Buradan post görevini görüntüleyerek para kazanabilirsin.
Mevcut bir post görevi varsa görüntüle butonuna bas ve ödülünü al!
            """,
            'en': """
📢 *POST VIEWING*

You can earn money by viewing post tasks here.
If there's a current post task, tap view and get your reward!
            """
        }

        keyboard = {
            'inline_keyboard': [
                [{'text': '👁️ Post Görüntüle', 'callback_data': 'view_post_task'}],
                [{'text': '📢 Reklam Oluştur', 'callback_data': 'start_ad'}],
                [{'text': '⏸️ Reklam Yönet', 'callback_data': 'ad_manage_list'}],
                [{'text': '💱 Reklam Bakiye Dönüştür', 'callback_data': 'ad_refund_list'}],
                [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
            ]
        } if lang == 'tr' else {
            'inline_keyboard': [
                [{'text': '👁️ View Post Task', 'callback_data': 'view_post_task'}],
                [{'text': '📢 Create Ad', 'callback_data': 'start_ad'}],
                [{'text': '⏸️ Manage Ads', 'callback_data': 'ad_manage_list'}],
                [{'text': '💱 Convert Ad Budget', 'callback_data': 'ad_refund_list'}],
                [{'text': '🏠 Main Menu', 'callback_data': 'main_menu'}]
            ]
        }

        send_message(user_id, ads_texts.get(lang, ads_texts['tr']), reply_markup=keyboard)

    def view_post_task(self, user_id, callback_id=None):
        """Post görevini görüntüle"""
        user = self.db.get_user(user_id)
        if not user:
            return

        # Post tipinde görev var mı kontrol et
        task = self.db.get_post_tasks(user_id)
        
        if not task:
            if callback_id:
                answer_callback_query(callback_id, "📭 Şu anda post görevi yok")
            send_message(user_id, "📭 Şu anda görüntülenecek post görevi bulunmuyor.")
            return
        
        # Post görevini tamamla
        reward = self.db.complete_post_task(user_id)
        
        if reward:
            if callback_id:
                answer_callback_query(callback_id, f"✅ Post görüntülendi!\n💰 Ödül: ${reward:.4f}", True)
            send_message(user_id, f"""
📢 *POST GÖRÜNTÜLENDİ*

✅ Post başarıyla görüntülendi!
💰 Ödülünüz: `${reward:.4f}`
📊 Bakiyeniz güncellendi.

🏠 Ana menüye dönmek için /start yazın.
            """)
            
            # Firebase'e kaydet
            if self.firebase.enabled:
                self.firebase.add('task_participations', {
                    'task_id': task['id'],
                    'user_id': user_id,
                    'reward': reward,
                    'status': 'approved',
                    'task_type': 'post',
                    'created_at': datetime.utcnow().isoformat()
                })
        else:
            if callback_id:
                answer_callback_query(callback_id, "❌ Bu görevi zaten görüntülediniz", True)
            send_message(user_id, "❌ Bu post görevini zaten görüntülediniz.")

    def start_ad_process(self, user_id, callback_id):
        """Reklam oluşturma süreci"""
        user = self.db.get_user(user_id)
        if not user:
            return
        self.user_states[user_id] = {'action': 'waiting_ad_poster'}
        answer_callback_query(callback_id, "📢 Reklam başlatıldı")
        keyboard = {
            'inline_keyboard': [
                [{'text': '❌ İptal Et', 'callback_data': 'cancel_action'}]
            ]
        }
        send_message(user_id, "🖼️ Poster görsel URL'sini veya file_id gönder.", reply_markup=keyboard)

    def handle_ad_poster(self, user_id, text, user):
        self.user_states[user_id] = {
            'action': 'waiting_ad_link',
            'poster': text.strip()
        }
        keyboard = {
            'inline_keyboard': [
                [{'text': '❌ İptal Et', 'callback_data': 'cancel_action'}]
            ]
        }
        send_message(user_id, "🔗 Reklam linkini gönder.", reply_markup=keyboard)

    def handle_ad_link(self, user_id, text, user):
        self.user_states[user_id]['action'] = 'waiting_ad_text'
        self.user_states[user_id]['link_url'] = text.strip()
        keyboard = {
            'inline_keyboard': [
                [{'text': '❌ İptal Et', 'callback_data': 'cancel_action'}]
            ]
        }
        send_message(user_id, "📝 Reklam metnini gönder.", reply_markup=keyboard)

    def handle_ad_text(self, user_id, text, user):
        self.user_states[user_id]['action'] = 'waiting_ad_budget'
        self.user_states[user_id]['ad_text'] = text.strip()
        keyboard = {
            'inline_keyboard': [
                [{'text': '❌ İptal Et', 'callback_data': 'cancel_action'}]
            ]
        }
        send_message(user_id, "💰 Reklam bütçesini gir.", reply_markup=keyboard)

    def handle_ad_budget(self, user_id, text, user):
        try:
            budget = float(text)
            if budget <= 0:
                send_message(user_id, "❌ Lütfen sayı giriniz veya İptal ediniz.")
                return
        except ValueError:
            send_message(user_id, "❌ Lütfen sayı giriniz veya İptal ediniz.")
            return

        if user['balance'] < budget:
            send_message(user_id, "❌ Bakiye yetersiz. Depozit yap veya reklam bakiyeni çevir.")
            return

        poster = self.user_states[user_id]['poster']
        link_url = self.user_states[user_id]['link_url']
        ad_text = self.user_states[user_id]['ad_text']

        self.db.cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (budget, user_id))
        ad_id = self.db.create_ad(user_id, poster, link_url, ad_text, budget)
        self.db.connection.commit()

        if ad_id:
            if self.firebase.enabled:
                self.firebase.upsert('ads', ad_id, {
                    'owner_id': user_id,
                    'poster': poster,
                    'link_url': link_url,
                    'ad_text': ad_text,
                    'budget': budget,
                    'remaining_budget': budget,
                    'status': 'active',
                    'created_at': datetime.utcnow().isoformat()
                })
            send_message(user_id, f"✅ Reklam oluşturuldu! ID: #{ad_id}\n💰 Bütçe: ${budget:.2f}")
        else:
            send_message(user_id, "❌ Reklam oluşturulamadı.")

        del self.user_states[user_id]

    def show_ad(self, user_id, callback_id=None):
        """Eski reklam görüntüleme - POST GÖREVİNE DÖNÜŞTÜ"""
        self.view_post_task(user_id, callback_id)

    def handle_ad_reward(self, user_id, ad_id, callback_id):
        """Eski reklam ödülü - POST GÖREVİNE DÖNÜŞTÜ"""
        self.view_post_task(user_id, callback_id)

    def show_ad_refund_list(self, user_id, callback_id=None):
        ads = self.db.get_user_ads(user_id)
        if not ads:
            if callback_id:
                answer_callback_query(callback_id, "📭 Aktif reklam yok")
            send_message(user_id, "📭 Aktif reklam bulunamadı.")
            return

        keyboard = {
            'inline_keyboard': [
                [{'text': f"ID #{ad['id']} - ${ad['remaining_budget']:.2f}", 'callback_data': f"ad_refund_{ad['id']}"}]
                for ad in ads
            ] + [[{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]]
        }
        send_message(user_id, "💱 İade edilecek reklamı seç:", reply_markup=keyboard)
        if callback_id:
            answer_callback_query(callback_id)

    def handle_ad_refund(self, user_id, ad_id, callback_id):
        refunded = self.db.refund_ad_budget(ad_id, user_id)
        if refunded is None:
            answer_callback_query(callback_id, "❌ İade edilemedi", True)
            return
        if self.firebase.enabled:
            self.firebase.upsert('ads', ad_id, {
                'status': 'refunded',
                'remaining_budget': 0,
                'refunded_at': datetime.utcnow().isoformat()
            })
        answer_callback_query(callback_id, f"✅ İade edildi: ${refunded:.2f}", True)

    def show_ad_manage_list(self, user_id, callback_id=None):
        ads = self.db.get_owner_ads(user_id)
        if not ads:
            if callback_id:
                answer_callback_query(callback_id, "📭 Reklam yok")
            send_message(user_id, "📭 Reklam bulunamadı.")
            return
        keyboard = {'inline_keyboard': []}
        for ad in ads[:10]:
            status = ad['status']
            label = "⏸️ Duraklat" if status == 'active' else "▶️ Devam Et"
            action = f"ad_pause_{ad['id']}" if status == 'active' else f"ad_resume_{ad['id']}"
            keyboard['inline_keyboard'].append([
                {'text': f"#{ad['id']} {status} ${ad['remaining_budget']:.4f}", 'callback_data': action}
            ])
        keyboard['inline_keyboard'].append([{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}])
        send_message(user_id, "⚙️ Reklam yönetimi:", reply_markup=keyboard)
        if callback_id:
            answer_callback_query(callback_id)

    def handle_ad_pause(self, user_id, ad_id, callback_id):
        self.db.cursor.execute('UPDATE ads SET status = ? WHERE id = ? AND owner_id = ?', ('paused', ad_id, user_id))
        self.db.connection.commit()
        if self.firebase.enabled:
            self.firebase.upsert('ads', ad_id, {
                'status': 'paused',
                'paused_at': datetime.utcnow().isoformat()
            })
        answer_callback_query(callback_id, "⏸️ Duraklatıldı", True)

    def handle_ad_resume(self, user_id, ad_id, callback_id):
        self.db.cursor.execute('UPDATE ads SET status = ? WHERE id = ? AND owner_id = ?', ('active', ad_id, user_id))
        self.db.connection.commit()
        if self.firebase.enabled:
            self.firebase.upsert('ads', ad_id, {
                'status': 'active',
                'resumed_at': datetime.utcnow().isoformat()
            })
        answer_callback_query(callback_id, "▶️ Devam etti", True)
    
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
                if lang in ['tr', 'en']:  # SADECE 2 DİL
                    self.db.cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (lang, user_id))
                    self.db.connection.commit()
                    answer_callback_query(callback_id, "✅ Dil seçildi / Language selected")
                    self.show_main_menu(user_id, lang)
                else:
                    answer_callback_query(callback_id, "❌ Desteklenmeyen dil / Unsupported language")
            
            elif data == 'main_menu':
                user = self.db.get_user(user_id)
                if user:
                    self.show_main_menu(user_id, user['language'])
            elif data == 'check_channels':
                user = self.db.get_user(user_id)
                if user and self.enforce_mandatory_channels(user_id, user['language']):
                    self.show_main_menu(user_id, user['language'])
            elif data == 'firebase_guide':
                self.show_firebase_guide(user_id)
            
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

            elif data == 'cancel_action':
                self.cancel_user_action(user_id, callback_id)
                return
            
            elif data == 'copy_ref':
                user = self.db.get_user(user_id)
                if user:
                    answer_callback_query(callback_id, f"📋 Referans Kodunuz: {user['referral_code']}\nBu kodu kopyalayıp paylaşabilirsiniz.", True)
            
            elif data == 'show_ads':
                self.show_ads_menu(user_id)

            elif data == 'start_ad':
                self.start_ad_process(user_id, callback_id)

            elif data == 'view_ad' or data == 'view_post_task':
                self.view_post_task(user_id, callback_id)

            elif data == 'ad_refund_list':
                self.show_ad_refund_list(user_id, callback_id)

            elif data.startswith('ad_reward_'):
                ad_id = int(data.split('_')[-1])
                self.view_post_task(user_id, callback_id)

            elif data.startswith('ad_refund_'):
                ad_id = int(data.split('_')[-1])
                self.handle_ad_refund(user_id, ad_id, callback_id)

            elif data == 'ad_manage_list':
                self.show_ad_manage_list(user_id, callback_id)

            elif data.startswith('ad_pause_'):
                ad_id = int(data.split('_')[-1])
                self.handle_ad_pause(user_id, ad_id, callback_id)

            elif data.startswith('ad_resume_'):
                ad_id = int(data.split('_')[-1])
                self.handle_ad_resume(user_id, ad_id, callback_id)
            
        except Exception as e:
            print(f"Callback error: {e}")
            answer_callback_query(callback_id, "❌ Bir hata oluştu / An error occurred")

    def show_admin_panel(self, admin_id):
        """Admin panelini göster"""
        stats = self.db.admin_get_stats()

        text = f"""
🛡️ **ADMIN PANEL**

👥 `{stats['total_users']}` kullanıcı
🟢 `{stats['active_users']}` aktif
🆕 `{stats['new_users']}` yeni (24h)
💰 `${stats['total_balance']:.2f}` toplam bakiye
📥 `{stats['pending_withdrawals']}` bekleyen çekim

📌 **Hızlı Komutlar**
• `/addbalance USER_ID|@username AMOUNT [REASON]`
• `/createtask TITLE REWARD MAX_PARTICIPANTS TYPE DESCRIPTION`
"""

        keyboard = {
            'inline_keyboard': [
                [{'text': '📊 İstatistik', 'callback_data': 'admin_stats'}],
                [{'text': '🔄 Yenile', 'callback_data': 'admin_refresh'}]
            ]
        }

        send_message(admin_id, text, reply_markup=keyboard)

    def handle_admin_callback(self, admin_id, data, callback_id, callback_query):
        """Admin callback işlemleri"""
        if data == 'admin_refresh':
            answer_callback_query(callback_id, "🔄 Panel yenilendi")
            self.show_admin_panel(admin_id)
            return

        if data == 'admin_stats':
            stats = self.db.admin_get_stats()
            text = f"""
📊 **İSTATİSTİKLER**

👥 Toplam Kullanıcı: `{stats['total_users']}`
🟢 Aktif Kullanıcı: `{stats['active_users']}`
🆕 Yeni Kullanıcı (24h): `{stats['new_users']}`
💰 Toplam Bakiye: `${stats['total_balance']:.2f}`
📥 Bekleyen Çekim: `{stats['pending_withdrawals']}`
"""
            keyboard = {
                'inline_keyboard': [
                    [{'text': '🔙 Geri', 'callback_data': 'admin_refresh'}]
                ]
            }
            send_message(admin_id, text, reply_markup=keyboard)
            answer_callback_query(callback_id)
            return

        answer_callback_query(callback_id, "ℹ️ İşlem tamamlandı")
    
    # ANA MENÜ GÖSTERİMİ
    def show_main_menu(self, user_id, lang='tr'):
        """Ana menüyü göster"""
        user = self.db.get_user(user_id)
        if not user:
            return

        if not self.enforce_mandatory_channels(user_id, lang):
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
3. ✅ Görevi tamamla
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
3. ✅ Complete the task
4. 💰 Get your reward instantly!

⚡ *For Quick Start:*
- New tasks added daily
- Earn extra with referrals
- Regular bonuses and promotions
            """
        }
        
        text = welcome_texts.get(lang, welcome_texts['tr'])
        
        keyboard = {
            'keyboard': [
                ["🎯 Görevler", "💰 Bakiye"],
                ["💳 Yükle", "📢 Reklam"],
                ["👥 Davet", "👤 Profil"],
                ["❓ Yardım", "⚙️ Ayarlar"]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False
        } if lang == 'tr' else {
            'keyboard': [
                ["🎯 Tasks", "💰 Balance"],
                ["💳 Deposit", "📢 Ads"],
                ["👥 Referral", "👤 Profile"],
                ["❓ Help", "⚙️ Settings"]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False
        }

        if str(user_id) in ADMIN_IDS:
            keyboard['keyboard'].append(["🛡️ Admin Panel"])
        
        send_message(user_id, text, reply_markup=keyboard)
    
    # GÖREVLER SAYFASI
    def show_tasks(self, user_id):
        """Görevleri göster"""
        user = self.db.get_user(user_id)
        if not user:
            return

        if not self.enforce_mandatory_channels(user_id, user['language']):
            return
        
        tasks = self.db.get_active_tasks(user_id)
        lang = user['language']
        
        if not tasks:
            no_tasks_texts = {
                'tr': """
📭 *GÖREV YOK*

Şu anda görev bulunmuyor.
Yeni görev eklemek için **/createtask** kullan.
                """,
                'en': """
📭 *NO TASKS*

There are no tasks right now.
Create a task with **/createtask**.
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

Aşağıdaki görevleri tamamlayarak ödül kazanabilirsiniz. 
**NOT:** Görev ödüllerinin %67'si ödenir (örn: 0.0015$ → 0.001$)

📋 *Talimatlar:*
1. Katılmak istediğiniz görevi seçin
2. Görevin açıklamasını dikkatlice okuyun
3. Talimatları eksiksiz uygulayın
4. Tamamlandığında ödül otomatik eklenir
            """,
            'en': f"""
🎯 *AVAILABLE TASKS* ({len(tasks)})

You can earn rewards by completing the tasks below.
**NOTE:** 67% of task rewards are paid (eg: 0.0015$ → 0.001$)

📋 *Instructions:*
1. Select the task you want to join
2. Read the task description carefully
3. Follow the instructions completely
4. Reward is added automatically
            """
        }.get(lang)
        
        keyboard = {'inline_keyboard': []}
        
        type_map = {
            'channel_join': 'Kanal',
            'group_join': 'Grup',
            'bot_start': 'Bot',
            'post': 'Post'
        }
        for task in tasks[:10]:  # İlk 10 görevi göster
            task_type_label = type_map.get(task['task_type'], task['task_type'])
            original_reward = task['reward']
            actual_reward = original_reward * 0.67
            btn_text = f"{task_type_label} | {task['title']} - ${actual_reward:.4f} ({task['current_participants']}/{task['max_participants']})"
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
        ad_summary = self.db.get_ad_budget_summary(user_id)
        
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
├ 📈 Referans Kazancı: `${(user['total_earned'] * REF_TASK_COMMISSION):.2f}`
└ 📢 Reklam Bütçesi: `${ad_summary['remaining_budget']:.2f}` ({ad_summary['active_ads']} aktif)

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
├ 📈 Referral Earnings: `${(user['total_earned'] * REF_TASK_COMMISSION):.2f}`
└ 📢 Ad Budget: `${ad_summary['remaining_budget']:.2f}` ({ad_summary['active_ads']} active)

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
            """
        }
        
        text = balance_texts.get(lang, balance_texts['tr'])
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🏧 Para Çek', 'callback_data': 'show_withdraw'}],
                [{'text': '💳 Bakiye Yükle', 'callback_data': 'show_deposit'}],
                [{'text': '📢 Reklam', 'callback_data': 'show_ads'}],
                [{'text': '🎯 Görevlere Git', 'callback_data': 'show_tasks'}],
                [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)

    # BAKİYE YÜKLEME SAYFASI
    def show_deposit(self, user_id):
        """Bakiye yükleme ekranı"""
        user = self.db.get_user(user_id)
        if not user:
            return

        lang = user['language']

        deposit_texts = {
            'tr': f"""
💳 *BAKİYE YÜKLEME*

ℹ️ Manuel yükleme için bize yaz:
👉 @AlperenTHE

**NOT:** Minimum yatırım tutarı yoktur.
İstediğiniz kadar yatırım yapabilirsiniz.
""",
            'en': f"""
💳 *DEPOSIT*

ℹ️ Manual deposit, contact:
👉 @AlperenTHE

**NOTE:** There is no minimum deposit amount.
You can deposit any amount you want.
"""
        }

        text = deposit_texts.get(lang, deposit_texts['tr'])

        keyboard = {
            'inline_keyboard': [
                [{'text': '📞 @AlperenTHE', 'url': 'https://t.me/AlperenTHE'}],
                [{'text': '💰 Bakiye', 'callback_data': 'show_balance'}],
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
        
        withdraw_texts = {
            'tr': """
🚫 *PARA ÇEKME ŞU AN KAPALI*

━━━━━━━━━━━━━━━━
Şu anda çekim talepleri devre dışıdır.
Yeni duyuru geldiğinde tekrar açılacaktır.
━━━━━━━━━━━━━━━━
""",
            'en': """
🚫 *WITHDRAWALS ARE DISABLED*

━━━━━━━━━━━━━━━━
Withdrawals are currently disabled.
They will be re-enabled with a new announcement.
━━━━━━━━━━━━━━━━
"""
        }

        text = withdraw_texts.get(lang, withdraw_texts['tr'])

        keyboard = {
            'inline_keyboard': [
                [{'text': '💳 Bakiye Yükle', 'callback_data': 'show_deposit'}],
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
        ad_summary = self.db.get_ad_budget_summary(user_id)
        
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
├ 📢 Reklam Bütçesi: `${ad_summary['remaining_budget']:.2f}` ({ad_summary['active_ads']} aktif)
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
├ 📢 Ad Budget: `${ad_summary['remaining_budget']:.2f}` ({ad_summary['active_ads']} active)
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
   • Tamamlandığında ödül otomatik eklenir
   • Bakiye anında güncellenir

2. **Para çekme şartları nelerdir?**
   • Şu an çekim kapalı
   • Yeniden açıldığında şartlar duyurulacak

3. **Referans sisteminden nasıl kazanırım?**
   • Her yeni referans: `${REF_WELCOME_BONUS}` bonus
   • Referanslarınızın her görev kazancından: `%{REF_TASK_COMMISSION * 100}` komisyon
   • Ödemeler otomatik ve anlıktır

4. **Görev onay süresi ne kadar?**
   • Otomatik onay aktif
   • Ödül anlık eklenir

5. **Bakiye neden artmıyor?**
   • Sistemde teknik bir sorun olabilir
   • Lütfen destek ekibiyle iletişime geçin

6. **Minimum yatırım tutarı nedir?**
   • **Minimum yatırım tutarı yoktur.**
   • İstediğiniz kadar yatırım yapabilirsiniz.

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

🚀 *Firebase Veritabanı Rehberi:*
• Detaylı kurulum ve entegrasyon için **/firebase** komutunu kullanın
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
   • Reward is added automatically
   • Balance updates instantly

2. **What are the withdrawal conditions?**
   • Withdrawals are currently disabled
   • Conditions will be announced when reopened

3. **How do I earn from referral system?**
   • Each new referral: `${REF_WELCOME_BONUS}` bonus
   • From each task earning of your referrals: `%{REF_TASK_COMMISSION * 100}` commission
   • Payments are automatic and instant

4. **How long does task approval take?**
   • Auto-approval is enabled
   • Rewards are instant

5. **Why isn't my balance increasing?**
   • There may be a technical issue in the system
   • Please contact the support team

6. **What is the minimum deposit amount?**
   • **There is no minimum deposit amount.**
   • You can deposit any amount you want.

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

🚀 *Firebase Database Guide:*
• Use **/firebase** to view the step-by-step setup
            """
        }
        
        text = help_texts.get(lang, help_texts['tr'])
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '📞 Destekle İletişim', 'url': f'tg://resolve?domain={SUPPORT_USERNAME[1:]}'}],
                [{'text': '📢 Resmi Kanal', 'url': 'https://t.me/TaskizLive'}],
                [{'text': '🔥 Firebase Rehberi', 'callback_data': 'firebase_guide'}],
                [{'text': '🏠 Ana Menü', 'callback_data': 'main_menu'}]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)

    def show_firebase_guide(self, user_id):
        """Firebase rehberini göster"""
        user = self.db.get_user(user_id)
        if not user:
            return

        lang = user['language']

        firebase_texts = {
            'tr': f"""
🔥 **FIREBASE KISA REHBER** 🔥

✅ **Seçim:** **Firestore** (önerilen) veya **Realtime DB**  
✅ **Amaç:** Hızlı, güvenli, gerçek zamanlı yapı

**1) Proje Aç**
• https://console.firebase.google.com/  
• **Firestore** veya **Realtime DB** aç

**2) Service Account (JSON)**
• **Project Settings → Service accounts**  
• **Generate new private key**

**3) ENV Değişkenleri**
• `FIREBASE_CREDENTIALS_JSON`  
• `FIREBASE_PROJECT_ID` (Firestore)  
• `FIREBASE_DATABASE_URL` (Realtime)

**4) Kurulum**
`pip install firebase-admin`

**5) Firestore Bağlantı**
```python
import firebase_admin
from firebase_admin import credentials, firestore
import json

cred = credentials.Certificate(json.loads(os.environ["FIREBASE_CREDENTIALS_JSON"]))
firebase_admin.initialize_app(cred, {
    "projectId": os.environ["FIREBASE_PROJECT_ID"]
})
db = firestore.client()
```

✅ Kurulum tamam! Artık botunuz Firebase ile çalışmaya hazır.
            """,
            'en': f"""
🔥 **FIREBASE QUICK GUIDE** 🔥

✅ **Choice:** **Firestore** (recommended) or **Realtime DB**  
✅ **Goal:** Fast, secure, real-time setup

**1) Create Project**
• https://console.firebase.google.com/  
• Enable **Firestore** or **Realtime DB**

**2) Service Account (JSON)**
• **Project Settings → Service accounts**  
• **Generate new private key**

**3) ENV Variables**
• `FIREBASE_CREDENTIALS_JSON`  
• `FIREBASE_PROJECT_ID` (Firestore)  
• `FIREBASE_DATABASE_URL` (Realtime)

**4) Install**
`pip install firebase-admin`

**5) Firestore Connection**
```python
import firebase_admin
from firebase_admin import credentials, firestore
import json

cred = credentials.Certificate(json.loads(os.environ["FIREBASE_CREDENTIALS_JSON"]))
firebase_admin.initialize_app(cred, {
    "projectId": os.environ["FIREBASE_PROJECT_ID"]
})
db = firestore.client()
```

✅ Setup complete! Your bot is ready to use Firebase.
            """
        }

        text = firebase_texts.get(lang, firebase_texts['tr'])
        send_message(user_id, text, parse_mode="Markdown")
