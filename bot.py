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

# ═══════════════════════════════════════
#         BOT TEMEL AYARLAR
# ═══════════════════════════════════════
TOKEN            = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS        = os.environ.get("ADMIN_ID", "7904032877").split(",")
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "@AlperenTHE")
WEBHOOK_URL      = os.environ.get("WEBHOOK_URL", "")
STATS_CHANNEL    = os.environ.get("STATS_CHANNEL", "@TaskizLive")
BOT_USERNAME     = os.environ.get("BOT_USERNAME", "TaskizBot")
BOT_NAME         = os.environ.get("BOT_NAME", "TaskizBot")

# ═══════════════════════════════════════
#       ZORUNLU KANALLAR
# ═══════════════════════════════════════
MANDATORY_CHANNELS = [
    {'username': 'TaskizLive', 'link': 'https://t.me/TaskizLive', 'name': '📊 TaskizLive', 'emoji': '📊'},
]

# ═══════════════════════════════════════
#       ZORUNLU GRUPLAR
# ═══════════════════════════════════════
MANDATORY_GROUPS = []

if not TOKEN:
    raise ValueError("Bot token gerekli! TELEGRAM_BOT_TOKEN ortam değişkenini ayarlayın.")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
FIREBASE_PROJECT_ID       = os.environ.get("FIREBASE_PROJECT_ID", "")

# ═══════════════════════════════════════
#          DİL DESTEĞİ (3 DİL)
# ═══════════════════════════════════════
SUPPORTED_LANGUAGES = {
    'tr':   {'name': 'Türkçe',             'flag': '🇹🇷'},
    'en':   {'name': 'English',            'flag': '🇺🇸'},
    'pt_br':{'name': 'Português (Brasil)', 'flag': '🇧🇷'},
}

# ═══════════════════════════════════════
#         SİSTEM AYARLARI
# ═══════════════════════════════════════
MIN_WITHDRAW              = 0.05    # TON
REF_WELCOME_BONUS         = 0.005   # TON per referral
REF_TASK_COMMISSION       = 0.25    # 25% of referral's task reward
MIN_REFERRALS_FOR_WITHDRAW = 0      # Ref şartı yok (sadece bakiye)

# Flask
app = Flask(__name__)

@app.route("/", methods=["GET"])
def healthcheck():
    return jsonify({"status": "ok", "bot": BOT_NAME})

# ═══════════════════════════════════════
#         TELEGRAM API FONKSİYONLARI
# ═══════════════════════════════════════
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
        print(f"❌ Mesaj hatası: {e}")
        return None

def send_photo(chat_id, photo, caption=None, reply_markup=None, parse_mode='Markdown'):
    url = BASE_URL + "sendPhoto"
    payload = {'chat_id': chat_id, 'photo': photo, 'parse_mode': parse_mode}
    if caption:
        payload['caption'] = caption
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"❌ Fotoğraf hatası: {e}")
        return None

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode='Markdown'):
    url = BASE_URL + "editMessageText"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
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

def delete_message(chat_id, message_id):
    url = BASE_URL + "deleteMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'message_id': message_id}, timeout=5)
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
    try:
        response = requests.post(url, json={'chat_id': chat_id, 'user_id': user_id}, timeout=10)
        data = response.json()
        if data.get('ok'):
            status = data['result']['status']
            return status in ['member', 'administrator', 'creator']
        return False
    except:
        return False

def get_updates(offset=None, timeout=30):
    url = BASE_URL + "getUpdates"
    params = {'timeout': timeout}
    if offset is not None:
        params['offset'] = offset
    try:
        response = requests.get(url, params=params, timeout=timeout + 5)
        data = response.json()
        if data.get('ok'):
            return data.get('result', [])
    except Exception as e:
        print(f"❌ Update hatası: {e}")
    return []

# ═══════════════════════════════════════
#         FIREBASE İStemcisi
# ═══════════════════════════════════════
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
            print("✅ Firebase bağlandı")
        except Exception as e:
            print(f"Firebase init hatası: {e}")

    def upsert(self, collection, doc_id, payload):
        if not self.enabled:
            return
        try:
            self.db.collection(collection).document(str(doc_id)).set(payload, merge=True)
        except Exception as e:
            print(f"Firebase yazma hatası: {e}")

    def add(self, collection, payload):
        if not self.enabled:
            return
        try:
            self.db.collection(collection).add(payload)
        except Exception as e:
            print(f"Firebase ekleme hatası: {e}")

# ═══════════════════════════════════════
#         VERİTABANI
# ═══════════════════════════════════════
class Database:
    def __init__(self, db_path='taskizbot.db'):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.lock = threading.Lock()
        self.setup_database()
        print("✅ Veritabanı hazır")

    def execute(self, query, params=()):
        with self.lock:
            self.cursor.execute(query, params)
            self.connection.commit()
            return self.cursor

    def setup_database(self):
        queries = [
            '''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT DEFAULT 'tr',
                balance REAL DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                tasks_completed INTEGER DEFAULT 0,
                total_earned REAL DEFAULT 0,
                total_referrals INTEGER DEFAULT 0,
                ton_address TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )''',
            '''CREATE TABLE IF NOT EXISTS balance_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                transaction_type TEXT,
                description TEXT,
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                reward REAL,
                max_participants INTEGER,
                current_participants INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                task_type TEXT DEFAULT 'general',
                task_link TEXT DEFAULT '',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS task_participations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                proof_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_id, user_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                ton_address TEXT,
                status TEXT DEFAULT 'pending',
                tx_hash TEXT,
                admin_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER UNIQUE,
                channels_joined INTEGER DEFAULT 0,
                earned_amount REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                poster TEXT,
                link_url TEXT,
                ad_text TEXT,
                budget REAL DEFAULT 0,
                remaining_budget REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS ad_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id INTEGER,
                viewer_id INTEGER,
                reward REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ad_id, viewer_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                target_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
        ]
        for q in queries:
            self.cursor.execute(q)
        self.connection.commit()
        self.add_sample_tasks()

    def add_sample_tasks(self):
        count = self.cursor.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        if count == 0:
            sample_tasks = [
                ('Kanal Görevi #1', 'Belirtilen kanala katılın', 0.003, 100, 'channel_join', 'https://t.me/example', 1),
                ('Grup Görevi #1',  'Belirtilen gruba katılın',  0.002, 100, 'group_join',   'https://t.me/example', 1),
                ('Bot Görevi #1',   'Belirtilen botu başlatın',  0.001, 100, 'bot_start',    'https://t.me/example', 1),
                ('Post Görevi #1',  'Postu beğen ve yorum yap',  0.001, 100, 'post',         'https://t.me/example', 1),
            ]
            for t in sample_tasks:
                self.cursor.execute(
                    'INSERT INTO tasks (title, description, reward, max_participants, task_type, task_link, created_by) VALUES (?,?,?,?,?,?,?)',
                    t
                )
            self.connection.commit()

    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            user = dict(row)
            self.cursor.execute(
                'SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND status = ?',
                (user_id, 'active')
            )
            user['total_referrals'] = self.cursor.fetchone()[0]
            return user
        return None

    def create_user(self, user_id, username, first_name, last_name, language='tr', referred_by=None):
        existing = self.get_user(user_id)
        if existing:
            return existing
        referral_code = str(uuid.uuid4())[:8].upper()
        self.cursor.execute(
            'INSERT INTO users (user_id, username, first_name, last_name, language, referral_code, referred_by) VALUES (?,?,?,?,?,?,?)',
            (user_id, username, first_name, last_name, language, referral_code, referred_by)
        )
        if referred_by:
            # Referans kaydı - channels_joined=0 (beklemede)
            self.cursor.execute(
                'INSERT OR IGNORE INTO referrals (referrer_id, referred_id, channels_joined, status) VALUES (?,?,0,"pending")',
                (referred_by, user_id)
            )
        self.connection.commit()
        return self.get_user(user_id)

    def activate_referral(self, referred_id):
        """Ref kanalları doğrulandıktan sonra bonusu ver"""
        self.cursor.execute('SELECT * FROM referrals WHERE referred_id = ? AND status = "pending"', (referred_id,))
        row = self.cursor.fetchone()
        if not row:
            return False
        ref = dict(row)
        referrer_id = ref['referrer_id']
        # Bonus ver
        self.cursor.execute('UPDATE users SET balance = balance + ?, total_referrals = total_referrals + 1 WHERE user_id = ?',
                            (REF_WELCOME_BONUS, referrer_id))
        self.cursor.execute('UPDATE referrals SET status = "active", channels_joined = 1, earned_amount = ? WHERE referred_id = ?',
                            (REF_WELCOME_BONUS, referred_id))
        self.cursor.execute('INSERT INTO balance_transactions (user_id, amount, transaction_type, description) VALUES (?,?,?,?)',
                            (referrer_id, REF_WELCOME_BONUS, 'referral_bonus', f'Referans bonusu: {referred_id}'))
        self.connection.commit()
        # Referans verende bildirim
        try:
            send_message(STATS_CHANNEL, f"👥 *YENİ AKTİF REFERANS*\n👤 Referans: `{referrer_id}`\n🆕 Yeni Üye: `{referred_id}`\n💎 Bonus: `{REF_WELCOME_BONUS} TON`")
        except:
            pass
        return referrer_id

    def admin_add_balance(self, user_id, amount, admin_id, reason=""):
        self.cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        self.cursor.execute('INSERT INTO balance_transactions (user_id, amount, transaction_type, admin_id, description) VALUES (?,?,?,?,?)',
                            (user_id, amount, 'admin_add', admin_id, reason or "Admin ekledi"))
        self.cursor.execute('INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?,?,?,?)',
                            (admin_id, 'add_balance', user_id, f"{amount} TON | {reason}"))
        self.connection.commit()
        return True

    def admin_remove_balance(self, user_id, amount, admin_id, reason=""):
        self.cursor.execute('UPDATE users SET balance = MAX(0, balance - ?) WHERE user_id = ?', (amount, user_id))
        self.cursor.execute('INSERT INTO balance_transactions (user_id, amount, transaction_type, admin_id, description) VALUES (?,?,?,?,?)',
                            (user_id, -amount, 'admin_remove', admin_id, reason or "Admin çıkardı"))
        self.connection.commit()
        return True

    def admin_ban_user(self, user_id, admin_id):
        self.cursor.execute('UPDATE users SET status = "banned" WHERE user_id = ?', (user_id,))
        self.cursor.execute('INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?,?,?,?)',
                            (admin_id, 'ban_user', user_id, 'Yasaklandı'))
        self.connection.commit()

    def admin_unban_user(self, user_id, admin_id):
        self.cursor.execute('UPDATE users SET status = "active" WHERE user_id = ?', (user_id,))
        self.connection.commit()

    def admin_get_stats(self):
        total_users  = self.cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        active_users = self.cursor.execute("SELECT COUNT(*) FROM users WHERE status='active' AND last_active > datetime('now','-1 day')").fetchone()[0]
        new_users    = self.cursor.execute("SELECT COUNT(*) FROM users WHERE created_at > datetime('now','-1 day')").fetchone()[0]
        total_bal    = self.cursor.execute('SELECT COALESCE(SUM(balance),0) FROM users').fetchone()[0]
        pending_w    = self.cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0]
        total_tasks  = self.cursor.execute("SELECT COUNT(*) FROM task_participations WHERE status='approved'").fetchone()[0]
        total_paid   = self.cursor.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='paid'").fetchone()[0]
        return {
            'total_users': total_users, 'active_users': active_users, 'new_users': new_users,
            'total_balance': total_bal, 'pending_withdrawals': pending_w,
            'total_tasks': total_tasks, 'total_paid': total_paid
        }

    def get_active_tasks(self, user_id=None):
        if user_id:
            self.cursor.execute('''
                SELECT t.* FROM tasks t
                WHERE t.status = 'active'
                AND t.current_participants < t.max_participants
                AND NOT EXISTS (SELECT 1 FROM task_participations tp WHERE tp.task_id = t.id AND tp.user_id = ?)
                ORDER BY t.reward DESC, t.created_at DESC
            ''', (user_id,))
        else:
            self.cursor.execute("SELECT * FROM tasks WHERE status='active' AND current_participants < max_participants ORDER BY reward DESC")
        return [dict(r) for r in self.cursor.fetchall()]

    def complete_task(self, user_id, task_id):
        try:
            self.cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
            task = self.cursor.fetchone()
            if not task:
                return None
            task = dict(task)
            self.cursor.execute('SELECT COUNT(*) FROM task_participations WHERE task_id=? AND user_id=?', (task_id, user_id))
            if self.cursor.fetchone()[0] > 0:
                return None
            reward = task['reward']
            self.cursor.execute('INSERT INTO task_participations (task_id, user_id, status) VALUES (?,?,?)', (task_id, user_id, 'approved'))
            self.cursor.execute('UPDATE tasks SET current_participants = current_participants + 1 WHERE id = ?', (task_id,))
            self.cursor.execute('UPDATE users SET balance = balance + ?, tasks_completed = tasks_completed + 1, total_earned = total_earned + ? WHERE user_id = ?',
                                (reward, reward, user_id))
            self.cursor.execute('INSERT INTO balance_transactions (user_id, amount, transaction_type, description) VALUES (?,?,?,?)',
                                (user_id, reward, 'task_reward', task['title']))
            # Referans komisyonu
            user = self.get_user(user_id)
            if user and user['referred_by']:
                commission = reward * REF_TASK_COMMISSION
                self.cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (commission, user['referred_by']))
                self.cursor.execute('UPDATE referrals SET earned_amount = earned_amount + ? WHERE referred_id = ?', (commission, user_id))
                self.cursor.execute('INSERT INTO balance_transactions (user_id, amount, transaction_type, description) VALUES (?,?,?,?)',
                                    (user['referred_by'], commission, 'referral_commission', f'Komisyon: {user_id}'))
            self.connection.commit()
            return reward
        except Exception as e:
            print(f"complete_task hatası: {e}")
            return None

    def create_withdrawal(self, user_id, amount, ton_address):
        try:
            self.cursor.execute('INSERT INTO withdrawals (user_id, amount, ton_address, status) VALUES (?,?,?,?)',
                                (user_id, amount, ton_address, 'pending'))
            self.cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
            self.cursor.execute('INSERT INTO balance_transactions (user_id, amount, transaction_type, description) VALUES (?,?,?,?)',
                                (user_id, -amount, 'withdrawal', f'TON: {ton_address[:12]}...'))
            self.connection.commit()
            return self.cursor.lastrowid
        except Exception as e:
            print(f"withdrawal hatası: {e}")
            return None

    def get_pending_withdrawals(self):
        self.cursor.execute('''
            SELECT w.*, u.first_name, u.username FROM withdrawals w
            JOIN users u ON w.user_id = u.user_id
            WHERE w.status = 'pending' ORDER BY w.created_at ASC
        ''')
        return [dict(r) for r in self.cursor.fetchall()]

    def approve_withdrawal(self, withdrawal_id, admin_id, tx_hash=""):
        self.cursor.execute("UPDATE withdrawals SET status='paid', tx_hash=?, processed_at=CURRENT_TIMESTAMP WHERE id=?",
                            (tx_hash, withdrawal_id))
        self.cursor.execute('INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?,?,?,?)',
                            (admin_id, 'approve_withdrawal', withdrawal_id, tx_hash))
        self.connection.commit()

    def reject_withdrawal(self, withdrawal_id, admin_id, reason=""):
        self.cursor.execute('SELECT * FROM withdrawals WHERE id = ?', (withdrawal_id,))
        w = self.cursor.fetchone()
        if w:
            w = dict(w)
            self.cursor.execute("UPDATE withdrawals SET status='rejected', admin_note=? WHERE id=?", (reason, withdrawal_id))
            self.cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (w['amount'], w['user_id']))
            self.cursor.execute('INSERT INTO balance_transactions (user_id, amount, transaction_type, description) VALUES (?,?,?,?)',
                                (w['user_id'], w['amount'], 'withdrawal_refund', f'Reddedildi: {reason}'))
            self.connection.commit()

    def search_user(self, term):
        try:
            uid = int(term)
            self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (uid,))
        except:
            self.cursor.execute('SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ?',
                                (f'%{term}%', f'%{term}%'))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_all_tasks(self):
        self.cursor.execute('SELECT * FROM tasks ORDER BY created_at DESC')
        return [dict(r) for r in self.cursor.fetchall()]

    def update_last_active(self, user_id):
        self.cursor.execute('UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
        self.connection.commit()

    def create_ad(self, owner_id, poster, link_url, ad_text, budget):
        self.cursor.execute('INSERT INTO ads (owner_id, poster, link_url, ad_text, budget, remaining_budget) VALUES (?,?,?,?,?,?)',
                            (owner_id, poster, link_url, ad_text, budget, budget))
        self.connection.commit()
        return self.cursor.lastrowid

    def get_post_task(self, user_id):
        self.cursor.execute('''
            SELECT * FROM ads WHERE status='active' AND remaining_budget > 0 AND owner_id != ?
            AND id NOT IN (SELECT ad_id FROM ad_views WHERE viewer_id = ?)
            ORDER BY RANDOM() LIMIT 1
        ''', (user_id, user_id))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def record_ad_view(self, ad_id, viewer_id, reward):
        try:
            self.cursor.execute('INSERT INTO ad_views (ad_id, viewer_id, reward) VALUES (?,?,?)', (ad_id, viewer_id, reward))
            self.cursor.execute('UPDATE ads SET remaining_budget = remaining_budget - ? WHERE id = ?', (reward, ad_id))
            self.cursor.execute('UPDATE ads SET status = "completed" WHERE id = ? AND remaining_budget <= 0', (ad_id,))
            self.cursor.execute('UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?',
                                (reward, reward, viewer_id))
            self.cursor.execute('INSERT INTO balance_transactions (user_id, amount, transaction_type, description) VALUES (?,?,?,?)',
                                (viewer_id, reward, 'ad_view', f'Reklam #{ad_id}'))
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def set_ton_address(self, user_id, address):
        self.cursor.execute('UPDATE users SET ton_address = ? WHERE user_id = ?', (address, user_id))
        self.connection.commit()


# ═══════════════════════════════════════
#         METINLER (3 DİL)
# ═══════════════════════════════════════
TEXTS = {
    'tr': {
        'select_lang':   "🌍 *DİL SEÇ*\nKullanmak istediğiniz dili seçin:",
        'welcome_back':  "🌟 Tekrar hoş geldin *{name}*!",
        'join_channels': "⚠️ *ZORUNLU ÜYELİK*\n\nBottan yararlanmak için lütfen tüm kanal ve gruplara katılın:\n\n*Kanallar:*\n{channels}\n*Gruplar:*\n{groups}\n\n✅ Katıldıktan sonra aşağıdaki butona bas.",
        'check_btn':     "✅ Katıldım, Kontrol Et",
        'not_joined':    "❌ Henüz tüm kanallara katılmadınız!\n\nEksik: {missing}",
        'menu_balance':  "💰 Bakiye",
        'menu_tasks':    "🎯 Görevler",
        'menu_ref':      "👥 Davet Et",
        'menu_withdraw': "💎 Çekim",
        'menu_profile':  "👤 Profil",
        'menu_ads':      "📢 Reklam",
        'menu_help':     "❓ Yardım",
        'menu_settings': "⚙️ Ayarlar",
        'menu_admin':    "🛡️ Admin",
        'tasks_title':   "🎯 *MEVCUT GÖREVLER* ({count})",
        'no_tasks':      "📭 Şu an görev yok. Yakında yeni görevler eklenecek!",
        'task_done':     "✅ Görev tamamlandı!\n💎 Ödül: `{reward} TON`",
        'task_already':  "❌ Bu görevi zaten tamamladınız!",
        'balance_title': "💰 *BAKİYE*",
        'balance_text':  "💎 Mevcut Bakiye: `{balance} TON`\n📊 Toplam Kazanç: `{earned} TON`\n🎯 Tamamlanan Görev: `{tasks}`\n👥 Aktif Referans: `{refs}`",
        'withdraw_title':"💎 *TON ÇEKİM*",
        'withdraw_text': "💎 Bakiye: `{balance} TON`\n\nMin. çekim: `{min_w} TON`\n\n💳 TON Adresinizi girin:",
        'withdraw_low':  "❌ Yetersiz bakiye! Min. {min_w} TON gerekli.\n💎 Bakiyeniz: {balance} TON",
        'withdraw_ok':   "✅ Çekim Talebi Alındı!\n\n💎 Miktar: {amount} TON\n🏦 Adres: `{address}`\n⏳ İşlem süresi: 24-48 saat",
        'enter_amount':  "💰 Çekmek istediğiniz miktarı girin (TON):",
        'enter_address': "🏦 TON cüzdan adresinizi girin:",
        'invalid_amount':"❌ Geçersiz miktar!",
        'ref_title':     "👥 *REFERANS SİSTEMİ*",
        'ref_text':      "🔗 Referans linkin:\n`{link}`\n\n💰 Ref başı bonus: `{bonus} TON`\n👥 Aktif referansın: `{count}`\n💎 Toplam kazanç: `{earned} TON`\n\n⚠️ Referansların tüm kanallara katılmalı!",
        'profile_title': "👤 *PROFİL*",
        'profile_text':  "👤 İsim: *{name}*\n🆔 ID: `{uid}`\n🌍 Dil: {lang}\n\n💎 Bakiye: `{balance} TON`\n🎯 Görevler: `{tasks}`\n👥 Referanslar: `{refs}`\n📅 Kayıt: `{date}`",
        'help_title':    "❓ *YARDIM*",
        'settings_title':"⚙️ *AYARLAR*",
        'ton_address_set':"✅ TON adresiniz kaydedildi!",
    },
    'en': {
        'select_lang':   "🌍 *SELECT LANGUAGE*\nPlease choose your language:",
        'welcome_back':  "🌟 Welcome back *{name}*!",
        'join_channels': "⚠️ *MANDATORY MEMBERSHIP*\n\nJoin all channels and groups to use the bot:\n\n*Channels:*\n{channels}\n*Groups:*\n{groups}\n\n✅ Press the button after joining.",
        'check_btn':     "✅ I Joined, Check",
        'not_joined':    "❌ You haven't joined all channels!\n\nMissing: {missing}",
        'menu_balance':  "💰 Balance",
        'menu_tasks':    "🎯 Tasks",
        'menu_ref':      "👥 Invite",
        'menu_withdraw': "💎 Withdraw",
        'menu_profile':  "👤 Profile",
        'menu_ads':      "📢 Ads",
        'menu_help':     "❓ Help",
        'menu_settings': "⚙️ Settings",
        'menu_admin':    "🛡️ Admin",
        'tasks_title':   "🎯 *AVAILABLE TASKS* ({count})",
        'no_tasks':      "📭 No tasks right now. New tasks coming soon!",
        'task_done':     "✅ Task completed!\n💎 Reward: `{reward} TON`",
        'task_already':  "❌ You already completed this task!",
        'balance_title': "💰 *BALANCE*",
        'balance_text':  "💎 Current Balance: `{balance} TON`\n📊 Total Earned: `{earned} TON`\n🎯 Tasks Completed: `{tasks}`\n👥 Active Referrals: `{refs}`",
        'withdraw_title':"💎 *TON WITHDRAW*",
        'withdraw_text': "💎 Balance: `{balance} TON`\n\nMin. withdrawal: `{min_w} TON`\n\n💳 Enter your TON address:",
        'withdraw_low':  "❌ Insufficient balance! Min. {min_w} TON required.\n💎 Your balance: {balance} TON",
        'withdraw_ok':   "✅ Withdrawal Request Received!\n\n💎 Amount: {amount} TON\n🏦 Address: `{address}`\n⏳ Processing time: 24-48 hours",
        'enter_amount':  "💰 Enter the amount to withdraw (TON):",
        'enter_address': "🏦 Enter your TON wallet address:",
        'invalid_amount':"❌ Invalid amount!",
        'ref_title':     "👥 *REFERRAL SYSTEM*",
        'ref_text':      "🔗 Your referral link:\n`{link}`\n\n💰 Bonus per referral: `{bonus} TON`\n👥 Active referrals: `{count}`\n💎 Total earnings: `{earned} TON`\n\n⚠️ Referrals must join all channels!",
        'profile_title': "👤 *PROFILE*",
        'profile_text':  "👤 Name: *{name}*\n🆔 ID: `{uid}`\n🌍 Language: {lang}\n\n💎 Balance: `{balance} TON`\n🎯 Tasks: `{tasks}`\n👥 Referrals: `{refs}`\n📅 Joined: `{date}`",
        'help_title':    "❓ *HELP*",
        'settings_title':"⚙️ *SETTINGS*",
        'ton_address_set':"✅ Your TON address has been saved!",
    },
    'pt_br': {
        'select_lang':   "🌍 *SELECIONAR IDIOMA*\nEscolha seu idioma:",
        'welcome_back':  "🌟 Bem-vindo de volta *{name}*!",
        'join_channels': "⚠️ *PARTICIPAÇÃO OBRIGATÓRIA*\n\nEntre em todos os canais e grupos para usar o bot:\n\n*Canais:*\n{channels}\n*Grupos:*\n{groups}\n\n✅ Pressione o botão após entrar.",
        'check_btn':     "✅ Entrei, Verificar",
        'not_joined':    "❌ Você ainda não entrou em todos os canais!\n\nFaltando: {missing}",
        'menu_balance':  "💰 Saldo",
        'menu_tasks':    "🎯 Tarefas",
        'menu_ref':      "👥 Convidar",
        'menu_withdraw': "💎 Sacar",
        'menu_profile':  "👤 Perfil",
        'menu_ads':      "📢 Anúncios",
        'menu_help':     "❓ Ajuda",
        'menu_settings': "⚙️ Ajustes",
        'menu_admin':    "🛡️ Admin",
        'tasks_title':   "🎯 *TAREFAS DISPONÍVEIS* ({count})",
        'no_tasks':      "📭 Sem tarefas no momento. Novas tarefas em breve!",
        'task_done':     "✅ Tarefa concluída!\n💎 Recompensa: `{reward} TON`",
        'task_already':  "❌ Você já completou esta tarefa!",
        'balance_title': "💰 *SALDO*",
        'balance_text':  "💎 Saldo Atual: `{balance} TON`\n📊 Total Ganho: `{earned} TON`\n🎯 Tarefas Concluídas: `{tasks}`\n👥 Indicações Ativas: `{refs}`",
        'withdraw_title':"💎 *SAQUE TON*",
        'withdraw_text': "💎 Saldo: `{balance} TON`\n\nMín. de saque: `{min_w} TON`\n\n💳 Digite seu endereço TON:",
        'withdraw_low':  "❌ Saldo insuficiente! Mín. {min_w} TON necessário.\n💎 Seu saldo: {balance} TON",
        'withdraw_ok':   "✅ Pedido de Saque Recebido!\n\n💎 Valor: {amount} TON\n🏦 Endereço: `{address}`\n⏳ Tempo de processamento: 24-48 horas",
        'enter_amount':  "💰 Digite o valor para sacar (TON):",
        'enter_address': "🏦 Digite seu endereço de carteira TON:",
        'invalid_amount':"❌ Valor inválido!",
        'ref_title':     "👥 *SISTEMA DE INDICAÇÕES*",
        'ref_text':      "🔗 Seu link de indicação:\n`{link}`\n\n💰 Bônus por indicação: `{bonus} TON`\n👥 Indicações ativas: `{count}`\n💎 Total ganho: `{earned} TON`\n\n⚠️ Seus indicados devem entrar em todos os canais!",
        'profile_title': "👤 *PERFIL*",
        'profile_text':  "👤 Nome: *{name}*\n🆔 ID: `{uid}`\n🌍 Idioma: {lang}\n\n💎 Saldo: `{balance} TON`\n🎯 Tarefas: `{tasks}`\n👥 Indicações: `{refs}`\n📅 Registro: `{date}`",
        'help_title':    "❓ *AJUDA*",
        'settings_title':"⚙️ *AJUSTES*",
        'ton_address_set':"✅ Seu endereço TON foi salvo!",
    },
}

def t(lang, key, **kwargs):
    """Çeviri fonksiyonu"""
    lang = lang if lang in TEXTS else 'en'
    text = TEXTS[lang].get(key, TEXTS['en'].get(key, key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except:
            pass
    return text


# ═══════════════════════════════════════
#           ANA BOT SINIFI
# ═══════════════════════════════════════
class TaskizBot:
    def __init__(self):
        self.db = Database()
        self.firebase = FirebaseClient()
        self.user_states: Dict = {}
        print(f"🤖 {BOT_NAME} başlatıldı!")

    def check_all_channels(self, user_id):
        """Tüm zorunlu kanal ve grupları kontrol et"""
        missing = []
        for ch in MANDATORY_CHANNELS:
            if not get_chat_member(f"@{ch['username']}", user_id):
                missing.append(ch)
        for gr in MANDATORY_GROUPS:
            if not get_chat_member(f"@{gr['username']}", user_id):
                missing.append(gr)
        return missing

    def enforce_channels(self, user_id, lang):
        """Kanal zorunluluğunu uygula, eksikse mesaj gönder. True = tamam"""
        missing = self.check_all_channels(user_id)
        if not missing:
            return True
        ch_lines = "\n".join([f"{c['emoji']} {c['name']}" for c in MANDATORY_CHANNELS])
        gr_lines = "\n".join([f"{g['emoji']} {g['name']}" for g in MANDATORY_GROUPS])
        text = t(lang, 'join_channels', channels=ch_lines, groups=gr_lines)
        # Butonlar
        buttons = []
        for c in MANDATORY_CHANNELS:
            buttons.append([{'text': f"{c['emoji']} {c['name']}", 'url': c['link']}])
        for g in MANDATORY_GROUPS:
            buttons.append([{'text': f"{g['emoji']} {g['name']}", 'url': g['link']}])
        buttons.append([{'text': t(lang, 'check_btn'), 'callback_data': 'check_channels'}])
        send_message(user_id, text, reply_markup={'inline_keyboard': buttons})
        return False

    def get_main_keyboard(self, lang, is_admin=False):
        tr_btn = {
            'tr': [
                [t(lang,'menu_balance'), t(lang,'menu_tasks')],
                [t(lang,'menu_withdraw'), t(lang,'menu_ref')],
                [t(lang,'menu_ads'), t(lang,'menu_profile')],
                [t(lang,'menu_settings'), t(lang,'menu_help')],
            ],
            'en': [
                [t(lang,'menu_balance'), t(lang,'menu_tasks')],
                [t(lang,'menu_withdraw'), t(lang,'menu_ref')],
                [t(lang,'menu_ads'), t(lang,'menu_profile')],
                [t(lang,'menu_settings'), t(lang,'menu_help')],
            ],
            'pt_br': [
                [t(lang,'menu_balance'), t(lang,'menu_tasks')],
                [t(lang,'menu_withdraw'), t(lang,'menu_ref')],
                [t(lang,'menu_ads'), t(lang,'menu_profile')],
                [t(lang,'menu_settings'), t(lang,'menu_help')],
            ],
        }
        rows = tr_btn.get(lang, tr_btn['en'])
        if is_admin:
            rows.append([t(lang, 'menu_admin')])
        return {'keyboard': rows, 'resize_keyboard': True, 'one_time_keyboard': False}

    def show_language_selection(self, user_id):
        text = "🌍 *DİL / LANGUAGE / IDIOMA*\n\nLütfen dilinizi seçin / Please select your language / Por favor selecione seu idioma:"
        keyboard = {
            'inline_keyboard': [
                [{'text': '🇹🇷 Türkçe', 'callback_data': 'lang_tr'}],
                [{'text': '🇺🇸 English', 'callback_data': 'lang_en'}],
                [{'text': '🇧🇷 Português (Brasil)', 'callback_data': 'lang_pt_br'}],
            ]
        }
        send_message(user_id, text, reply_markup=keyboard)

    def show_main_menu(self, user_id, lang='tr'):
        user = self.db.get_user(user_id)
        if not user:
            return
        if not self.enforce_channels(user_id, lang):
            return

        stars = "⭐" * min(5, max(1, int(user['total_referrals'] / 5) + 1))
        menus = {
            'tr': f"""
╔══════════════════════╗
║  🚀 *{BOT_NAME}*  ║
╚══════════════════════╝

👋 Hoş geldin, *{user['first_name']}*! {stars}

┌─────────────────────
│ 💎 Bakiye:  `{user['balance']:.4f} TON`
│ 🎯 Görevler: `{user['tasks_completed']}`
│ 👥 Referans: `{user['total_referrals']}`
│ 📈 Kazanç:  `{user['total_earned']:.4f} TON`
└─────────────────────

💡 *Görev tamamla → TON kazan!*
🔗 *Arkadaşını davet et → +{REF_WELCOME_BONUS} TON!*
""",
            'en': f"""
╔══════════════════════╗
║  🚀 *{BOT_NAME}*  ║
╚══════════════════════╝

👋 Welcome, *{user['first_name']}*! {stars}

┌─────────────────────
│ 💎 Balance:  `{user['balance']:.4f} TON`
│ 🎯 Tasks:    `{user['tasks_completed']}`
│ 👥 Referrals:`{user['total_referrals']}`
│ 📈 Earned:  `{user['total_earned']:.4f} TON`
└─────────────────────

💡 *Complete tasks → Earn TON!*
🔗 *Invite friends → +{REF_WELCOME_BONUS} TON each!*
""",
            'pt_br': f"""
╔══════════════════════╗
║  🚀 *{BOT_NAME}*  ║
╚══════════════════════╝

👋 Bem-vindo, *{user['first_name']}*! {stars}

┌─────────────────────
│ 💎 Saldo:   `{user['balance']:.4f} TON`
│ 🎯 Tarefas: `{user['tasks_completed']}`
│ 👥 Indicações:`{user['total_referrals']}`
│ 📈 Ganhos: `{user['total_earned']:.4f} TON`
└─────────────────────

💡 *Conclua tarefas → Ganhe TON!*
🔗 *Convide amigos → +{REF_WELCOME_BONUS} TON cada!*
""",
        }
        text = menus.get(lang, menus['en'])
        keyboard = self.get_main_keyboard(lang, str(user_id) in ADMIN_IDS)
        send_message(user_id, text, reply_markup=keyboard)

    def show_tasks(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        if not self.enforce_channels(user_id, lang):
            return
        tasks = self.db.get_active_tasks(user_id)
        if not tasks:
            send_message(user_id, t(lang, 'no_tasks'),
                         reply_markup={'inline_keyboard': [[{'text': '🔄 Yenile', 'callback_data': 'refresh_tasks'}],
                                                          [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]]})
            return
        type_icons = {'channel_join': '📢', 'group_join': '👥', 'bot_start': '🤖', 'post': '📝', 'general': '🎯'}
        text = t(lang, 'tasks_title', count=len(tasks)) + "\n\n"
        buttons = []
        for task in tasks[:12]:
            icon = type_icons.get(task['task_type'], '🎯')
            buttons.append([{'text': f"{icon} {task['title']} — {task['reward']:.4f} TON ({task['current_participants']}/{task['max_participants']})",
                             'callback_data': f'task_{task["id"]}'}])
        buttons.append([{'text': '🔄 Yenile', 'callback_data': 'refresh_tasks'}, {'text': '🏠 Menü', 'callback_data': 'main_menu'}])
        send_message(user_id, text + "👇 Görev seç:", reply_markup={'inline_keyboard': buttons})

    def show_task_detail(self, user_id, task_id, callback_id=None):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        self.db.cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        task = self.db.cursor.fetchone()
        if not task:
            if callback_id:
                answer_callback_query(callback_id, "❌ Görev bulunamadı")
            return
        task = dict(task)
        type_labels = {
            'tr': {'channel_join': 'Kanal Katılım', 'group_join': 'Grup Katılım', 'bot_start': 'Bot Başlat', 'post': 'Post Görevi', 'general': 'Genel Görev'},
            'en': {'channel_join': 'Channel Join', 'group_join': 'Group Join', 'bot_start': 'Start Bot', 'post': 'Post Task', 'general': 'General Task'},
            'pt_br': {'channel_join': 'Entrar no Canal', 'group_join': 'Entrar no Grupo', 'bot_start': 'Iniciar Bot', 'post': 'Tarefa Post', 'general': 'Tarefa Geral'},
        }
        type_label = type_labels.get(lang, type_labels['en']).get(task['task_type'], task['task_type'])
        texts = {
            'tr': f"🎯 *{task['title']}*\n\n📝 {task['description']}\n\n💎 Ödül: `{task['reward']:.4f} TON`\n🏷️ Tür: {type_label}\n👥 Katılım: {task['current_participants']}/{task['max_participants']}\n🔗 Link: {task.get('task_link','—')}",
            'en': f"🎯 *{task['title']}*\n\n📝 {task['description']}\n\n💎 Reward: `{task['reward']:.4f} TON`\n🏷️ Type: {type_label}\n👥 Participants: {task['current_participants']}/{task['max_participants']}\n🔗 Link: {task.get('task_link','—')}",
            'pt_br': f"🎯 *{task['title']}*\n\n📝 {task['description']}\n\n💎 Recompensa: `{task['reward']:.4f} TON`\n🏷️ Tipo: {type_label}\n👥 Participantes: {task['current_participants']}/{task['max_participants']}\n🔗 Link: {task.get('task_link','—')}",
        }
        text = texts.get(lang, texts['en'])
        btn_labels = {'tr': ('✅ Tamamladım', '🔙 Geri', '🏠 Menü'),
                      'en': ('✅ Done', '🔙 Back', '🏠 Menu'),
                      'pt_br': ('✅ Concluída', '🔙 Voltar', '🏠 Menu')}
        labels = btn_labels.get(lang, btn_labels['en'])
        keyboard = {'inline_keyboard': []}
        if task.get('task_link') and task['task_link'] not in ('', '—'):
            keyboard['inline_keyboard'].append([{'text': '🔗 Görevi Aç / Open Task', 'url': task['task_link']}])
        keyboard['inline_keyboard'].extend([
            [{'text': labels[0], 'callback_data': f'complete_task_{task_id}'}],
            [{'text': labels[1], 'callback_data': 'show_tasks'}, {'text': labels[2], 'callback_data': 'main_menu'}]
        ])
        if callback_id:
            answer_callback_query(callback_id)
        send_message(user_id, text, reply_markup=keyboard)

    def join_task(self, user_id, task_id, callback_id=None):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        reward = self.db.complete_task(user_id, task_id)
        if reward is None:
            if callback_id:
                answer_callback_query(callback_id, t(lang, 'task_already'), True)
            return
        if callback_id:
            answer_callback_query(callback_id, t(lang, 'task_done', reward=f'{reward:.4f}'), True)
        send_message(user_id, t(lang, 'task_done', reward=f'{reward:.4f}'),
                     reply_markup={'inline_keyboard': [
                         [{'text': '🎯 Daha Fazla Görev', 'callback_data': 'show_tasks'}],
                         [{'text': '💰 Bakiye', 'callback_data': 'show_balance'}]
                     ]})

    def show_balance(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        title = t(lang, 'balance_title') + "\n\n"
        body = t(lang, 'balance_text',
                 balance=f"{user['balance']:.4f}", earned=f"{user['total_earned']:.4f}",
                 tasks=user['tasks_completed'], refs=user['total_referrals'])
        btn_labels = {
            'tr':    ('💎 Para Çek', '🎯 Görevler', '👥 Davet Et', '🏠 Menü'),
            'en':    ('💎 Withdraw', '🎯 Tasks', '👥 Invite', '🏠 Menu'),
            'pt_br': ('💎 Sacar', '🎯 Tarefas', '👥 Convidar', '🏠 Menu'),
        }
        lb = btn_labels.get(lang, btn_labels['en'])
        keyboard = {'inline_keyboard': [
            [{'text': lb[0], 'callback_data': 'show_withdraw'}, {'text': lb[1], 'callback_data': 'show_tasks'}],
            [{'text': lb[2], 'callback_data': 'show_referral'}, {'text': lb[3], 'callback_data': 'main_menu'}],
        ]}
        send_message(user_id, title + body, reply_markup=keyboard)

    def show_withdraw(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        title = t(lang, 'withdraw_title') + "\n\n"
        body = t(lang, 'withdraw_text', balance=f"{user['balance']:.4f}", min_w=MIN_WITHDRAW)
        if user['balance'] < MIN_WITHDRAW:
            send_message(user_id,
                         title + t(lang, 'withdraw_low', min_w=MIN_WITHDRAW, balance=f"{user['balance']:.4f}"),
                         reply_markup={'inline_keyboard': [
                             [{'text': '🎯 Görev Yap', 'callback_data': 'show_tasks'}],
                             [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]
                         ]})
            return
        # İşlem başlat
        self.user_states[user_id] = {'action': 'wait_withdraw_amount'}
        keyboard = {'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel_action'}]]}
        send_message(user_id, title + body, reply_markup=keyboard)

    def show_referral(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user['referral_code']}"
        self.db.cursor.execute('SELECT COALESCE(SUM(earned_amount),0) FROM referrals WHERE referrer_id = ? AND status="active"', (user_id,))
        earned = self.db.cursor.fetchone()[0]
        title = t(lang, 'ref_title') + "\n\n"
        body = t(lang, 'ref_text', link=ref_link, bonus=REF_WELCOME_BONUS,
                 count=user['total_referrals'], earned=f"{earned:.4f}")
        share_texts = {
            'tr': f"🚀 {BOT_NAME} ile TON kazan! Link: {ref_link}",
            'en': f"🚀 Earn TON with {BOT_NAME}! Link: {ref_link}",
            'pt_br': f"🚀 Ganhe TON com {BOT_NAME}! Link: {ref_link}",
        }
        btn_labels = {'tr': '📤 Linki Paylaş', 'en': '📤 Share Link', 'pt_br': '📤 Compartilhar'}
        keyboard = {'inline_keyboard': [
            [{'text': btn_labels.get(lang, '📤 Share'), 'url': f"https://t.me/share/url?url={ref_link}&text={share_texts.get(lang,'')}"}],
            [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]
        ]}
        send_message(user_id, title + body, reply_markup=keyboard)

    def show_profile(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        lang_labels = {'tr': '🇹🇷 Türkçe', 'en': '🇺🇸 English', 'pt_br': '🇧🇷 Português'}
        date_str = user['created_at'][:10] if user['created_at'] else '—'
        title = t(lang, 'profile_title') + "\n\n"
        body = t(lang, 'profile_text',
                 name=user['first_name'], uid=user['user_id'],
                 lang=lang_labels.get(lang, lang),
                 balance=f"{user['balance']:.4f}", tasks=user['tasks_completed'],
                 refs=user['total_referrals'], date=date_str)
        btn_labels = {'tr': ('⚙️ Ayarlar', '🌍 Dil Değiştir', '🏠 Menü'),
                      'en': ('⚙️ Settings', '🌍 Change Language', '🏠 Menu'),
                      'pt_br': ('⚙️ Ajustes', '🌍 Mudar Idioma', '🏠 Menu')}
        lb = btn_labels.get(lang, btn_labels['en'])
        keyboard = {'inline_keyboard': [
            [{'text': lb[0], 'callback_data': 'show_settings'}],
            [{'text': lb[1], 'callback_data': 'change_language'}],
            [{'text': lb[2], 'callback_data': 'main_menu'}],
        ]}
        send_message(user_id, title + body, reply_markup=keyboard)

    def show_settings(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        ton_addr = user.get('ton_address', '') or '—'
        texts = {
            'tr': f"⚙️ *AYARLAR*\n\n🏦 TON Adresin: `{ton_addr}`\n\nÇekim işlemlerinde kullanmak için TON adresinizi kaydedin.",
            'en': f"⚙️ *SETTINGS*\n\n🏦 Your TON Address: `{ton_addr}`\n\nSave your TON address for withdrawals.",
            'pt_br': f"⚙️ *AJUSTES*\n\n🏦 Seu Endereço TON: `{ton_addr}`\n\nSalve seu endereço TON para saques.",
        }
        btn_set = {'tr': '💳 TON Adres Kaydet', 'en': '💳 Save TON Address', 'pt_br': '💳 Salvar Endereço TON'}
        keyboard = {'inline_keyboard': [
            [{'text': btn_set.get(lang, btn_set['en']), 'callback_data': 'set_ton_address'}],
            [{'text': '🌍 Dil / Language', 'callback_data': 'change_language'}],
            [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]
        ]}
        send_message(user_id, texts.get(lang, texts['en']), reply_markup=keyboard)

    def show_ads_menu(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        texts = {
            'tr': "📢 *REKLAM MENÜSİ*\n\nPost görüntüleyerek veya reklam yayınlayarak TON kazan!",
            'en': "📢 *ADS MENU*\n\nEarn TON by viewing posts or running ads!",
            'pt_br': "📢 *MENU DE ANÚNCIOS*\n\nGanhe TON visualizando posts ou anunciando!",
        }
        keyboard = {'inline_keyboard': [
            [{'text': '👁️ Post Görüntüle / View Post', 'callback_data': 'view_post'}],
            [{'text': '📢 Reklam Oluştur / Create Ad', 'callback_data': 'start_ad'}],
            [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]
        ]}
        send_message(user_id, texts.get(lang, texts['en']), reply_markup=keyboard)

    def view_post(self, user_id, callback_id=None):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        ad = self.db.get_post_task(user_id)
        if not ad:
            msg = {'tr': "📭 Şu an görüntülenecek reklam yok.", 'en': "📭 No ads to view right now.", 'pt_br': "📭 Nenhum anúncio disponível."}
            if callback_id:
                answer_callback_query(callback_id, msg.get(lang, msg['en']), True)
            return
        ad_reward = round(ad['remaining_budget'] * 0.01, 5)  # %1'i kullanıcıya
        ad_reward = min(ad_reward, 0.001)
        if self.db.record_ad_view(ad['id'], user_id, ad_reward):
            success_msg = {'tr': f"✅ Reklam görüntülendi!\n💎 Ödül: `{ad_reward:.5f} TON`\n\n📝 {ad['ad_text']}\n🔗 {ad['link_url']}",
                           'en': f"✅ Ad viewed!\n💎 Reward: `{ad_reward:.5f} TON`\n\n📝 {ad['ad_text']}\n🔗 {ad['link_url']}",
                           'pt_br': f"✅ Anúncio visualizado!\n💎 Recompensa: `{ad_reward:.5f} TON`\n\n📝 {ad['ad_text']}\n🔗 {ad['link_url']}"}
            if callback_id:
                answer_callback_query(callback_id, "✅ +TON", True)
            send_message(user_id, success_msg.get(lang, success_msg['en']),
                         reply_markup={'inline_keyboard': [
                             [{'text': '🌐 Siteyi Ziyaret Et', 'url': ad['link_url']}],
                             [{'text': '👁️ Başka Reklam', 'callback_data': 'view_post'}],
                             [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]
                         ]})
        else:
            if callback_id:
                answer_callback_query(callback_id, "❌ Bu reklamı zaten izlediniz", True)

    def show_help(self, user_id):
        user = self.db.get_user(user_id)
        if not user:
            return
        lang = user['language']
        texts = {
            'tr': f"""❓ *YARDIM ve DESTEK*

🤖 *Bot:* {BOT_NAME}
👤 *Destek:* {SUPPORT_USERNAME}

━━━━━━━━━━━━━━━
📚 *SSS:*

1️⃣ *Nasıl kazanırım?*
   Görevler bölümünden görev tamamlayın

2️⃣ *Para çekme şartı?*
   Min. {MIN_WITHDRAW} TON bakiye yeterli

3️⃣ *Referans bonusu?*
   Her aktif ref için: {REF_WELCOME_BONUS} TON
   ⚠️ Ref kanallara katılmalı!

4️⃣ *Çekim ne zaman?*
   Talep sonrası 24-48 saat

━━━━━━━━━━━━━━━
⚡ *Komutlar:*
/start - Ana menü
/tasks - Görevler
/balance - Bakiye
/withdraw - Çekim
/referral - Referans""",
            'en': f"""❓ *HELP & SUPPORT*

🤖 *Bot:* {BOT_NAME}
👤 *Support:* {SUPPORT_USERNAME}

━━━━━━━━━━━━━━━
📚 *FAQ:*

1️⃣ *How to earn?*
   Complete tasks from Tasks section

2️⃣ *Withdrawal condition?*
   Min. {MIN_WITHDRAW} TON balance required

3️⃣ *Referral bonus?*
   {REF_WELCOME_BONUS} TON per active referral
   ⚠️ Referrals must join channels!

4️⃣ *Withdrawal time?*
   24-48 hours after request

━━━━━━━━━━━━━━━
⚡ *Commands:*
/start - Main menu
/tasks - Tasks
/balance - Balance
/withdraw - Withdraw
/referral - Referrals""",
            'pt_br': f"""❓ *AJUDA e SUPORTE*

🤖 *Bot:* {BOT_NAME}
👤 *Suporte:* {SUPPORT_USERNAME}

━━━━━━━━━━━━━━━
📚 *FAQ:*

1️⃣ *Como ganhar?*
   Conclua tarefas na seção Tarefas

2️⃣ *Condição de saque?*
   Min. {MIN_WITHDRAW} TON de saldo

3️⃣ *Bônus de indicação?*
   {REF_WELCOME_BONUS} TON por indicação ativa
   ⚠️ Indicados devem entrar nos canais!

4️⃣ *Tempo de saque?*
   24-48 horas após solicitação

━━━━━━━━━━━━━━━
⚡ *Comandos:*
/start - Menu principal
/tasks - Tarefas
/balance - Saldo"""
        }
        keyboard = {'inline_keyboard': [
            [{'text': f'📞 {SUPPORT_USERNAME}', 'url': f'https://t.me/{SUPPORT_USERNAME[1:]}'}],
            [{'text': '📢 Kanal / Channel', 'url': f'https://t.me/{STATS_CHANNEL[1:]}'}],
            [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]
        ]}
        send_message(user_id, texts.get(lang, texts['en']), reply_markup=keyboard)

    # ─── ADMIN PANELİ ───────────────────────────────
    def show_admin_panel(self, admin_id):
        stats = self.db.admin_get_stats()
        text = f"""🛡️ *ADMIN PANEL — {BOT_NAME}*

━━━━━━━━━━━━━━━━
👥 Toplam Kullanıcı: `{stats['total_users']}`
🟢 Aktif (24h): `{stats['active_users']}`
🆕 Yeni (24h): `{stats['new_users']}`
━━━━━━━━━━━━━━━━
💎 Toplam Bakiye: `{stats['total_balance']:.4f} TON`
📥 Bekleyen Çekim: `{stats['pending_withdrawals']}`
✅ Ödenen: `{stats['total_paid']:.4f} TON`
🎯 Toplam Görev: `{stats['total_tasks']}`
━━━━━━━━━━━━━━━━

📌 *Komutlar:*
`/addbalance <id> <miktar> [sebep]`
`/removebalance <id> <miktar>`
`/createtask <başlık>|<açıklama>|<ödül>|<max>|<tür>|<link>`
`/broadcast <mesaj>`
`/ban <user_id>`
`/unban <user_id>`
`/getuser <id_veya_username>`
"""
        keyboard = {'inline_keyboard': [
            [{'text': '📊 İstatistik', 'callback_data': 'admin_stats'},
             {'text': '📥 Çekimler', 'callback_data': 'admin_withdrawals'}],
            [{'text': '👥 Kullanıcılar', 'callback_data': 'admin_users'},
             {'text': '🎯 Görevler', 'callback_data': 'admin_tasks'}],
            [{'text': '🔄 Yenile', 'callback_data': 'admin_refresh'}],
        ]}
        send_message(admin_id, text, reply_markup=keyboard)

    def handle_admin_callback(self, admin_id, data, callback_id, cq):
        if data == 'admin_refresh':
            answer_callback_query(callback_id, "🔄 Yenilendi")
            self.show_admin_panel(admin_id)
        elif data == 'admin_stats':
            stats = self.db.admin_get_stats()
            text = f"📊 *İSTATİSTİKLER*\n\n👥 Toplam: `{stats['total_users']}`\n🟢 Aktif: `{stats['active_users']}`\n🆕 Yeni (24h): `{stats['new_users']}`\n💎 Bakiye: `{stats['total_balance']:.4f} TON`\n📥 Bekleyen: `{stats['pending_withdrawals']}`\n✅ Ödenen: `{stats['total_paid']:.4f} TON`"
            send_message(admin_id, text, reply_markup={'inline_keyboard': [[{'text': '🔙 Geri', 'callback_data': 'admin_refresh'}]]})
            answer_callback_query(callback_id)
        elif data == 'admin_withdrawals':
            pending = self.db.get_pending_withdrawals()
            if not pending:
                answer_callback_query(callback_id, "✅ Bekleyen çekim yok", True)
                return
            for w in pending[:5]:
                text = f"📥 *ÇEKİM #{w['id']}*\n👤 {w['first_name']} (`{w['user_id']}`)\n💎 {w['amount']:.4f} TON\n🏦 `{w['ton_address']}`\n📅 {w['created_at'][:16]}"
                kb = {'inline_keyboard': [
                    [{'text': '✅ Onayla', 'callback_data': f'admin_approve_w_{w["id"]}'},
                     {'text': '❌ Reddet', 'callback_data': f'admin_reject_w_{w["id"]}'}]
                ]}
                send_message(admin_id, text, reply_markup=kb)
            answer_callback_query(callback_id)
        elif data.startswith('admin_approve_w_'):
            wid = int(data.split('_')[-1])
            self.db.approve_withdrawal(wid, admin_id)
            answer_callback_query(callback_id, "✅ Çekim onaylandı", True)
            # Kullanıcıya bildirim
            self.db.cursor.execute('SELECT * FROM withdrawals WHERE id = ?', (wid,))
            w = self.db.cursor.fetchone()
            if w:
                w = dict(w)
                for lng in ['tr', 'en', 'pt_br']:
                    send_message(w['user_id'], f"✅ *Çekim Onaylandı!*\n💎 `{w['amount']:.4f} TON` gönderildi!\n🏦 Adres: `{w['ton_address']}`")
                    break
        elif data.startswith('admin_reject_w_'):
            wid = int(data.split('_')[-1])
            self.db.reject_withdrawal(wid, admin_id, "Admin tarafından reddedildi")
            answer_callback_query(callback_id, "❌ Çekim reddedildi", True)
        elif data == 'admin_tasks':
            tasks = self.db.get_all_tasks()
            text = f"🎯 *GÖREVLER* ({len(tasks)})\n\n"
            for task in tasks[:8]:
                status_icon = '🟢' if task['status'] == 'active' else '🔴'
                text += f"{status_icon} #{task['id']} {task['title']} — {task['reward']:.4f} TON ({task['current_participants']}/{task['max_participants']})\n"
            send_message(admin_id, text, reply_markup={'inline_keyboard': [[{'text': '🔙 Geri', 'callback_data': 'admin_refresh'}]]})
            answer_callback_query(callback_id)
        elif data == 'admin_users':
            self.db.cursor.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 10')
            users = [dict(r) for r in self.db.cursor.fetchall()]
            text = "👥 *SON KULLANICILAR*\n\n"
            for u in users:
                text += f"👤 {u['first_name']} (`{u['user_id']}`) — {u['balance']:.4f} TON\n"
            send_message(admin_id, text, reply_markup={'inline_keyboard': [[{'text': '🔙 Geri', 'callback_data': 'admin_refresh'}]]})
            answer_callback_query(callback_id)
        else:
            answer_callback_query(callback_id, "ℹ️ İşlem tamamlandı")

    def handle_admin_message(self, user_id, text):
        parts = text.split(None, 1)
        cmd = parts[0].lower()

        if cmd == '/addbalance':
            try:
                args = parts[1].split()
                target_id = int(args[0])
                amount = float(args[1])
                reason = ' '.join(args[2:]) if len(args) > 2 else "Admin"
                if self.db.admin_add_balance(target_id, amount, user_id, reason):
                    send_message(user_id, f"✅ `{target_id}` kullanıcısına `{amount} TON` eklendi!")
                    send_message(target_id, f"💎 Hesabınıza `{amount} TON` eklendi!\nSebep: {reason}")
                else:
                    send_message(user_id, "❌ Kullanıcı bulunamadı!")
            except Exception as e:
                send_message(user_id, f"❌ Hata: {e}\nKullanım: /addbalance <user_id> <miktar> [sebep]")

        elif cmd == '/removebalance':
            try:
                args = parts[1].split()
                target_id = int(args[0])
                amount = float(args[1])
                self.db.admin_remove_balance(target_id, amount, user_id)
                send_message(user_id, f"✅ `{target_id}` kullanıcısından `{amount} TON` çıkarıldı!")
            except Exception as e:
                send_message(user_id, f"❌ Hata: {e}")

        elif cmd == '/createtask':
            try:
                # Format: /createtask başlık|açıklama|ödül|max|tür|link
                data = parts[1].split('|')
                title, desc, reward, max_p, ttype, link = data[0], data[1], float(data[2]), int(data[3]), data[4], data[5] if len(data) > 5 else ''
                self.db.cursor.execute(
                    'INSERT INTO tasks (title, description, reward, max_participants, task_type, task_link, created_by) VALUES (?,?,?,?,?,?,?)',
                    (title.strip(), desc.strip(), reward, max_p, ttype.strip(), link.strip(), user_id)
                )
                self.db.connection.commit()
                send_message(user_id, f"✅ Görev oluşturuldu!\n🎯 {title}\n💎 {reward} TON\n👥 Max: {max_p}")
            except Exception as e:
                send_message(user_id, f"❌ Hata: {e}\nFormat: /createtask başlık|açıklama|ödül|max|tür|link")

        elif cmd == '/broadcast':
            msg = parts[1] if len(parts) > 1 else ""
            if not msg:
                send_message(user_id, "❌ Mesaj gerekli!")
                return
            self.db.cursor.execute("SELECT user_id FROM users WHERE status='active'")
            users = [r[0] for r in self.db.cursor.fetchall()]
            sent = 0
            for uid in users:
                try:
                    send_message(uid, f"📢 *DUYURU*\n\n{msg}")
                    sent += 1
                    time.sleep(0.05)
                except:
                    pass
            send_message(user_id, f"✅ Yayın tamamlandı! {sent}/{len(users)} gönderildi.")

        elif cmd == '/ban':
            try:
                target_id = int(parts[1].strip())
                self.db.admin_ban_user(target_id, user_id)
                send_message(user_id, f"✅ `{target_id}` yasaklandı!")
            except Exception as e:
                send_message(user_id, f"❌ Hata: {e}")

        elif cmd == '/unban':
            try:
                target_id = int(parts[1].strip())
                self.db.admin_unban_user(target_id, user_id)
                send_message(user_id, f"✅ `{target_id}` yasağı kaldırıldı!")
            except Exception as e:
                send_message(user_id, f"❌ Hata: {e}")

        elif cmd == '/getuser':
            term = parts[1].strip() if len(parts) > 1 else ""
            u = self.db.search_user(term)
            if u:
                send_message(user_id, f"👤 *KULLANICI*\n\nID: `{u['user_id']}`\nAd: {u['first_name']}\nUsername: @{u.get('username','—')}\nDil: {u['language']}\n💎 Bakiye: `{u['balance']:.4f} TON`\nDurum: {u['status']}")
            else:
                send_message(user_id, "❌ Kullanıcı bulunamadı!")
        else:
            self.show_admin_panel(user_id)

    # ─── UPDATE HANDLER ──────────────────────────────
    def handle_update(self, update):
        try:
            if 'message' in update:
                self.handle_message(update['message'])
            elif 'callback_query' in update:
                self.handle_callback_query(update['callback_query'])
        except Exception as e:
            print(f"handle_update hatası: {e}")

    def handle_message(self, message):
        user_id = message['from']['id']
        text = message.get('text', '')

        if not text:
            # Fotoğraf vs - reklam poster için
            if user_id in self.user_states and self.user_states[user_id].get('action') == 'wait_ad_poster':
                photos = message.get('photo', [])
                if photos:
                    file_id = photos[-1]['file_id']
                    self.user_states[user_id]['poster'] = file_id
                    self.user_states[user_id]['action'] = 'wait_ad_link'
                    send_message(user_id, "🔗 Reklam linkini gönder:")
            return

        # Banlı kontrolü
        user = self.db.get_user(user_id)
        if user and user.get('status') == 'banned':
            send_message(user_id, "🚫 Hesabınız askıya alınmıştır.")
            return

        # Admin komutları
        if str(user_id) in ADMIN_IDS and text.startswith('/') and text != '/start':
            if not user:
                user = self.db.create_user(user_id,
                    message['from'].get('username', ''),
                    message['from'].get('first_name', ''),
                    message['from'].get('last_name', ''), 'tr')
            self.handle_admin_message(user_id, text)
            return

        # Yeni kullanıcı
        referred_by = None
        if text.startswith('/start'):
            parts = text.split()
            if len(parts) > 1:
                ref_code = parts[1]
                self.db.cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (ref_code,))
                row = self.db.cursor.fetchone()
                if row and row[0] != user_id:
                    referred_by = row[0]

        if not user:
            username   = message['from'].get('username', '')
            first_name = message['from'].get('first_name', '')
            last_name  = message['from'].get('last_name', '')
            user = self.db.create_user(user_id, username, first_name, last_name, 'tr', referred_by)
            try:
                send_message(STATS_CHANNEL, f"👤 *YENİ ÜYE*\n{first_name} (`{user_id}`)\nRef: {referred_by or '—'}")
            except:
                pass
            self.show_language_selection(user_id)
            return

        self.db.update_last_active(user_id)

        # Duruma göre işle
        if user_id in self.user_states:
            self.handle_state(user_id, text, user)
            return

        # Admin panel komutu
        if str(user_id) in ADMIN_IDS and text == '/admin':
            self.show_admin_panel(user_id)
            return

        self.process_command(user_id, text, user)

    def handle_state(self, user_id, text, user):
        state = self.user_states.get(user_id, {})
        action = state.get('action', '')
        lang = user['language']

        if action == 'wait_withdraw_amount':
            try:
                amount = float(text.replace(',', '.'))
                if amount < MIN_WITHDRAW:
                    send_message(user_id, t(lang, 'withdraw_low', min_w=MIN_WITHDRAW, balance=f"{user['balance']:.4f}"))
                    return
                if amount > user['balance']:
                    send_message(user_id, t(lang, 'withdraw_low', min_w=MIN_WITHDRAW, balance=f"{user['balance']:.4f}"))
                    return
                self.user_states[user_id] = {'action': 'wait_withdraw_address', 'amount': amount}
                send_message(user_id, t(lang, 'enter_address'),
                             reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel_action'}]]})
            except ValueError:
                send_message(user_id, t(lang, 'invalid_amount'))

        elif action == 'wait_withdraw_address':
            amount = state.get('amount', 0)
            address = text.strip()
            if len(address) < 10:
                send_message(user_id, "❌ Geçersiz TON adresi!")
                return
            wid = self.db.create_withdrawal(user_id, amount, address)
            if wid:
                send_message(user_id, t(lang, 'withdraw_ok', amount=f"{amount:.4f}", address=address),
                             reply_markup={'inline_keyboard': [[{'text': '🏠 Menü', 'callback_data': 'main_menu'}]]})
                try:
                    send_message(STATS_CHANNEL, f"💎 *YENİ ÇEKİM #{wid}*\n👤 {user['first_name']} (`{user_id}`)\n💎 {amount:.4f} TON\n🏦 `{address}`")
                except:
                    pass
                # Admin bildirimi
                for aid in ADMIN_IDS:
                    send_message(int(aid), f"📥 *Yeni Çekim Talebi #{wid}*\n👤 {user['first_name']} (`{user_id}`)\n💎 {amount:.4f} TON\n🏦 `{address}`\n\nOnaylamak için /admin",
                                 reply_markup={'inline_keyboard': [
                                     [{'text': '✅ Onayla', 'callback_data': f'admin_approve_w_{wid}'},
                                      {'text': '❌ Reddet', 'callback_data': f'admin_reject_w_{wid}'}]
                                 ]})
            del self.user_states[user_id]

        elif action == 'wait_ton_address':
            address = text.strip()
            if len(address) < 10:
                send_message(user_id, "❌ Geçersiz adres!")
                return
            self.db.set_ton_address(user_id, address)
            send_message(user_id, t(lang, 'ton_address_set'))
            del self.user_states[user_id]
            self.show_settings(user_id)

        elif action == 'wait_ad_link':
            self.user_states[user_id]['link_url'] = text.strip()
            self.user_states[user_id]['action'] = 'wait_ad_text'
            send_message(user_id, "📝 Reklam metnini gönder:")

        elif action == 'wait_ad_text':
            self.user_states[user_id]['ad_text'] = text.strip()
            self.user_states[user_id]['action'] = 'wait_ad_budget'
            send_message(user_id, "💰 Reklam bütçesi (TON):")

        elif action == 'wait_ad_budget':
            try:
                budget = float(text)
                if budget <= 0:
                    raise ValueError
                fresh_user = self.db.get_user(user_id)
                if fresh_user['balance'] < budget:
                    send_message(user_id, "❌ Yetersiz bakiye!")
                    return
                poster = state.get('poster', '')
                link_url = state.get('link_url', '')
                ad_text = state.get('ad_text', '')
                self.db.cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (budget, user_id))
                ad_id = self.db.create_ad(user_id, poster, link_url, ad_text, budget)
                self.db.connection.commit()
                send_message(user_id, f"✅ Reklam oluşturuldu! #ID: {ad_id}\n💰 Bütçe: {budget} TON")
                del self.user_states[user_id]
            except ValueError:
                send_message(user_id, "❌ Geçersiz miktar!")

    def process_command(self, user_id, text, user):
        lang = user['language']
        # Menü butonları için çok dilli eşleştirme
        balance_btns = [t(l, 'menu_balance') for l in TEXTS]
        tasks_btns   = [t(l, 'menu_tasks') for l in TEXTS]
        ref_btns     = [t(l, 'menu_ref') for l in TEXTS]
        wd_btns      = [t(l, 'menu_withdraw') for l in TEXTS]
        prof_btns    = [t(l, 'menu_profile') for l in TEXTS]
        ads_btns     = [t(l, 'menu_ads') for l in TEXTS]
        help_btns    = [t(l, 'menu_help') for l in TEXTS]
        set_btns     = [t(l, 'menu_settings') for l in TEXTS]
        adm_btns     = [t(l, 'menu_admin') for l in TEXTS]

        if text == '/start':
            self.show_main_menu(user_id, lang)
        elif text in ['/tasks'] + tasks_btns:
            self.show_tasks(user_id)
        elif text in ['/balance'] + balance_btns:
            self.show_balance(user_id)
        elif text in ['/withdraw'] + wd_btns:
            self.show_withdraw(user_id)
        elif text in ['/referral', '/ref'] + ref_btns:
            self.show_referral(user_id)
        elif text in ['/profile'] + prof_btns:
            self.show_profile(user_id)
        elif text in ['/ads'] + ads_btns:
            self.show_ads_menu(user_id)
        elif text in ['/help'] + help_btns:
            self.show_help(user_id)
        elif text in ['/settings'] + set_btns:
            self.show_settings(user_id)
        elif text in adm_btns and str(user_id) in ADMIN_IDS:
            self.show_admin_panel(user_id)
        else:
            self.show_main_menu(user_id, lang)

    def handle_callback_query(self, cq):
        user_id    = cq['from']['id']
        data       = cq.get('data', '')
        callback_id = cq['id']

        # Banlı kontrolü
        user = self.db.get_user(user_id)
        if user and user.get('status') == 'banned':
            answer_callback_query(callback_id, "🚫 Hesabınız askıya alınmıştır.", True)
            return

        try:
            # Admin
            if str(user_id) in ADMIN_IDS and data.startswith('admin_'):
                self.handle_admin_callback(user_id, data, callback_id, cq)
                return

            if data.startswith('lang_'):
                lang = data[5:]  # lang_tr -> tr, lang_pt_br -> pt_br
                if lang in SUPPORTED_LANGUAGES:
                    self.db.cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (lang, user_id))
                    self.db.connection.commit()
                    answer_callback_query(callback_id, "✅ Dil seçildi!")
                    # Ref kanallarını kontrol et ve referansı aktifleştir
                    fresh_user = self.db.get_user(user_id)
                    if fresh_user and fresh_user.get('referred_by'):
                        missing = self.check_all_channels(user_id)
                        if not missing:
                            ref_owner = self.db.activate_referral(user_id)
                            if ref_owner:
                                try:
                                    ref_owner_user = self.db.get_user(ref_owner)
                                    if ref_owner_user:
                                        rlang = ref_owner_user['language']
                                        send_message(ref_owner, f"🎉 *Yeni Aktif Referans!*\n💎 +`{REF_WELCOME_BONUS} TON` bakiyenize eklendi!")
                                except:
                                    pass
                    self.show_main_menu(user_id, lang)
                else:
                    answer_callback_query(callback_id, "❌ Desteklenmeyen dil")

            elif data == 'check_channels':
                fresh_user = self.db.get_user(user_id)
                if not fresh_user:
                    return
                missing = self.check_all_channels(user_id)
                if missing:
                    names = ", ".join([m['name'] for m in missing])
                    answer_callback_query(callback_id, t(fresh_user['language'], 'not_joined', missing=names), True)
                else:
                    answer_callback_query(callback_id, "✅ Tebrikler! Tüm kanallara katıldınız!")
                    # Referansı aktifleştir
                    if fresh_user.get('referred_by'):
                        ref_owner = self.db.activate_referral(user_id)
                        if ref_owner:
                            try:
                                send_message(ref_owner, f"🎉 *Yeni Aktif Referans!*\n💎 +`{REF_WELCOME_BONUS} TON` eklendi!")
                            except:
                                pass
                    self.show_main_menu(user_id, fresh_user['language'])

            elif data == 'main_menu':
                fresh_user = self.db.get_user(user_id)
                if fresh_user:
                    self.show_main_menu(user_id, fresh_user['language'])

            elif data == 'show_tasks':
                self.show_tasks(user_id)
            elif data == 'show_balance':
                self.show_balance(user_id)
            elif data == 'show_withdraw':
                fresh_user = self.db.get_user(user_id)
                if fresh_user:
                    self.show_withdraw(user_id)
            elif data == 'show_referral':
                self.show_referral(user_id)
            elif data == 'show_profile':
                self.show_profile(user_id)
            elif data == 'show_settings':
                self.show_settings(user_id)
            elif data == 'show_ads':
                self.show_ads_menu(user_id)
            elif data == 'change_language':
                self.show_language_selection(user_id)
            elif data == 'refresh_tasks':
                self.show_tasks(user_id)
                answer_callback_query(callback_id, "🔄 Yenilendi!")
            elif data.startswith('task_'):
                task_id = int(data[5:])
                self.show_task_detail(user_id, task_id, callback_id)
            elif data.startswith('complete_task_'):
                task_id = int(data[14:])
                self.join_task(user_id, task_id, callback_id)
            elif data == 'view_post':
                self.view_post(user_id, callback_id)
            elif data == 'start_ad':
                fresh_user = self.db.get_user(user_id)
                if fresh_user:
                    self.user_states[user_id] = {'action': 'wait_ad_poster'}
                    answer_callback_query(callback_id)
                    send_message(user_id, "🖼️ Reklam poster URL veya resim gönder:",
                                 reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel_action'}]]})
            elif data == 'set_ton_address':
                fresh_user = self.db.get_user(user_id)
                if fresh_user:
                    self.user_states[user_id] = {'action': 'wait_ton_address'}
                    answer_callback_query(callback_id)
                    send_message(user_id, "🏦 TON adresinizi girin:",
                                 reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel_action'}]]})
            elif data == 'cancel_action':
                if user_id in self.user_states:
                    del self.user_states[user_id]
                answer_callback_query(callback_id, "❌ İptal edildi")
                fresh_user = self.db.get_user(user_id)
                if fresh_user:
                    self.show_main_menu(user_id, fresh_user['language'])
            else:
                answer_callback_query(callback_id)

        except Exception as e:
            print(f"callback hatası: {e}")
            answer_callback_query(callback_id, "❌ Bir hata oluştu")


# ═══════════════════════════════════════
#         ÇALIŞMA FONKSİYONLARI
# ═══════════════════════════════════════
def run_polling():
    bot = TaskizBot()
    offset = None
    print("🔄 Polling başlatıldı...")
    while True:
        try:
            updates = get_updates(offset=offset, timeout=30)
            for update in updates:
                uid = update.get('update_id')
                if uid is not None:
                    offset = uid + 1
                threading.Thread(target=bot.handle_update, args=(update,), daemon=True).start()
        except Exception as e:
            print(f"Polling hatası: {e}")
            time.sleep(5)

def run_web():
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    polling_thread = threading.Thread(target=run_polling, daemon=True)
    polling_thread.start()
    run_web()
