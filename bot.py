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
import firebase_admin
from firebase_admin import credentials, firestore

# ════════════════════════════════════════════
#              TEMEL AYARLAR
# ════════════════════════════════════════════
TOKEN            = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS        = os.environ.get("ADMIN_ID", "7904032877").split(",")
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "@AlperenTHE")
STATS_CHANNEL    = os.environ.get("STATS_CHANNEL", "@TaskizLive")
BOT_USERNAME     = os.environ.get("BOT_USERNAME", "TaskizBot")
BOT_NAME         = os.environ.get("BOT_NAME", "TaskizBot")

# ════════════════════════════════════════════
#         ZORUNLU KANALLAR / GRUPLAR
# ════════════════════════════════════════════
MANDATORY_CHANNELS = [
    {'username': 'TaskizLive', 'link': 'https://t.me/TaskizLive', 'name': 'TaskizLive', 'emoji': '📊'},
]
MANDATORY_GROUPS = []

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN ortam değişkeni gerekli!")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
FIREBASE_PROJECT_ID       = os.environ.get("FIREBASE_PROJECT_ID", "taskiz-2db5a")
FIREBASE_DATABASE_URL     = os.environ.get("FIREBASE_DATABASE_URL", "https://taskiz-2db5a-default-rtdb.firebaseio.com/")

# ════════════════════════════════════════════
#              DİL DESTEĞİ
# ════════════════════════════════════════════
SUPPORTED_LANGUAGES = {
    'tr':    {'name': 'Türkçe',             'flag': '🇹🇷'},
    'en':    {'name': 'English',            'flag': '🇺🇸'},
    'pt_br': {'name': 'Português (Brasil)', 'flag': '🇧🇷'},
}

# ════════════════════════════════════════════
#              SİSTEM AYARLARI
# ════════════════════════════════════════════
MIN_WITHDRAW        = 0.05   # TON
REF_WELCOME_BONUS   = 0.005  # TON
REF_TASK_COMMISSION = 0.25   # 25%

# Görev oluşturma bütçe seçenekleri
TASK_BUDGET_OPTIONS = [0.1, 0.25, 0.5, 1.0, 2.0, 5.0]

# Görev türüne göre katılımcı başı ödül
TASK_REWARDS = {
    'channel_join': 0.0025,   # Kanal katılım
    'group_join':   0.0025,   # Grup katılım
    'bot_start':    0.001,    # Bot başlatma
}

# ════════════════════════════════════════════
#              FLASK
# ════════════════════════════════════════════
app = Flask(__name__)

@app.route("/", methods=["GET"])
def healthcheck():
    return jsonify({"status": "ok", "bot": BOT_NAME})

# ════════════════════════════════════════════
#           TELEGRAM API
# ════════════════════════════════════════════
def _post(method, payload, timeout=10):
    try:
        r = requests.post(BASE_URL + method, json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        print(f"API {method} hatası: {e}")
        return None

def send_message(chat_id, text, reply_markup=None, parse_mode='Markdown'):
    p = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode, 'disable_web_page_preview': True}
    if reply_markup:
        p['reply_markup'] = json.dumps(reply_markup)
    return _post("sendMessage", p)

def copy_message(chat_id, from_chat_id, message_id, reply_markup=None, caption=None):
    """Mesajı orijinal formatta kopyala (forward gibi ama "Forwarded from" yazısı olmadan)"""
    p = {'chat_id': chat_id, 'from_chat_id': from_chat_id, 'message_id': message_id}
    if reply_markup:
        p['reply_markup'] = json.dumps(reply_markup)
    if caption:
        p['caption'] = caption
    return _post("copyMessage", p)

def answer_callback(cb_id, text=None, alert=False):
    p = {'callback_query_id': cb_id}
    if text:
        p['text'] = text
    if alert:
        p['show_alert'] = True
    _post("answerCallbackQuery", p, timeout=5)

def get_chat_member(chat_id, user_id):
    """
    Üyelik kontrolü.
    Bot kanalda ADMIN olmalı — yoksa True döner (engelleme yok).
    """
    for _ in range(3):
        try:
            r = requests.post(BASE_URL + "getChatMember",
                              json={"chat_id": chat_id, "user_id": user_id},
                              timeout=10)
            data = r.json()
            if data.get("ok"):
                return data["result"]["status"] in ["member", "administrator", "creator", "restricted"]
            err = data.get("description", "").lower()
            print(f"getChatMember [{chat_id}] → {err}")
            if any(x in err for x in ["chat not found", "bot is not a member", "bot was kicked",
                                        "not enough rights", "have no rights"]):
                return True  # Bot admin değil → engelleme yapma
            return False
        except requests.exceptions.Timeout:
            time.sleep(0.5)
        except Exception as e:
            print(f"getChatMember exc: {e}")
            time.sleep(0.5)
    return True

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
#              FIREBASE
# ════════════════════════════════════════════
class FirebaseClient:
    """
    Firebase = Birincil kalici depolama.
    SQLite  = Hizli okuma icin yerel onbellek.
    Her deploy sonrasi SQLite sifirlanir ama Firebase kalicidir.
    """
    def __init__(self):
        self.enabled = False
        self.fs   = None
        self._queue  = []
        self._qlock  = threading.Lock()

        # FIREBASE_DATABASE_URL is module-level env var
        cred_json = FIREBASE_CREDENTIALS_JSON or ''
        project   = FIREBASE_PROJECT_ID or ''

        if not cred_json or not project:
            print('WARNING Firebase env vars eksik -- sadece SQLite kullanilacak')
            return
        try:
            cred = credentials.Certificate(json.loads(cred_json))
            if not firebase_admin._apps:
                opts = {'projectId': project}
                if FIREBASE_DATABASE_URL:  # noqa
                    opts['databaseURL'] = FIREBASE_DATABASE_URL
                firebase_admin.initialize_app(cred, opts)
            self.fs = firestore.client()
            self.enabled = True
            print('Firebase baglandi (Firestore)')
            t = threading.Thread(target=self._flush_loop, daemon=True)
            t.start()
        except Exception as e:
            print(f'Firebase baglanti hatasi: {e}')

    def _flush_loop(self):
        while True:
            time.sleep(3)
            with self._qlock:
                items = self._queue[:]
                self._queue.clear()
            for col, doc_id, data in items:
                try:
                    self.fs.collection(col).document(str(doc_id)).set(data, merge=True)
                except Exception as e:
                    print(f'Firebase flush [{col}/{doc_id}]: {e}')

    def save(self, col, doc_id, data):
        if not self.enabled:
            return
        with self._qlock:
            for i, (c, d, _) in enumerate(self._queue):
                if c == col and d == str(doc_id):
                    self._queue[i] = (col, str(doc_id), data)
                    return
            self._queue.append((col, str(doc_id), data))

    def save_now(self, col, doc_id, data):
        if not self.enabled:
            return
        try:
            self.fs.collection(col).document(str(doc_id)).set(data, merge=True)
        except Exception as e:
            print(f'Firebase save_now [{col}]: {e}')

    def load_collection(self, col):
        if not self.enabled:
            return []
        try:
            docs = self.fs.collection(col).stream()
            return [(doc.id, doc.to_dict()) for doc in docs]
        except Exception as e:
            print(f'Firebase load [{col}]: {e}')
            return []

    def restore_to_sqlite(self, db_obj):
        if not self.enabled:
            print('Firebase devre disi -- veriler sifirdan basliyor')
            return
        print('Firebase den veriler yukleniyor...')
        conn = db_obj.conn

        users = self.load_collection('users')
        for doc_id, u in users:
            try:
                conn.execute(
                    'INSERT OR REPLACE INTO users '
                    '(user_id,username,first_name,last_name,language,balance,'
                    'referral_code,referred_by,tasks_completed,total_earned,'
                    'total_referrals,ton_address,created_at,last_active,status)'
                    ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (
                        int(u.get('user_id', 0) or doc_id),
                        u.get('username',''), u.get('first_name',''), u.get('last_name',''),
                        u.get('language','tr'), float(u.get('balance',0)),
                        u.get('referral_code',''), u.get('referred_by'),
                        int(u.get('tasks_completed',0)), float(u.get('total_earned',0)),
                        int(u.get('total_referrals',0)), u.get('ton_address',''),
                        u.get('created_at',''), u.get('last_active',''),
                        u.get('status','active'),
                    )
                )
            except Exception as e:
                print(f'User restore [{doc_id}]: {e}')
        print(f'  {len(users)} kullanici yuklendi')

        tasks = self.load_collection('tasks')
        for doc_id, t in tasks:
            try:
                tid = t.get('id') or doc_id
                if not str(tid).lstrip('-').isdigit():
                    tid = 0
                conn.execute(
                    'INSERT OR REPLACE INTO tasks '
                    '(id,title,description,reward,max_participants,current_participants,'
                    'status,task_type,target_username,target_link,fwd_chat_id,'
                    'fwd_message_id,created_by,budget,created_at)'
                    ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (
                        int(tid), t.get('title',''), t.get('description',''),
                        float(t.get('reward',0)), int(t.get('max_participants',100)),
                        int(t.get('current_participants',0)), t.get('status','active'),
                        t.get('task_type','channel_join'), t.get('target_username',''),
                        t.get('target_link',''), t.get('fwd_chat_id',''),
                        int(t.get('fwd_message_id',0)), int(t.get('created_by',0) or 0),
                        float(t.get('budget',0)), t.get('created_at',''),
                    )
                )
            except Exception as e:
                print(f'Task restore [{doc_id}]: {e}')
        print(f'  {len(tasks)} gorev yuklendi')

        comps = self.load_collection('task_completions')
        for doc_id, c in comps:
            try:
                conn.execute(
                    'INSERT OR IGNORE INTO task_completions(task_id,user_id,created_at) VALUES(?,?,?)',
                    (int(c.get('task_id',0)), int(c.get('user_id',0)), c.get('created_at',''))
                )
            except:
                pass
        print(f'  {len(comps)} tamamlama yuklendi')

        wds = self.load_collection('withdrawals')
        for doc_id, w in wds:
            try:
                wid = w.get('id') or 0
                if not str(wid).lstrip('-').isdigit():
                    wid = 0
                conn.execute(
                    'INSERT OR REPLACE INTO withdrawals '
                    '(id,user_id,amount,ton_address,status,tx_hash,admin_note,created_at)'
                    ' VALUES(?,?,?,?,?,?,?,?)',
                    (
                        int(wid), int(w.get('user_id',0)),
                        float(w.get('amount',0)), w.get('ton_address',''),
                        w.get('status','pending'), w.get('tx_hash',''),
                        w.get('admin_note',''), w.get('created_at',''),
                    )
                )
            except Exception as e:
                print(f'WD restore [{doc_id}]: {e}')
        print(f'  {len(wds)} cekim yuklendi')

        refs = self.load_collection('referrals')
        for doc_id, r in refs:
            try:
                conn.execute(
                    'INSERT OR IGNORE INTO referrals(referrer_id,referred_id,earned,status,created_at) VALUES(?,?,?,?,?)',
                    (int(r.get('referrer_id',0)), int(r.get('referred_id',0)),
                     float(r.get('earned',0)), r.get('status','pending'), r.get('created_at',''))
                )
            except:
                pass
        print(f'  {len(refs)} referans yuklendi')

        pens = self.load_collection('channel_leave_penalties')
        for doc_id, p in pens:
            try:
                conn.execute(
                    'INSERT OR IGNORE INTO channel_leave_penalties(user_id,task_id,amount,reason,created_at) VALUES(?,?,?,?,?)',
                    (int(p.get('user_id',0)), int(p.get('task_id',0)),
                     float(p.get('amount',0)), p.get('reason',''), p.get('created_at',''))
                )
            except:
                pass
        print(f'  {len(pens)} ceza kaydi yuklendi')

        conn.commit()
        print('Firebase restore tamamlandi!')


# ════════════════════════════════════════════
#              VERİTABANI
# ════════════════════════════════════════════
class DB:
    def __init__(self, path='taskiz.db', firebase=None):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._lock = threading.Lock()
        self.fb = firebase  # FirebaseClient referansı
        self._setup()
        # Deploy sonrası Firebase'den verileri geri yükle
        if self.fb:
            self.fb.restore_to_sqlite(self)
        print("✅ Veritabanı hazır")

    def q(self, sql, p=()):
        with self._lock:
            self.cur.execute(sql, p)
            self.conn.commit()
            return self.cur

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
                reward              REAL DEFAULT 0.005,
                max_participants    INTEGER DEFAULT 100,
                current_participants INTEGER DEFAULT 0,
                status              TEXT DEFAULT 'active',
                task_type           TEXT DEFAULT 'channel_join',
                -- channel_join | group_join | bot_start
                target_username     TEXT DEFAULT '',
                target_link         TEXT DEFAULT '',
                -- bot_start için: forward edilen mesajın bilgileri
                fwd_chat_id         TEXT DEFAULT '',
                fwd_message_id      INTEGER DEFAULT 0,
                -- görevi kim oluşturdu
                created_by          INTEGER DEFAULT 0,
                -- görev için harcanan bütçe
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
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
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

            CREATE TABLE IF NOT EXISTS admin_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id   INTEGER,
                action     TEXT,
                target_id  INTEGER,
                details    TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS channel_leave_penalties (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                task_id    INTEGER,
                amount     REAL,
                reason     TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        self.conn.commit()

    # ── KULLANICI ────────────────────────────
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
        u = self.get_user(uid)
        if self.fb and u:
            self.fb.save('users', str(uid), dict(u))
            if referred_by:
                self.cur.execute('SELECT * FROM referrals WHERE referred_id=?', (uid,))
                rrow = self.cur.fetchone()
                if rrow:
                    self.fb.save('referrals', str(uid), dict(rrow))
        return u

    def activate_referral(self, referred_id):
        self.cur.execute('SELECT * FROM referrals WHERE referred_id=? AND status="pending"', (referred_id,))
        row = self.cur.fetchone()
        if not row:
            return None
        ref = dict(row)
        rid = ref['referrer_id']
        self.q('UPDATE users SET balance=balance+?,total_referrals=total_referrals+1 WHERE user_id=?',
               (REF_WELCOME_BONUS, rid))
        self.q('UPDATE referrals SET status="active",earned=? WHERE referred_id=?',
               (REF_WELCOME_BONUS, referred_id))
        self.q('INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
               (rid, REF_WELCOME_BONUS, 'ref_bonus', f'Ref: {referred_id}'))
        if self.fb:
            u = self.get_user(rid)
            if u:
                self.fb.save('users', str(rid), dict(u))
            self.cur.execute('SELECT * FROM referrals WHERE referred_id=?', (referred_id,))
            rrow = self.cur.fetchone()
            if rrow:
                self.fb.save('referrals', str(referred_id), dict(rrow))
        return rid

    def update_active(self, uid):
        self.q('UPDATE users SET last_active=CURRENT_TIMESTAMP WHERE user_id=?', (uid,))

    def set_lang(self, uid, lang):
        self.q('UPDATE users SET language=? WHERE user_id=?', (lang, uid))
        if self.fb:
            u = self.get_user(uid)
            if u: self.fb.save('users', str(uid), dict(u))

    def set_ton(self, uid, addr):
        self.q('UPDATE users SET ton_address=? WHERE user_id=?', (addr, uid))
        if self.fb:
            u = self.get_user(uid)
            if u: self.fb.save('users', str(uid), dict(u))

    # ── GÖREVLER ─────────────────────────────
    def create_task(self, title, description, reward, max_p, task_type,
                    target_username, target_link, fwd_chat_id, fwd_message_id,
                    created_by, budget):
        self.q('''INSERT INTO tasks(title,description,reward,max_participants,task_type,
                    target_username,target_link,fwd_chat_id,fwd_message_id,created_by,budget)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
               (title, description, reward, max_p, task_type,
                target_username, target_link, str(fwd_chat_id), fwd_message_id,
                created_by, budget))
        tid = self.cur.lastrowid
        if self.fb:
            task = self.get_task(tid)
            if task: self.fb.save_now('tasks', str(tid), dict(task))
        return tid

    def get_task(self, tid):
        self.cur.execute('SELECT * FROM tasks WHERE id=?', (tid,))
        row = self.cur.fetchone()
        return dict(row) if row else None

    def get_tasks_for_user(self, uid, task_type=None):
        base = '''SELECT t.* FROM tasks t
                  WHERE t.status='active'
                  AND t.current_participants < t.max_participants
                  AND NOT EXISTS(SELECT 1 FROM task_completions c WHERE c.task_id=t.id AND c.user_id=?)'''
        p = [uid]
        if task_type:
            base += ' AND t.task_type=?'
            p.append(task_type)
        base += ' ORDER BY t.reward DESC, t.created_at DESC'
        self.cur.execute(base, p)
        return [dict(r) for r in self.cur.fetchall()]

    def get_all_tasks(self):
        self.cur.execute("SELECT * FROM tasks WHERE status!='deleted' ORDER BY created_at DESC")
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
        # Görev dolunca kapat
        self.cur.execute('SELECT current_participants,max_participants FROM tasks WHERE id=?', (tid,))
        row = self.cur.fetchone()
        if row and row[0] >= row[1]:
            self.q("UPDATE tasks SET status='completed' WHERE id=?", (tid,))
        self.q('UPDATE users SET balance=balance+?,tasks_completed=tasks_completed+1,total_earned=total_earned+? WHERE user_id=?',
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
            if self.fb:
                ref_u = self.get_user(user['referred_by'])
                if ref_u: self.fb.save('users', str(user['referred_by']), dict(ref_u))
        # Firebase sync — kullanici + gorev + tamamlama
        if self.fb:
            fresh = self.get_user(uid)
            if fresh: self.fb.save('users', str(uid), dict(fresh))
            task_fresh = self.get_task(tid)
            if task_fresh: self.fb.save('tasks', str(tid), dict(task_fresh))
            now = datetime.now().isoformat()
            comp_key = f'{uid}_{tid}'
            self.fb.save('task_completions', comp_key, {'task_id': tid, 'user_id': uid, 'created_at': now})
        return reward

    def toggle_task(self, tid):
        self.cur.execute('SELECT status FROM tasks WHERE id=?', (tid,))
        row = self.cur.fetchone()
        if not row:
            return None
        new = 'inactive' if row[0] == 'active' else 'active'
        self.q('UPDATE tasks SET status=? WHERE id=?', (new, tid))
        return new

    def delete_task(self, tid):
        self.q("UPDATE tasks SET status='deleted' WHERE id=?", (tid,))

    # ── ÇEKİM ────────────────────────────────
    def create_withdrawal(self, uid, amount, addr):
        self.q('INSERT INTO withdrawals(user_id,amount,ton_address) VALUES(?,?,?)', (uid, amount, addr))
        wid = self.cur.lastrowid
        self.q('UPDATE users SET balance=balance-? WHERE user_id=?', (amount, uid))
        self.q('INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
               (uid, -amount, 'withdrawal', addr[:20]))
        if self.fb:
            u = self.get_user(uid)
            if u: self.fb.save('users', str(uid), dict(u))
            self.cur.execute('SELECT * FROM withdrawals WHERE id=?', (wid,))
            wd = self.cur.fetchone()
            if wd: self.fb.save_now('withdrawals', str(wid), dict(wd))
        return wid

    def approve_wd(self, wid, admin_id, tx_hash=''):
        self.q("UPDATE withdrawals SET status='paid',tx_hash=?,processed_at=CURRENT_TIMESTAMP WHERE id=?",
               (tx_hash, wid))
        self.q('INSERT INTO admin_logs(admin_id,action,target_id,details) VALUES(?,?,?,?)',
               (admin_id, 'approve_wd', wid, tx_hash))
        if self.fb:
            self.cur.execute('SELECT * FROM withdrawals WHERE id=?', (wid,))
            wd = self.cur.fetchone()
            if wd: self.fb.save('withdrawals', str(wid), dict(wd))

    def reject_wd(self, wid, admin_id, reason=''):
        self.cur.execute('SELECT * FROM withdrawals WHERE id=?', (wid,))
        w = self.cur.fetchone()
        if w:
            w = dict(w)
            self.q("UPDATE withdrawals SET status='rejected',admin_note=? WHERE id=?", (reason, wid))
            self.q('UPDATE users SET balance=balance+? WHERE user_id=?', (w['amount'], w['user_id']))
            self.q('INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
                   (w['user_id'], w['amount'], 'wd_refund', reason or 'Reddedildi'))

    def get_pending_wds(self):
        self.cur.execute('''SELECT w.*,u.first_name,u.username FROM withdrawals w
                           JOIN users u ON w.user_id=u.user_id
                           WHERE w.status='pending' ORDER BY w.created_at ASC''')
        return [dict(r) for r in self.cur.fetchall()]

    # ── ADMİN ─────────────────────────────────
    def add_balance(self, uid, amount, admin_id, reason=''):
        self.q('UPDATE users SET balance=balance+? WHERE user_id=?', (amount, uid))
        self.q('INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
               (uid, amount, 'admin_add', reason or 'Admin'))
        self.q('INSERT INTO admin_logs(admin_id,action,target_id,details) VALUES(?,?,?,?)',
               (admin_id, 'add_balance', uid, f'{amount} TON | {reason}'))
        if self.fb:
            u = self.get_user(uid)
            if u: self.fb.save('users', str(uid), dict(u))

    def remove_balance(self, uid, amount, admin_id):
        self.q('UPDATE users SET balance=MAX(0,balance-?) WHERE user_id=?', (amount, uid))

    def ban(self, uid):
        self.q("UPDATE users SET status='banned' WHERE user_id=?", (uid,))
        if self.fb:
            u = self.get_user(uid)
            if u: self.fb.save('users', str(uid), dict(u))

    def unban(self, uid):
        self.q("UPDATE users SET status='active' WHERE user_id=?", (uid,))
        if self.fb:
            u = self.get_user(uid)
            if u: self.fb.save('users', str(uid), dict(u))

    def search_user(self, term):
        try:
            uid = int(term)
            self.cur.execute('SELECT * FROM users WHERE user_id=?', (uid,))
        except ValueError:
            self.cur.execute('SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ?',
                             (f'%{term}%', f'%{term}%'))
        row = self.cur.fetchone()
        return dict(row) if row else None

    def check_and_penalize_left_channels(self, uid):
        """
        Kullanici kanal/grup gorevini tamamlamis ama kanaldan ayrilmissa
        kazandigi odulu geri al.
        """
        sql = (
            "SELECT tc.task_id, t.reward, t.target_username, t.task_type "
            "FROM task_completions tc "
            "JOIN tasks t ON tc.task_id = t.id "
            "WHERE tc.user_id = ? "
            "AND t.task_type IN ('channel_join','group_join') "
            "AND t.target_username != '' "
            "AND NOT EXISTS ("
            "    SELECT 1 FROM channel_leave_penalties p "
            "    WHERE p.user_id = ? AND p.task_id = tc.task_id"
            ")"
        )
        self.cur.execute(sql, (uid, uid))
        completed = [dict(r) for r in self.cur.fetchall()]
        total_penalized = 0.0
        for task in completed:
            target    = "@" + task['target_username']
            is_member = get_chat_member(target, uid)
            if not is_member:
                amount = task['reward']
                self.cur.execute('SELECT balance FROM users WHERE user_id=?', (uid,))
                row = self.cur.fetchone()
                if row:
                    deduct = min(amount, row[0])
                    if deduct > 0:
                        self.q('UPDATE users SET balance=balance-? WHERE user_id=?', (deduct, uid))
                        self.q(
                            'INSERT INTO channel_leave_penalties(user_id,task_id,amount,reason) VALUES(?,?,?,?)',
                            (uid, task['task_id'], deduct, 'Kanaldan ayrildi: ' + task['target_username'])
                        )
                        self.q(
                            'INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
                            (uid, -deduct, 'channel_leave_penalty', '@' + task['target_username'])
                        )
                        total_penalized += deduct
        return total_penalized

    def stats(self):
        c = self.cur
        return {
            'users':       c.execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'active':      c.execute("SELECT COUNT(*) FROM users WHERE last_active>datetime('now','-1 day')").fetchone()[0],
            'new':         c.execute("SELECT COUNT(*) FROM users WHERE created_at>datetime('now','-1 day')").fetchone()[0],
            'balance':     c.execute('SELECT COALESCE(SUM(balance),0) FROM users').fetchone()[0],
            'pending_wds': c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0],
            'total_paid':  c.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='paid'").fetchone()[0],
            'tasks_done':  c.execute('SELECT COUNT(*) FROM task_completions').fetchone()[0],
            'active_tasks':c.execute("SELECT COUNT(*) FROM tasks WHERE status='active'").fetchone()[0],
        }


# ════════════════════════════════════════════
#              METINLER (3 DİL)
# ════════════════════════════════════════════
_T = {
    'tr': {
        'lang_pick':    "🌍 *DİL SEÇ* — Bir dil seçin:",
        'menu_balance': '💰 Bakiye',
        'menu_tasks':   '🎯 Görevler',
        'menu_invite':  '👥 Davet',
        'menu_withdraw':'💎 Çekim',
        'menu_profile': '👤 Profil',
        'menu_tasks_create':'🛠️ Görev Yayınla',
        'menu_help':    '❓ Yardım',
        'menu_settings':'⚙️ Ayarlar',
        'menu_admin':   '🛡️ Admin',
        'no_tasks':     "📭 Şu an görev yok. Yakında yeni görevler eklenecek!",
        'task_done':    "✅ *Tamamlandı!* +`{reward} TON` eklendi!",
        'task_already': "❌ Bu görevi zaten tamamladınız!",
        'not_member':   "❌ Henüz katılmadınız!\n\n👉 Önce katılın, sonra tekrar deneyin.",
        'wd_low':       "❌ Yetersiz bakiye! Min `{min} TON` gerekli.\n💎 Bakiyen: `{bal} TON`",
        'wd_ok':        "✅ *Çekim Talebi Alındı!*\n💎 `{amount} TON`\n🏦 `{addr}`\n⏳ 24-48 saat",
        'enter_amount': "💰 Çekim miktarını gir (TON):",
        'enter_addr':   "🏦 TON cüzdan adresinizi girin:",
        'bad_num':      "❌ Geçersiz sayı!",
        'bad_addr':     "❌ Geçersiz TON adresi!",
        'ton_saved':    "✅ TON adresin kaydedildi!",
        'check_btn':    "✅ Katıldım, Kontrol Et",
        'channel_check':"⏳ Üyelik kontrol ediliyor...",
    },
    'en': {
        'lang_pick':    "🌍 *SELECT LANGUAGE* — Choose a language:",
        'menu_balance': '💰 Balance',
        'menu_tasks':   '🎯 Tasks',
        'menu_invite':  '👥 Invite',
        'menu_withdraw':'💎 Withdraw',
        'menu_profile': '👤 Profile',
        'menu_tasks_create':'🛠️ Publish Task',
        'menu_help':    '❓ Help',
        'menu_settings':'⚙️ Settings',
        'menu_admin':   '🛡️ Admin',
        'no_tasks':     "📭 No tasks right now. New tasks coming soon!",
        'task_done':    "✅ *Done!* +`{reward} TON` added!",
        'task_already': "❌ You already completed this task!",
        'not_member':   "❌ You haven't joined yet!\n\n👉 Join first, then try again.",
        'wd_low':       "❌ Insufficient balance! Min `{min} TON` needed.\n💎 Balance: `{bal} TON`",
        'wd_ok':        "✅ *Withdrawal Requested!*\n💎 `{amount} TON`\n🏦 `{addr}`\n⏳ 24-48 hours",
        'enter_amount': "💰 Enter withdrawal amount (TON):",
        'enter_addr':   "🏦 Enter your TON wallet address:",
        'bad_num':      "❌ Invalid number!",
        'bad_addr':     "❌ Invalid TON address!",
        'ton_saved':    "✅ TON address saved!",
        'check_btn':    "✅ I Joined, Check",
        'channel_check':"⏳ Checking membership...",
    },
    'pt_br': {
        'lang_pick':    "🌍 *SELECIONAR IDIOMA* — Escolha um idioma:",
        'menu_balance': '💰 Saldo',
        'menu_tasks':   '🎯 Tarefas',
        'menu_invite':  '👥 Convidar',
        'menu_withdraw':'💎 Sacar',
        'menu_profile': '👤 Perfil',
        'menu_tasks_create':'🛠️ Publicar Tarefa',
        'menu_help':    '❓ Ajuda',
        'menu_settings':'⚙️ Ajustes',
        'menu_admin':   '🛡️ Admin',
        'no_tasks':     "📭 Sem tarefas agora. Novas tarefas em breve!",
        'task_done':    "✅ *Concluída!* +`{reward} TON` adicionado!",
        'task_already': "❌ Você já completou esta tarefa!",
        'not_member':   "❌ Você ainda não entrou!\n\n👉 Entre primeiro, depois tente novamente.",
        'wd_low':       "❌ Saldo insuficiente! Mín `{min} TON` necessário.\n💎 Saldo: `{bal} TON`",
        'wd_ok':        "✅ *Saque Solicitado!*\n💎 `{amount} TON`\n🏦 `{addr}`\n⏳ 24-48 horas",
        'enter_amount': "💰 Digite o valor do saque (TON):",
        'enter_addr':   "🏦 Digite seu endereço de carteira TON:",
        'bad_num':      "❌ Número inválido!",
        'bad_addr':     "❌ Endereço TON inválido!",
        'ton_saved':    "✅ Endereço TON salvo!",
        'check_btn':    "✅ Entrei, Verificar",
        'channel_check':"⏳ Verificando participação...",
    },
}

def T(lang, key, **kw):
    lang = lang if lang in _T else 'en'
    txt  = _T[lang].get(key, _T['en'].get(key, key))
    if kw:
        try:
            txt = txt.format(**kw)
        except:
            pass
    return txt

ALL_LANGS = list(SUPPORTED_LANGUAGES.keys())

def all_menu_labels(key):
    return [T(l, key) for l in ALL_LANGS]


# ════════════════════════════════════════════
#              ANA BOT
# ════════════════════════════════════════════
class Bot:
    def __init__(self):
        fb            = FirebaseClient()
        self.db       = DB(firebase=fb)
        self.firebase = fb
        self.states   = {}   # user_id → dict
        print(f"🤖 {BOT_NAME} hazır!")

    # ──────────────────────────────────────────
    #   KANAL KONTROLÜ
    # ──────────────────────────────────────────
    def missing_channels(self, uid):
        return [ch for ch in MANDATORY_CHANNELS + MANDATORY_GROUPS
                if not get_chat_member(f"@{ch['username']}", uid)]

    def enforce_channels(self, uid, lang):
        missing = self.missing_channels(uid)
        if not missing:
            return True
        all_req = MANDATORY_CHANNELS + MANDATORY_GROUPS
        joined  = [c for c in all_req if c not in missing]
        lines   = [f"✅ {c['emoji']} {c['name']}" for c in joined] + \
                  [f"❌ {c['emoji']} {c['name']}" for c in missing]
        texts   = {
            'tr':    "⚠️ *ZORUNLU ÜYELİK*\n\n" + '\n'.join(lines) + "\n\n👇 Kanala katıl, sonra *Kontrol Et* butonuna bas.",
            'en':    "⚠️ *MANDATORY MEMBERSHIP*\n\n" + '\n'.join(lines) + "\n\n👇 Join the channel then press *Check*.",
            'pt_br': "⚠️ *PARTICIPAÇÃO OBRIGATÓRIA*\n\n" + '\n'.join(lines) + "\n\n👇 Entre no canal e pressione *Verificar*.",
        }
        buttons = [[{'text': f"👉 {c['emoji']} {c['name']}", 'url': c['link']}] for c in missing]
        buttons.append([{'text': T(lang, 'check_btn'), 'callback_data': 'check_channels'}])
        send_message(uid, texts.get(lang, texts['en']), reply_markup={'inline_keyboard': buttons})
        return False

    # ──────────────────────────────────────────
    #   KLAVYE
    # ──────────────────────────────────────────
    def main_kb(self, lang, is_admin=False):
        rows = [
            [T(lang,'menu_balance'),       T(lang,'menu_tasks')],
            [T(lang,'menu_withdraw'),      T(lang,'menu_invite')],
            [T(lang,'menu_tasks_create'),  T(lang,'menu_profile')],
            [T(lang,'menu_settings'),      T(lang,'menu_help')],
        ]
        if is_admin:
            rows.append([T(lang,'menu_admin')])
        return {'keyboard': rows, 'resize_keyboard': True, 'one_time_keyboard': False}

    # ──────────────────────────────────────────
    #   DİL SEÇİMİ
    # ──────────────────────────────────────────
    def show_lang_select(self, uid):
        send_message(uid,
            "🌍 *DİL / LANGUAGE / IDIOMA*\nLütfen dilinizi seçin / Please choose / Por favor escolha:",
            reply_markup={'inline_keyboard': [
                [{'text': '🇹🇷 Türkçe',             'callback_data': 'lang_tr'}],
                [{'text': '🇺🇸 English',            'callback_data': 'lang_en'}],
                [{'text': '🇧🇷 Português (Brasil)', 'callback_data': 'lang_pt_br'}],
            ]})

    # ──────────────────────────────────────────
    #   ANA MENÜ
    # ──────────────────────────────────────────
    def show_menu(self, uid, lang=None):
        user = self.db.get_user(uid)
        if not user:
            return
        if not lang:
            lang = user['language']
        if not self.enforce_channels(uid, lang):
            return
        stars = '⭐' * min(5, max(1, int(user['total_referrals'] / 5) + 1))
        msgs  = {
            'tr': f"""╔══════════════════════╗
║   🚀  *{BOT_NAME}*   ║
╚══════════════════════╝
👋 Hoş geldin, *{user['first_name']}*! {stars}
┌──────────────────────
│ 💎 Bakiye:    `{user['balance']:.4f} TON`
│ 🎯 Görevler:  `{user['tasks_completed']}`
│ 👥 Referans:  `{user['total_referrals']}`
│ 📈 Kazanç:    `{user['total_earned']:.4f} TON`
└──────────────────────
💡 Görev tamamla → TON kazan!
🔗 Davet et → +{REF_WELCOME_BONUS} TON/kişi!
🛠️ Kendi görevini yayınla!""",
            'en': f"""╔══════════════════════╗
║   🚀  *{BOT_NAME}*   ║
╚══════════════════════╝
👋 Welcome, *{user['first_name']}*! {stars}
┌──────────────────────
│ 💎 Balance:   `{user['balance']:.4f} TON`
│ 🎯 Tasks:     `{user['tasks_completed']}`
│ 👥 Referrals: `{user['total_referrals']}`
│ 📈 Earned:    `{user['total_earned']:.4f} TON`
└──────────────────────
💡 Complete tasks → Earn TON!
🔗 Invite → +{REF_WELCOME_BONUS} TON/person!
🛠️ Publish your own tasks!""",
            'pt_br': f"""╔══════════════════════╗
║   🚀  *{BOT_NAME}*   ║
╚══════════════════════╝
👋 Bem-vindo, *{user['first_name']}*! {stars}
┌──────────────────────
│ 💎 Saldo:     `{user['balance']:.4f} TON`
│ 🎯 Tarefas:   `{user['tasks_completed']}`
│ 👥 Indicações:`{user['total_referrals']}`
│ 📈 Ganhos:    `{user['total_earned']:.4f} TON`
└──────────────────────
💡 Conclua tarefas → Ganhe TON!
🔗 Convide → +{REF_WELCOME_BONUS} TON/pessoa!
🛠️ Publique suas próprias tarefas!""",
        }
        send_message(uid, msgs.get(lang, msgs['en']),
                     reply_markup=self.main_kb(lang, str(uid) in ADMIN_IDS))

    # ──────────────────────────────────────────
    #   GÖREVLER
    # ──────────────────────────────────────────
    def show_tasks(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang  = user['language']
        if not self.enforce_channels(uid, lang):
            return
        # Tamamladığı kanal görevlerini kontrol et (kanaldan çıktıysa ceza)
        self.db.check_and_penalize_left_channels(uid)
        tasks = self.db.get_tasks_for_user(uid)
        if not tasks:
            send_message(uid, T(lang, 'no_tasks'), reply_markup={'inline_keyboard': [
                [{'text': '🔄 Yenile', 'callback_data': 'refresh_tasks'}],
                [{'text': '🏠 Menü',   'callback_data': 'main_menu'}],
            ]})
            return

        type_icons = {'channel_join': '📢', 'group_join': '👥', 'bot_start': '🤖'}
        hdrs = {
            'tr':    f"🎯 *GÖREVLER* — {len(tasks)} görev mevcut\n\n💡 Bir göreve tıkla:",
            'en':    f"🎯 *TASKS* — {len(tasks)} available\n\n💡 Tap a task:",
            'pt_br': f"🎯 *TAREFAS* — {len(tasks)} disponíveis\n\n💡 Toque em uma tarefa:",
        }
        buttons = []
        for task in tasks[:15]:
            icon  = type_icons.get(task['task_type'], '🎯')
            filled = task['current_participants']
            total  = task['max_participants']
            pct    = int((filled / total) * 8) if total else 0
            bar    = '█' * pct + '░' * (8 - pct)
            buttons.append([{
                'text': f"{icon} {task['title']}  •  {task['reward']:.4f} TON  [{bar}]",
                'callback_data': f"task_{task['id']}"
            }])
        buttons.append([
            {'text': '🔄 Yenile', 'callback_data': 'refresh_tasks'},
            {'text': '🏠 Menü',   'callback_data': 'main_menu'},
        ])
        send_message(uid, hdrs.get(lang, hdrs['en']),
                     reply_markup={'inline_keyboard': buttons})

    # ──────────────────────────────────────────
    #   GÖREV DETAY
    # ──────────────────────────────────────────
    def show_task_detail(self, uid, tid, cb_id=None):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        task = self.db.get_task(tid)
        if not task:
            if cb_id:
                answer_callback(cb_id, "❌ Görev bulunamadı", True)
            return

        if cb_id:
            answer_callback(cb_id)

        already = self.db.has_done(uid, tid)
        type_labels = {
            'tr':    {'channel_join': '📢 Kanal Katılım', 'group_join': '👥 Grup Katılım', 'bot_start': '🤖 Bot Görevi'},
            'en':    {'channel_join': '📢 Channel Join',  'group_join': '👥 Group Join',   'bot_start': '🤖 Bot Task'},
            'pt_br': {'channel_join': '📢 Entrar no Canal','group_join': '👥 Entrar no Grupo','bot_start': '🤖 Tarefa Bot'},
        }
        type_lbl = type_labels.get(lang, type_labels['en']).get(task['task_type'], '🎯')

        descs = {
            'tr': f"""🎯 *{task['title']}*
━━━━━━━━━━━━━━━━
{f"📝 {task['description']}" if task['description'] else ""}
━━━━━━━━━━━━━━━━
💎 Ödül:     `{task['reward']:.4f} TON`
🏷️ Tür:      {type_lbl}
👥 Katılım:  {task['current_participants']}/{task['max_participants']}
{"━━━━━━━━━━━━━━━━"+chr(10)+"✅ Bu görevi tamamladınız!" if already else ""}""",
            'en': f"""🎯 *{task['title']}*
━━━━━━━━━━━━━━━━
{f"📝 {task['description']}" if task['description'] else ""}
━━━━━━━━━━━━━━━━
💎 Reward:    `{task['reward']:.4f} TON`
🏷️ Type:      {type_lbl}
👥 Participants:{task['current_participants']}/{task['max_participants']}
{"━━━━━━━━━━━━━━━━"+chr(10)+"✅ You already completed this task!" if already else ""}""",
            'pt_br': f"""🎯 *{task['title']}*
━━━━━━━━━━━━━━━━
{f"📝 {task['description']}" if task['description'] else ""}
━━━━━━━━━━━━━━━━
💎 Recompensa:`{task['reward']:.4f} TON`
🏷️ Tipo:      {type_lbl}
👥 Participantes:{task['current_participants']}/{task['max_participants']}
{"━━━━━━━━━━━━━━━━"+chr(10)+"✅ Você já completou esta tarefa!" if already else ""}""",
        }
        text = descs.get(lang, descs['en'])

        if already:
            send_message(uid, text, reply_markup={'inline_keyboard': [
                [{'text': '🔙 Görevler', 'callback_data': 'show_tasks'}],
            ]})
            return

        tt = task['task_type']
        buttons = []

        if tt in ('channel_join', 'group_join'):
            if task['target_link']:
                join_labels = {'tr': '👉 Katıl', 'en': '👉 Join', 'pt_br': '👉 Entrar'}
                buttons.append([{'text': join_labels.get(lang, join_labels['en']), 'url': task['target_link']}])
            verify_labels = {'tr': '✅ Katıldım, Ödülü Al', 'en': '✅ I Joined, Get Reward', 'pt_br': '✅ Entrei, Pegar Recompensa'}
            buttons.append([{'text': verify_labels.get(lang, verify_labels['en']),
                             'callback_data': f'verify_{tid}'}])

        elif tt == 'bot_start':
            # Bot görevinde: önce forward mesajını göster, sonra buton
            if task['fwd_chat_id'] and task['fwd_message_id']:
                go_labels    = {'tr': '🤖 Bota Git', 'en': '🤖 Go to Bot', 'pt_br': '🤖 Ir para o Bot'}
                done_labels  = {'tr': '✅ Botu Başlattım, Ödülü Al', 'en': '✅ I Started the Bot, Get Reward', 'pt_br': '✅ Iniciei o Bot, Pegar Recompensa'}
                if task['target_link']:
                    buttons.append([{'text': go_labels.get(lang, go_labels['en']), 'url': task['target_link']}])
                buttons.append([{'text': done_labels.get(lang, done_labels['en']),
                                 'callback_data': f'done_bot_{tid}'}])
            else:
                # Forward mesajı yoksa düz buton
                go_labels = {'tr': '🤖 Bota Git', 'en': '🤖 Go to Bot', 'pt_br': '🤖 Ir para o Bot'}
                if task['target_link']:
                    buttons.append([{'text': go_labels.get(lang, go_labels['en']), 'url': task['target_link']}])
                buttons.append([{'text': '✅ Tamamladım', 'callback_data': f'done_bot_{tid}'}])

        back_labels = {'tr': '🔙 Geri', 'en': '🔙 Back', 'pt_br': '🔙 Voltar'}
        buttons.append([
            {'text': back_labels.get(lang, back_labels['en']), 'callback_data': 'show_tasks'},
            {'text': '🏠 Menü', 'callback_data': 'main_menu'},
        ])

        # Bot görevi için forward mesajını önce gönder
        if tt == 'bot_start' and task['fwd_chat_id'] and task['fwd_message_id']:
            try:
                copy_message(uid, task['fwd_chat_id'], task['fwd_message_id'])
            except:
                pass

        send_message(uid, text, reply_markup={'inline_keyboard': buttons})

    def verify_membership(self, uid, tid, cb_id):
        """Kanal/grup üyeliğini kontrol et ve görevi tamamla"""
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

        answer_callback(cb_id, T(lang, 'channel_check'))

        target = task['target_username']
        if target:
            target_id = f"@{target.lstrip('@')}"
            if not get_chat_member(target_id, uid):
                fail = {
                    'tr':    f"❌ *Henüz katılmadınız!*\n\n👉 Önce @{target} kanalına/grubuna katılın.",
                    'en':    f"❌ *You haven't joined yet!*\n\n👉 Join @{target} first.",
                    'pt_br': f"❌ *Você ainda não entrou!*\n\n👉 Entre em @{target} primeiro.",
                }
                keyboard = {'inline_keyboard': [
                    [{'text': '👉 Git / Go', 'url': task['target_link']}],
                    [{'text': '🔄 Tekrar Dene / Retry', 'callback_data': f'verify_{tid}'}],
                ]}
                send_message(uid, fail.get(lang, fail['en']), reply_markup=keyboard)
                return

        reward = self.db.complete_task(uid, tid)
        if reward:
            send_message(uid, T(lang, 'task_done', reward=f'{reward:.4f}'),
                         reply_markup={'inline_keyboard': [
                             [{'text': '🎯 Daha Fazla Görev', 'callback_data': 'show_tasks'}],
                             [{'text': '💰 Bakiye',           'callback_data': 'show_balance'}],
                         ]})
        else:
            answer_callback(cb_id, T(lang, 'task_already'), True)

    def done_bot_task(self, uid, tid, cb_id):
        """Bot görevi tamamla (sadece tıklama yeterli)"""
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        if self.db.has_done(uid, tid):
            answer_callback(cb_id, T(lang, 'task_already'), True)
            return
        reward = self.db.complete_task(uid, tid)
        if reward:
            answer_callback(cb_id, f"✅ +{reward:.4f} TON!", True)
            send_message(uid, T(lang, 'task_done', reward=f'{reward:.4f}'),
                         reply_markup={'inline_keyboard': [
                             [{'text': '🎯 Daha Fazla Görev', 'callback_data': 'show_tasks'}],
                             [{'text': '💰 Bakiye',           'callback_data': 'show_balance'}],
                         ]})

    # ──────────────────────────────────────────
    #   GÖREV YAYINLA (HERKES)
    # ──────────────────────────────────────────
    def show_task_publish(self, uid):
        """Herkesin görev oluşturma ekranı"""
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        msgs = {
            'tr': f"""🛠️ *GÖREV YAYINLA*
━━━━━━━━━━━━━━━━
Kendi kanalın/grubun/botun için görev yayınla.
Kullanıcılar görevi tamamladıkça sen de büyürsün!

💎 Bakiyen: `{user['balance']:.4f} TON`

*Görev Türleri:*
📢 Kanal — Kullanıcı kanala katılır
👥 Grup — Kullanıcı gruba katılır
🤖 Bot — Kullanıcı botunu başlatır (forward mesajı gerekir)

*Bütçe Seçenekleri:*
Bütçe = Katılımcı başı {TASK_REWARD_PER_USER} TON ödül
━━━━━━━━━━━━━━━━
Görev türünü seç:""",
            'en': f"""🛠️ *PUBLISH TASK*
━━━━━━━━━━━━━━━━
Publish a task for your channel/group/bot.
Users complete it and your audience grows!

💎 Balance: `{user['balance']:.4f} TON`

*Task Types:*
📢 Channel — User joins your channel
👥 Group — User joins your group
🤖 Bot — User starts your bot (forward message required)

*Budget Options:*
Budget = {TASK_REWARD_PER_USER} TON reward per participant
━━━━━━━━━━━━━━━━
Select task type:""",
            'pt_br': f"""🛠️ *PUBLICAR TAREFA*
━━━━━━━━━━━━━━━━
Publique uma tarefa para seu canal/grupo/bot.
Usuários completam e sua audiência cresce!

💎 Saldo: `{user['balance']:.4f} TON`

*Tipos de Tarefa:*
📢 Canal — Usuário entra no seu canal
👥 Grupo — Usuário entra no seu grupo
🤖 Bot — Usuário inicia seu bot (mensagem forward necessária)

*Opções de Orçamento:*
Orçamento = recompensa de {TASK_REWARD_PER_USER} TON por participante
━━━━━━━━━━━━━━━━
Selecione o tipo de tarefa:""",
        }
        keyboard = {'inline_keyboard': [
            [{'text': '📢 Kanal Görevi',  'callback_data': 'pub_type_channel_join'}],
            [{'text': '👥 Grup Görevi',   'callback_data': 'pub_type_group_join'}],
            [{'text': '🤖 Bot Görevi',    'callback_data': 'pub_type_bot_start'}],
            [{'text': '🏠 Menü',          'callback_data': 'main_menu'}],
        ]}
        send_message(uid, msgs.get(lang, msgs['en']), reply_markup=keyboard)

    def pub_type_selected(self, uid, task_type, cb_id):
        """Görev türü seçildi"""
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        answer_callback(cb_id)
        self.states[uid] = {'action': 'pub_title', 'task_type': task_type}
        type_names = {
            'tr':    {'channel_join': '📢 Kanal', 'group_join': '👥 Grup', 'bot_start': '🤖 Bot'},
            'en':    {'channel_join': '📢 Channel', 'group_join': '👥 Group', 'bot_start': '🤖 Bot'},
            'pt_br': {'channel_join': '📢 Canal', 'group_join': '👥 Grupo', 'bot_start': '🤖 Bot'},
        }
        tname  = type_names.get(lang, type_names['en']).get(task_type, task_type)
        reward = TASK_REWARDS.get(task_type, 0.001)
        msgs   = {
            'tr':    f"✅ Tür: *{tname}*\n💎 Katılımcı başı ödül: `{reward} TON`\n\n📌 *Görev başlığını gir:*\n_(Kısa ve çekici, örn: TaskizBot\'u Başlat!)_",
            'en':    f"✅ Type: *{tname}*\n💎 Reward per user: `{reward} TON`\n\n📌 *Enter task title:*\n_(Short and catchy, e.g: Start TaskizBot!)_",
            'pt_br': f"✅ Tipo: *{tname}*\n💎 Recompensa por usuário: `{reward} TON`\n\n📌 *Digite o título da tarefa:*\n_(Curto e atraente, ex: Iniciar TaskizBot!)_",
        }
        send_message(uid, msgs.get(lang, msgs['en']),
                     reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})

    def pub_handle_step(self, uid, text):
        """Görev oluşturma adımları (metin girişi)"""
        user   = self.db.get_user(uid)
        if not user:
            return
        lang   = user['language']
        state  = self.states.get(uid, {})
        action = state.get('action', '')
        cancel_kb = {'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]}

        if action == 'pub_title':
            state['title']   = text.strip()
            state['action']  = 'pub_description'
            self.states[uid] = state
            desc_prompts = {
                'tr':    "📝 *Açıklama gir:*\n_(Kullanıcıya ne yapacağını anlat, örn: Botumu başlat ve menüye gir!)_\n\n⏭️ Atlamak için - yazabilirsin",
                'en':    "📝 *Enter description:*\n_(Tell users what to do, e.g: Start my bot and open the menu!)_\n\n⏭️ Type - to skip",
                'pt_br': "📝 *Digite a descrição:*\n_(Diga aos usuários o que fazer, ex: Inicie meu bot e abra o menu!)_\n\n⏭️ Digite - para pular",
            }
            send_message(uid, desc_prompts.get(lang, desc_prompts['en']), reply_markup=cancel_kb)

        elif action == 'pub_description':
            state['description'] = '' if text.strip() == '-' else text.strip()
            state['action']      = 'pub_username'
            self.states[uid]     = state
            tt = state.get('task_type', '')
            prompts = {
                'tr':    {'channel_join': '📢 *Kanal kullanıcı adını gir* (@ olmadan):\n_Örn: TaskizLive_',
                          'group_join':   '👥 *Grup kullanıcı adını gir* (@ olmadan):',
                          'bot_start':    '🤖 *Bot kullanıcı adını gir* (@ olmadan):\n_Örn: TaskizBot_'},
                'en':    {'channel_join': '📢 *Enter channel username* (without @):\n_e.g: TaskizLive_',
                          'group_join':   '👥 *Enter group username* (without @):',
                          'bot_start':    '🤖 *Enter bot username* (without @):\n_e.g: TaskizBot_'},
                'pt_br': {'channel_join': '📢 *Digite o username do canal* (sem @):\n_ex: TaskizLive_',
                          'group_join':   '👥 *Digite o username do grupo* (sem @):',
                          'bot_start':    '🤖 *Digite o username do bot* (sem @):\n_ex: TaskizBot_'},
            }
            send_message(uid, prompts.get(lang, prompts['en']).get(tt, 'Username:'), reply_markup=cancel_kb)

        elif action == 'pub_username':
            username = text.strip().lstrip('@')
            state['target_username'] = username
            state['target_link']     = f"https://t.me/{username}"
            state['action'] = 'pub_budget'
            self.states[uid] = state
            self._show_budget_select(uid, lang)

        elif action == 'pub_budget_custom':
            try:
                budget = float(text.replace(',', '.'))
                if budget <= 0:
                    raise ValueError
                self._pub_budget_chosen(uid, lang, budget)
            except ValueError:
                send_message(uid, T(lang, 'bad_num'), reply_markup=cancel_kb)

    def _show_budget_select(self, uid, lang):
        """Bütçe seçim ekranı — görev türüne göre ödül hesapla"""
        state   = self.states.get(uid, {})
        tt      = state.get('task_type', 'channel_join')
        reward  = TASK_REWARDS.get(tt, 0.001)
        type_labels = {
            'tr':    {'channel_join': '📢 Kanal', 'group_join': '👥 Grup', 'bot_start': '🤖 Bot'},
            'en':    {'channel_join': '📢 Channel', 'group_join': '👥 Group', 'bot_start': '🤖 Bot'},
            'pt_br': {'channel_join': '📢 Canal', 'group_join': '👥 Grupo', 'bot_start': '🤖 Bot'},
        }
        tname = type_labels.get(lang, type_labels['en']).get(tt, tt)
        msgs = {
            'tr':    f"💰 *BÜTÇE SEÇ* — {tname}\n\n💎 Katılımcı başı ödül: `{reward} TON`\n👥 Katılımcı = Bütçe ÷ {reward}\n\nBakiyenden düşülecek:",
            'en':    f"💰 *SELECT BUDGET* — {tname}\n\n💎 Reward per user: `{reward} TON`\n👥 Participants = Budget ÷ {reward}\n\nWill be deducted from your balance:",
            'pt_br': f"💰 *SELECIONAR ORÇAMENTO* — {tname}\n\n💎 Recompensa por usuário: `{reward} TON`\n👥 Participantes = Orçamento ÷ {reward}\n\nSerá deduzido do seu saldo:",
        }
        buttons = []
        for budget in TASK_BUDGET_OPTIONS:
            participants = int(budget / reward)
            buttons.append([{'text': f"💎 {budget} TON → {participants} katılımcı  ({reward} TON/kişi)",
                             'callback_data': f"pub_budget_{budget}"}])
        custom_labels = {'tr': '✏️ Özel Miktar Gir', 'en': '✏️ Enter Custom Amount', 'pt_br': '✏️ Digitar Valor Personalizado'}
        buttons.append([{'text': custom_labels.get(lang, custom_labels['en']),
                         'callback_data': 'pub_budget_custom'}])
        buttons.append([{'text': '❌ İptal', 'callback_data': 'cancel'}])
        send_message(uid, msgs.get(lang, msgs['en']), reply_markup={'inline_keyboard': buttons})

    def _pub_budget_chosen(self, uid, lang, budget):
        """Bütçe seçildi, onay ekranı göster"""
        user = self.db.get_user(uid)
        if not user:
            return
        if user['balance'] < budget:
            send_message(uid, T(lang, 'wd_low', min=budget, bal=f"{user['balance']:.4f}"),
                         reply_markup={'inline_keyboard': [
                             [{'text': '🎯 Görev Yap',  'callback_data': 'show_tasks'}],
                             [{'text': '🏠 Menü',       'callback_data': 'main_menu'}],
                         ]})
            return

        state  = self.states.get(uid, {})
        tt     = state.get('task_type', 'channel_join')
        reward = TASK_REWARDS.get(tt, 0.001)
        max_p  = max(1, int(budget / reward))
        state['budget']  = budget
        state['max_p']   = max_p
        state['reward']  = reward
        state['action']  = 'pub_confirm'
        self.states[uid] = state

        tt = state.get('task_type', '')
        type_names = {
            'tr':    {'channel_join': '📢 Kanal', 'group_join': '👥 Grup', 'bot_start': '🤖 Bot'},
            'en':    {'channel_join': '📢 Channel', 'group_join': '👥 Group', 'bot_start': '🤖 Bot'},
            'pt_br': {'channel_join': '📢 Canal', 'group_join': '👥 Grupo', 'bot_start': '🤖 Bot'},
        }
        tname = type_names.get(lang, type_names['en']).get(tt, tt)

        # Bot göreviyse forward mesajı iste
        if tt == 'bot_start':
            state['action'] = 'pub_forward_wait'
            self.states[uid] = state
            fw_msgs = {
                'tr':    "📨 *FORWARD MESAJI*\n\nBot göreviniz için kullanıcılara gösterilecek bir mesaj ilet!\n\nBotunuzdan veya herhangi bir kanaldan bir mesajı *şimdi forward et:*",
                'en':    "📨 *FORWARD MESSAGE*\n\nForward a message that will be shown to users for your bot task!\n\n*Forward a message now* from your bot or any channel:",
                'pt_br': "📨 *MENSAGEM FORWARD*\n\nEnvie uma mensagem que será mostrada aos usuários para sua tarefa de bot!\n\n*Encaminhe uma mensagem agora* do seu bot ou qualquer canal:",
            }
            send_message(uid, fw_msgs.get(lang, fw_msgs['en']),
                         reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})
            return

        # Kanal/grup için direkt onay
        self._show_pub_confirm(uid, lang, state)

    def _show_pub_confirm(self, uid, lang, state):
        tt = state.get('task_type', '')
        type_names = {
            'tr':    {'channel_join': '📢 Kanal', 'group_join': '👥 Grup', 'bot_start': '🤖 Bot'},
            'en':    {'channel_join': '📢 Channel', 'group_join': '👥 Group', 'bot_start': '🤖 Bot'},
            'pt_br': {'channel_join': '📢 Canal', 'group_join': '👥 Grupo', 'bot_start': '🤖 Bot'},
        }
        tname = type_names.get(lang, type_names['en']).get(tt, tt)
        fwd_info = ""
        if tt == 'bot_start' and state.get('fwd_message_id'):
            fwd_info = "\n📨 Forward: ✅ Mesaj alındı"

        msgs = {
            'tr': f"""✅ *GÖREV ÖNİZLEME*
━━━━━━━━━━━━━━━━
📌 Başlık:     *{state.get('title', '—')}*
🏷️ Tür:        {tname}
🎯 Hedef:      @{state.get('target_username', '—')}
💎 Ödül/kişi: `{state.get('reward', 0):.4f} TON`
👥 Max:        `{state.get('max_p', 0)} kişi`
💰 Toplam:     `{state.get('budget', 0):.4f} TON`{fwd_info}
━━━━━━━━━━━━━━━━
Onaylıyor musun?""",
            'en': f"""✅ *TASK PREVIEW*
━━━━━━━━━━━━━━━━
📌 Title:      *{state.get('title', '—')}*
🏷️ Type:       {tname}
🎯 Target:     @{state.get('target_username', '—')}
💎 Reward:    `{state.get('reward', 0):.4f} TON`/user
👥 Max:       `{state.get('max_p', 0)} users`
💰 Total:     `{state.get('budget', 0):.4f} TON`{fwd_info}
━━━━━━━━━━━━━━━━
Confirm?""",
            'pt_br': f"""✅ *PRÉVIA DA TAREFA*
━━━━━━━━━━━━━━━━
📌 Título:     *{state.get('title', '—')}*
🏷️ Tipo:       {tname}
🎯 Alvo:       @{state.get('target_username', '—')}
💎 Recompensa:`{state.get('reward', 0):.4f} TON`/usuário
👥 Máx:       `{state.get('max_p', 0)} usuários`
💰 Total:     `{state.get('budget', 0):.4f} TON`{fwd_info}
━━━━━━━━━━━━━━━━
Confirmar?""",
        }
        ok_labels   = {'tr': '✅ Yayınla',     'en': '✅ Publish',    'pt_br': '✅ Publicar'}
        back_labels = {'tr': '🔙 Bütçe Değiştir','en': '🔙 Change Budget','pt_br': '🔙 Alterar Orçamento'}
        keyboard = {'inline_keyboard': [
            [{'text': ok_labels.get(lang, ok_labels['en']),   'callback_data': 'pub_save'}],
            [{'text': back_labels.get(lang, back_labels['en']),'callback_data': 'pub_budget_back'}],
            [{'text': '❌ İptal', 'callback_data': 'cancel'}],
        ]}
        send_message(uid, msgs.get(lang, msgs['en']), reply_markup=keyboard)

    def pub_handle_forward(self, uid, message):
        """Kullanıcı forward mesajı gönderdi"""
        user  = self.db.get_user(uid)
        state = self.states.get(uid, {})
        if state.get('action') != 'pub_forward_wait':
            return False
        lang = user['language'] if user else 'tr'

        # Forward bilgilerini çıkar
        fwd_chat     = (message.get('forward_from_chat') or
                        message.get('forward_origin', {}).get('chat', {}))
        fwd_msg_id   = (message.get('forward_from_message_id') or
                        message.get('forward_origin', {}).get('message_id'))
        fwd_chat_id  = fwd_chat.get('id') if fwd_chat else None

        if not fwd_chat_id or not fwd_msg_id:
            fail_msgs = {
                'tr':    "❌ *Forward bilgisi alınamadı!*\n\nBir kanaldan veya bottan mesajı doğrudan forward edin.\n_(Bazı kanallar forwarding'i engelliyor olabilir)_",
                'en':    "❌ *Couldn't get forward info!*\n\nPlease forward a message directly from a channel or bot.\n_(Some channels may disable forwarding)_",
                'pt_br': "❌ *Não foi possível obter informações de forward!*\n\nEncaminhe uma mensagem diretamente de um canal ou bot.",
            }
            send_message(uid, fail_msgs.get(lang, fail_msgs['en']),
                         reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})
            return True

        state['fwd_chat_id']    = str(fwd_chat_id)
        state['fwd_message_id'] = fwd_msg_id
        state['action']         = 'pub_confirm'
        self.states[uid]        = state

        ok_msgs = {
            'tr':    "✅ *Mesaj alındı!* Şimdi görevi onaylayın:",
            'en':    "✅ *Message received!* Now confirm your task:",
            'pt_br': "✅ *Mensagem recebida!* Agora confirme sua tarefa:",
        }
        send_message(uid, ok_msgs.get(lang, ok_msgs['en']))
        self._show_pub_confirm(uid, lang, state)
        return True

    def pub_save(self, uid, cb_id):
        """Görevi kaydet ve bakiyeyi düş"""
        user  = self.db.get_user(uid)
        state = self.states.get(uid, {})
        if not user or not state:
            return
        lang   = user['language']
        budget = state.get('budget', 0)
        answer_callback(cb_id)

        if user['balance'] < budget:
            send_message(uid, T(lang, 'wd_low', min=budget, bal=f"{user['balance']:.4f}"))
            return

        # Bakiyeden düş
        self.db.q('UPDATE users SET balance=balance-? WHERE user_id=?', (budget, uid))
        self.db.q('INSERT INTO txns(user_id,amount,type,note) VALUES(?,?,?,?)',
                  (uid, -budget, 'task_budget', state.get('title', '')))

        tid = self.db.create_task(
            title           = state.get('title', 'Görev'),
            description     = '',
            reward          = state.get('reward', TASK_REWARD_PER_USER),
            max_p           = state.get('max_p', 100),
            task_type       = state.get('task_type', 'channel_join'),
            target_username = state.get('target_username', ''),
            target_link     = state.get('target_link', ''),
            fwd_chat_id     = state.get('fwd_chat_id', ''),
            fwd_message_id  = state.get('fwd_message_id', 0),
            created_by      = uid,
            budget          = budget,
        )

        if uid in self.states:
            del self.states[uid]

        success_msgs = {
            'tr': f"🎉 *Görev #{tid} Yayınlandı!*\n\n📌 {state.get('title','')}\n💎 Bütçe: `{budget:.4f} TON`\n👥 Max: `{state.get('max_p',0)} kişi`\n\nGöreviniz artık herkese görünür!",
            'en': f"🎉 *Task #{tid} Published!*\n\n📌 {state.get('title','')}\n💎 Budget: `{budget:.4f} TON`\n👥 Max: `{state.get('max_p',0)} users`\n\nYour task is now visible to everyone!",
            'pt_br': f"🎉 *Tarefa #{tid} Publicada!*\n\n📌 {state.get('title','')}\n💎 Orçamento: `{budget:.4f} TON`\n👥 Máx: `{state.get('max_p',0)} usuários`\n\nSua tarefa agora está visível para todos!",
        }
        send_message(uid, success_msgs.get(lang, success_msgs['en']),
                     reply_markup={'inline_keyboard': [
                         [{'text': '🎯 Görevleri Gör', 'callback_data': 'show_tasks'}],
                         [{'text': '🏠 Menü',          'callback_data': 'main_menu'}],
                     ]})
        # İstatistik kanalına bildir
        try:
            send_message(STATS_CHANNEL, f"🛠️ *YENİ GÖREV #{tid}*\n{state.get('title','')}\n💎 {budget:.4f} TON | 👤 {uid}")
        except:
            pass

    # ──────────────────────────────────────────
    #   BAKİYE / ÇEKİM / DAVET / PROFİL
    # ──────────────────────────────────────────
    def show_balance(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        # Kanaldan ayrıldıysa ceza uygula
        penalty = self.db.check_and_penalize_left_channels(uid)
        # Güncel bakiyeyle devam et
        user = self.db.get_user(uid)
        if penalty and penalty > 0:
            pen_str = f"{penalty:.4f}"
            warn_msgs = {
                'tr':    "⚠️ *Bakiye Düşürüldü!*\n\nKatıldığın bir kanaldan/gruptan ayrıldın.\n💸 `-" + pen_str + " TON` bakiyenden düşüldü.",
                'en':    "⚠️ *Balance Deducted!*\n\nYou left a channel/group you joined.\n💸 `-" + pen_str + " TON` deducted from your balance.",
                'pt_br': "⚠️ *Saldo Deduzido!*\n\nVocê saiu de um canal/grupo que entrou.\n💸 `-" + pen_str + " TON` deduzido do seu saldo.",
            }
            send_message(uid, warn_msgs.get(lang, warn_msgs['en']))
        msgs = {
            'tr': f"""💰 *BAKİYE*
━━━━━━━━━━━━━━━━
💎 Mevcut: `{user['balance']:.4f} TON`
━━━━━━━━━━━━━━━━
📊 Kazanç:   `{user['total_earned']:.4f} TON`
🎯 Görevler: `{user['tasks_completed']}`
👥 Referans: `{user['total_referrals']}`
⚡ Min Çekim: `{MIN_WITHDRAW} TON`""",
            'en': f"""💰 *BALANCE*
━━━━━━━━━━━━━━━━
💎 Current: `{user['balance']:.4f} TON`
━━━━━━━━━━━━━━━━
📊 Earned:  `{user['total_earned']:.4f} TON`
🎯 Tasks:   `{user['tasks_completed']}`
👥 Refs:    `{user['total_referrals']}`
⚡ Min Withdraw: `{MIN_WITHDRAW} TON`""",
            'pt_br': f"""💰 *SALDO*
━━━━━━━━━━━━━━━━
💎 Atual: `{user['balance']:.4f} TON`
━━━━━━━━━━━━━━━━
📊 Ganhos:  `{user['total_earned']:.4f} TON`
🎯 Tarefas: `{user['tasks_completed']}`
👥 Indicações:`{user['total_referrals']}`
⚡ Mín Saque: `{MIN_WITHDRAW} TON`""",
        }
        btn = {'tr':('💎 Çekim','🎯 Görevler','👥 Davet','🏠 Menü'),
               'en':('💎 Withdraw','🎯 Tasks','👥 Invite','🏠 Menu'),
               'pt_br':('💎 Sacar','🎯 Tarefas','👥 Convidar','🏠 Menu')}
        lb = btn.get(lang, btn['en'])
        send_message(uid, msgs.get(lang, msgs['en']), reply_markup={'inline_keyboard': [
            [{'text': lb[0], 'callback_data': 'show_withdraw'}, {'text': lb[1], 'callback_data': 'show_tasks'}],
            [{'text': lb[2], 'callback_data': 'show_invite'},   {'text': lb[3], 'callback_data': 'main_menu'}],
        ]})

    def show_withdraw(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        if user['balance'] < MIN_WITHDRAW:
            send_message(uid, T(lang, 'wd_low', min=MIN_WITHDRAW, bal=f"{user['balance']:.4f}"),
                         reply_markup={'inline_keyboard': [
                             [{'text': '🎯 Görev Yap', 'callback_data': 'show_tasks'}],
                             [{'text': '🏠 Menü',      'callback_data': 'main_menu'}],
                         ]})
            return
        hdrs = {
            'tr':    f"💎 *TON ÇEKİM*\n💰 Bakiyen: `{user['balance']:.4f} TON`  |  Min: `{MIN_WITHDRAW} TON`\n\n",
            'en':    f"💎 *TON WITHDRAW*\n💰 Balance: `{user['balance']:.4f} TON`  |  Min: `{MIN_WITHDRAW} TON`\n\n",
            'pt_br': f"💎 *SAQUE TON*\n💰 Saldo: `{user['balance']:.4f} TON`  |  Mín: `{MIN_WITHDRAW} TON`\n\n",
        }
        self.states[uid] = {'action': 'wd_amount'}
        send_message(uid, hdrs.get(lang, hdrs['en']) + T(lang, 'enter_amount'),
                     reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})

    def show_invite(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang     = user['language']
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user['referral_code']}"
        self.db.cur.execute('SELECT COALESCE(SUM(earned),0) FROM referrals WHERE referrer_id=? AND status="active"', (uid,))
        earned = self.db.cur.fetchone()[0]
        msgs = {
            'tr': f"""👥 *REFERANS*
━━━━━━━━━━━━━━━━
🔗 Linkin:
`{ref_link}`
━━━━━━━━━━━━━━━━
💰 Ref başı: `{REF_WELCOME_BONUS} TON`
👥 Aktif ref: `{user['total_referrals']}`
💎 Kazanç:    `{earned:.4f} TON`
━━━━━━━━━━━━━━━━
⚠️ Davet ettiğin kişi kanallara katılmalı!""",
            'en': f"""👥 *REFERRAL*
━━━━━━━━━━━━━━━━
🔗 Your link:
`{ref_link}`
━━━━━━━━━━━━━━━━
💰 Per referral: `{REF_WELCOME_BONUS} TON`
👥 Active refs:  `{user['total_referrals']}`
💎 Earned:       `{earned:.4f} TON`
━━━━━━━━━━━━━━━━
⚠️ Referred person must join all channels!""",
            'pt_br': f"""👥 *INDICAÇÃO*
━━━━━━━━━━━━━━━━
🔗 Seu link:
`{ref_link}`
━━━━━━━━━━━━━━━━
💰 Por indicação: `{REF_WELCOME_BONUS} TON`
👥 Indicações:    `{user['total_referrals']}`
💎 Ganhos:        `{earned:.4f} TON`
━━━━━━━━━━━━━━━━
⚠️ Indicados devem entrar em todos os canais!""",
        }
        share = {
            'tr':    f"🚀 {BOT_NAME} ile TON kazan! {ref_link}",
            'en':    f"🚀 Earn TON with {BOT_NAME}! {ref_link}",
            'pt_br': f"🚀 Ganhe TON com {BOT_NAME}! {ref_link}",
        }
        btn_sh = {'tr': '📤 Paylaş', 'en': '📤 Share', 'pt_br': '📤 Compartilhar'}
        send_message(uid, msgs.get(lang, msgs['en']), reply_markup={'inline_keyboard': [
            [{'text': btn_sh.get(lang, btn_sh['en']),
              'url': f"https://t.me/share/url?url={ref_link}&text={share.get(lang,'')}"}],
            [{'text': '🏠 Menü', 'callback_data': 'main_menu'}],
        ]})

    def show_profile(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        ll   = {'tr': '🇹🇷 Türkçe', 'en': '🇺🇸 English', 'pt_br': '🇧🇷 Português'}
        ton  = user.get('ton_address') or '—'
        msgs = {
            'tr': f"""👤 *PROFİL*
━━━━━━━━━━━━━━━━
👤 Ad: *{user['first_name']}*
🆔 ID: `{user['user_id']}`
🌍 Dil: {ll.get(lang, lang)}
🏦 TON: `{ton[:24]}{'…' if len(ton)>24 else ''}`
━━━━━━━━━━━━━━━━
💎 Bakiye:   `{user['balance']:.4f} TON`
🎯 Görevler: `{user['tasks_completed']}`
👥 Referans: `{user['total_referrals']}`
📅 Kayıt:    `{str(user['created_at'])[:10]}`""",
            'en': f"""👤 *PROFILE*
━━━━━━━━━━━━━━━━
👤 Name: *{user['first_name']}*
🆔 ID: `{user['user_id']}`
🌍 Lang: {ll.get(lang, lang)}
🏦 TON: `{ton[:24]}{'…' if len(ton)>24 else ''}`
━━━━━━━━━━━━━━━━
💎 Balance:  `{user['balance']:.4f} TON`
🎯 Tasks:    `{user['tasks_completed']}`
👥 Referrals:`{user['total_referrals']}`
📅 Joined:   `{str(user['created_at'])[:10]}`""",
            'pt_br': f"""👤 *PERFIL*
━━━━━━━━━━━━━━━━
👤 Nome: *{user['first_name']}*
🆔 ID: `{user['user_id']}`
🌍 Idioma: {ll.get(lang, lang)}
🏦 TON: `{ton[:24]}{'…' if len(ton)>24 else ''}`
━━━━━━━━━━━━━━━━
💎 Saldo:    `{user['balance']:.4f} TON`
🎯 Tarefas:  `{user['tasks_completed']}`
👥 Indicações:`{user['total_referrals']}`
📅 Registro: `{str(user['created_at'])[:10]}`""",
        }
        btn = {'tr':('⚙️ Ayarlar','🌍 Dil','🏠 Menü'),
               'en':('⚙️ Settings','🌍 Language','🏠 Menu'),
               'pt_br':('⚙️ Ajustes','🌍 Idioma','🏠 Menu')}
        lb = btn.get(lang, btn['en'])
        send_message(uid, msgs.get(lang, msgs['en']), reply_markup={'inline_keyboard': [
            [{'text': lb[0], 'callback_data': 'show_settings'},
             {'text': lb[1], 'callback_data': 'change_lang'}],
            [{'text': lb[2], 'callback_data': 'main_menu'}],
        ]})

    def show_settings(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        ton  = user.get('ton_address') or '—'
        msgs = {
            'tr':    f"⚙️ *AYARLAR*\n\n🏦 TON Adresin:\n`{ton}`\n\nÇekim için TON adresini kaydet:",
            'en':    f"⚙️ *SETTINGS*\n\n🏦 TON Address:\n`{ton}`\n\nSave your TON address for withdrawals:",
            'pt_br': f"⚙️ *AJUSTES*\n\n🏦 Endereço TON:\n`{ton}`\n\nSalve seu endereço para saques:",
        }
        btn_ton = {'tr': '💳 TON Adres Kaydet', 'en': '💳 Save TON Address', 'pt_br': '💳 Salvar Endereço TON'}
        send_message(uid, msgs.get(lang, msgs['en']), reply_markup={'inline_keyboard': [
            [{'text': btn_ton.get(lang, btn_ton['en']), 'callback_data': 'set_ton'}],
            [{'text': '🌍 Dil Değiştir / Change Language', 'callback_data': 'change_lang'}],
            [{'text': '🏠 Menü', 'callback_data': 'main_menu'}],
        ]})

    def show_help(self, uid):
        user = self.db.get_user(uid)
        if not user:
            return
        lang = user['language']
        msgs = {
            'tr': f"""❓ *YARDIM*
━━━━━━━━━━━━━━━━
🤖 *{BOT_NAME}* | 👤 {SUPPORT_USERNAME}
━━━━━━━━━━━━━━━━
1️⃣ *Görevler:*
   📢 Kanal → Katıl, doğrula, kazan
   👥 Grup → Katıl, doğrula, kazan
   🤖 Bot → Başlat, onayla, kazan

2️⃣ *Çekim:* Min. `{MIN_WITHDRAW} TON`

3️⃣ *Referans:* `{REF_WELCOME_BONUS} TON` / aktif kişi
   ⚠️ Kişi kanallara katılmalı!

4️⃣ *Görev Yayınla:*
   Kendi kanalın için görev oluştur
   Bakiyenden bütçe seç, yayınla!

━━━━━━━━━━━━━━━━
/start /tasks /balance /withdraw""",
            'en': f"""❓ *HELP*
━━━━━━━━━━━━━━━━
🤖 *{BOT_NAME}* | 👤 {SUPPORT_USERNAME}
━━━━━━━━━━━━━━━━
1️⃣ *Tasks:*
   📢 Channel → Join, verify, earn
   👥 Group → Join, verify, earn
   🤖 Bot → Start, confirm, earn

2️⃣ *Withdraw:* Min. `{MIN_WITHDRAW} TON`

3️⃣ *Referral:* `{REF_WELCOME_BONUS} TON` / active person
   ⚠️ Must join all channels!

4️⃣ *Publish Task:*
   Create tasks for your own channel
   Choose budget from balance, publish!

━━━━━━━━━━━━━━━━
/start /tasks /balance /withdraw""",
            'pt_br': f"""❓ *AJUDA*
━━━━━━━━━━━━━━━━
🤖 *{BOT_NAME}* | 👤 {SUPPORT_USERNAME}
━━━━━━━━━━━━━━━━
1️⃣ *Tarefas:*
   📢 Canal → Entrar, verificar, ganhar
   👥 Grupo → Entrar, verificar, ganhar
   🤖 Bot → Iniciar, confirmar, ganhar

2️⃣ *Saque:* Mín. `{MIN_WITHDRAW} TON`

3️⃣ *Indicação:* `{REF_WELCOME_BONUS} TON` / pessoa ativa
   ⚠️ Deve entrar em todos os canais!

4️⃣ *Publicar Tarefa:*
   Crie tarefas para seu próprio canal
   Escolha orçamento do saldo, publique!

━━━━━━━━━━━━━━━━
/start /tasks /balance /withdraw""",
        }
        send_message(uid, msgs.get(lang, msgs['en']), reply_markup={'inline_keyboard': [
            [{'text': f'📞 {SUPPORT_USERNAME}', 'url': f'https://t.me/{SUPPORT_USERNAME[1:]}'}],
            [{'text': '🏠 Menü', 'callback_data': 'main_menu'}],
        ]})

    # ──────────────────────────────────────────
    #   ADMİN PANELİ
    # ──────────────────────────────────────────
    def show_admin(self, uid):
        s = self.db.stats()
        text = f"""🛡️ *ADMİN — {BOT_NAME}*
━━━━━━━━━━━━━━━━━━━━
👥 Kullanıcı:    `{s['users']}`
🟢 Aktif (24h):  `{s['active']}`
🆕 Yeni (24h):   `{s['new']}`
━━━━━━━━━━━━━━━━━━━━
💎 Toplam Bakiye:`{s['balance']:.4f} TON`
📥 Bekleyen Çekim:`{s['pending_wds']}`
✅ Ödenen:        `{s['total_paid']:.4f} TON`
🎯 Görev Tamamlama:`{s['tasks_done']}`
📋 Aktif Görev:  `{s['active_tasks']}`
━━━━━━━━━━━━━━━━━━━━
📌 Komutlar:
`/addbalance <id> <miktar> [sebep]`
`/removebalance <id> <miktar>`
`/ban <id>` | `/unban <id>`
`/getuser <id/username>`
`/broadcast <mesaj>`"""
        keyboard = {'inline_keyboard': [
            [{'text': '📥 Bekleyen Çekimler', 'callback_data': 'admin_wds'},
             {'text': '📋 Görev Listesi',    'callback_data': 'admin_tasks'}],
            [{'text': '👥 Son Kullanıcılar',  'callback_data': 'admin_users'},
             {'text': '🔄 Yenile',            'callback_data': 'admin_refresh'}],
        ]}
        send_message(uid, text, reply_markup=keyboard)

    def handle_admin_cb(self, uid, data, cb_id):
        if data == 'admin_refresh':
            answer_callback(cb_id, "🔄")
            self.show_admin(uid)

        elif data == 'admin_wds':
            pending = self.db.get_pending_wds()
            if not pending:
                answer_callback(cb_id, "✅ Bekleyen çekim yok", True)
                return
            answer_callback(cb_id)
            for w in pending[:5]:
                text = (f"📥 *ÇEKİM #{w['id']}*\n"
                        f"👤 {w['first_name']} (`{w['user_id']}`)\n"
                        f"💎 {w['amount']:.4f} TON\n"
                        f"🏦 `{w['ton_address']}`\n"
                        f"📅 {str(w['created_at'])[:16]}")
                send_message(uid, text, reply_markup={'inline_keyboard': [[
                    {'text': '✅ Onayla', 'callback_data': f'admin_wd_ok_{w["id"]}'},
                    {'text': '❌ Reddet', 'callback_data': f'admin_wd_no_{w["id"]}'},
                ]]})

        elif data.startswith('admin_wd_ok_'):
            wid = int(data.split('_')[-1])
            self.db.cur.execute('SELECT * FROM withdrawals WHERE id=?', (wid,))
            w = self.db.cur.fetchone()
            self.db.approve_wd(wid, uid)
            answer_callback(cb_id, "✅ Onaylandı!", True)
            if w:
                w = dict(w)
                u = self.db.get_user(w['user_id'])
                ul = u['language'] if u else 'en'
                ok_msgs = {
                    'tr': f"✅ *Çekim Onaylandı!*\n💎 `{w['amount']:.4f} TON` gönderildi!\n🏦 `{w['ton_address']}`",
                    'en': f"✅ *Withdrawal Approved!*\n💎 `{w['amount']:.4f} TON` sent!\n🏦 `{w['ton_address']}`",
                    'pt_br': f"✅ *Saque Aprovado!*\n💎 `{w['amount']:.4f} TON` enviado!\n🏦 `{w['ton_address']}`",
                }
                send_message(w['user_id'], ok_msgs.get(ul, ok_msgs['en']))

        elif data.startswith('admin_wd_no_'):
            wid = int(data.split('_')[-1])
            self.db.cur.execute('SELECT * FROM withdrawals WHERE id=?', (wid,))
            w = self.db.cur.fetchone()
            self.db.reject_wd(wid, uid, "Admin reddetti")
            answer_callback(cb_id, "❌ Reddedildi!", True)
            if w:
                w = dict(w)
                u = self.db.get_user(w['user_id'])
                ul = u['language'] if u else 'en'
                rej_msgs = {
                    'tr': f"❌ *Çekim Reddedildi*\n💎 `{w['amount']:.4f} TON` iade edildi.",
                    'en': f"❌ *Withdrawal Rejected*\n💎 `{w['amount']:.4f} TON` refunded.",
                    'pt_br': f"❌ *Saque Rejeitado*\n💎 `{w['amount']:.4f} TON` devolvido.",
                }
                send_message(w['user_id'], rej_msgs.get(ul, rej_msgs['en']))

        elif data == 'admin_tasks':
            answer_callback(cb_id)
            tasks = self.db.get_all_tasks()
            if not tasks:
                send_message(uid, "📭 Görev yok.")
                return
            icons = {'channel_join': '📢', 'group_join': '👥', 'bot_start': '🤖'}
            st_ic = {'active': '🟢', 'inactive': '🔴', 'completed': '✅', 'deleted': '⛔'}
            buttons = []
            for t in tasks[:20]:
                icon = icons.get(t['task_type'], '🎯')
                si   = st_ic.get(t['status'], '❓')
                buttons.append([{'text': f"{si} {icon} #{t['id']} {t['title']} — {t['reward']:.4f} TON ({t['current_participants']}/{t['max_participants']})",
                                 'callback_data': f"admin_task_{t['id']}"}])
            buttons.append([{'text': '🔙 Admin', 'callback_data': 'admin_refresh'}])
            send_message(uid, f"📋 *GÖREVLER* ({len(tasks)}):", reply_markup={'inline_keyboard': buttons})

        elif data.startswith('admin_task_') and not data.startswith('admin_tasks'):
            tid = int(data.split('_')[-1])
            answer_callback(cb_id)
            task = self.db.get_task(tid)
            if not task:
                return
            icons = {'channel_join': '📢', 'group_join': '👥', 'bot_start': '🤖'}
            text = (f"📋 *GÖREV #{tid}*\n"
                    f"📌 {task['title']}\n"
                    f"🏷️ {icons.get(task['task_type'],'')} {task['task_type']}\n"
                    f"🎯 @{task['target_username']}\n"
                    f"💎 {task['reward']:.4f} TON\n"
                    f"👥 {task['current_participants']}/{task['max_participants']}\n"
                    f"📊 {task['status']}\n"
                    f"👤 Oluşturan: `{task['created_by']}`")
            toggle_lbl = '🔴 Pasif Yap' if task['status'] == 'active' else '🟢 Aktif Yap'
            send_message(uid, text, reply_markup={'inline_keyboard': [
                [{'text': toggle_lbl,   'callback_data': f'admin_toggle_{tid}'},
                 {'text': '🗑️ Sil',    'callback_data': f'admin_del_{tid}'}],
                [{'text': '🔙 Liste',   'callback_data': 'admin_tasks'}],
            ]})

        elif data.startswith('admin_toggle_'):
            tid = int(data.split('_')[-1])
            new = self.db.toggle_task(tid)
            lbl = '🟢 Aktif' if new == 'active' else '🔴 Pasif'
            answer_callback(cb_id, f"{lbl} yapıldı!", True)
            # Detayı yenile
            task = self.db.get_task(tid)
            if task:
                self.handle_admin_cb(uid, f'admin_task_{tid}', cb_id)

        elif data.startswith('admin_del_'):
            tid = int(data.split('_')[-1])
            self.db.delete_task(tid)
            answer_callback(cb_id, "🗑️ Silindi!", True)
            self.handle_admin_cb(uid, 'admin_tasks', cb_id)

        elif data == 'admin_users':
            answer_callback(cb_id)
            users = self.db.cur.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 10').fetchall()
            text  = "👥 *SON 10 KULLANICI*\n\n"
            for u in users:
                u = dict(u)
                text += f"👤 {u['first_name']} (`{u['user_id']}`) — {u['balance']:.4f} TON\n"
            send_message(uid, text, reply_markup={'inline_keyboard': [[{'text': '🔙 Admin', 'callback_data': 'admin_refresh'}]]})

        else:
            answer_callback(cb_id)

    def handle_admin_cmd(self, uid, text):
        parts = text.split(None, 1)
        cmd   = parts[0].lower()
        arg   = parts[1].strip() if len(parts) > 1 else ''

        if cmd == '/addbalance':
            try:
                a = arg.split(); target = int(a[0]); amt = float(a[1]); reason = ' '.join(a[2:]) or 'Admin'
                self.db.add_balance(target, amt, uid, reason)
                send_message(uid, f"✅ `{target}` → +`{amt} TON` eklendi!")
                send_message(target, f"💎 Hesabınıza `{amt} TON` eklendi! Sebep: {reason}")
            except Exception as e:
                send_message(uid, f"❌ Hata: {e}\n/addbalance <id> <miktar> [sebep]")

        elif cmd == '/removebalance':
            try:
                a = arg.split(); target = int(a[0]); amt = float(a[1])
                self.db.remove_balance(target, amt, uid)
                send_message(uid, f"✅ `{target}` → -{amt} TON")
            except Exception as e:
                send_message(uid, f"❌ Hata: {e}")

        elif cmd == '/ban':
            try:
                self.db.ban(int(arg))
                send_message(uid, f"✅ `{arg}` yasaklandı!")
            except Exception as e:
                send_message(uid, f"❌ {e}")

        elif cmd == '/unban':
            try:
                self.db.unban(int(arg))
                send_message(uid, f"✅ `{arg}` yasağı kaldırıldı!")
            except Exception as e:
                send_message(uid, f"❌ {e}")

        elif cmd == '/getuser':
            u = self.db.search_user(arg)
            if u:
                send_message(uid, f"👤 ID:`{u['user_id']}` | {u['first_name']} @{u.get('username','—')}\n"
                                  f"💎 {u['balance']:.4f} TON | 🎯 {u['tasks_completed']} görev | Durum: {u['status']}\n"
                                  f"TON: `{u.get('ton_address','—')}`")
            else:
                send_message(uid, "❌ Kullanıcı bulunamadı!")

        elif cmd == '/broadcast':
            if not arg:
                send_message(uid, "❌ /broadcast <mesaj>")
                return
            rows = self.db.cur.execute("SELECT user_id FROM users WHERE status='active'").fetchall()
            sent = 0
            for row in rows:
                try:
                    send_message(row[0], f"📢 *DUYURU*\n\n{arg}")
                    sent += 1
                    time.sleep(0.05)
                except:
                    pass
            send_message(uid, f"✅ {sent}/{len(rows)} gönderildi.")

        else:
            self.show_admin(uid)

    # ──────────────────────────────────────────
    #   UPDATE HANDLER
    # ──────────────────────────────────────────
    def handle_update(self, update):
        try:
            if 'message' in update:
                self.handle_msg(update['message'])
            elif 'callback_query' in update:
                self.handle_cb(update['callback_query'])
        except Exception as e:
            print(f"handle_update: {e}")

    def handle_msg(self, msg):
        uid        = msg['from']['id']
        text       = msg.get('text', '')
        is_forward = 'forward_from_chat' in msg or 'forward_origin' in msg

        # Forward mesajı — görev oluşturma için
        if is_forward:
            state = self.states.get(uid, {})
            if state.get('action') == 'pub_forward_wait':
                self.pub_handle_forward(uid, msg)
                return

        if not text:
            return

        user = self.db.get_user(uid)
        if user and user.get('status') == 'banned':
            send_message(uid, "🚫 Hesabınız askıya alınmıştır.")
            return

        # Admin komutları
        if str(uid) in ADMIN_IDS:
            if text == '/admin':
                if not user:
                    user = self.db.create_user(uid, msg['from'].get('username',''),
                                               msg['from'].get('first_name',''),
                                               msg['from'].get('last_name',''))
                self.show_admin(uid)
                return
            if text.startswith('/') and text != '/start':
                if not user:
                    user = self.db.create_user(uid, msg['from'].get('username',''),
                                               msg['from'].get('first_name',''),
                                               msg['from'].get('last_name',''))
                self.handle_admin_cmd(uid, text)
                return

        # Referans kodu çıkar
        referred_by = None
        if text.startswith('/start'):
            parts = text.split()
            if len(parts) > 1:
                self.db.cur.execute('SELECT user_id FROM users WHERE referral_code=?', (parts[1],))
                row = self.db.cur.fetchone()
                if row and row[0] != uid:
                    referred_by = row[0]

        # Yeni kullanıcı
        if not user:
            user = self.db.create_user(uid, msg['from'].get('username',''),
                                       msg['from'].get('first_name',''),
                                       msg['from'].get('last_name',''),
                                       'tr', referred_by)
            try:
                send_message(STATS_CHANNEL,
                             f"👤 *YENİ ÜYE*\n{user['first_name']} (`{uid}`)\nRef: {referred_by or '—'}")
            except:
                pass
            self.show_lang_select(uid)
            return

        self.db.update_active(uid)
        state  = self.states.get(uid, {})
        action = state.get('action', '')

        # Aktif görev oluşturma adımları
        if action.startswith('pub_'):
            self.pub_handle_step(uid, text)
            return

        # Çekim adımları
        if action == 'wd_amount':
            lang = user['language']
            try:
                amount = float(text.replace(',', '.'))
                if amount < MIN_WITHDRAW or amount > user['balance']:
                    send_message(uid, T(lang, 'wd_low', min=MIN_WITHDRAW, bal=f"{user['balance']:.4f}"))
                    return
                self.states[uid] = {'action': 'wd_addr', 'amount': amount}
                send_message(uid, T(lang, 'enter_addr'),
                             reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})
            except ValueError:
                send_message(uid, T(lang, 'bad_num'))
            return

        if action == 'wd_addr':
            lang = user['language']
            addr = text.strip()
            if len(addr) < 10:
                send_message(uid, T(lang, 'bad_addr'))
                return
            amount = state['amount']
            wid    = self.db.create_withdrawal(uid, amount, addr)
            del self.states[uid]
            send_message(uid, T(lang, 'wd_ok', amount=f'{amount:.4f}', addr=addr),
                         reply_markup={'inline_keyboard': [[{'text': '🏠 Menü', 'callback_data': 'main_menu'}]]})
            try:
                send_message(STATS_CHANNEL,
                             f"💎 *YENİ ÇEKİM #{wid}*\n👤 {user['first_name']} (`{uid}`)\n💎 {amount:.4f} TON")
            except:
                pass
            for aid in ADMIN_IDS:
                try:
                    send_message(int(aid),
                                 f"📥 *Çekim #{wid}*\n👤 {user['first_name']} (`{uid}`)\n💎 {amount:.4f} TON\n🏦 `{addr}`",
                                 reply_markup={'inline_keyboard': [[
                                     {'text': '✅ Onayla', 'callback_data': f'admin_wd_ok_{wid}'},
                                     {'text': '❌ Reddet', 'callback_data': f'admin_wd_no_{wid}'},
                                 ]]})
                except:
                    pass
            return

        if action == 'set_ton':
            addr = text.strip()
            lang = user['language']
            if len(addr) < 10:
                send_message(uid, T(lang, 'bad_addr'))
                return
            self.db.set_ton(uid, addr)
            del self.states[uid]
            send_message(uid, T(lang, 'ton_saved'))
            self.show_settings(uid)
            return

        self.process_cmd(uid, text, user)

    def process_cmd(self, uid, text, user):
        lang = user['language']
        if text == '/start' or text in all_menu_labels('menu_balance') and text == T(lang,'menu_balance'):
            pass

        if text == '/start':
            self.show_menu(uid, lang)
        elif text in ['/tasks']   + all_menu_labels('menu_tasks'):
            self.show_tasks(uid)
        elif text in ['/balance'] + all_menu_labels('menu_balance'):
            self.show_balance(uid)
        elif text in ['/withdraw']+ all_menu_labels('menu_withdraw'):
            self.show_withdraw(uid)
        elif text in ['/invite','/referral']+ all_menu_labels('menu_invite'):
            self.show_invite(uid)
        elif text in all_menu_labels('menu_tasks_create'):
            self.show_task_publish(uid)
        elif text in ['/profile'] + all_menu_labels('menu_profile'):
            self.show_profile(uid)
        elif text in ['/settings']+ all_menu_labels('menu_settings'):
            self.show_settings(uid)
        elif text in ['/help']    + all_menu_labels('menu_help'):
            self.show_help(uid)
        elif text in all_menu_labels('menu_admin') and str(uid) in ADMIN_IDS:
            self.show_admin(uid)
        else:
            self.show_menu(uid, lang)

    def handle_cb(self, cq):
        uid    = cq['from']['id']
        data   = cq.get('data', '')
        cb_id  = cq['id']

        user = self.db.get_user(uid)
        if user and user.get('status') == 'banned':
            answer_callback(cb_id, "🚫 Hesabınız askıya alınmıştır.", True)
            return

        lang = user['language'] if user else 'tr'

        try:
            # Admin callback'ler
            if str(uid) in ADMIN_IDS and data.startswith('admin_'):
                self.handle_admin_cb(uid, data, cb_id)
                return

            # Dil seçimi
            if data.startswith('lang_'):
                new_lang = data[5:]
                if new_lang in SUPPORTED_LANGUAGES:
                    self.db.set_lang(uid, new_lang)
                    answer_callback(cb_id, "✅ Dil seçildi!")
                    # Referansı aktifleştir
                    fresh = self.db.get_user(uid)
                    if fresh and fresh.get('referred_by'):
                        missing = self.missing_channels(uid)
                        if not missing:
                            ref_owner = self.db.activate_referral(uid)
                            if ref_owner:
                                try:
                                    send_message(ref_owner, f"🎉 *Yeni Aktif Referans!*\n💎 +`{REF_WELCOME_BONUS} TON` eklendi!")
                                except:
                                    pass
                    self.show_menu(uid, new_lang)
                return

            # Kanal kontrolü
            if data == 'check_channels':
                missing = self.missing_channels(uid)
                if missing:
                    names = ', '.join([m['name'] for m in missing])
                    fail  = {'tr':f"❌ Henüz katılmadınız!\nEksik: {names}", 'en':f"❌ Not joined!\nMissing: {names}", 'pt_br':f"❌ Não entrou!\nFaltando: {names}"}
                    answer_callback(cb_id, fail.get(lang, fail['en']), True)
                    self.enforce_channels(uid, lang)
                else:
                    ok = {'tr': "✅ Tebrikler!", 'en': "✅ Great!", 'pt_br': "✅ Ótimo!"}
                    answer_callback(cb_id, ok.get(lang, ok['en']), True)
                    fresh = self.db.get_user(uid)
                    if fresh and fresh.get('referred_by'):
                        ref_owner = self.db.activate_referral(uid)
                        if ref_owner:
                            try:
                                send_message(ref_owner, f"🎉 *Yeni Aktif Referans!*\n💎 +`{REF_WELCOME_BONUS} TON` eklendi!")
                            except:
                                pass
                    self.show_menu(uid, lang)
                return

            # Görev yayınlama
            if data.startswith('pub_type_'):
                tt = data[len('pub_type_'):]
                self.pub_type_selected(uid, tt, cb_id)
                return

            if data.startswith('pub_budget_') and data != 'pub_budget_back' and data != 'pub_budget_custom':
                budget = float(data[len('pub_budget_'):])
                answer_callback(cb_id)
                self._pub_budget_chosen(uid, lang, budget)
                return

            if data == 'pub_budget_custom':
                answer_callback(cb_id)
                self.states[uid] = {**self.states.get(uid, {}), 'action': 'pub_budget_custom'}
                custom_msg = {'tr': "✏️ Özel bütçe miktarını gir (TON):",
                              'en': "✏️ Enter custom budget amount (TON):",
                              'pt_br': "✏️ Digite o valor personalizado do orçamento (TON):"}
                send_message(uid, custom_msg.get(lang, custom_msg['en']),
                             reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})
                return

            if data == 'pub_budget_back':
                answer_callback(cb_id)
                self._show_budget_select(uid, lang)
                return

            if data == 'pub_save':
                self.pub_save(uid, cb_id)
                return

            # Görevler
            if data == 'show_tasks' or data == 'refresh_tasks':
                self.show_tasks(uid)
                if data == 'refresh_tasks':
                    answer_callback(cb_id, "🔄 Yenilendi!")
                return

            if data.startswith('task_'):
                tid = int(data[5:])
                self.show_task_detail(uid, tid, cb_id)
                return

            if data.startswith('verify_'):
                tid = int(data.split('_')[-1])
                self.verify_membership(uid, tid, cb_id)
                return

            if data.startswith('done_bot_'):
                tid = int(data.split('_')[-1])
                self.done_bot_task(uid, tid, cb_id)
                return

            # Diğer
            routes = {
                'main_menu':      lambda: self.show_menu(uid, lang),
                'show_balance':   lambda: self.show_balance(uid),
                'show_withdraw':  lambda: self.show_withdraw(uid),
                'show_invite':    lambda: self.show_invite(uid),
                'show_profile':   lambda: self.show_profile(uid),
                'show_settings':  lambda: self.show_settings(uid),
                'change_lang':    lambda: self.show_lang_select(uid),
                'show_publish':   lambda: self.show_task_publish(uid),
            }

            if data in routes:
                answer_callback(cb_id)
                routes[data]()
                return

            if data == 'set_ton':
                answer_callback(cb_id)
                self.states[uid] = {'action': 'set_ton'}
                send_message(uid, T(lang, 'enter_addr'),
                             reply_markup={'inline_keyboard': [[{'text': '❌ İptal', 'callback_data': 'cancel'}]]})
                return

            if data == 'cancel':
                if uid in self.states:
                    del self.states[uid]
                answer_callback(cb_id, "❌ İptal edildi")
                self.show_menu(uid, lang)
                return

            answer_callback(cb_id)

        except Exception as e:
            print(f"handle_cb hatası: {e}")
            answer_callback(cb_id, "❌ Bir hata oluştu")


# ════════════════════════════════════════════
#              POLLING & WEB
# ════════════════════════════════════════════
def run_polling():
    bot    = Bot()
    offset = None
    print("🔄 Polling başlatıldı...")
    while True:
        try:
            updates = get_updates(offset=offset, timeout=30)
            for upd in updates:
                uid = upd.get('update_id')
                if uid is not None:
                    offset = uid + 1
                threading.Thread(target=bot.handle_update, args=(upd,), daemon=True).start()
        except Exception as e:
            print(f"Polling hatası: {e}")
            time.sleep(5)

def run_web():
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_polling, daemon=True).start()
    run_web()
