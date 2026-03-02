import os
import time
import json
import requests
from datetime import datetime
import threading
import sqlite3
from flask import Flask, jsonify
import uuid
import random

# Firebase için (opsiyonel)
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("⚠️ Firebase modülü yok, sadece SQLite kullanılacak")

# ════════════════════════════════════════════
#              TEMEL AYARLAR
# ════════════════════════════════════════════
TOKEN            = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS        = os.environ.get("ADMIN_ID", "7904032877").split(",")
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "@AlperenTHE")
STATS_CHANNEL    = os.environ.get("STATS_CHANNEL", "@TaskizLive")
BOT_USERNAME     = os.environ.get("BOT_USERNAME", "TaskizBot")
BOT_NAME         = os.environ.get("BOT_NAME", "TaskizBot")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN gerekli!")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Firebase varsa al
FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
FIREBASE_PROJECT_ID       = os.environ.get("FIREBASE_PROJECT_ID", "taskiz-2db5a")
FIREBASE_DATABASE_URL     = os.environ.get("FIREBASE_DATABASE_URL", "")

# ════════════════════════════════════════════
#              SİSTEM AYARLARI
# ════════════════════════════════════════════
MIN_WITHDRAW        = 0.05   # TON
REF_WELCOME_BONUS   = 0.005  # TON
REF_TASK_COMMISSION = 0.25   # 25%
TASK_BUDGET_MULTIPLIER = 1.5  # Kullanıcının ödediği bütçe, dağıtılan toplam ödülün 1.5 katı

# Görev oluşturma bütçe seçenekleri
TASK_BUDGET_OPTIONS = [0.1, 0.25, 0.5, 1.0, 2.0, 5.0]

# Görev türüne göre katılımcı başı ödül
TASK_REWARDS = {
    'channel_join': 0.0025,
    'group_join':   0.0025,
    'bot_start':    0.001,
}

# Desteklenen diller
SUPPORTED_LANGUAGES = {
    'tr':    {'name': 'Türkçe',             'flag': '🇹🇷'},
    'en':    {'name': 'English',            'flag': '🇺🇸'},
    'pt_br': {'name': 'Português (Brasil)', 'flag': '🇧🇷'},
}

# ════════════════════════════════════════════
#              FLASK (healthcheck)
# ════════════════════════════════════════════
app = Flask(__name__)

@app.route("/", methods=["GET"])
def healthcheck():
    return jsonify({"status": "ok", "bot": BOT_NAME, "time": datetime.now().isoformat()})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "alive"})

# ════════════════════════════════════════════
#           TELEGRAM API
# ════════════════════════════════════════════
def _post(method, payload, timeout=15):
    try:
        r = requests.post(BASE_URL + method, json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        print(f"❌ API {method} hatası: {e}")
        return None

def send_message(chat_id, text, reply_markup=None, parse_mode='Markdown'):
    p = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode, 'disable_web_page_preview': True}
    if reply_markup:
        p['reply_markup'] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup
    return _post("sendMessage", p)

def copy_message(chat_id, from_chat_id, message_id):
    p = {'chat_id': chat_id, 'from_chat_id': from_chat_id, 'message_id': message_id}
    return _post("copyMessage", p)

def answer_callback(cb_id, text=None, alert=False):
    p = {'callback_query_id': cb_id}
    if text:
        p['text'] = text
    if alert:
        p['show_alert'] = True
    _post("answerCallbackQuery", p, timeout=5)

def get_chat_member(chat_id, user_id):
    try:
        r = requests.post(BASE_URL + "getChatMember",
                          json={"chat_id": chat_id, "user_id": user_id},
                          timeout=8)
        data = r.json()
        if not data.get("ok"):
            return False
        status = data["result"]["status"]
        return status not in ("left", "kicked")
    except Exception as e:
        print(f"getChatMember hatası: {e}")
        return False

def get_updates(offset=None, timeout=30):
    params = {'timeout': timeout}
    if offset is not None:
        params['offset'] = offset
    try:
        r = requests.get(BASE_URL + "getUpdates", params=params, timeout=timeout + 5)
        data = r.json()
        if data.get('ok'):
            return data.get('result', [])
    except Exception as e:
        print(f"getUpdates hatası: {e}")
    return []

# ════════════════════════════════════════════
#              VERİTABANI (SQLite)
# ════════════════════════════════════════════
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('taskiz.db', check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._lock = threading.Lock()
        self._setup()
        print("✅ Veritabanı hazır (SQLite)")

    def _setup(self):
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id         INTEGER PRIMARY KEY,
                username        TEXT DEFAULT '',
                first_name      TEXT DEFAULT '',
                last_name       TEXT DEFAULT '',
                language        TEXT DEFAULT 'tr',
                balance         REAL DEFAULT 0,
                referral_code   TEXT UNIQUE,
                referred_by     INTEGER,
                tasks_completed INTEGER DEFAULT 0,
                total_earned    REAL DEFAULT 0,
                total_referrals INTEGER DEFAULT 0,
                ton_address     TEXT DEFAULT '',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status          TEXT DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                title               TEXT,
                description         TEXT DEFAULT '',
                reward              REAL DEFAULT 0.0025,
                max_participants    INTEGER DEFAULT 100,
                current_participants INTEGER DEFAULT 0,
                status              TEXT DEFAULT 'active',
                task_type           TEXT DEFAULT 'channel_join',
                target_username     TEXT DEFAULT '',
                target_link         TEXT DEFAULT '',
                fwd_chat_id         TEXT DEFAULT '',
                fwd_message_id      INTEGER DEFAULT 0,
                created_by          INTEGER DEFAULT 0,
                budget              REAL DEFAULT 0,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS task_completions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id    INTEGER,
                user_id    INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS withdrawals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                amount      REAL,
                ton_address TEXT,
                status      TEXT DEFAULT 'pending',
                tx_hash     TEXT DEFAULT '',
                admin_note  TEXT DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER UNIQUE,
                earned      REAL DEFAULT 0,
                status      TEXT DEFAULT 'pending',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS txns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                amount      REAL,
                type        TEXT,
                note        TEXT DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        self.conn.commit()

    def q(self, sql, params=()):
        with self._lock:
            self.cur.execute(sql, params)
            self.conn.commit()
            return self.cur

    def get_user(self, uid):
        self.cur.execute('SELECT * FROM users WHERE user_id=?', (uid,))
        row = self.cur.fetchone()
        if not row:
            return None
        u = dict(row)
        self.cur.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status="active"', (uid,))
        u['total_referrals'] = self.cur.fetchone()[0]
        return u

    def create_user(self, uid, username, first_name, last_name, lang='tr', referred_by=None):
        if self.get_user(uid):
            return self.get_user(uid)
        code = str(uuid.uuid4())[:8].upper()
        self.q('INSERT INTO users(user_id,username,first_name,last_name,language,referral_code,referred_by) VALUES(?,?,?,?,?,?,?)',
               (uid, username, first_name, last_name, lang, code, referred_by))
        if referred_by:
            self.q('INSERT OR IGNORE INTO referrals(referrer_id,referred_id,status) VALUES(?,?,"pending")',
                   (referred_by, uid))
        return self.get_user(uid)

    def update_active(self, uid):
        self.q('UPDATE users SET last_active=CURRENT_TIMESTAMP WHERE user_id=?', (uid,))

    def set_lang(self, uid, lang):
        self.q('UPDATE users SET language=? WHERE user_id=?', (lang, uid))

    def set_ton(self, uid, addr):
        self.q('UPDATE users SET ton_address=? WHERE user_id=?', (addr, uid))

    def create_task(self, title, description, reward, max_p, task_type,
                    target_username, target_link, fwd_chat_id, fwd_message_id,
                    created_by, budget):
        self.q('''INSERT INTO tasks(title,description,reward,max_participants,task_type,
                    target_username,target_link,fwd_chat_id,fwd_message_id,created_by,budget)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
               (title, description, reward, max_p, task_type,
                target_username, target_link, str(fwd_chat_id), fwd_message_id,
                created_by, budget))
        return self.cur.lastrowid

    def get_task(self, tid):
        self.cur.execute('SELECT * FROM tasks WHERE id=?', (tid,))
        row = self.cur.fetchone()
        return dict(row) if row else None

    def get_tasks_for_user(self, uid, task_type=None):
        base = '''SELECT t.* FROM tasks t
                  WHERE t.status='active'
                  AND t.current_participants < t.max_participants
                  AND NOT EXISTS(SELECT 1 FROM task_completions c WHERE c.task_id=t.id AND c.user_id=?)'''
        params = [uid]
        if task_type:
            base += ' AND t.task_type=?'
            params.append(task_type)
        base += ' ORDER BY t.reward DESC, t.created_at DESC'
        self.cur.execute(base, params)
        return [dict(r) for r in self.cur.fetchall()]

    def has_done(self, uid, tid):
        self.cur.execute('SELECT 1 FROM task_completions WHERE user_id=? AND task_id=?', (uid, tid))
        return bool(self.cur.fetchone())

    def complete_task(self, uid, tid):
        if self.has_done(uid, tid):
            return None
        task = self.get_task(tid)
        if not task or task['status'] != 'active':
            return None
        reward = task['reward']
        self.q('INSERT INTO task_completions(task_id,user_id) VALUES(?,?)', (tid, uid))
        self.q('UPDATE tasks SET current_participants=current_participants+1 WHERE id=?', (tid,))
        
        # Görev doldu mu kontrol et
        self.cur.execute('SELECT current_participants, max_participants FROM tasks WHERE id=?', (tid,))
        row = self.cur.fetchone()
        if row and row[0] >= row[1]:
            self.q("UPDATE tasks SET status='completed' WHERE id=?", (tid,))
        
        # Kullanıcıya ödül ekle
        self.q('UPDATE users SET balance=balance+?, tasks_completed=tasks_completed+1, total_earned=total_earned+? WHERE user_id=?',
               (reward, reward, uid))
        self.q('INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
               (uid, reward, 'task_reward', task['title']))
        
        # Referans komisyonu
        user = self.get_user(uid)
        if user and user['referred_by']:
            commission = reward * REF_TASK_COMMISSION
            self.q('UPDATE users SET balance=balance+? WHERE user_id=?', (commission, user['referred_by']))
            self.q('INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
                   (user['referred_by'], commission, 'ref_commission', f'Görev komisyon: {uid}'))
        
        return reward

    def create_withdrawal(self, uid, amount, addr):
        self.q('INSERT INTO withdrawals(user_id,amount,ton_address) VALUES(?,?,?)', (uid, amount, addr))
        wid = self.cur.lastrowid
        self.q('UPDATE users SET balance=balance-? WHERE user_id=?', (amount, uid))
        self.q('INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
               (uid, -amount, 'withdrawal', addr[:20]))
        return wid

    def get_pending_wds(self):
        self.cur.execute('''SELECT w.*, u.first_name, u.username FROM withdrawals w
                           JOIN users u ON w.user_id=u.user_id
                           WHERE w.status='pending' ORDER BY w.created_at ASC''')
        return [dict(r) for r in self.cur.fetchall()]

    def approve_wd(self, wid, admin_id, tx_hash=''):
        self.q("UPDATE withdrawals SET status='paid', tx_hash=? WHERE id=?", (tx_hash, wid))

    def reject_wd(self, wid, admin_id, reason=''):
        self.cur.execute('SELECT * FROM withdrawals WHERE id=?', (wid,))
        w = self.cur.fetchone()
        if w:
            w = dict(w)
            self.q("UPDATE withdrawals SET status='rejected', admin_note=? WHERE id=?", (reason, wid))
            self.q('UPDATE users SET balance=balance+? WHERE user_id=?', (w['amount'], w['user_id']))

    def add_balance(self, uid, amount, admin_id, reason=''):
        self.q('UPDATE users SET balance=balance+? WHERE user_id=?', (amount, uid))
        self.q('INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
               (uid, amount, 'admin_add', reason))

    def ban(self, uid):
        self.q("UPDATE users SET status='banned' WHERE user_id=?", (uid,))

    def unban(self, uid):
        self.q("UPDATE users SET status='active' WHERE user_id=?", (uid,))

    def stats(self):
        return {
            'users': self.cur.execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'balance': self.cur.execute('SELECT COALESCE(SUM(balance),0) FROM users').fetchone()[0],
            'pending_wds': self.cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0],
            'tasks_done': self.cur.execute('SELECT COUNT(*) FROM task_completions').fetchone()[0],
            'active_tasks': self.cur.execute("SELECT COUNT(*) FROM tasks WHERE status='active'").fetchone()[0],
        }

# ════════════════════════════════════════════
#              METINLER
# ════════════════════════════════════════════
_TEXTS = {
    'tr': {
        'welcome': '''╔══════════════════════╗
║   🚀 GÖREV MERKEZİ  ║
╚══════════════════════╝
👋 Hoş geldin, {name}!
┌──────────────────────
│ 💎 Bakiye:    `{balance:.4f} TON`
│ 🎯 Tamamlanan: `{completed}`
│ 👥 Referans:  `{referrals}`
└──────────────────────
💡 Görev tamamla → TON kazan!
🔗 Davet et → +{ref_bonus} TON/kişi!
🛠️ Kendi görevini yayınla!''',
        'no_tasks': "📭 Şu an görev yok. Yakında yenileri eklenecek!",
        'task_done': "✅ *Tamamlandı!* +`{reward} TON` eklendi!",
        'task_already': "❌ Bu görevi zaten tamamladınız!",
        'enter_amount': "💰 Çekim miktarını gir (TON):",
        'enter_addr': "🏦 TON cüzdan adresinizi girin:",
        'bad_num': "❌ Geçersiz sayı!",
        'bad_addr': "❌ Geçersiz TON adresi!",
        'wd_low': "❌ Yetersiz bakiye! Min `{min} TON` gerekli.\n💎 Bakiyen: `{bal} TON`",
        'wd_ok': "✅ *Çekim Talebi Alındı!*\n💎 `{amount} TON`\n🏦 `{addr}`\n⏳ 24-48 saat",
        'check_btn': "✅ Katıldım, Kontrol Et",
        'ton_saved': "✅ TON adresin kaydedildi!",
    },
    'en': {
        'welcome': '''╔══════════════════════╗
║   🚀 TASK CENTER    ║
╚══════════════════════╝
👋 Welcome, {name}!
┌──────────────────────
│ 💎 Balance:   `{balance:.4f} TON`
│ 🎯 Completed: `{completed}`
│ 👥 Referrals: `{referrals}`
└──────────────────────
💡 Complete tasks → Earn TON!
🔗 Invite → +{ref_bonus} TON/person!
🛠️ Publish your own tasks!''',
        'no_tasks': "📭 No tasks right now. New tasks coming soon!",
        'task_done': "✅ *Done!* +`{reward} TON` added!",
        'task_already': "❌ You already completed this task!",
        'enter_amount': "💰 Enter withdrawal amount (TON):",
        'enter_addr': "🏦 Enter your TON wallet address:",
        'bad_num': "❌ Invalid number!",
        'bad_addr': "❌ Invalid TON address!",
        'wd_low': "❌ Insufficient balance! Min `{min} TON` needed.\n💎 Balance: `{bal} TON`",
        'wd_ok': "✅ *Withdrawal Requested!*\n💎 `{amount} TON`\n🏦 `{addr}`\n⏳ 24-48 hours",
        'check_btn': "✅ I Joined, Check",
        'ton_saved': "✅ TON address saved!",
    }
}

def T(lang, key, **kwargs):
    text = _TEXTS.get(lang, _TEXTS['en']).get(key, _TEXTS['en'].get(key, key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except:
            pass
    return text

# ════════════════════════════════════════════
#              BOT SINIFI
# ════════════════════════════════════════════
class TaskBot:
    def __init__(self):
        self.db = Database()
        self.states = {}  # Kullanıcı state'leri
        print(f"🤖 {BOT_NAME} hazır!")

    def main_keyboard(self, lang, is_admin=False):
        keyboard = [
            [{'text': '💰 Bakiye' if lang == 'tr' else '💰 Balance'}, 
             {'text': '🎯 Görevler' if lang == 'tr' else '🎯 Tasks'}],
            [{'text': '💎 Çekim' if lang == 'tr' else '💎 Withdraw'}, 
             {'text': '👥 Davet' if lang == 'tr' else '👥 Invite'}],
            [{'text': '🛠️ Görev Oluştur' if lang == 'tr' else '🛠️ Create Task'}, 
             {'text': '📋 Görevlerim' if lang == 'tr' else '📋 My Tasks'}],
            [{'text': '👤 Profil' if lang == 'tr' else '👤 Profile'}, 
             {'text': '⚙️ Ayarlar' if lang == 'tr' else '⚙️ Settings'}],
            [{'text': '❓ Yardım' if lang == 'tr' else '❓ Help'}],
        ]
        if is_admin:
            keyboard.append([{'text': '🛡️ Admin'}])
        return {'keyboard': keyboard, 'resize_keyboard': True}

    def show_lang_select(self, uid):
        keyboard = {
            'inline_keyboard': [
                [{'text': '🇹🇷 Türkçe', 'callback_data': 'lang_tr'}],
                [{'text': '🇺🇸 English', 'callback_data': 'lang_en'}],
            ]
        }
        send_message(uid, "🌍 *DİL SEÇİNİZ*\nPlease select your language:", reply_markup=keyboard)

    def show_menu(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        text = T(lang, 'welcome', 
                 name=user['first_name'],
                 balance=user['balance'],
                 completed=user['tasks_completed'],
                 referrals=user['total_referrals'],
                 ref_bonus=REF_WELCOME_BONUS)
        is_admin = str(uid) in ADMIN_IDS
        send_message(uid, text, reply_markup=self.main_keyboard(lang, is_admin))

    def show_tasks(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        tasks = self.db.get_tasks_for_user(uid)
        
        if not tasks:
            keyboard = {'inline_keyboard': [
                [{'text': '🔄 Yenile', 'callback_data': 'refresh_tasks'}],
                [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]
            ]}
            send_message(uid, T(lang, 'no_tasks'), reply_markup=keyboard)
            return

        for task in tasks[:10]:
            text = f"🎯 *{task['title']}*\n"
            text += f"💎 Ödül: `{task['reward']:.4f} TON`\n"
            text += f"👥 Katılım: {task['current_participants']}/{task['max_participants']}\n"
            
            keyboard = {'inline_keyboard': [
                [{'text': '🔍 Detay', 'callback_data': f"task_{task['id']}"}]
            ]}
            send_message(uid, text, reply_markup=keyboard)

    def show_task_detail(self, uid, tid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        task = self.db.get_task(tid)
        if not task:
            return

        if self.db.has_done(uid, tid):
            send_message(uid, T(lang, 'task_already'))
            return

        text = f"🎯 *{task['title']}*\n"
        if task['description']:
            text += f"📝 {task['description']}\n"
        text += f"\n💎 Ödül: `{task['reward']:.4f} TON`\n"
        text += f"👥 Katılım: {task['current_participants']}/{task['max_participants']}\n"

        buttons = []
        if task['target_link']:
            buttons.append([{'text': '🔗 Git', 'url': task['target_link']}])
        
        buttons.append([{'text': T(lang, 'check_btn'), 'callback_data': f"verify_{tid}"}])
        buttons.append([{'text': '🔙 Geri', 'callback_data': 'show_tasks'}])
        
        send_message(uid, text, reply_markup={'inline_keyboard': buttons})

    def verify_membership(self, uid, tid, cb_id):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        
        if self.db.has_done(uid, tid):
            answer_callback(cb_id, T(lang, 'task_already'), True)
            return

        task = self.db.get_task(tid)
        if not task:
            return

        answer_callback(cb_id, "⏳ Kontrol ediliyor...")

        if task['target_username']:
            target = f"@{task['target_username'].lstrip('@')}"
            is_member = get_chat_member(target, uid)
            if not is_member:
                fail_text = "❌ Henüz katılmadınız! Lütfen önce katılın."
                keyboard = {'inline_keyboard': [
                    [{'text': '🔗 Katıl', 'url': task['target_link']}],
                    [{'text': '🔄 Tekrar Dene', 'callback_data': f"verify_{tid}"}]
                ]}
                send_message(uid, fail_text, reply_markup=keyboard)
                return

        reward = self.db.complete_task(uid, tid)
        if reward:
            send_message(uid, T(lang, 'task_done', reward=f"{reward:.4f}"))
            self.show_menu(uid)

    def show_task_publish(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        
        text = f"""🛠️ *GÖREV OLUŞTUR*
💎 Bakiyen: `{user['balance']:.4f} TON`

Görev türünü seç:"""
        
        keyboard = {'inline_keyboard': [
            [{'text': '📢 Kanal Görevi', 'callback_data': 'pub_type_channel_join'}],
            [{'text': '👥 Grup Görevi', 'callback_data': 'pub_type_group_join'}],
            [{'text': '🤖 Bot Görevi', 'callback_data': 'pub_type_bot_start'}],
            [{'text': '❌ İptal', 'callback_data': 'cancel'}]
        ]}
        send_message(uid, text, reply_markup=keyboard)

    def show_withdraw(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        
        if user['balance'] < MIN_WITHDRAW:
            send_message(uid, T(lang, 'wd_low', min=MIN_WITHDRAW, bal=f"{user['balance']:.4f}"))
            return
        
        self.states[uid] = {'action': 'wd_amount'}
        send_message(uid, T(lang, 'enter_amount'),
                    reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})

    def show_invite(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user['referral_code']}"
        
        text = f"""👥 *DAVET ET*
🔗 Linkin:
`{ref_link}`

💰 Her aktif referans için: `{REF_WELCOME_BONUS} TON`
👥 Aktif referans: `{user['total_referrals']}`"""
        
        keyboard = {'inline_keyboard': [
            [{'text': '📤 Paylaş', 'url': f"https://t.me/share/url?url={ref_link}"}],
            [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]
        ]}
        send_message(uid, text, reply_markup=keyboard)

    def show_profile(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        
        text = f"""👤 *PROFİL*
🆔 ID: `{user['user_id']}`
👤 İsim: {user['first_name']}
💎 Bakiye: `{user['balance']:.4f} TON`
🎯 Tamamlanan: {user['tasks_completed']}
👥 Referans: {user['total_referrals']}
🏦 TON: `{user['ton_address'] or '—'}`"""
        
        send_message(uid, text)

    def show_settings(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        
        text = f"""⚙️ *AYARLAR*
🏦 TON Adresi: `{user['ton_address'] or '—'}`"""
        
        keyboard = {'inline_keyboard': [
            [{'text': '💳 TON Adres Kaydet', 'callback_data': 'set_ton'}],
            [{'text': '🌍 Dil Değiştir', 'callback_data': 'change_lang'}],
            [{'text': '🏠 Menü', 'callback_data': 'main_menu'}]
        ]}
        send_message(uid, text, reply_markup=keyboard)

    def show_help(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        
        text = f"""❓ *YARDIM*
🤖 {BOT_NAME}

📌 *Komutlar:*
/start - Ana menü
/tasks - Görevler
/balance - Bakiye
/withdraw - Çekim
/profile - Profil

💎 *Çekim:* Minimum {MIN_WITHDRAW} TON
👥 *Referans:* {REF_WELCOME_BONUS} TON/kişi
🛠️ *Görev Oluştur:* Kendi görevini yayınla

📞 Destek: {SUPPORT_USERNAME}"""
        
        send_message(uid, text)

    def show_admin(self, uid):
        stats = self.db.stats()
        text = f"""🛡️ *ADMIN PANELİ*
━━━━━━━━━━━━━━━━
👥 Kullanıcı: {stats['users']}
💎 Toplam Bakiye: {stats['balance']:.4f} TON
📥 Bekleyen Çekim: {stats['pending_wds']}
🎯 Tamamlanan Görev: {stats['tasks_done']}
📋 Aktif Görev: {stats['active_tasks']}

📌 Komutlar:
/addbalance ID MİKTAR
/ban ID
/unban ID"""
        
        keyboard = {'inline_keyboard': [
            [{'text': '📥 Çekimler', 'callback_data': 'admin_wds'}],
            [{'text': '🔄 Yenile', 'callback_data': 'admin_refresh'}]
        ]}
        send_message(uid, text, reply_markup=keyboard)

    # ========== GÖREV OLUŞTURMA ADIMLARI ==========
    def pub_type_selected(self, uid, task_type, cb_id):
        answer_callback(cb_id)
        self.states[uid] = {
            'action': 'pub_title',
            'task_type': task_type,
            'reward': TASK_REWARDS.get(task_type, 0.0025)
        }
        send_message(uid, "📌 *Görev başlığını gir:*\n_(Örn: Kanalıma Katıl ve Kazan!)_",
                    reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})

    def pub_handle_title(self, uid, text):
        self.states[uid]['title'] = text
        self.states[uid]['action'] = 'pub_description'
        send_message(uid, "📝 *Görev açıklamasını gir:*\n_(Atlamak için - yaz)_",
                    reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})

    def pub_handle_description(self, uid, text):
        self.states[uid]['description'] = '' if text == '-' else text
        self.states[uid]['action'] = 'pub_username'
        send_message(uid, "🎯 *Hedef kullanıcı adını gir:*\n_(Örn: TaskizLive - @ olmadan)_",
                    reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})

    def pub_handle_username(self, uid, text):
        username = text.strip().lstrip('@')
        self.states[uid]['target_username'] = username
        self.states[uid]['target_link'] = f"https://t.me/{username}"
        self.states[uid]['action'] = 'pub_budget'
        
        # Bütçe seçeneklerini göster
        task_type = self.states[uid]['task_type']
        reward = self.states[uid]['reward']
        
        text = f"💰 *BÜTÇE SEÇ*\n"
        text += f"💎 Katılımcı başı ödül: `{reward} TON`\n"
        text += f"⚡ Çarpan: 1/{TASK_BUDGET_MULTIPLIER}\n\n"
        
        buttons = []
        for budget in TASK_BUDGET_OPTIONS:
            max_p = int(budget / (reward * TASK_BUDGET_MULTIPLIER))
            if max_p < 1:
                max_p = 1
            buttons.append([{
                'text': f"{budget} TON → {max_p} katılımcı",
                'callback_data': f"pub_budget_{budget}"
            }])
        buttons.append([{'text': '✏️ Özel Miktar', 'callback_data': 'pub_budget_custom'}])
        buttons.append([{'text': '❌ İptal', 'callback_data': 'cancel'}])
        
        send_message(uid, text, reply_markup={'inline_keyboard': buttons})

    def pub_handle_budget(self, uid, budget):
        user = self.db.get_user(uid)
        if not user:
            return
        
        state = self.states.get(uid, {})
        if user['balance'] < budget:
            send_message(uid, f"❌ Yetersiz bakiye! Bakiyen: {user['balance']:.4f} TON")
            return
        
        reward = state['reward']
        max_p = int(budget / (reward * TASK_BUDGET_MULTIPLIER))
        if max_p < 1:
            max_p = 1
        
        state['budget'] = budget
        state['max_p'] = max_p
        state['action'] = 'pub_confirm'
        
        text = f"""✅ *GÖREV ÖNİZLEME*
📌 Başlık: {state.get('title')}
🎯 Hedef: @{state.get('target_username')}
💎 Ödül: {reward} TON/kişi
👥 Katılımcı: {max_p} kişi
💰 Toplam Ödül: {reward * max_p:.4f} TON
💳 Ödenecek: {budget} TON

Onaylıyor musun?"""
        
        keyboard = {'inline_keyboard': [
            [{'text': '✅ Yayınla', 'callback_data': 'pub_save'}],
            [{'text': '🔙 Geri', 'callback_data': 'pub_budget_back'}],
            [{'text': '❌ İptal', 'callback_data': 'cancel'}]
        ]}
        send_message(uid, text, reply_markup=keyboard)

    def pub_save_task(self, uid, cb_id):
        user = self.db.get_user(uid)
        if not user:
            return
        
        state = self.states.get(uid, {})
        if not state:
            return
        
        answer_callback(cb_id)
        
        # Bakiyeden düş
        self.db.q('UPDATE users SET balance=balance-? WHERE user_id=?', (state['budget'], uid))
        
        # Görevi kaydet
        tid = self.db.create_task(
            title=state.get('title', 'Görev'),
            description=state.get('description', ''),
            reward=state.get('reward'),
            max_p=state.get('max_p'),
            task_type=state.get('task_type'),
            target_username=state.get('target_username'),
            target_link=state.get('target_link'),
            fwd_chat_id='',
            fwd_message_id=0,
            created_by=uid,
            budget=state.get('budget')
        )
        
        # State'i temizle
        del self.states[uid]
        
        send_message(uid, f"🎉 *Görev #{tid} yayınlandı!*\n\nGöreviniz artık herkese açık!")
        self.show_menu(uid)

    # ========== HANDLER'LAR ==========
    def handle_message(self, msg):
        uid = msg['from']['id']
        text = msg.get('text', '')
        
        # Kullanıcıyı getir veya oluştur
        user = self.db.get_user(uid)
        
        # /start komutu
        if text and text.startswith('/start'):
            referred_by = None
            parts = text.split()
            if len(parts) > 1:
                self.db.cur.execute('SELECT user_id FROM users WHERE referral_code=?', (parts[1],))
                row = self.db.cur.fetchone()
                if row and row[0] != uid:
                    referred_by = row[0]
            
            if not user:
                user = self.db.create_user(
                    uid,
                    msg['from'].get('username', ''),
                    msg['from'].get('first_name', ''),
                    msg['from'].get('last_name', ''),
                    'tr',
                    referred_by
                )
                self.show_lang_select(uid)
            else:
                self.db.update_active(uid)
                self.show_menu(uid)
            return
        
        if not user:
            return
        
        self.db.update_active(uid)
        lang = user['language']
        
        # State kontrolü (görev oluşturma vs)
        if uid in self.states:
            state = self.states[uid]
            action = state.get('action')
            
            if action == 'wd_amount':
                try:
                    amount = float(text.replace(',', '.'))
                    if amount < MIN_WITHDRAW or amount > user['balance']:
                        send_message(uid, T(lang, 'wd_low', min=MIN_WITHDRAW, bal=f"{user['balance']:.4f}"))
                        return
                    self.states[uid] = {'action': 'wd_addr', 'amount': amount}
                    send_message(uid, T(lang, 'enter_addr'))
                except ValueError:
                    send_message(uid, T(lang, 'bad_num'))
                return
            
            elif action == 'wd_addr':
                addr = text.strip()
                if len(addr) < 10:
                    send_message(uid, T(lang, 'bad_addr'))
                    return
                amount = state['amount']
                wid = self.db.create_withdrawal(uid, amount, addr)
                del self.states[uid]
                send_message(uid, T(lang, 'wd_ok', amount=f"{amount:.4f}", addr=addr))
                self.show_menu(uid)
                return
            
            elif action == 'set_ton':
                addr = text.strip()
                if len(addr) < 10:
                    send_message(uid, T(lang, 'bad_addr'))
                    return
                self.db.set_ton(uid, addr)
                del self.states[uid]
                send_message(uid, T(lang, 'ton_saved'))
                self.show_settings(uid)
                return
            
            elif action == 'pub_title':
                self.pub_handle_title(uid, text)
                return
            
            elif action == 'pub_description':
                self.pub_handle_description(uid, text)
                return
            
            elif action == 'pub_username':
                self.pub_handle_username(uid, text)
                return
        
        # Menü butonları
        if text == '💰 Bakiye' or text == '💰 Balance':
            self.show_balance(uid)
        elif text == '🎯 Görevler' or text == '🎯 Tasks':
            self.show_tasks(uid)
        elif text == '💎 Çekim' or text == '💎 Withdraw':
            self.show_withdraw(uid)
        elif text == '👥 Davet' or text == '👥 Invite':
            self.show_invite(uid)
        elif text == '🛠️ Görev Oluştur' or text == '🛠️ Create Task':
            self.show_task_publish(uid)
        elif text == '📋 Görevlerim' or text == '📋 My Tasks':
            self.show_my_tasks(uid)
        elif text == '👤 Profil' or text == '👤 Profile':
            self.show_profile(uid)
        elif text == '⚙️ Ayarlar' or text == '⚙️ Settings':
            self.show_settings(uid)
        elif text == '❓ Yardım' or text == '❓ Help':
            self.show_help(uid)
        elif text == '🛡️ Admin' and str(uid) in ADMIN_IDS:
            self.show_admin(uid)
        else:
            self.show_menu(uid)

    def show_balance(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        text = f"""💰 *BAKİYE*
💎 Mevcut: `{user['balance']:.4f} TON`
📊 Kazanç: `{user['total_earned']:.4f} TON`
🎯 Görev: {user['tasks_completed']}
⚡ Min Çekim: {MIN_WITHDRAW} TON"""
        send_message(uid, text)

    def show_my_tasks(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        self.db.cur.execute("SELECT * FROM tasks WHERE created_by=? ORDER BY created_at DESC", (uid,))
        tasks = [dict(r) for r in self.db.cur.fetchall()]
        
        if not tasks:
            send_message(uid, "📭 Henüz görev oluşturmadınız.")
            return
        
        for task in tasks[:5]:
            status_icon = '🟢' if task['status'] == 'active' else '🔴'
            text = f"""{status_icon} *Görev #{task['id']}*
📌 {task['title']}
👥 {task['current_participants']}/{task['max_participants']}
💎 {task['reward']:.4f} TON/kişi"""
            send_message(uid, text)

    def handle_callback(self, cq):
        uid = cq['from']['id']
        data = cq.get('data', '')
        cb_id = cq['id']
        
        user = self.db.get_user(uid)
        if not user:
            answer_callback(cb_id, "Önce /start yapın", True)
            return
        
        lang = user['language']
        
        # Dil seçimi
        if data.startswith('lang_'):
            new_lang = data[5:]
            if new_lang in SUPPORTED_LANGUAGES:
                self.db.set_lang(uid, new_lang)
                answer_callback(cb_id, "✅ Dil seçildi!")
                self.show_menu(uid)
            return
        
        # Görev detay
        if data.startswith('task_'):
            tid = int(data[5:])
            answer_callback(cb_id)
            self.show_task_detail(uid, tid)
            return
        
        # Doğrulama
        if data.startswith('verify_'):
            tid = int(data.split('_')[-1])
            self.verify_membership(uid, tid, cb_id)
            return
        
        # Görev oluşturma
        if data.startswith('pub_type_'):
            task_type = data[9:]
            self.pub_type_selected(uid, task_type, cb_id)
            return
        
        if data.startswith('pub_budget_') and data not in ['pub_budget_back', 'pub_budget_custom']:
            budget = float(data[11:])
            answer_callback(cb_id)
            self.pub_handle_budget(uid, budget)
            return
        
        if data == 'pub_budget_custom':
            answer_callback(cb_id)
            self.states[uid]['action'] = 'pub_budget_custom'
            send_message(uid, "✏️ Özel bütçe miktarını gir (TON):")
            return
        
        if data == 'pub_budget_back':
            answer_callback(cb_id)
            self.states[uid]['action'] = 'pub_budget'
            task_type = self.states[uid]['task_type']
            reward = self.states[uid]['reward']
            text = f"💰 *BÜTÇE SEÇ*\n💎 Ödül: {reward} TON/kişi\n⚡ Çarpan: 1/{TASK_BUDGET_MULTIPLIER}"
            buttons = []
            for budget in TASK_BUDGET_OPTIONS:
                max_p = int(budget / (reward * TASK_BUDGET_MULTIPLIER))
                if max_p < 1:
                    max_p = 1
                buttons.append([{'text': f"{budget} TON → {max_p} katılımcı", 'callback_data': f"pub_budget_{budget}"}])
            buttons.append([{'text': '✏️ Özel Miktar', 'callback_data': 'pub_budget_custom'}])
            buttons.append([{'text': '❌ İptal', 'callback_data': 'cancel'}])
            send_message(uid, text, reply_markup={'inline_keyboard': buttons})
            return
        
        if data == 'pub_save':
            self.pub_save_task(uid, cb_id)
            return
        
        # Ana menü
        if data == 'main_menu':
            answer_callback(cb_id)
            self.show_menu(uid)
            return
        
        if data == 'refresh_tasks':
            answer_callback(cb_id, "🔄 Yenileniyor...")
            self.show_tasks(uid)
            return
        
        if data == 'show_tasks':
            answer_callback(cb_id)
            self.show_tasks(uid)
            return
        
        if data == 'set_ton':
            answer_callback(cb_id)
            self.states[uid] = {'action': 'set_ton'}
            send_message(uid, T(lang, 'enter_addr'))
            return
        
        if data == 'change_lang':
            answer_callback(cb_id)
            self.show_lang_select(uid)
            return
        
        if data == 'cancel':
            if uid in self.states:
                del self.states[uid]
            answer_callback(cb_id, "❌ İptal edildi")
            self.show_menu(uid)
            return
        
        # Admin callback'leri
        if data == 'admin_refresh' and str(uid) in ADMIN_IDS:
            answer_callback(cb_id, "🔄")
            self.show_admin(uid)
            return
        
        if data == 'admin_wds' and str(uid) in ADMIN_IDS:
            answer_callback(cb_id)
            wds = self.db.get_pending_wds()
            if not wds:
                send_message(uid, "✅ Bekleyen çekim yok")
                return
            for w in wds[:5]:
                text = f"""📥 *ÇEKİM #{w['id']}*
👤 {w['first_name']} (`{w['user_id']}`)
💎 {w['amount']:.4f} TON
🏦 {w['ton_address']}"""
                keyboard = {'inline_keyboard': [
                    [{'text': '✅ Onayla', 'callback_data': f"admin_wd_ok_{w['id']}"},
                     {'text': '❌ Reddet', 'callback_data': f"admin_wd_no_{w['id']}"}]
                ]}
                send_message(uid, text, reply_markup=keyboard)
            return
        
        if data.startswith('admin_wd_ok_') and str(uid) in ADMIN_IDS:
            wid = int(data.split('_')[-1])
            self.db.approve_wd(wid, uid)
            answer_callback(cb_id, "✅ Onaylandı!", True)
            self.show_admin(uid)
            return
        
        if data.startswith('admin_wd_no_') and str(uid) in ADMIN_IDS:
            wid = int(data.split('_')[-1])
            self.db.reject_wd(wid, uid, "Admin reddetti")
            answer_callback(cb_id, "❌ Reddedildi!", True)
            self.show_admin(uid)
            return
        
        answer_callback(cb_id)

    def handle_update(self, update):
        try:
            if 'message' in update:
                self.handle_message(update['message'])
            elif 'callback_query' in update:
                self.handle_callback(update['callback_query'])
        except Exception as e:
            print(f"❌ Hata: {e}")

# ════════════════════════════════════════════
#              POLLING
# ════════════════════════════════════════════
def run_polling():
    bot = TaskBot()
    offset = 0
    print("🔄 Polling başlatıldı...")
    
    while True:
        try:
            updates = get_updates(offset=offset, timeout=30)
            for update in updates:
                if 'update_id' in update:
                    offset = update['update_id'] + 1
                threading.Thread(target=bot.handle_update, args=(update,), daemon=True).start()
        except Exception as e:
            print(f"❌ Polling hatası: {e}")
            time.sleep(5)

# ════════════════════════════════════════════
#              ANA FONKSİYON
# ════════════════════════════════════════════
if __name__ == "__main__":
    # Polling'i ayrı thread'de başlat
    threading.Thread(target=run_polling, daemon=True).start()
    
    # Flask'i başlat (healthcheck için)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
