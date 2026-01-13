import os
import time
import json
import requests
from datetime import datetime, timedelta
import threading
import sqlite3
from flask import Flask, jsonify
import hashlib
import pytz
import random
from typing import Optional, Dict, List, Tuple

# Telegram Ayarları
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "7904032877")
MANDATORY_CHANNEL = os.environ.get("MANDATORY_CHANNEL", "GorevYapsamChat")
REFERENCE_GROUP = os.environ.get("REFERENCE_GROUP", "GYReferans")  # Referans Kasma Grubu

if not TOKEN:
    raise ValueError("Bot token gerekli!")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Türkiye saati için
TURKEY_TZ = pytz.timezone('Europe/Istanbul')

# TRX Ayarları
TRX_ADDRESS = "TVJKGbdBQrbvQzq6WZhb3kaGa3LYgVrMSK"
TRX_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=tron&vs_currencies=try"
MIN_DEPOSIT_TRY = 25.0
MAX_DEPOSIT_TRY = 200.0
DEPOSIT_BONUS_PERCENT = 35
MIN_WITHDRAW = 50.0  # Minimum çekim 50₺

# Görev Ücretleri
GROUP_TASK_PRICE = 0.5  # Grup görevi ücreti (Reklamveren öder)
CHANNEL_TASK_PRICE = 1.25  # Kanal görevi ücreti (Reklamveren öder)

# Flask App
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "online", "bot": "Görev Yapsam Bot v22.0"})

def get_turkey_time():
    """Türkiye saatini döndür"""
    return datetime.now(TURKEY_TZ)

# Referans Grubu Bildirim Sistemi
class ReferenceGroupNotifier:
    def __init__(self, db):
        self.db = db
        self.last_notification_id = None
        self.running = False
    
    def start(self):
        self.running = True
        threading.Thread(target=self.run, daemon=True).start()
        print(f"📢 Referans grubu bildirim sistemi başlatıldı: @{REFERENCE_GROUP}")
    
    def run(self):
        # Başlangıçta 5 saniye bekle
        time.sleep(5)
        
        while self.running:
            try:
                self.update_reference_group()
                time.sleep(180)  # Her 3 dakikada bir güncelle
            except Exception as e:
                print(f"❌ Referans grubu güncelleme hatası: {e}")
                time.sleep(60)
    
    def update_reference_group(self):
        """Referans grubunu güncelle"""
        try:
            message = self.generate_reference_message()
            
            if self.last_notification_id:
                # Mesajı düzenle
                try:
                    response = edit_message_text(f"@{REFERENCE_GROUP}", self.last_notification_id, message)
                    if not response or not response.get('ok'):
                        # Mesaj silinmiş, yeni mesaj gönder
                        self.send_new_message(message)
                except:
                    # Hata olursa yeni mesaj gönder
                    self.send_new_message(message)
            else:
                # İlk mesajı gönder
                self.send_new_message(message)
                
        except Exception as e:
            print(f"❌ Referans grubu güncelleme hatası: {e}")
    
    def send_new_message(self, message):
        """Yeni referans mesajı gönder"""
        response = send_message(f"@{REFERENCE_GROUP}", message)
        if response and response.get('ok'):
            self.last_notification_id = response['result']['message_id']
    
    def generate_reference_message(self):
        """Referans grubu mesajı oluştur"""
        now = get_turkey_time()
        
        # Toplam kullanıcı
        self.db.cursor.execute("SELECT COUNT(*) FROM users")
        total_users = self.db.cursor.fetchone()[0]
        
        # Aktif kullanıcılar (son 24 saat)
        yesterday = (now - timedelta(hours=24)).isoformat()
        self.db.cursor.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (yesterday,))
        active_users = self.db.cursor.fetchone()[0]
        
        # Reklamverenler
        self.db.cursor.execute("SELECT COUNT(*) FROM users WHERE is_advertiser = 1")
        total_advertisers = self.db.cursor.fetchone()[0]
        
        # Toplam bakiye
        self.db.cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = self.db.cursor.fetchone()[0] or 0
        
        # Toplam reklamveren bakiyesi
        self.db.cursor.execute("SELECT SUM(advertiser_balance) FROM users")
        total_ad_balance = self.db.cursor.fetchone()[0] or 0
        
        # Bugünkü depozitler
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        self.db.cursor.execute('''
            SELECT COUNT(*), SUM(amount_try) 
            FROM deposits 
            WHERE status = 'completed' AND created_at > ?
        ''', (today_start,))
        today_result = self.db.cursor.fetchone()
        today_deposits = today_result[0] or 0
        today_deposit_amount = today_result[1] or 0
        
        # Bugünkü çekimler
        self.db.cursor.execute('''
            SELECT COUNT(*), SUM(amount) 
            FROM withdrawals 
            WHERE status = 'completed' AND created_at > ?
        ''', (today_start,))
        today_withdraw_result = self.db.cursor.fetchone()
        today_withdrawals = today_withdraw_result[0] or 0
        today_withdraw_amount = today_withdraw_result[1] or 0
        
        # Bugünkü görevler
        self.db.cursor.execute('''
            SELECT COUNT(*), SUM(total_spent) 
            FROM tasks 
            WHERE created_at > ?
        ''', (today_start,))
        today_tasks_result = self.db.cursor.fetchone()
        today_tasks = today_tasks_result[0] or 0
        today_tasks_spent = today_tasks_result[1] or 0
        
        # Bugünkü kazanç
        self.db.cursor.execute('''
            SELECT SUM(reward_paid) 
            FROM task_participations 
            WHERE paid_at > ? AND status = 'verified'
        ''', (today_start,))
        today_earnings_result = self.db.cursor.fetchone()
        today_earnings = today_earnings_result[0] or 0
        
        # Toplam depozit
        self.db.cursor.execute('''
            SELECT SUM(amount_try) 
            FROM deposits 
            WHERE status = 'completed'
        ''')
        total_deposit_amount = self.db.cursor.fetchone()[0] or 0
        
        # Toplam çekim
        self.db.cursor.execute('''
            SELECT SUM(amount) 
            FROM withdrawals 
            WHERE status = 'completed'
        ''')
        total_withdraw_amount = self.db.cursor.fetchone()[0] or 0
        
        # Son depozitler (bugünkü)
        self.db.cursor.execute('''
            SELECT d.*, u.name 
            FROM deposits d 
            LEFT JOIN users u ON d.user_id = u.user_id 
            WHERE d.status = 'completed' AND DATE(d.completed_at) = DATE(?)
            ORDER BY d.completed_at DESC 
            LIMIT 5
        ''', (now.isoformat(),))
        recent_deposits = self.db.cursor.fetchall()
        
        # Son görevler (bugünkü)
        self.db.cursor.execute('''
            SELECT t.*, u.name as advertiser_name 
            FROM tasks t 
            LEFT JOIN users u ON t.advertiser_id = u.user_id 
            WHERE DATE(t.created_at) = DATE(?)
            ORDER BY t.created_at DESC 
            LIMIT 5
        ''', (now.isoformat(),))
        recent_tasks = self.db.cursor.fetchall()
        
        # Son çekimler (bugünkü)
        self.db.cursor.execute('''
            SELECT w.*, u.name 
            FROM withdrawals w 
            LEFT JOIN users u ON w.user_id = u.user_id 
            WHERE w.status = 'completed' AND DATE(w.completed_at) = DATE(?)
            ORDER BY w.completed_at DESC 
            LIMIT 5
        ''', (now.isoformat(),))
        recent_withdrawals = self.db.cursor.fetchall()
        
        # Son görev tamamlamalar (bugünkü)
        self.db.cursor.execute('''
            SELECT tp.*, u.name as participant_name, t.target_name
            FROM task_participations tp
            LEFT JOIN users u ON tp.user_id = u.user_id
            LEFT JOIN tasks t ON tp.task_id = t.task_id
            WHERE tp.status = 'verified' AND DATE(tp.paid_at) = DATE(?)
            ORDER BY tp.paid_at DESC 
            LIMIT 5
        ''', (now.isoformat(),))
        recent_task_completions = self.db.cursor.fetchall()
        
        # Mesaj oluştur
        message = f"""
<b>📊 GÖREV YAPSAM BOT - REFERANS GRUBU</b>
<b>⏰ Son Güncelleme:</b> {now.strftime('%d.%m.%Y %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👥 KULLANICI İSTATİSTİKLERİ</b>
├ <b>Toplam Kullanıcı:</b> {total_users}
├ <b>Aktif Kullanıcı (24s):</b> {active_users}
├ <b>Reklamverenler:</b> {total_advertisers}
├ <b>Toplam Bakiye:</b> {total_balance:.2f}₺
└ <b>Reklam Bakiyesi:</b> {total_ad_balance:.2f}₺

<b>💰 FİNANSAL İSTATİSTİKLER</b>
├ <b>Toplam Yatırım:</b> {total_deposit_amount:.2f}₺
├ <b>Toplam Çekim:</b> {total_withdraw_amount:.2f}₺
└ <b>Toplam Harcama:</b> {total_ad_balance:.2f}₺

<b>📈 BUGÜNKÜ İSTATİSTİKLER ({now.strftime('%d.%m.%Y')})</b>
├ <b>Depozit:</b> {today_deposits} adet, {today_deposit_amount:.2f}₺
├ <b>Çekim:</b> {today_withdrawals} adet, {today_withdraw_amount:.2f}₺
├ <b>Görev:</b> {today_tasks} adet, {today_tasks_spent:.2f}₺
└ <b>Kazanç:</b> {today_earnings:.2f}₺

<b>💰 SON 5 DEPOZİT (BUGÜN)</b>
"""
        
        if recent_deposits:
            for dep in recent_deposits:
                user_name = dep['name'] or "Anonim"
                deposit_type = "👑" if dep['deposit_type'] == 'advertiser' else "👤"
                time_str = dep['completed_at'][11:16] if dep['completed_at'] else "??:??"
                message += f"├ {deposit_type} <b>{user_name[:15]}</b>: {dep['amount_try']:.2f}₺ ({time_str})\n"
            message += "└ ────────────────\n"
        else:
            message += "└ <i>Bugün depozit yok</i>\n"
        
        message += f"\n<b>💸 SON 5 ÇEKİM (BUGÜN)</b>\n"
        if recent_withdrawals:
            for wd in recent_withdrawals:
                user_name = wd['name'] or "Anonim"
                time_str = wd['completed_at'][11:16] if wd['completed_at'] else "??:??"
                message += f"├ 👤 <b>{user_name[:15]}</b>: {wd['amount']:.2f}₺ ({time_str})\n"
            message += "└ ────────────────\n"
        else:
            message += "└ <i>Bugün çekim yok</i>\n"
        
        message += f"\n<b>📢 SON 5 GÖREV (BUGÜN)</b>\n"
        if recent_tasks:
            for task in recent_tasks:
                task_type = "👥" if task['task_type'] == 'group' else "📢"
                advertiser_name = task['advertiser_name'] or "Anonim"
                time_str = task['created_at'][11:16]
                message += f"├ {task_type} <b>{advertiser_name[:15]}</b>: {task['reward_amount']:.2f}₺ ({time_str})\n"
            message += "└ ────────────────\n"
        else:
            message += "└ <i>Bugün görev yok</i>\n"
        
        message += f"\n<b>✅ SON 5 GÖREV TAMAMLAMA (BUGÜN)</b>\n"
        if recent_task_completions:
            for comp in recent_task_completions:
                participant_name = comp['participant_name'] or "Anonim"
                time_str = comp['paid_at'][11:16] if comp['paid_at'] else "??:??"
                message += f"├ 👤 <b>{participant_name[:15]}</b>: {comp['reward_paid']:.2f}₺ ({time_str})\n"
            message += "└ ────────────────\n"
        else:
            message += "└ <i>Bugün görev tamamlama yok</i>\n"
        
        # Aktif kampanyalar
        self.db.cursor.execute('''
            SELECT * FROM campaigns 
            WHERE status = 'active'
            ORDER BY created_at DESC 
            LIMIT 3
        ''')
        active_campaigns = self.db.cursor.fetchall()
        
        if active_campaigns:
            message += f"\n<b>🎯 AKTİF KAMPANYALAR</b>\n"
            for campaign in active_campaigns:
                message += f"├ <b>{campaign['name']}</b>: {campaign['description'][:50]}...\n"
            message += "└ ────────────────\n"
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>🤖 BOT:</b> @GorevYapsamBot
<b>💬 SOHBET:</b> @{MANDATORY_CHANNEL}
<b>📢 REFERANS:</b> @{REFERENCE_GROUP}
<b>🔄 GERÇEK ZAMANLI GÜNCELLENMEKTEDİR</b>
"""
        
        return message
    
    def notify_deposit(self, user_id, amount, deposit_type="user"):
        """Depozit bildirimi gönder"""
        try:
            user = self.db.get_user(user_id)
            user_name = user.get('name', 'Anonim')
            
            message = f"""
<b>💰 YENİ DEPOZİT!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

{'👑 REKLAMVEREN' if deposit_type == 'advertiser' else '👤 KULLANICI'}

<b>👤 Kullanıcı:</b> {user_name}
<b>💰 Tutar:</b> {amount:.2f}₺
<b>⏰ Zaman:</b> {get_turkey_time().strftime('%H:%M:%S')}

{'💡 Reklamveren bakiyesine eklendi!' if deposit_type == 'advertiser' else '🎉 Bonuslu bakiye yüklendi!'}
"""
            
            send_message(f"@{REFERENCE_GROUP}", message)
            
        except Exception as e:
            print(f"❌ Depozit bildirimi hatası: {e}")
    
    def notify_withdrawal(self, user_id, amount, withdrawal_id):
        """Çekim bildirimi gönder"""
        try:
            user = self.db.get_user(user_id)
            user_name = user.get('name', 'Anonim')
            
            message = f"""
<b>💸 YENİ PARA ÇEKİMİ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👤 Kullanıcı:</b> {user_name}
<b>💰 Tutar:</b> {amount:.2f}₺
<b>📋 Talep ID:</b> {withdrawal_id[:10]}
<b>⏰ Zaman:</b> {get_turkey_time().strftime('%H:%M:%S')}

💡 Kullanıcı parasını çekti!
"""
            
            send_message(f"@{REFERENCE_GROUP}", message)
            
        except Exception as e:
            print(f"❌ Çekim bildirimi hatası: {e}")
    
    def notify_task_completed(self, task_id, user_id, amount):
        """Görev tamamlama bildirimi"""
        try:
            user = self.db.get_user(user_id)
            user_name = user.get('name', 'Anonim')
            
            # Görev bilgilerini al
            self.db.cursor.execute('''
                SELECT t.*, u.name as advertiser_name 
                FROM tasks t 
                LEFT JOIN users u ON t.advertiser_id = u.user_id 
                WHERE t.task_id = ?
            ''', (task_id,))
            task = self.db.cursor.fetchone()
            
            if task:
                task_type = "👥 GRUP" if task['task_type'] == 'group' else "📢 KANAL"
                advertiser_name = task['advertiser_name'] or "Anonim"
                
                message = f"""
<b>✅ GÖREV TAMAMLANDI!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>{task_type} GÖREVİ</b>

<b>👤 Katılımcı:</b> {user_name}
<b>👑 Reklamveren:</b> {advertiser_name}
<b>💰 Ödül:</b> {amount:.2f}₺
<b>⏰ Zaman:</b> {get_turkey_time().strftime('%H:%M:%S')}

💡 Kullanıcı görevi tamamladı ve ödülünü aldı!
"""
                
                send_message(f"@{REFERENCE_GROUP}", message)
                
        except Exception as e:
            print(f"❌ Görev bildirimi hatası: {e}")
    
    def notify_new_task(self, task_id, advertiser_id):
        """Yeni görev bildirimi"""
        try:
            user = self.db.get_user(advertiser_id)
            user_name = user.get('name', 'Anonim')
            
            # Görev bilgilerini al
            self.db.cursor.execute('''
                SELECT * FROM tasks WHERE task_id = ?
            ''', (task_id,))
            task = self.db.cursor.fetchone()
            
            if task:
                task_type = "👥 GRUP" if task['task_type'] == 'group' else "📢 KANAL"
                
                message = f"""
<b>📢 YENİ GÖREV OLUŞTURULDU!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>{task_type} GÖREVİ</b>

<b>👑 Reklamveren:</b> {user_name}
<b>🎯 Hedef:</b> {task['target_name']}
<b>💰 Ödül:</b> {task['reward_amount']:.2f}₺
<b>👥 Katılımcı:</b> {task['max_participants']} kişi
<b>⏰ Zaman:</b> {get_turkey_time().strftime('%H:%M:%S')}

💡 Yeni görev oluşturuldu!
"""
                
                send_message(f"@{REFERENCE_GROUP}", message)
                
        except Exception as e:
            print(f"❌ Yeni görev bildirimi hatası: {e}")
    
    def notify_withdrawal_completed(self, withdrawal_id, user_id, amount):
        """Çekim tamamlama bildirimi"""
        try:
            user = self.db.get_user(user_id)
            user_name = user.get('name', 'Anonim')
            
            message = f"""
<b>✅ PARA ÇEKİMİ TAMAMLANDI!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👤 Kullanıcı:</b> {user_name}
<b>💰 Tutar:</b> {amount:.2f}₺
<b>📋 Talep ID:</b> {withdrawal_id[:10]}
<b>⏰ Zaman:</b> {get_turkey_time().strftime('%H:%M:%S')}

💡 Çekim işlemi başarıyla tamamlandı!
"""
            
            send_message(f"@{REFERENCE_GROUP}", message)
            
        except Exception as e:
            print(f"❌ Çekim tamamlama bildirimi hatası: {e}")

# Database
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot.db', check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.init_db()
    
    def init_db(self):
        # Kullanıcılar
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                username TEXT,
                balance REAL DEFAULT 0.0,
                ads_balance REAL DEFAULT 0.0,
                normal_balance REAL DEFAULT 0.0,
                total_earned REAL DEFAULT 0.0,
                tasks_completed INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                ref_earned REAL DEFAULT 0.0,
                daily_streak INTEGER DEFAULT 0,
                last_daily TEXT,
                in_channel INTEGER DEFAULT 0,
                created_at TEXT,
                welcome_bonus INTEGER DEFAULT 0,
                total_deposited REAL DEFAULT 0.0,
                deposit_count INTEGER DEFAULT 0,
                total_bonus REAL DEFAULT 0.0,
                language TEXT DEFAULT 'tr',
                notification_enabled INTEGER DEFAULT 1,
                last_active TEXT,
                referral_code TEXT,
                referred_by TEXT,
                total_withdrawn REAL DEFAULT 0.0,
                withdraw_count INTEGER DEFAULT 0,
                last_notification_time TEXT,
                is_referred INTEGER DEFAULT 0,
                ref_first_login INTEGER DEFAULT 0,
                ref_link_used TEXT,
                is_advertiser INTEGER DEFAULT 0,
                advertiser_balance REAL DEFAULT 0.0,
                total_spent_on_ads REAL DEFAULT 0.0,
                active_group_id TEXT,
                active_channel_id TEXT,
                last_join_check TEXT
            )
        ''')
        
        # Görevler (Tasks)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                advertiser_id TEXT,
                task_type TEXT,
                target_id TEXT,
                target_name TEXT,
                task_description TEXT,
                reward_amount REAL,
                max_participants INTEGER,
                current_participants INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                completed_at TEXT,
                total_spent REAL DEFAULT 0.0,
                is_paid INTEGER DEFAULT 0
            )
        ''')
        
        # Görev Katılımları
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_participations (
                participation_id TEXT PRIMARY KEY,
                task_id TEXT,
                user_id TEXT,
                user_name TEXT,
                status TEXT DEFAULT 'pending',
                joined_at TEXT,
                left_at TEXT,
                reward_paid REAL DEFAULT 0.0,
                paid_at TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
            )
        ''')
        
        # Referans kayıtları
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id TEXT,
                referred_id TEXT,
                referral_link TEXT,
                amount REAL DEFAULT 0.0,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                completed_at TEXT,
                reward_type TEXT,
                FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                FOREIGN KEY (referred_id) REFERENCES users (user_id)
            )
        ''')
        
        # Çekimler
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                withdrawal_id TEXT PRIMARY KEY,
                user_id TEXT,
                amount REAL,
                trx_address TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                completed_at TEXT,
                admin_notes TEXT,
                txid TEXT
            )
        ''')
        
        # Depozitler
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposits (
                deposit_id TEXT PRIMARY KEY,
                user_id TEXT,
                amount_try REAL,
                amount_trx REAL,
                txid TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                completed_at TEXT,
                bonus_amount REAL DEFAULT 0.0,
                trx_price REAL,
                deposit_type TEXT DEFAULT 'user'
            )
        ''')
        
        # Kampanyalar
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                reward REAL,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                expires_at TEXT
            )
        ''')
        
        self.conn.commit()
        print("✅ Veritabanı hazır")
    
    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = self.cursor.fetchone()
        
        if not user:
            now = get_turkey_time().isoformat()
            referral_code = f"ref_{user_id[-8:]}"
            self.cursor.execute('''
                INSERT INTO users (user_id, name, balance, ads_balance, normal_balance, created_at, language, last_active, referral_code, last_notification_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, '', 0.0, 0.0, 0.0, now, 'tr', now, referral_code, now))
            self.conn.commit()
            
            self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = self.cursor.fetchone()
        
        return dict(user) if user else {}
    
    def update_user(self, user_id, data):
        if not data: return False
        data['last_active'] = get_turkey_time().isoformat()
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        values = list(data.values())
        values.append(user_id)
        query = f"UPDATE users SET {set_clause} WHERE user_id = ?"
        self.cursor.execute(query, values)
        self.conn.commit()
        return True
    
    def add_balance(self, user_id, amount, balance_type="normal", bonus_percent=0, source="system"):
        """Bakiye ekle - balance_type: 'normal' veya 'advertiser'"""
        user = self.get_user(user_id)
        
        if balance_type == "advertiser":
            # Reklam bakiyesi ekle
            bonus = amount * bonus_percent / 100
            total = amount + bonus
            new_balance = user.get('ads_balance', 0) + total
            
            self.cursor.execute('''
                UPDATE users 
                SET ads_balance = ?, total_deposited = total_deposited + ?
                WHERE user_id = ?
            ''', (new_balance, amount, user_id))
            
        else:
            # Normal bakiye ekle
            bonus = amount * bonus_percent / 100
            total = amount + bonus
            new_balance = user.get('balance', 0) + total
            
            self.cursor.execute('''
                UPDATE users 
                SET balance = ?, normal_balance = normal_balance + ?, total_earned = total_earned + ?, total_bonus = total_bonus + ? 
                WHERE user_id = ?
            ''', (new_balance, total, total, bonus, user_id))
        
        self.conn.commit()
        
        # Bakiye eklendi bildirimi
        if amount > 0:
            balance_type_text = "reklam" if balance_type == "advertiser" else "normal"
            source_text = "sistem" if source == "system" else "referans"
            message = f"""
<b>💰 {balance_type_text.upper()} BAKİYE EKLENDİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>+{total:.2f}₺ {balance_type_text} bakiyenize eklendi!</b>

📊 <b>Detaylar:</b>
• Kaynak: {source_text}
• Tutar: {amount:.2f}₺
• Bonus: {bonus:.2f}₺ (%{bonus_percent})
• Yeni {balance_type_text.capitalize()} Bakiye: {new_balance:.2f}₺

💡 <b>Hemen görev yapmaya başlayın!</b>
"""
            send_message(user_id, message)
        
        return True
    
    def convert_balance(self, user_id, amount, from_type, to_type):
        """Bakiye dönüştür - reklam bakiyesini normal bakiyeye veya tam tersi"""
        user = self.get_user(user_id)
        
        if from_type == "advertiser" and to_type == "normal":
            # Reklam bakiyesinden normal bakiyeye
            if user.get('ads_balance', 0) < amount:
                return False, "Yetersiz reklam bakiyesi!"
            
            new_ad_balance = user.get('ads_balance', 0) - amount
            new_normal_balance = user.get('normal_balance', 0) + amount
            
            self.cursor.execute('''
                UPDATE users 
                SET ads_balance = ?, normal_balance = ?, balance = normal_balance
                WHERE user_id = ?
            ''', (new_ad_balance, new_normal_balance, user_id))
            
            message = f"✅ {amount:.2f}₺ reklam bakiyesi normal bakiyeye dönüştürüldü!"
            
        elif from_type == "normal" and to_type == "advertiser":
            # Normal bakiyeden reklam bakiyesine
            if user.get('normal_balance', 0) < amount:
                return False, "Yetersiz normal bakiye!"
            
            new_normal_balance = user.get('normal_balance', 0) - amount
            new_ad_balance = user.get('ads_balance', 0) + amount
            
            self.cursor.execute('''
                UPDATE users 
                SET normal_balance = ?, ads_balance = ?, balance = normal_balance
                WHERE user_id = ?
            ''', (new_normal_balance, new_ad_balance, user_id))
            
            message = f"✅ {amount:.2f}₺ normal bakiye reklam bakiyesine dönüştürüldü!"
        
        else:
            return False, "Geçersiz dönüşüm türü!"
        
        self.conn.commit()
        return True, message
    
    def add_advertiser_balance(self, user_id, amount):
        """Reklamveren bakiyesine ekle"""
        return self.add_balance(user_id, amount, "advertiser", 0, "deposit")
    
    def deduct_advertiser_balance(self, user_id, amount):
        """Reklamveren bakiyesinden düş"""
        user = self.get_user(user_id)
        current_balance = user.get('ads_balance', 0)
        
        if current_balance < amount:
            return False, "Yetersiz reklamveren bakiyesi!"
        
        new_balance = current_balance - amount
        
        self.cursor.execute('''
            UPDATE users 
            SET ads_balance = ?, total_spent_on_ads = total_spent_on_ads + ?
            WHERE user_id = ?
        ''', (new_balance, amount, user_id))
        self.conn.commit()
        
        return True, f"{amount:.2f}₺ reklamveren bakiyenizden düşüldü"
    
    def create_task(self, advertiser_id, task_type, target_id, target_name, description, reward, max_participants):
        """Yeni görev oluştur"""
        task_id = hashlib.md5(f"{advertiser_id}{target_id}{time.time()}".encode()).hexdigest()[:10].upper()
        now = get_turkey_time().isoformat()
        
        self.cursor.execute('''
            INSERT INTO tasks (task_id, advertiser_id, task_type, target_id, target_name, 
                             task_description, reward_amount, max_participants, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (task_id, advertiser_id, task_type, target_id, target_name, 
              description, reward, max_participants, now))
        self.conn.commit()
        
        return task_id
    
    def join_task(self, task_id, user_id, user_name):
        """Göreve katıl"""
        participation_id = hashlib.md5(f"{task_id}{user_id}{time.time()}".encode()).hexdigest()[:10].upper()
        now = get_turkey_time().isoformat()
        
        # Önce katılım var mı kontrol et
        self.cursor.execute('''
            SELECT * FROM task_participations 
            WHERE task_id = ? AND user_id = ?
        ''', (task_id, user_id))
        existing = self.cursor.fetchone()
        
        if existing:
            return False, "Zaten bu göreve katıldınız!"
        
        self.cursor.execute('''
            INSERT INTO task_participations (participation_id, task_id, user_id, user_name, joined_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (participation_id, task_id, user_id, user_name, now))
        
        # Görev katılımcı sayısını güncelle
        self.cursor.execute('''
            UPDATE tasks SET current_participants = current_participants + 1 
            WHERE task_id = ?
        ''', (task_id,))
        
        self.conn.commit()
        return True, "Göreve katıldınız!"
    
    def verify_task_participation(self, participation_id):
        """Görev katılımını doğrula ve ödeme yap"""
        self.cursor.execute('''
            SELECT tp.*, t.advertiser_id, t.reward_amount, t.task_type
            FROM task_participations tp
            JOIN tasks t ON tp.task_id = t.task_id
            WHERE tp.participation_id = ?
        ''', (participation_id,))
        participation = self.cursor.fetchone()
        
        if not participation:
            return False, "Katılım bulunamadı"
        
        if participation['status'] == 'verified':
            return False, "Zaten doğrulanmış"
        
        now = get_turkey_time().isoformat()
        
        # Reklamveren bakiyesini kontrol et
        advertiser = self.get_user(participation['advertiser_id'])
        if advertiser.get('ads_balance', 0) < participation['reward_amount']:
            return False, "Reklamveren bakiyesi yetersiz!"
        
        # Reklamveren bakiyesinden düş
        success, message = self.deduct_advertiser_balance(
            participation['advertiser_id'], 
            participation['reward_amount']
        )
        
        if not success:
            return False, message
        
        # Kullanıcıya ödeme yap
        user = self.get_user(participation['user_id'])
        new_balance = user.get('balance', 0) + participation['reward_amount']
        
        self.cursor.execute('''
            UPDATE users 
            SET balance = ?, normal_balance = normal_balance + ?, tasks_completed = tasks_completed + 1, total_earned = total_earned + ?
            WHERE user_id = ?
        ''', (new_balance, participation['reward_amount'], participation['reward_amount'], participation['user_id']))
        
        # Katılımı güncelle
        self.cursor.execute('''
            UPDATE task_participations 
            SET status = 'verified', reward_paid = ?, paid_at = ?
            WHERE participation_id = ?
        ''', (participation['reward_amount'], now, participation_id))
        
        # Görev giderini güncelle
        self.cursor.execute('''
            UPDATE tasks 
            SET total_spent = total_spent + ?
            WHERE task_id = ?
        ''', (participation['reward_amount'], participation['task_id']))
        
        self.conn.commit()
        
        return True, f"{participation['reward_amount']:.2f}₺ ödendi"
    
    def create_withdrawal(self, user_id, amount, trx_address):
        """Para çekme talebi oluştur"""
        withdrawal_id = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:10].upper()
        now = get_turkey_time().isoformat()
        
        self.cursor.execute('''
            INSERT INTO withdrawals (withdrawal_id, user_id, amount, trx_address, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        ''', (withdrawal_id, user_id, amount, trx_address, now))
        self.conn.commit()
        
        return withdrawal_id
    
    def complete_withdrawal(self, withdrawal_id, txid):
        """Para çekme işlemini tamamla"""
        now = get_turkey_time().isoformat()
        
        # Çekim bilgilerini al
        self.cursor.execute('''
            SELECT * FROM withdrawals WHERE withdrawal_id = ?
        ''', (withdrawal_id,))
        withdrawal = self.cursor.fetchone()
        
        if not withdrawal:
            return False, "Çekim bulunamadı"
        
        # Kullanıcıyı güncelle
        self.cursor.execute('''
            UPDATE users 
            SET total_withdrawn = total_withdrawn + ?, withdraw_count = withdraw_count + 1
            WHERE user_id = ?
        ''', (withdrawal['amount'], withdrawal['user_id']))
        
        # Çekimi tamamla
        self.cursor.execute('''
            UPDATE withdrawals 
            SET status = 'completed', completed_at = ?, txid = ?
            WHERE withdrawal_id = ?
        ''', (now, txid, withdrawal_id))
        
        self.conn.commit()
        return True, f"{withdrawal['amount']:.2f}₺ çekim tamamlandı"
    
    def check_referral_usage(self, user_id, referral_code):
        """Kullanıcının bu referans kodunu daha önce kullanıp kullanmadığını kontrol et"""
        self.cursor.execute('''
            SELECT ref_link_used FROM users WHERE user_id = ?
        ''', (user_id,))
        result = self.cursor.fetchone()
        if result and result[0]:
            return result[0] == referral_code
        return False
    
    def record_referral(self, referrer_id, referred_id, referral_link, amount=0.0):
        """Referans kaydı oluştur"""
        now = get_turkey_time().isoformat()
        self.cursor.execute('''
            INSERT INTO referral_logs (referrer_id, referred_id, referral_link, amount, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (referrer_id, referred_id, referral_link, amount, now, 'pending'))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def complete_referral(self, log_id, reward_type="welcome"):
        """Referansı tamamla ve bonus ver"""
        now = get_turkey_time().isoformat()
        self.cursor.execute('''
            UPDATE referral_logs 
            SET status = 'completed', completed_at = ?, reward_type = ?
            WHERE log_id = ?
        ''', (now, reward_type, log_id))
        self.conn.commit()

# Telegram Fonksiyonları
def send_message(chat_id, text, markup=None, parse_mode='HTML'):
    url = BASE_URL + "sendMessage"
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
    if markup: data['reply_markup'] = json.dumps(markup)
    try: 
        response = requests.post(url, json=data, timeout=10).json()
        return response
    except Exception as e:
        print(f"❌ Mesaj hatası: {e}")
        return None

def edit_message_text(chat_id, message_id, text, markup=None, parse_mode='HTML'):
    url = BASE_URL + "editMessageText"
    data = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'parse_mode': parse_mode}
    if markup: data['reply_markup'] = json.dumps(markup)
    try: 
        response = requests.post(url, json=data, timeout=10).json()
        return response
    except Exception as e:
        print(f"❌ Mesaj düzenleme hatası: {e}")
        return None

def answer_callback(callback_id, text=None, show_alert=False):
    url = BASE_URL + "answerCallbackQuery"
    data = {'callback_query_id': callback_id}
    if text: data['text'] = text
    if show_alert: data['show_alert'] = True
    try: 
        requests.post(url, json=data, timeout=5)
    except: 
        pass

def get_chat_member(chat_id, user_id):
    url = BASE_URL + "getChatMember"
    data = {'chat_id': chat_id, 'user_id': int(user_id)}
    try:
        response = requests.post(url, json=data, timeout=10).json()
        if response.get('ok'):
            status = response['result']['status']
            return status in ['member', 'administrator', 'creator']
    except: 
        print(f"❌ Chat member kontrol hatası: chat_id={chat_id}, user_id={user_id}")
        return False

def get_chat(chat_id):
    url = BASE_URL + "getChat"
    data = {'chat_id': chat_id}
    try:
        response = requests.post(url, json=data, timeout=10).json()
        if response.get('ok'):
            return response['result']
    except: 
        return None

def check_bot_admin(chat_id):
    bot_id = int(TOKEN.split(':')[0])
    url = BASE_URL + "getChatMember"
    data = {'chat_id': chat_id, 'user_id': bot_id}
    try:
        response = requests.post(url, json=data, timeout=10).json()
        if response.get('ok'):
            status = response['result']['status']
            return status in ['administrator', 'creator']
    except: 
        return False

# Bot Sistemi
class BotSystem:
    def __init__(self):
        self.db = Database()
        self.reference_notifier = ReferenceGroupNotifier(self.db)
        self.user_states = {}
        self.trx_price = 12.61
        self.update_trx_price()
        self.background_checker = BackgroundChecker(self.db)
        self.background_checker.start()
        self.reference_notifier.start()
        print("🤖 Bot sistemi başlatıldı")
    
    def update_trx_price(self):
        try:
            response = requests.get(TRX_PRICE_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.trx_price = data.get('tron', {}).get('try', 12.61)
        except: 
            pass
    
    def set_user_state(self, user_id, state, data=None):
        self.user_states[user_id] = {'state': state, 'data': data or {}, 'step': 1}
    
    def get_user_state(self, user_id):
        return self.user_states.get(user_id, {'state': None, 'data': {}, 'step': 1})
    
    def clear_user_state(self, user_id):
        if user_id in self.user_states:
            del self.user_states[user_id]
    
    def start_polling(self):
        offset = 0
        print("🔄 Telegram polling başladı...")
        
        while True:
            try:
                url = BASE_URL + "getUpdates"
                params = {'offset': offset, 'timeout': 10, 'allowed_updates': ['message', 'callback_query', 'chat_member']}
                response = requests.get(url, params=params, timeout=15).json()
                
                if response.get('ok'):
                    updates = response['result']
                    for update in updates:
                        offset = update['update_id'] + 1
                        
                        if 'message' in update:
                            threading.Thread(target=self.process_message, args=(update['message'],)).start()
                        elif 'callback_query' in update:
                            threading.Thread(target=self.process_callback, args=(update['callback_query'],)).start()
                        elif 'chat_member' in update:
                            threading.Thread(target=self.process_chat_member_update, args=(update['chat_member'],)).start()
                
            except Exception as e:
                print(f"❌ Polling hatası: {e}")
                time.sleep(2)
    
    def process_chat_member_update(self, chat_member_update):
        """Kullanıcı grup/kanal üyelik değişikliklerini işle"""
        try:
            if 'old_chat_member' in chat_member_update and 'new_chat_member' in chat_member_update:
                user_id = str(chat_member_update['new_chat_member']['user']['id'])
                chat_id = str(chat_member_update['chat']['id'])
                
                old_status = chat_member_update['old_chat_member']['status']
                new_status = chat_member_update['new_chat_member']['status']
                
                # Kullanıcı gruptan/kanaldan ayrıldı mı?
                if old_status in ['member', 'administrator', 'creator'] and new_status == 'left':
                    print(f"⚠️ Kullanıcı {user_id} gruptan/kanaldan ayrıldı: {chat_id}")
                    
                    # Grup mu kanal mı kontrol et
                    chat_info = get_chat(chat_id)
                    if chat_info:
                        chat_type = chat_info.get('type', '')
                        
                        if chat_type == 'group' or chat_type == 'supergroup':
                            # Grup için işlem yap
                            deducted, amount = self.handle_user_left_group(user_id, chat_id)
                            if deducted:
                                print(f"✅ {user_id} kullanıcısından {amount}₺ düşüldü (gruptan ayrılma)")
                        
                        elif chat_type == 'channel':
                            # Kanal için işlem yap
                            deducted, amount = self.handle_user_left_channel(user_id, chat_id)
                            if deducted:
                                print(f"✅ {user_id} kullanıcısından {amount}₺ düşüldü (kanaldan ayrılma)")
                        
                        # Zorunlu kanal kontrolü
                        if f"@{MANDATORY_CHANNEL}" in chat_info.get('username', ''):
                            print(f"⚠️ Kullanıcı {user_id} zorunlu kanaldan ayrıldı!")
                            self.db.update_user(user_id, {'in_channel': 0})
                            send_message(user_id, f"""
<b>⚠️ ZORUNLU KANALDAN AYRILDINIZ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ <b>@{MANDATORY_CHANNEL} kanalından ayrıldınız!</b>

📊 <b>Sonuçlar:</b>
• Botu kullanamazsınız
• Mevcut görevleriniz iptal edilebilir
• Kazançlarınız düşülebilir

💡 <b>Tekrar katılmak için:</b>
1. @{MANDATORY_CHANNEL} kanalına katılın
2. /start yazarak botu yeniden başlatın
""")
                
                # Kullanıcı gruba/kanala katıldı mı?
                elif old_status == 'left' and new_status in ['member', 'administrator', 'creator']:
                    print(f"✅ Kullanıcı {user_id} gruba/kanala katıldı: {chat_id}")
                    
                    # Zorunlu kanal kontrolü
                    chat_info = get_chat(chat_id)
                    if chat_info and f"@{MANDATORY_CHANNEL}" in chat_info.get('username', ''):
                        print(f"✅ Kullanıcı {user_id} zorunlu kanala katıldı!")
                        self.db.update_user(user_id, {'in_channel': 1})
        
        except Exception as e:
            print(f"❌ Chat member update hatası: {e}")
    
    def handle_user_left_group(self, user_id, chat_id):
        """Kullanıcı gruptan çıkınca işlem yap"""
        # Aktif grup görevlerini bul
        self.db.cursor.execute('''
            SELECT tp.*, t.reward_amount, t.advertiser_id
            FROM task_participations tp
            JOIN tasks t ON tp.task_id = t.task_id
            WHERE tp.user_id = ? AND t.target_id = ? 
            AND t.task_type = 'group' AND tp.status = 'verified'
        ''', (user_id, chat_id))
        
        participations = self.db.cursor.fetchall()
        
        total_deducted = 0
        for participation in participations:
            # Kullanıcının bakiyesinden düş
            user = self.db.get_user(user_id)
            if user.get('balance', 0) >= participation['reward_amount']:
                new_balance = user.get('balance', 0) - participation['reward_amount']
                new_normal_balance = user.get('normal_balance', 0) - participation['reward_amount']
                
                self.db.cursor.execute('''
                    UPDATE users SET balance = ?, normal_balance = ?, total_earned = total_earned - ? WHERE user_id = ?
                ''', (new_balance, new_normal_balance, participation['reward_amount'], user_id))
                
                # Reklamverene iade
                advertiser = self.db.get_user(participation['advertiser_id'])
                new_ad_balance = advertiser.get('ads_balance', 0) + participation['reward_amount']
                self.db.cursor.execute('''
                    UPDATE users SET ads_balance = ?, total_spent_on_ads = total_spent_on_ads - ?
                    WHERE user_id = ?
                ''', (new_ad_balance, participation['reward_amount'], participation['advertiser_id']))
                
                # Katılım durumunu güncelle
                now = get_turkey_time().isoformat()
                self.db.cursor.execute('''
                    UPDATE task_participations 
                    SET status = 'left', left_at = ?, reward_paid = 0
                    WHERE participation_id = ?
                ''', (now, participation['participation_id']))
                
                total_deducted += participation['reward_amount']
                
                # Bildirim gönder
                send_message(user_id, f"""
<b>⚠️ GRUPTAN AYRILMA CEZASI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ <b>{participation['reward_amount']:.2f}₺ bakiyenizden düşüldü!</b>

📊 <b>Sebep:</b>
• Grubu terk ettiğiniz için
• Görev ödülü iade edildi

💡 <b>Tekrar katılın ve kazanmaya devam edin!</b>
""")
        
        self.db.conn.commit()
        return total_deducted > 0, total_deducted
    
    def handle_user_left_channel(self, user_id, chat_id):
        """Kullanıcı kanaldan çıkınca işlem yap"""
        # Aktif kanal görevlerini bul
        self.db.cursor.execute('''
            SELECT tp.*, t.reward_amount, t.advertiser_id
            FROM task_participations tp
            JOIN tasks t ON tp.task_id = t.task_id
            WHERE tp.user_id = ? AND t.target_id = ? 
            AND t.task_type = 'channel' AND tp.status = 'verified'
        ''', (user_id, chat_id))
        
        participations = self.db.cursor.fetchall()
        
        total_deducted = 0
        for participation in participations:
            # Kullanıcının bakiyesinden düş
            user = self.db.get_user(user_id)
            if user.get('balance', 0) >= participation['reward_amount']:
                new_balance = user.get('balance', 0) - participation['reward_amount']
                new_normal_balance = user.get('normal_balance', 0) - participation['reward_amount']
                
                self.db.cursor.execute('''
                    UPDATE users SET balance = ?, normal_balance = ?, total_earned = total_earned - ? WHERE user_id = ?
                ''', (new_balance, new_normal_balance, participation['reward_amount'], user_id))
                
                # Reklamverene iade
                advertiser = self.db.get_user(participation['advertiser_id'])
                new_ad_balance = advertiser.get('ads_balance', 0) + participation['reward_amount']
                self.db.cursor.execute('''
                    UPDATE users SET ads_balance = ?, total_spent_on_ads = total_spent_on_ads - ?
                    WHERE user_id = ?
                ''', (new_ad_balance, participation['reward_amount'], participation['advertiser_id']))
                
                # Katılım durumunu güncelle
                now = get_turkey_time().isoformat()
                self.db.cursor.execute('''
                    UPDATE task_participations 
                    SET status = 'left', left_at = ?, reward_paid = 0
                    WHERE participation_id = ?
                ''', (now, participation['participation_id']))
                
                total_deducted += participation['reward_amount']
                
                # Bildirim gönder
                send_message(user_id, f"""
<b>⚠️ KANALDAN AYRILMA CEZASI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ <b>{participation['reward_amount']:.2f}₺ bakiyenizden düşüldü!</b>

📊 <b>Sebep:</b>
• Kanalı terk ettiğiniz için
• Görev ödülü iade edildi

💡 <b>Tekrar katılın ve kazanmaya devam edin!</b>
""")
        
        self.db.conn.commit()
        return total_deducted > 0, total_deducted
    
    def process_message(self, message):
        try:
            if 'from' not in message: 
                return
            
            user_id = str(message['from']['id'])
            
            # Hızlı yanıt
            if 'text' in message:
                text = message['text']
                if text.startswith('/start'):
                    self.handle_start(user_id, text)
                    return
                elif text == '/menu':
                    self.show_main_menu(user_id)
                    return
                elif text == '/admin' and user_id == ADMIN_ID:
                    self.show_admin_panel(user_id)
                    return
                elif text == '/reklamveren':
                    self.show_advertiser_menu(user_id)
                    return
                elif text == '/gorevler':
                    self.show_available_tasks(user_id)
                    return
                elif text == '/istatistik':
                    self.show_user_stats(user_id)
                    return
                elif text == '/referans':
                    self.show_referral_menu(user_id)
                    return
            
            user_state = self.get_user_state(user_id)
            
            user = self.db.get_user(user_id)
            if not user.get('name'):
                self.db.update_user(user_id, {
                    'name': message['from'].get('first_name', 'Kullanıcı'),
                    'username': message['from'].get('username', '')
                })
            
            # Kullanıcı state'i varsa önce onu işle
            if user_state['state']:
                self.handle_user_state(user_id, message, user_state)
                return
        
        except Exception as e:
            print(f"❌ Mesaj hatası: {e}")
    
    def process_callback(self, callback):
        try:
            user_id = str(callback['from']['id'])
            data = callback['data']
            callback_id = callback['id']
            
            # Hızlı yanıt
            answer_callback(callback_id, "⏳ İşleniyor...")
            
            # Temel navigasyon
            if data == 'menu':
                self.show_main_menu(user_id)
            elif data == 'back':
                self.show_main_menu(user_id)
            elif data == 'cancel':
                self.clear_user_state(user_id)
                self.show_main_menu(user_id)
            elif data == 'advertiser_back':
                self.show_advertiser_menu(user_id)
            
            # Ana menü butonları
            elif data == 'tasks':
                self.show_available_tasks(user_id)
            elif data == 'my_tasks':
                self.show_my_tasks(user_id)
            elif data == 'deposit':
                self.show_deposit_menu(user_id)
            elif data == 'withdraw':
                self.show_withdraw_menu(user_id)
            elif data == 'profile':
                self.show_profile(user_id)
            elif data == 'referral':
                self.show_referral_menu(user_id)
            elif data == 'help':
                self.show_help(user_id)
            elif data == 'advertiser_menu':
                self.show_advertiser_menu(user_id)
            elif data == 'stats':
                self.show_user_stats(user_id)
            elif data == 'convert_balance':
                self.show_convert_balance_menu(user_id)
            
            # Reklamveren butonları
            elif data == 'advertiser_deposit':
                self.show_advertiser_deposit_menu(user_id)
            elif data == 'advertiser_balance':
                self.show_advertiser_balance(user_id)
            elif data == 'advertiser_create_task':
                self.start_advertiser_task_creation(user_id)
            elif data == 'advertiser_my_tasks':
                self.show_advertiser_my_tasks(user_id)
            elif data == 'advertiser_withdraw':
                self.start_advertiser_withdraw(user_id)
            elif data == 'toggle_advertiser':
                self.toggle_advertiser_mode(user_id)
            
            # Bakiye dönüşüm butonları
            elif data == 'convert_to_normal':
                self.start_convert_balance(user_id, 'to_normal')
            elif data == 'convert_to_ads':
                self.start_convert_balance(user_id, 'to_ads')
            
            # Görev türü
            elif data.startswith('task_type_'):
                task_type = data.replace('task_type_', '')
                self.handle_task_type_selection(user_id, task_type)
            
            # Depozit tutarları
            elif data.startswith('deposit_amount_'):
                parts = data.replace('deposit_amount_', '').split('_')
                amount = float(parts[0])
                deposit_type = parts[1] if len(parts) > 1 else 'user'
                self.start_deposit(user_id, amount, deposit_type)
            
            # Görev katılımı
            elif data.startswith('join_task_'):
                task_id = data.replace('join_task_', '')
                self.join_task(user_id, task_id)
            
            # Görev doğrulama
            elif data.startswith('verify_task_'):
                participation_id = data.replace('verify_task_', '')
                self.verify_task_participation(user_id, participation_id)
            
            # Para çekme
            elif data == 'start_withdraw':
                self.start_withdraw_process(user_id)
            
            # Referans butonları
            elif data == 'referral_copy':
                self.copy_referral_link(user_id)
            elif data == 'referral_share':
                self.share_referral_link(user_id)
            elif data == 'referral_details':
                self.show_referral_details(user_id)
            
            # Admin butonları
            elif data == 'admin_panel':
                self.show_admin_panel(user_id)
            elif data == 'admin_stats':
                self.show_admin_stats(user_id)
            elif data == 'admin_users':
                self.show_admin_users(user_id)
            elif data == 'admin_deposits':
                self.show_admin_deposits(user_id)
            elif data == 'admin_advertisers':
                self.show_admin_advertisers(user_id)
            elif data == 'admin_withdrawals':
                self.show_admin_withdrawals(user_id)
            
            # Kanal kontrolü
            elif data == 'joined':
                if get_chat_member(f"@{MANDATORY_CHANNEL}", user_id):
                    self.db.update_user(user_id, {'in_channel': 1})
                    self.show_main_menu(user_id)
                else:
                    send_message(user_id, "❌ Hala kanala katılmadınız!")
        
        except Exception as e:
            print(f"❌ Callback hatası: {e}")
            send_message(user_id, "❌ Bir hata oluştu!")
    
    def handle_start(self, user_id, text):
        # Kanal kontrolü
        if not get_chat_member(f"@{MANDATORY_CHANNEL}", user_id):
            markup = {
                'inline_keyboard': [[
                    {'text': '💬 Sohbete Katıl', 'url': f'https://t.me/{MANDATORY_CHANNEL}'},
                    {'text': '✅ Katıldım', 'callback_data': 'joined'}
                ]]
            }
            send_message(user_id, f"""
<b>🤖 GÖREV YAPSAM BOT</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 <b>Botu kullanmak için sohbet kanalına katılın:</b>
👉 @{MANDATORY_CHANNEL}

📢 <b>Referans Grubu:</b>
👉 @{REFERENCE_GROUP}

💡 <b>Katıldıktan sonra "Katıldım" butonuna basın</b>
""", markup)
            return
        
        user = self.db.get_user(user_id)
        
        # Hoşgeldin bonusu
        if not user.get('welcome_bonus'):
            # Önce referans kontrolü yap
            ref_code_used = None
            is_referred = 0
            ref_first_login = 0
            referrer_id = None
            
            if ' ' in text:
                parts = text.split()
                if len(parts) > 1 and parts[1].startswith('ref_'):
                    ref_code = parts[1]
                    referrer_id = parts[1].replace('ref_', '')
                    
                    if referrer_id and referrer_id != user_id:
                        referrer = self.db.get_user(referrer_id)
                        if referrer:
                            # Kullanıcı daha önce bu referansı kullanmış mı?
                            if not self.db.check_referral_usage(user_id, ref_code):
                                # İlk defa bu referansla geliyor
                                is_referred = 1
                                ref_first_login = 1
                                ref_code_used = ref_code
                                
                                # Referans kaydını logla
                                referral_link = f"https://t.me/GorevYapsamBot?start={ref_code}"
                                log_id = self.db.record_referral(referrer_id, user_id, referral_link, 1.0)
                                
                                # Referans sahibine bonus ekle
                                self.db.add_balance(referrer_id, 1.0, "normal", 0, "referral")
                                self.db.update_user(referrer_id, {
                                    'referrals': referrer.get('referrals', 0) + 1,
                                    'ref_earned': referrer.get('ref_earned', 0) + 1.0
                                })
                                
                                # Referansı tamamla
                                self.db.complete_referral(log_id, "welcome")
                                
                                # Referans bildirimi gönder
                                send_message(referrer_id, f"""
<b>🎉 REFERANS KAZANCI!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Yeni referansınız:</b> {user.get('name', 'Kullanıcı')}
💰 <b>Kazandınız:</b> 1.00₺
📊 <b>Toplam referans:</b> {referrer.get('referrals', 0) + 1}

💡 <b>Referans linkinizi paylaşmaya devam edin!</b>
""")
            
            # Hoşgeldin bonusunu ver
            self.db.add_balance(user_id, 2.0, "normal", 0, "welcome_bonus")
            self.db.update_user(user_id, {
                'welcome_bonus': 1, 
                'in_channel': 1,
                'is_referred': is_referred,
                'ref_first_login': ref_first_login,
                'ref_link_used': ref_code_used,
                'referred_by': referrer_id if is_referred else None
            })
            
            # Referans ile geldiyse ekstra mesaj gönder
            if is_referred:
                send_message(user_id, f"""
<b>🎉 HOŞ GELDİNİZ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ <b>2₺ hoşgeldin bonusu hesabınıza yüklendi!</b>
👥 <b>Referans ile kaydoldunuz!</b>
💰 <b>Referans sahibine 1₺ bonus yüklendi!</b>

💬 <b>Sohbet Kanalı:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans Grubu:</b> @{REFERENCE_GROUP}

💡 <b>Hemen görev yapmaya başlayabilirsiniz!</b>
""")
            else:
                send_message(user_id, f"""
<b>🎉 HOŞ GELDİNİZ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ <b>2₺ hoşgeldin bonusu hesabınıza yüklendi!</b>
💰 <b>Hemen görev yapmaya başlayabilirsiniz!</b>

💬 <b>Sohbet Kanalı:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans Grubu:</b> @{REFERENCE_GROUP}

👥 <b>Referans linkinizi paylaşarak daha fazla kazanın!</b>
""")
        
        # Eğer zaten kayıtlıysa ve referans linki ile gelmişse
        elif ' ' in text and user.get('is_referred') == 0:
            parts = text.split()
            if len(parts) > 1 and parts[1].startswith('ref_'):
                ref_code = parts[1]
                referrer_id = parts[1].replace('ref_', '')
                
                if referrer_id and referrer_id != user_id:
                    # Kullanıcı daha önce referansla gelmemişse
                    if not user.get('ref_link_used'):
                        referrer = self.db.get_user(referrer_id)
                        if referrer:
                            # Referans kaydını logla
                            referral_link = f"https://t.me/GorevYapsamBot?start={ref_code}"
                            log_id = self.db.record_referral(referrer_id, user_id, referral_link, 0.5)
                            
                            # Referans sahibine bonus ekle (daha az bonus)
                            self.db.add_balance(referrer_id, 0.5, "normal", 0, "referral_late")
                            self.db.update_user(referrer_id, {
                                'referrals': referrer.get('referrals', 0) + 1,
                                'ref_earned': referrer.get('ref_earned', 0) + 0.5
                            })
                            
                            # Referansı tamamla
                            self.db.complete_referral(log_id, "late_join")
                            
                            # Kullanıcıyı güncelle
                            self.db.update_user(user_id, {
                                'is_referred': 1,
                                'ref_link_used': ref_code,
                                'referred_by': referrer_id
                            })
                            
                            # Bildirim gönder
                            send_message(referrer_id, f"""
<b>🎉 GEÇ KATILIM REFERANS KAZANCI!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Yeni geç katılım referansınız:</b> {user.get('name', 'Kullanıcı')}
💰 <b>Kazandınız:</b> 0.50₺
📊 <b>Toplam referans:</b> {referrer.get('referrals', 0) + 1}

💡 <b>Referans linkinizi paylaşmaya devam edin!</b>
""")
        
        self.show_main_menu(user_id)
    
    def show_main_menu(self, user_id):
        user = self.db.get_user(user_id)
        
        # Kanal kontrolü yap
        if not get_chat_member(f"@{MANDATORY_CHANNEL}", user_id):
            self.db.update_user(user_id, {'in_channel': 0})
            markup = {
                'inline_keyboard': [[
                    {'text': '💬 Sohbete Katıl', 'url': f'https://t.me/{MANDATORY_CHANNEL}'},
                    {'text': '✅ Katıldım', 'callback_data': 'joined'}
                ]]
            }
            send_message(user_id, f"""
<b>⚠️ KANAL KONTROLÜ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ <b>Sohbet kanalından ayrıldınız!</b>

💬 <b>Botu kullanmak için:</b>
👉 @{MANDATORY_CHANNEL}

📢 <b>Referans Grubu:</b>
👉 @{REFERENCE_GROUP}

💡 <b>Katıldıktan sonra "Katıldım" butonuna basın</b>
""", markup)
            return
        
        # Reklamveren modunu kontrol et
        is_advertiser = user.get('is_advertiser', 0)
        advertiser_text = "\n<b>👑 Reklamveren Modu:</b> Aktif" if is_advertiser else ""
        
        # Normal ve reklam bakiyesi göster
        normal_balance = user.get('normal_balance', 0)
        ads_balance = user.get('ads_balance', 0)
        total_balance = user.get('balance', 0)
        
        message = f"""
<b>🤖 GÖREV YAPSAM BOT</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👤 Hoş geldin</b> {user.get('name', 'Kullanıcı')}!
<b>💰 Normal Bakiye:</b> <code>{normal_balance:.2f}₺</code>
<b>📢 Reklam Bakiye:</b> <code>{ads_balance:.2f}₺</code>
<b>💳 Toplam Bakiye:</b> <code>{total_balance:.2f}₺</code>{advertiser_text}

<b>🎯 Tamamlanan Görev:</b> {user.get('tasks_completed', 0)}
<b>👥 Referans:</b> {user.get('referrals', 0)}

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>📋 ANA MENÜ</b>
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '🎯 Görev Yap', 'callback_data': 'tasks'},
                    {'text': '💰 Bakiye Yükle', 'callback_data': 'deposit'}
                ],
                [
                    {'text': '🏧 Para Çek', 'callback_data': 'withdraw'},
                    {'text': '📊 İstatistik', 'callback_data': 'stats'}
                ],
                [
                    {'text': '🔄 Bakiye Dönüştür', 'callback_data': 'convert_balance'},
                    {'text': '👤 Profil', 'callback_data': 'profile'}
                ],
                [
                    {'text': '👥 Referans', 'callback_data': 'referral'},
                    {'text': '❓ Yardım', 'callback_data': 'help'}
                ]
            ]
        }
        
        # Reklamveren butonu
        if is_advertiser:
            markup['inline_keyboard'].insert(3, [
                {'text': '📢 Reklamveren', 'callback_data': 'advertiser_menu'}
            ])
        else:
            markup['inline_keyboard'].insert(3, [
                {'text': '👑 Reklamveren Ol', 'callback_data': 'toggle_advertiser'}
            ])
        
        # Admin butonu
        if user_id == ADMIN_ID:
            markup['inline_keyboard'].append([
                {'text': '👑 Admin Panel', 'callback_data': 'admin_panel'}
            ])
        
        send_message(user_id, message, markup)
    
    def show_convert_balance_menu(self, user_id):
        """Bakiye dönüşüm menüsü"""
        user = self.db.get_user(user_id)
        
        normal_balance = user.get('normal_balance', 0)
        ads_balance = user.get('ads_balance', 0)
        
        message = f"""
<b>🔄 BAKİYE DÖNÜŞTÜRME</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 Mevcut Bakiyeleriniz:</b>
• Normal Bakiye: {normal_balance:.2f}₺
• Reklam Bakiye: {ads_balance:.2f}₺

<b>💡 Bakiye Dönüşümü:</b>
• Normal bakiye ile görev yapabilir, para çekebilirsiniz
• Reklam bakiyesi ile reklam verebilirsiniz
• Bakiyelerinizi birbirine dönüştürebilirsiniz

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<b>👇 Dönüşüm Türünü Seçin:</b>
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': f'📢 → 💰 Reklamden Normale ({ads_balance:.2f}₺)', 'callback_data': 'convert_to_normal'},
                    {'text': f'💰 → 📢 Normalden Reklama ({normal_balance:.2f}₺)', 'callback_data': 'convert_to_ads'}
                ],
                [
                    {'text': '🔙 Ana Menü', 'callback_data': 'menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def start_convert_balance(self, user_id, conversion_type):
        """Bakiye dönüşümünü başlat"""
        user = self.db.get_user(user_id)
        
        if conversion_type == 'to_normal':
            # Reklam bakiyesinden normal bakiyeye
            max_amount = user.get('ads_balance', 0)
            if max_amount <= 0:
                send_message(user_id, "❌ Dönüştürecek reklam bakiyeniz yok!")
                self.show_convert_balance_menu(user_id)
                return
            
            self.set_user_state(user_id, 'convert_balance', {
                'conversion_type': 'to_normal',
                'max_amount': max_amount,
                'step': 1
            })
            
            send_message(user_id, f"""
<b>📢 → 💰 REKLAM BAKİYESİNİ NORMAL BAKİYEYE DÖNÜŞTÜR</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 Mevcut Reklam Bakiye:</b> {max_amount:.2f}₺

<b>📝 Dönüştürmek istediğiniz tutarı girin:</b>
• Sadece sayı girin (örn: 50)
• Maksimum: {max_amount:.2f}₺
• Minimum: 1₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<code>/cancel</code> iptal etmek için
""")
        
        else:  # to_ads
            # Normal bakiyeden reklam bakiyesine
            max_amount = user.get('normal_balance', 0)
            if max_amount <= 0:
                send_message(user_id, "❌ Dönüştürecek normal bakiyeniz yok!")
                self.show_convert_balance_menu(user_id)
                return
            
            self.set_user_state(user_id, 'convert_balance', {
                'conversion_type': 'to_ads',
                'max_amount': max_amount,
                'step': 1
            })
            
            send_message(user_id, f"""
<b>💰 → 📢 NORMAL BAKİYEYİ REKLAM BAKİYESİNE DÖNÜŞTÜR</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 Mevcut Normal Bakiye:</b> {max_amount:.2f}₺

<b>📝 Dönüştürmek istediğiniz tutarı girin:</b>
• Sadece sayı girin (örn: 50)
• Maksimum: {max_amount:.2f}₺
• Minimum: 1₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<code>/cancel</code> iptal etmek için
""")
    
    def show_user_stats(self, user_id):
        """Kullanıcı istatistiklerini göster"""
        user = self.db.get_user(user_id)
        
        # Toplam kazanç
        total_earned = user.get('total_earned', 0)
        
        # Bugünkü kazanç
        today_start = get_turkey_time().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        self.db.cursor.execute('''
            SELECT SUM(reward_paid) 
            FROM task_participations 
            WHERE user_id = ? AND paid_at > ? AND status = 'verified'
        ''', (user_id, today_start))
        today_earnings_result = self.db.cursor.fetchone()
        today_earnings = today_earnings_result[0] or 0
        
        # Haftalık kazanç
        week_start = (get_turkey_time() - timedelta(days=7)).isoformat()
        self.db.cursor.execute('''
            SELECT SUM(reward_paid) 
            FROM task_participations 
            WHERE user_id = ? AND paid_at > ? AND status = 'verified'
        ''', (user_id, week_start))
        weekly_earnings_result = self.db.cursor.fetchone()
        weekly_earnings = weekly_earnings_result[0] or 0
        
        # Aylık kazanç
        month_start = (get_turkey_time() - timedelta(days=30)).isoformat()
        self.db.cursor.execute('''
            SELECT SUM(reward_paid) 
            FROM task_participations 
            WHERE user_id = ? AND paid_at > ? AND status = 'verified'
        ''', (user_id, month_start))
        monthly_earnings_result = self.db.cursor.fetchone()
        monthly_earnings = monthly_earnings_result[0] or 0
        
        # Toplam görev
        total_tasks = user.get('tasks_completed', 0)
        
        # Bugünkü görev
        self.db.cursor.execute('''
            SELECT COUNT(*) 
            FROM task_participations 
            WHERE user_id = ? AND paid_at > ? AND status = 'verified'
        ''', (user_id, today_start))
        today_tasks_result = self.db.cursor.fetchone()
        today_tasks = today_tasks_result[0] or 0
        
        # Referans istatistikleri
        self.db.cursor.execute('''
            SELECT COUNT(*) as total_refs, SUM(amount) as total_ref_earned
            FROM referral_logs 
            WHERE referrer_id = ? AND status = 'completed'
        ''', (user_id,))
        ref_stats = self.db.cursor.fetchone()
        total_refs = ref_stats['total_refs'] if ref_stats else 0
        total_ref_earned = ref_stats['total_ref_earned'] if ref_stats and ref_stats['total_ref_earned'] else 0
        
        message = f"""
<b>📊 KULLANICI İSTATİSTİKLERİNİZ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👤 Kullanıcı:</b> {user.get('name', 'Kullanıcı')}
<b>🆔 ID:</b> <code>{user_id}</code>

<b>💰 BAKİYE DURUMU</b>
├ <b>Normal Bakiye:</b> {user.get('normal_balance', 0):.2f}₺
├ <b>Reklam Bakiye:</b> {user.get('ads_balance', 0):.2f}₺
└ <b>Toplam Bakiye:</b> {user.get('balance', 0):.2f}₺

<b>📈 KAZANÇ İSTATİSTİKLERİ</b>
├ <b>Bugünkü Kazanç:</b> {today_earnings:.2f}₺
├ <b>Haftalık Kazanç:</b> {weekly_earnings:.2f}₺
├ <b>Aylık Kazanç:</b> {monthly_earnings:.2f}₺
└ <b>Toplam Kazanç:</b> {total_earned:.2f}₺

<b>🎯 GÖREV İSTATİSTİKLERİ</b>
├ <b>Bugünkü Görev:</b> {today_tasks}
└ <b>Toplam Görev:</b> {total_tasks}

<b>👥 REFERANS İSTATİSTİKLERİ</b>
├ <b>Toplam Referans:</b> {total_refs}
└ <b>Referans Kazancı:</b> {total_ref_earned:.2f}₺

<b>💡 REKLAMVEREN İSTATİSTİKLERİ</b>
"""
        
        if user.get('is_advertiser', 0):
            message += f"""
├ <b>Reklamveren Durumu:</b> Aktif
├ <b>Toplam Harcama:</b> {user.get('total_spent_on_ads', 0):.2f}₺
└ <b>Toplam Yatırım:</b> {user.get('total_deposited', 0):.2f}₺
"""
        else:
            message += "└ <i>Reklamveren modu kapalı</i>"
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>📢 GERÇEK ZAMANLI BİLDİRİMLER</b>
<b>💬 Sohbet:</b> @{MANDATORY_CHANNEL}
<b>📢 Referans:</b> @{REFERENCE_GROUP}
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '🎯 Görev Yap', 'callback_data': 'tasks'},
                    {'text': '💰 Bakiye Yükle', 'callback_data': 'deposit'}
                ],
                [
                    {'text': '🔄 Bakiye Dönüştür', 'callback_data': 'convert_balance'},
                    {'text': '🔙 Ana Menü', 'callback_data': 'menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def toggle_advertiser_mode(self, user_id):
        """Reklamveren modunu aç/kapat"""
        user = self.db.get_user(user_id)
        current_status = user.get('is_advertiser', 0)
        new_status = 0 if current_status else 1
        
        self.db.update_user(user_id, {'is_advertiser': new_status})
        
        if new_status:
            message = f"""
<b>👑 REKLAMVEREN MODU AKTİF</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ <b>Reklamveren moduna geçtiniz!</b>

📊 <b>Artık şunları yapabilirsiniz:</b>
• 📢 Görev oluşturabilirsiniz
• 💰 Reklam bakiyesi yükleyebilirsiniz
• 📈 Reklamlarınızı takip edebilirsiniz

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>"Reklamveren" butonuna tıklayarak işlemlerinize başlayın!</b>
"""
            markup = {
                'inline_keyboard': [[
                    {'text': '📢 Reklamveren Menüsü', 'callback_data': 'advertiser_menu'},
                    {'text': '🔙 Ana Menü', 'callback_data': 'menu'}
                ]]
            }
        else:
            message = f"""
<b>👑 REKLAMVEREN MODU KAPALI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

ℹ️ <b>Reklamveren modunu kapattınız!</b>

📊 <b>Artık normal kullanıcı modundasınız:</b>
• 🎯 Görev yapabilirsiniz
• 💰 Normal bakiye yükleyebilirsiniz
• 💸 Kazançlarınızı çekebilirsiniz

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>Tekrar reklamveren olmak için "Reklamveren Ol" butonuna tıklayın!</b>
"""
            markup = {
                'inline_keyboard': [[
                    {'text': '👑 Reklamveren Ol', 'callback_data': 'toggle_advertiser'},
                    {'text': '🔙 Ana Menü', 'callback_data': 'menu'}
                ]]
            }
        
        send_message(user_id, message, markup)
    
    def show_advertiser_menu(self, user_id):
        user = self.db.get_user(user_id)
        
        if not user.get('is_advertiser', 0):
            send_message(user_id, "❌ Reklamveren modunda değilsiniz!")
            self.show_main_menu(user_id)
            return
        
        message = f"""
<b>👑 REKLAMVEREN MENÜSÜ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 Reklam Bakiye:</b> {user.get('ads_balance', 0):.2f}₺
<b>📈 Toplam Harcama:</b> {user.get('total_spent_on_ads', 0):.2f}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>📋 İŞLEMLER</b>
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '📢 Görev Oluştur', 'callback_data': 'advertiser_create_task'},
                    {'text': '💰 Bakiye Yükle', 'callback_data': 'advertiser_deposit'}
                ],
                [
                    {'text': '📊 Görevlerim', 'callback_data': 'advertiser_my_tasks'},
                    {'text': '💰 Bakiyem', 'callback_data': 'advertiser_balance'}
                ],
                [
                    {'text': '🔙 Ana Menü', 'callback_data': 'menu'},
                    {'text': '🚫 Reklamverenliği Kapat', 'callback_data': 'toggle_advertiser'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def show_advertiser_balance(self, user_id):
        user = self.db.get_user(user_id)
        
        message = f"""
<b>💰 REKLAMVEREN BAKİYE DETAYLARI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 Bakiye Bilgileri:</b>
• Reklam Bakiye: {user.get('ads_balance', 0):.2f}₺
• Normal Bakiye: {user.get('normal_balance', 0):.2f}₺
• Toplam Bakiye: {user.get('balance', 0):.2f}₺
• Toplam Yatırım: {user.get('total_deposited', 0):.2f}₺
• Toplam Harcama: {user.get('total_spent_on_ads', 0):.2f}₺

<b>💡 Not:</b>
• Reklam bakiyesi sadece reklam vermek için kullanılır
• Normal bakiye kazanılan paradır ve çekilebilir
• Reklam bakiyesi çekilemez, sadece reklamlarda kullanılır

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '💰 Bakiye Yükle', 'callback_data': 'advertiser_deposit'},
                    {'text': '📢 Görev Oluştur', 'callback_data': 'advertiser_create_task'}
                ],
                [
                    {'text': '🔙 Geri', 'callback_data': 'advertiser_menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def start_advertiser_task_creation(self, user_id):
        user = self.db.get_user(user_id)
        
        if user.get('ads_balance', 0) < GROUP_TASK_PRICE:
            message = f"""
<b>❌ YETERSİZ REKLAM BAKİYESİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ <b>Reklam bakiyeniz yetersiz!</b>

<b>📊 Mevcut Durum:</b>
• Reklam Bakiye: {user.get('ads_balance', 0):.2f}₺
• Minimum Gerekli: {GROUP_TASK_PRICE:.2f}₺

<b>💡 Çözüm:</b>
1. "💰 Bakiye Yükle" butonuna tıklayın
2. Reklam bakiyesi yükleyin
3. Tekrar görev oluşturmayı deneyin
"""
            
            markup = {
                'inline_keyboard': [
                    [
                        {'text': '💰 Bakiye Yükle', 'callback_data': 'advertiser_deposit'},
                        {'text': '🔙 Geri', 'callback_data': 'advertiser_menu'}
                    ]
                ]
            }
            
            send_message(user_id, message, markup)
            return
        
        message = """
<b>📢 REKLAMVEREN GÖREV OLUŞTURMA</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👇 Görev Türünü Seçin:</b>

<b>👥 GRUP GÖREVİ</b>
• Ödül: 0.5₺ her katılım
• Gereksinim: Bot grupta admin olmalı
• Katılımcılar gruba katılır

<b>📢 KANAL GÖREVİ</b>
• Ödül: 1.25₺ her katılım
• Gereksinim: Bot kanalda admin olmalı
• Katılımcılar kanala katılır
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '👥 Grup Görevi', 'callback_data': 'task_type_group'},
                    {'text': '📢 Kanal Görevi', 'callback_data': 'task_type_channel'}
                ],
                [
                    {'text': '🔙 Geri', 'callback_data': 'advertiser_menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def handle_task_type_selection(self, user_id, task_type):
        user = self.db.get_user(user_id)
        
        if task_type == 'group':
            reward = GROUP_TASK_PRICE
            task_type_text = "Grup"
        else:  # channel
            reward = CHANNEL_TASK_PRICE
            task_type_text = "Kanal"
        
        # Kullanıcının bakiyesini kontrol et
        if user.get('ads_balance', 0) < reward:
            send_message(user_id, f"❌ Yetersiz bakiye! Minimum {reward:.2f}₺ gereklidir.")
            self.show_advertiser_menu(user_id)
            return
        
        self.set_user_state(user_id, 'create_task', {
            'task_type': task_type,
            'reward': reward,
            'step': 1
        })
        
        send_message(user_id, f"""
<b>📢 {task_type_text.upper()} GÖREVİ OLUŞTURMA</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>ℹ️ Bilgiler:</b>
• Görev Türü: {task_type_text}
• Ödül: {reward:.2f}₺ her katılım
• Botun admin olduğu bir {task_type_text.lower()} gerekli

<b>📝 {task_type_text} ID veya linkini gönderin:</b>
• Örnek: @grup_adi veya https://t.me/grup_adi
• Botun {task_type_text.lower()}da admin olduğundan emin olun

<code>/cancel</code> iptal etmek için
""")
    
    def show_advertiser_deposit_menu(self, user_id):
        self.update_trx_price()
        
        message = f"""
<b>💰 REKLAMVEREN BAKİYE YÜKLEME</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>₿ TRX Fiyatı:</b> {self.trx_price:.2f}₺
<b>⚠️ Not:</b> Reklamveren bakiyesi sadece reklam vermek için kullanılır

<b>👇 Yüklemek istediğiniz tutarı seçin:</b>
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': f'50₺ Reklamveren', 'callback_data': 'deposit_amount_50_advertiser'},
                    {'text': f'100₺ Reklamveren', 'callback_data': 'deposit_amount_100_advertiser'}
                ],
                [
                    {'text': f'200₺ Reklamveren', 'callback_data': 'deposit_amount_200_advertiser'},
                    {'text': f'500₺ Reklamveren', 'callback_data': 'deposit_amount_500_advertiser'}
                ],
                [
                    {'text': '🔙 Geri', 'callback_data': 'advertiser_menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def show_available_tasks(self, user_id):
        """Kullanıcılar için mevcut görevleri göster"""
        # Zorunlu kanal kontrolü
        if not get_chat_member(f"@{MANDATORY_CHANNEL}", user_id):
            self.db.update_user(user_id, {'in_channel': 0})
            markup = {
                'inline_keyboard': [[
                    {'text': '💬 Sohbete Katıl', 'url': f'https://t.me/{MANDATORY_CHANNEL}'},
                    {'text': '✅ Katıldım', 'callback_data': 'joined'}
                ]]
            }
            send_message(user_id, f"""
<b>⚠️ KANAL KONTROLÜ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ <b>Önce sohbet kanalına katılmalısınız!</b>

💬 <b>Görev yapmak için:</b>
👉 @{MANDATORY_CHANNEL}

📢 <b>Referans Grubu:</b>
👉 @{REFERENCE_GROUP}

💡 <b>Katıldıktan sonra "Katıldım" butonuna basın</b>
""", markup)
            return
        
        # Aktif görevleri getir
        self.db.cursor.execute('''
            SELECT * FROM tasks 
            WHERE status = 'active' 
            ORDER BY created_at DESC 
            LIMIT 10
        ''')
        tasks = self.db.cursor.fetchall()
        
        if not tasks:
            message = f"""
<b>🎯 MEVCUT GÖREVLER</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📭 <b>Şu anda aktif görev bulunmuyor</b>

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>Yeni görevler eklendiğinde bildirim alacaksınız!</b>
"""
            markup = {
                'inline_keyboard': [[
                    {'text': '🔙 Ana Menü', 'callback_data': 'menu'}
                ]]
            }
        else:
            message = f"""
<b>🎯 MEVCUT GÖREVLER</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            for task in tasks:
                task_type = "👥 Grup" if task['task_type'] == 'group' else "📢 Kanal"
                reward = task['reward_amount']
                
                # Kullanıcı bu göreve katılmış mı kontrol et
                self.db.cursor.execute('''
                    SELECT * FROM task_participations 
                    WHERE task_id = ? AND user_id = ?
                ''', (task['task_id'], user_id))
                participation = self.db.cursor.fetchone()
                
                status = "✅ Katıldınız" if participation else "🟢 Katıl"
                
                message += f"""{task_type} <b>{task['target_name'][:20]}</b>
├ <b>Ödül:</b> {reward:.2f}₺
├ <b>Katılımcı:</b> {task['current_participants']}/{task['max_participants']}
└ <b>Durum:</b> {status}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            # İlk görev için katılma butonu
            if tasks:
                first_task = tasks[0]
                self.db.cursor.execute('''
                    SELECT * FROM task_participations 
                    WHERE task_id = ? AND user_id = ?
                ''', (first_task['task_id'], user_id))
                participation = self.db.cursor.fetchone()
                
                if not participation:
                    markup = {
                        'inline_keyboard': [
                            [
                                {'text': f'🎯 Katıl ({first_task["reward_amount"]:.2f}₺)', 
                                 'callback_data': f'join_task_{first_task["task_id"]}'}
                            ],
                            [
                                {'text': '🔙 Ana Menü', 'callback_data': 'menu'}
                            ]
                        ]
                    }
                else:
                    markup = {
                        'inline_keyboard': [[
                            {'text': '🔙 Ana Menü', 'callback_data': 'menu'}
                        ]]
                    }
        
        send_message(user_id, message, markup)
    
    def join_task(self, user_id, task_id):
        """Kullanıcı göreve katıl"""
        # Görev bilgilerini getir
        self.db.cursor.execute('''
            SELECT * FROM tasks WHERE task_id = ?
        ''', (task_id,))
        task = self.db.cursor.fetchone()
        
        if not task:
            send_message(user_id, "❌ Görev bulunamadı!")
            return
        
        # Zaten katılmış mı kontrol et
        self.db.cursor.execute('''
            SELECT * FROM task_participations 
            WHERE task_id = ? AND user_id = ?
        ''', (task_id, user_id))
        existing = self.db.cursor.fetchone()
        
        if existing:
            send_message(user_id, "❌ Zaten bu göreve katıldınız!")
            return
        
        # Kullanıcı grupta/kanalda mı kontrol et
        user = self.db.get_user(user_id)
        
        if task['task_type'] == 'group':
            if not get_chat_member(task['target_id'], user_id):
                # Gruba katılma linki göster
                markup = {
                    'inline_keyboard': [
                        [
                            {'text': '👥 Gruba Katıl', 'url': f'https://t.me/{task["target_id"].replace("@", "")}'},
                            {'text': '✅ Katıldım', 'callback_data': f'join_task_{task_id}'}
                        ]
                    ]
                }
                
                send_message(user_id, f"""
<b>👥 GRUPA KATILMA GÖREVİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Görev:</b> {task['target_name']}
💰 <b>Ödül:</b> {task['reward_amount']:.2f}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<b>📝 Adımlar:</b>
1. Yukarıdaki butona tıklayarak gruba katılın
2. Katıldıktan sonra "Katıldım" butonuna basın
3. Sistem otomatik olarak katılımınızı doğrulayacak
4. Ödülünüz bakiyenize eklenecek

⚠️ <b>Önemli:</b> Grubu terk ederseniz ödülünüz geri alınır!
""", markup)
                return
        else:  # channel
            if not get_chat_member(task['target_id'], user_id):
                # Kanala katılma linki göster
                markup = {
                    'inline_keyboard': [
                        [
                            {'text': '📢 Kanala Katıl', 'url': f'https://t.me/{task["target_id"].replace("@", "")}'},
                            {'text': '✅ Katıldım', 'callback_data': f'join_task_{task_id}'}
                        ]
                    ]
                }
                
                send_message(user_id, f"""
<b>📢 KANALA KATILMA GÖREVİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Görev:</b> {task['target_name']}
💰 <b>Ödül:</b> {task['reward_amount']:.2f}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<b>📝 Adımlar:</b>
1. Yukarıdaki butona tıklayarak kanala katılın
2. Katıldıktan sonra "Katıldım" butonuna basın
3. Sistem otomatik olarak katılımınızı doğrulayacak
4. Ödülünüz bakiyenize eklenecek

⚠️ <b>Önemli:</b> Kanalı terk ederseniz ödülünüz geri alınır!
""", markup)
                return
        
        # Kullanıcı zaten grupta/kanalda, doğrudan katılım kaydı oluştur
        success, message = self.db.join_task(task_id, user_id, user.get('name', 'Kullanıcı'))
        
        if success:
            # Reklamverene bildirim gönder
            send_message(task['advertiser_id'], f"""
<b>👤 YENİ GÖREV KATILIMI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>Yeni katılımcı!</b>

📊 <b>Detaylar:</b>
• Görev: {task['target_name']}
• Katılımcı: {user.get('name', 'Kullanıcı')}
• Ödül: {task['reward_amount']:.2f}₺
• Toplam Katılımcı: {task['current_participants'] + 1}

💡 <b>Katılımı doğrulamak için görevlerim sayfasına bakın!</b>
""")
            
            # Kullanıcıya bildirim
            send_message(user_id, f"""
<b>✅ GÖREVE KATILDINIZ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>Göreve başarıyla katıldınız!</b>

📊 <b>Detaylar:</b>
• Görev: {task['target_name']}
• Ödül: {task['reward_amount']:.2f}₺
• Durum: Doğrulama bekliyor

💡 <b>Reklamveren katılımınızı doğruladığında ödülünüz bakiyenize eklenecek!</b>

⚠️ <b>Önemli:</b> Grubu/Kanalı terk etmeyin, yoksa ödülünüz geri alınır!
""")
        else:
            send_message(user_id, f"❌ {message}")
    
    def verify_task_participation(self, user_id, participation_id):
        """Reklamveren katılımı doğrula"""
        # Katılım bilgilerini getir
        self.db.cursor.execute('''
            SELECT tp.*, t.advertiser_id, t.target_name, t.reward_amount, t.task_type, t.task_id
            FROM task_participations tp
            JOIN tasks t ON tp.task_id = t.task_id
            WHERE tp.participation_id = ?
        ''', (participation_id,))
        participation = self.db.cursor.fetchone()
        
        if not participation:
            send_message(user_id, "❌ Katılım bulunamadı!")
            return
        
        # Sadece reklamveren doğrulayabilir
        if str(participation['advertiser_id']) != user_id:
            send_message(user_id, "❌ Bu işlemi sadece görevin reklamvereni yapabilir!")
            return
        
        # Doğrudan doğrula
        success, result_message = self.db.verify_task_participation(participation_id)
        
        if success:
            # Referans grubuna bildirim gönder
            self.reference_notifier.notify_task_completed(
                participation['task_id'],
                participation['user_id'],
                participation['reward_amount']
            )
            
            # Reklamverene bildirim
            send_message(user_id, f"""
<b>✅ GÖREV DOĞRULANDI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>Görev başarıyla doğrulandı!</b>

📊 <b>Detaylar:</b>
• Katılımcı: {participation['user_name']}
• Ödül: {participation['reward_amount']:.2f}₺ ödendi
• Yeni Reklam Bakiye: {self.db.get_user(user_id)['ads_balance']:.2f}₺

💡 <b>Katılımcı ödülünü aldı!</b>
""")
        else:
            send_message(user_id, f"❌ {result_message}")
    
    def show_advertiser_my_tasks(self, user_id):
        """Reklamverenin görevlerini göster"""
        self.db.cursor.execute('''
            SELECT * FROM tasks 
            WHERE advertiser_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
        ''', (user_id,))
        tasks = self.db.cursor.fetchall()
        
        if not tasks:
            message = f"""
<b>📊 REKLAMVEREN GÖREVLERİM</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📭 <b>Henüz göreviniz bulunmuyor</b>

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>İlk görevinizi oluşturun!</b>
"""
            markup = {
                'inline_keyboard': [
                    [
                        {'text': '📢 Görev Oluştur', 'callback_data': 'advertiser_create_task'},
                        {'text': '🔙 Geri', 'callback_data': 'advertiser_menu'}
                    ]
                ]
            }
        else:
            message = f"""
<b>📊 SON 10 GÖREVİM</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            for task in tasks:
                task_type = "👥 Grup" if task['task_type'] == 'group' else "📢 Kanal"
                status = "🟢" if task['status'] == 'active' else "🟡" if task['status'] == 'pending' else "🔴"
                
                message += f"""{status} <b>{task['target_name'][:20]}</b>
├ <b>Tür:</b> {task_type}
├ <b>Ödül:</b> {task['reward_amount']:.2f}₺
├ <b>Katılım:</b> {task['current_participants']}/{task['max_participants']}
└ <b>Harcama:</b> {task['total_spent']:.2f}₺
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            # İlk görevin katılımlarını göster
            if tasks:
                first_task = tasks[0]
                self.db.cursor.execute('''
                    SELECT * FROM task_participations 
                    WHERE task_id = ? 
                    ORDER BY joined_at DESC 
                    LIMIT 5
                ''', (first_task['task_id'],))
                participations = self.db.cursor.fetchall()
                
                if participations:
                    message += f"\n<b>📋 {first_task['target_name'][:15]} Katılımları:</b>\n"
                    for part in participations:
                        status_icon = "✅" if part['status'] == 'verified' else "⏳" if part['status'] == 'pending' else "❌"
                        message += f"{status_icon} {part['user_name'][:15]} - {part['status']}\n"
                
                # Doğrulama butonları
                pending_participations = [p for p in participations if p['status'] == 'pending']
                if pending_participations:
                    buttons = []
                    for part in pending_participations[:3]:  # En fazla 3 buton
                        buttons.append([
                            {'text': f'✅ {part["user_name"][:10]}', 
                             'callback_data': f'verify_task_{part["participation_id"]}'}
                        ])
                    
                    buttons.append([
                        {'text': '🔙 Geri', 'callback_data': 'advertiser_menu'}
                    ])
                    
                    markup = {'inline_keyboard': buttons}
                else:
                    markup = {
                        'inline_keyboard': [[
                            {'text': '🔙 Geri', 'callback_data': 'advertiser_menu'}
                        ]]
                    }
        
        send_message(user_id, message, markup)
    
    def start_advertiser_withdraw(self, user_id):
        """Reklamveren para çekme işlemi"""
        user = self.db.get_user(user_id)
        ads_balance = user.get('ads_balance', 0)
        
        if ads_balance < MIN_WITHDRAW:
            message = f"""
<b>❌ YETERSİZ REKLAM BAKİYESİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ <b>Reklam bakiyeniz yetersiz!</b>

<b>📊 Mevcut Durum:</b>
• Reklam Bakiye: {ads_balance:.2f}₺
• Minimum Çekim: {MIN_WITHDRAW}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>Not:</b> Reklam bakiyesi genellikle çekilemez, 
sadece reklam vermek için kullanılır. 
Özel durumlar için admin ile iletişime geçin.
"""
            
            markup = {
                'inline_keyboard': [[
                    {'text': '🔙 Geri', 'callback_data': 'advertiser_menu'}
                ]]
            }
            
            send_message(user_id, message, markup)
            return
        
        message = f"""
<b>💸 REKLAMVEREN PARA ÇEKME</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 Mevcut Reklam Bakiye:</b> {ads_balance:.2f}₺

<b>⚠️ ÖNEMLİ UYARI:</b>
• Reklam bakiyesi genellikle çekilemez
• Sadece reklam vermek için kullanılır
• Özel durumlar için admin onayı gereklidir

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<b>📞 İletişim:</b>
Para çekme talebi için admin ile iletişime geçin:
👉 @GorevYapsamBot
"""
        
        markup = {
            'inline_keyboard': [[
                {'text': '🔙 Geri', 'callback_data': 'advertiser_menu'}
            ]]
        }
        
        send_message(user_id, message, markup)
    
    def handle_user_state(self, user_id, message, user_state):
        state = user_state['state']
        data = user_state['data']
        step = user_state.get('step', 1)
        
        # /cancel komutu
        if 'text' in message and message['text'] == '/cancel':
            self.clear_user_state(user_id)
            send_message(user_id, "🔄 İşlem iptal edildi.")
            user = self.db.get_user(user_id)
            if user.get('is_advertiser', 0):
                self.show_advertiser_menu(user_id)
            else:
                self.show_main_menu(user_id)
            return
        
        # GÖREV OLUŞTURMA
        if state == 'create_task':
            if step == 1:
                # Grup/Kanal linkini al
                target_input = message['text'].strip()
                
                # Link veya @username formatını işle
                if target_input.startswith('https://t.me/'):
                    target_id = '@' + target_input.split('/')[-1]
                elif target_input.startswith('@'):
                    target_id = target_input
                else:
                    target_id = '@' + target_input
                
                # Bot admin mi kontrol et
                if not check_bot_admin(target_id):
                    send_message(user_id, f"❌ Bot {target_id} grubunda/kanalında admin değil!")
                    self.clear_user_state(user_id)
                    self.show_advertiser_menu(user_id)
                    return
                
                # Grup/Kanal bilgilerini al
                chat_info = get_chat(target_id)
                if not chat_info:
                    send_message(user_id, f"❌ {target_id} bulunamadı veya erişilemiyor!")
                    self.clear_user_state(user_id)
                    self.show_advertiser_menu(user_id)
                    return
                
                target_name = chat_info.get('title', target_id)
                chat_type = chat_info.get('type', '')
                
                # Görev türüyle eşleşiyor mu kontrol et
                task_type = data['task_type']
                if (task_type == 'group' and chat_type not in ['group', 'supergroup']) or \
                   (task_type == 'channel' and chat_type != 'channel'):
                    send_message(user_id, f"❌ Bu bir {task_type} değil!")
                    self.clear_user_state(user_id)
                    self.show_advertiser_menu(user_id)
                    return
                
                # Veriyi güncelle
                data['target_id'] = target_id
                data['target_name'] = target_name
                data['step'] = 2
                self.set_user_state(user_id, state, data)
                
                send_message(user_id, f"""
<b>📝 GÖREV AÇIKLAMASI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>✅ {target_name} seçildi!</b>

<b>📋 Görev Bilgileri:</b>
• Tür: {'Grup' if task_type == 'group' else 'Kanal'}
• Ödül: {data['reward']:.2f}₺ her katılım
• Hedef: {target_name}

<b>📝 Görev açıklaması girin:</b>
• Katılımcıların ne yapması gerektiğini açıklayın
• Örnek: "Grubumuza katılın ve 24 saat kalın"
• Maksimum 200 karakter

<code>/cancel</code> iptal etmek için
""")
            
            elif step == 2:
                # Görev açıklamasını al
                description = message['text'].strip()
                
                if len(description) > 200:
                    send_message(user_id, "❌ Açıklama 200 karakterden uzun olamaz!")
                    return
                
                data['description'] = description
                data['step'] = 3
                self.set_user_state(user_id, state, data)
                
                send_message(user_id, f"""
<b>👥 KATILIMCI SAYISI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>✅ Açıklama kaydedildi!</b>

<b>📋 Görev Özeti:</b>
• Tür: {'Grup' if data['task_type'] == 'group' else 'Kanal'}
• Hedef: {data['target_name']}
• Ödül: {data['reward']:.2f}₺ her katılım
• Açıklama: {description[:50]}...

<b>📊 Kaç katılımcı kabul edeceksiniz?</b>
• Sadece sayı girin (örn: 10)
• Her katılımcı için {data['reward']:.2f}₺ ödeyeceksiniz
• Toplam maliyet: (katılımcı sayısı × {data['reward']:.2f}₺)

<code>/cancel</code> iptal etmek için
""")
            
            elif step == 3:
                # Katılımcı sayısını al
                try:
                    max_participants = int(message['text'].strip())
                    
                    if max_participants < 1:
                        send_message(user_id, "❌ En az 1 katılımcı gerekli!")
                        return
                    
                    if max_participants > 100:
                        send_message(user_id, "❌ Maksimum 100 katılımcı!")
                        return
                    
                    # Toplam maliyeti hesapla
                    total_cost = max_participants * data['reward']
                    user = self.db.get_user(user_id)
                    
                    if user.get('ads_balance', 0) < total_cost:
                        send_message(user_id, f"❌ Yetersiz bakiye! Toplam maliyet: {total_cost:.2f}₺, Mevcut: {user.get('ads_balance', 0):.2f}₺")
                        self.clear_user_state(user_id)
                        self.show_advertiser_menu(user_id)
                        return
                    
                    # Görevi oluştur
                    task_id = self.db.create_task(
                        user_id,
                        data['task_type'],
                        data['target_id'],
                        data['target_name'],
                        data['description'],
                        data['reward'],
                        max_participants
                    )
                    
                    # Bakiyeyi bloke et (henüz ödeme yapılmadı, sadece rezerve edildi)
                    self.db.cursor.execute('''
                        UPDATE users 
                        SET ads_balance = ads_balance - ?
                        WHERE user_id = ?
                    ''', (total_cost, user_id))
                    self.db.conn.commit()
                    
                    # Referans grubuna bildirim gönder
                    self.reference_notifier.notify_new_task(task_id, user_id)
                    
                    # Başarı mesajı
                    send_message(user_id, f"""
<b>✅ GÖREV OLUŞTURULDU!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>Göreviniz başarıyla oluşturuldu!</b>

📊 <b>Görev Detayları:</b>
• Görev ID: {task_id}
• Tür: {'Grup' if data['task_type'] == 'group' else 'Kanal'}
• Hedef: {data['target_name']}
• Ödül: {data['reward']:.2f}₺ her katılım
• Maksimum Katılımcı: {max_participants}
• Toplam Maliyet: {total_cost:.2f}₺ (bloke edildi)

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>Katılımcılar görevinize katıldıkça:</b>
1. Katılımları doğrulayın
2. Ödemeler otomatik olarak yapılır
3. Bloke edilen bakiye harcanır

📈 <b>Görevlerinizi takip etmek için "Görevlerim" butonuna tıklayın!</b>
""")
                    
                    self.clear_user_state(user_id)
                    self.show_advertiser_menu(user_id)
                    
                except ValueError:
                    send_message(user_id, "❌ Geçersiz sayı! Lütfen sadece sayı girin.")
        
        # BAKİYE DÖNÜŞTÜRME
        elif state == 'convert_balance':
            if step == 1:
                try:
                    amount = float(message['text'].strip())
                    max_amount = data['max_amount']
                    conversion_type = data['conversion_type']
                    
                    if amount < 1:
                        send_message(user_id, "❌ Minimum 1₺ dönüştürebilirsiniz!")
                        return
                    
                    if amount > max_amount:
                        send_message(user_id, f"❌ Maksimum {max_amount:.2f}₺ dönüştürebilirsiniz!")
                        return
                    
                    if conversion_type == 'to_normal':
                        # Reklam bakiyesinden normal bakiyeye
                        success, message_text = self.db.convert_balance(user_id, amount, "advertiser", "normal")
                        
                        if success:
                            send_message(user_id, f"""
<b>✅ BAKİYE DÖNÜŞTÜRÜLDÜ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>{amount:.2f}₺ reklam bakiyesi normal bakiyeye dönüştürüldü!</b>

📊 <b>Yeni Bakiyeler:</b>
• Normal Bakiye: {self.db.get_user(user_id)['normal_balance']:.2f}₺
• Reklam Bakiye: {self.db.get_user(user_id)['ads_balance']:.2f}₺
• Toplam Bakiye: {self.db.get_user(user_id)['balance']:.2f}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>Normal bakiyenizi görev yapmak veya para çekmek için kullanabilirsiniz!</b>
""")
                        else:
                            send_message(user_id, f"❌ {message_text}")
                    
                    else:  # to_ads
                        # Normal bakiyeden reklam bakiyesine
                        success, message_text = self.db.convert_balance(user_id, amount, "normal", "advertiser")
                        
                        if success:
                            send_message(user_id, f"""
<b>✅ BAKİYE DÖNÜŞTÜRÜLDÜ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>{amount:.2f}₺ normal bakiye reklam bakiyesine dönüştürüldü!</b>

📊 <b>Yeni Bakiyeler:</b>
• Normal Bakiye: {self.db.get_user(user_id)['normal_balance']:.2f}₺
• Reklam Bakiye: {self.db.get_user(user_id)['ads_balance']:.2f}₺
• Toplam Bakiye: {self.db.get_user(user_id)['balance']:.2f}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>Reklam bakiyenizi görev oluşturmak için kullanabilirsiniz!</b>
""")
                        else:
                            send_message(user_id, f"❌ {message_text}")
                    
                    self.clear_user_state(user_id)
                    time.sleep(2)
                    self.show_convert_balance_menu(user_id)
                    
                except ValueError:
                    send_message(user_id, "❌ Geçersiz tutar! Lütfen sadece sayı girin.")
        
        # TXID BEKLEME (Hem kullanıcı hem reklamveren)
        elif state == 'waiting_txid':
            txid = message['text'].strip()
            
            if len(txid) < 10:
                send_message(user_id, "❌ Geçersiz TXID!")
                return
            
            try:
                deposit_data = data
                deposit_id = deposit_data['deposit_id']
                amount = deposit_data['amount']
                deposit_type = deposit_data.get('deposit_type', 'user')
                
                # Depoziti tamamla
                self.db.cursor.execute('''
                    UPDATE deposits 
                    SET txid = ?, status = 'completed', completed_at = ?
                    WHERE deposit_id = ? AND user_id = ?
                ''', (txid, get_turkey_time().isoformat(), deposit_id, user_id))
                
                if deposit_type == 'advertiser':
                    # Reklamveren bakiyesine ekle
                    self.db.add_balance(user_id, amount, "advertiser", 0, "deposit")
                    
                    # Referans grubuna bildirim gönder
                    self.reference_notifier.notify_deposit(user_id, amount, 'advertiser')
                    
                    # Başarı mesajı
                    send_message(user_id, f"""
<b>✅ REKLAMVEREN BAKİYESİ YÜKLENDİ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 <b>Toplam: {amount:.2f}₺</b>
• Yatırım: {amount:.2f}₺
• Yeni Reklam Bakiye: {self.db.get_user(user_id)['ads_balance']:.2f}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

🎉 <b>Hemen reklam vermeye başlayın!</b>
""")
                else:
                    # Normal kullanıcı bakiyesine ekle
                    bonus = amount * DEPOSIT_BONUS_PERCENT / 100
                    total = amount + bonus
                    
                    user = self.db.get_user(user_id)
                    new_balance = user.get('balance', 0) + total
                    new_normal_balance = user.get('normal_balance', 0) + total
                    
                    self.db.cursor.execute('''
                        UPDATE users 
                        SET balance = ?, normal_balance = ?, total_deposited = total_deposited + ?, 
                        deposit_count = deposit_count + 1, total_bonus = total_bonus + ?
                        WHERE user_id = ?
                    ''', (new_balance, new_normal_balance, amount, bonus, user_id))
                    
                    # Referans komisyonu
                    ref_commission = 0
                    if user.get('referred_by'):
                        ref_commission = amount * 0.10  # %10 komisyon
                        referrer = self.db.get_user(user['referred_by'])
                        if referrer:
                            self.db.add_balance(user['referred_by'], ref_commission, "normal", 0, "referral_deposit")
                            
                            # Referans komisyonu kaydı
                            referral_link = f"https://t.me/GorevYapsamBot?start=ref_{user['referred_by']}"
                            log_id = self.db.record_referral(user['referred_by'], user_id, referral_link, ref_commission)
                            self.db.complete_referral(log_id, "referral_deposit")
                    
                    # Referans grubuna bildirim gönder
                    self.reference_notifier.notify_deposit(user_id, amount, 'user')
                    
                    # Başarı mesajı
                    ref_message = f"\n👥 <b>Referans Komisyonu:</b> {ref_commission:.2f}₺ (referans sahibine ödendi)" if ref_commission > 0 else ""
                    
                    send_message(user_id, f"""
<b>✅ BAKİYE YÜKLENDİ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 <b>Toplam: {total:.2f}₺</b>
• Yatırım: {amount:.2f}₺
• Bonus: {bonus:.2f}₺ (%{DEPOSIT_BONUS_PERCENT}){ref_message}
• Yeni Normal Bakiye: {new_normal_balance:.2f}₺
• Yeni Toplam Bakiye: {new_balance:.2f}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

🎉 <b>Hemen görev yapmaya başlayın!</b>
""")
                
                self.db.conn.commit()
                self.clear_user_state(user_id)
                time.sleep(2)
                
                user = self.db.get_user(user_id)
                if user.get('is_advertiser', 0) and deposit_type == 'advertiser':
                    self.show_advertiser_menu(user_id)
                else:
                    self.show_main_menu(user_id)
                
            except Exception as e:
                print(f"❌ TXID hatası: {e}")
                send_message(user_id, "❌ İşlem kaydedilemedi!")
        
        # TRX ADRESİ BEKLEME (Para çekme)
        elif state == 'waiting_trx_address':
            trx_address = message['text'].strip()
            
            if len(trx_address) < 10:
                send_message(user_id, "❌ Geçersiz TRX adresi!")
                return
            
            try:
                withdraw_data = data
                amount = withdraw_data['amount']
                
                # Para çekme talebi oluştur
                withdrawal_id = self.db.create_withdrawal(user_id, amount, trx_address)
                
                # Kullanıcının bakiyesini düş (bloke et)
                user = self.db.get_user(user_id)
                new_balance = user.get('balance', 0) - amount
                new_normal_balance = user.get('normal_balance', 0) - amount
                
                self.db.cursor.execute('''
                    UPDATE users 
                    SET balance = ?, normal_balance = ?
                    WHERE user_id = ?
                ''', (new_balance, new_normal_balance, user_id))
                
                # Referans grubuna bildirim gönder
                self.reference_notifier.notify_withdrawal(user_id, amount, withdrawal_id)
                
                # Admin'e bildirim gönder
                admin_message = f"""
<b>🔄 YENİ PARA ÇEKİM TALEBİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📋 Talep Detayları:</b>
• Talep ID: {withdrawal_id}
• Kullanıcı: {user.get('name', 'Anonim')}
• Kullanıcı ID: {user_id}
• Tutar: {amount:.2f}₺
• TRX Adresi: <code>{trx_address}</code>
• Zaman: {get_turkey_time().strftime('%H:%M:%S')}

<b>⚠️ İşlem:</b>
1. TRX gönderin
2. TXID'yi bu mesaja yanıt olarak gönderin
3. Sistem otomatik olarak onaylayacak
"""
                
                send_message(ADMIN_ID, admin_message)
                
                # Kullanıcıya bildirim
                send_message(user_id, f"""
<b>✅ PARA ÇEKİM TALEBİ ALINDI!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>Para çekme talebiniz alındı!</b>

📊 <b>Detaylar:</b>
• Talep ID: {withdrawal_id}
• Tutar: {amount:.2f}₺
• TRX Adresi: <code>{trx_address}</code>
• Durum: İnceleme bekliyor
• Yeni Normal Bakiye: {new_normal_balance:.2f}₺
• Yeni Toplam Bakiye: {new_balance:.2f}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>İşlem 24 saat içinde tamamlanacaktır.</b>
<b>Admin onayından sonra ödemeniz TRX adresinize gönderilecektir.</b>
""")
                
                self.clear_user_state(user_id)
                time.sleep(2)
                self.show_main_menu(user_id)
                
            except Exception as e:
                print(f"❌ TRX adresi hatası: {e}")
                send_message(user_id, "❌ İşlem kaydedilemedi!")
    
    def start_deposit(self, user_id, amount, deposit_type='user'):
        """Depozit işlemi başlat"""
        trx_amount = amount / self.trx_price
        
        if deposit_type == 'advertiser':
            message = f"""
<b>💰 REKLAMVEREN BAKİYE YÜKLEME</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 Ödeme Detayları:</b>
• Seçilen Tutar: {amount:.2f}₺
• <b>Toplam Alacak: {amount:.2f}₺</b>

<b>₿ TRX Bilgileri:</b>
• Gerekli TRX: {trx_amount:.4f} TRX
• TRX Fiyatı: {self.trx_price:.2f}₺

<b>🔗 TRX Adresi:</b>
<code>{TRX_ADDRESS}</code>

<b>📝 ADIMLAR:</b>
1. Yukarıdaki TRX adresini kopyalayın
2. Cüzdanınızdan <b>{trx_amount:.4f} TRX</b> gönderin
3. İşlem tamamlandığında TXID'yi bota gönderin
4. <b>{amount:.2f}₺</b> reklamveren bakiyenize otomatik yüklenecek

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<code>/cancel</code> iptal etmek için
"""
        else:
            bonus = amount * DEPOSIT_BONUS_PERCENT / 100
            total = amount + bonus
            
            message = f"""
<b>💰 BAKİYE YÜKLEME</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 Ödeme Detayları:</b>
• Seçilen Tutar: {amount:.2f}₺
• Bonus (%{DEPOSIT_BONUS_PERCENT}): {bonus:.2f}₺
• <b>Toplam Alacak: {total:.2f}₺</b>

<b>₿ TRX Bilgileri:</b>
• Gerekli TRX: {trx_amount:.4f} TRX
• TRX Fiyatı: {self.trx_price:.2f}₺

<b>🔗 TRX Adresi:</b>
<code>{TRX_ADDRESS}</code>

<b>📝 ADIMLAR:</b>
1. Yukarıdaki TRX adresini kopyalayın
2. Cüzdanınızdan <b>{trx_amount:.4f} TRX</b> gönderin
3. İşlem tamamlandığında TXID'yi bota gönderin
4. <b>{total:.2f}₺</b> bakiyenize otomatik yüklenecek

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<code>/cancel</code> iptal etmek için
"""
        
        deposit_id = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:10].upper()
        
        try:
            bonus_amount = amount * DEPOSIT_BONUS_PERCENT / 100 if deposit_type == 'user' else 0
            
            self.db.cursor.execute('''
                INSERT INTO deposits (deposit_id, user_id, amount_try, amount_trx, created_at, trx_price, bonus_amount, deposit_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (deposit_id, user_id, amount, trx_amount, get_turkey_time().isoformat(), self.trx_price, bonus_amount, deposit_type))
            self.db.conn.commit()
            
            self.set_user_state(user_id, 'waiting_txid', {
                'deposit_id': deposit_id, 
                'amount': amount,
                'deposit_type': deposit_type
            })
            send_message(user_id, message)
            
        except Exception as e:
            print(f"❌ Depozit hatası: {e}")
            send_message(user_id, "❌ Depozit oluşturulamadı!")
    
    def show_deposit_menu(self, user_id):
        """Normal kullanıcı depozit menüsü"""
        self.update_trx_price()
        
        message = f"""
<b>💰 BAKİYE YÜKLEME</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>₿ TRX Fiyatı:</b> {self.trx_price:.2f}₺
<b>🎁 Bonus Oranı:</b> %{DEPOSIT_BONUS_PERCENT}

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<b>👇 Yüklemek istediğiniz tutarı seçin:</b>
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': f'25₺ → {25 * (1 + DEPOSIT_BONUS_PERCENT/100):.2f}₺', 'callback_data': 'deposit_amount_25_user'},
                    {'text': f'50₺ → {50 * (1 + DEPOSIT_BONUS_PERCENT/100):.2f}₺', 'callback_data': 'deposit_amount_50_user'}
                ],
                [
                    {'text': f'100₺ → {100 * (1 + DEPOSIT_BONUS_PERCENT/100):.2f}₺', 'callback_data': 'deposit_amount_100_user'},
                    {'text': f'200₺ → {200 * (1 + DEPOSIT_BONUS_PERCENT/100):.2f}₺', 'callback_data': 'deposit_amount_200_user'}
                ],
                [
                    {'text': '🔙 Geri', 'callback_data': 'menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def show_withdraw_menu(self, user_id):
        user = self.db.get_user(user_id)
        normal_balance = user.get('normal_balance', 0)
        
        message = f"""
<b>🏧 PARA ÇEKME</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 Mevcut Normal Bakiye:</b> {normal_balance:.2f}₺
<b>💰 Mevcut Toplam Bakiye:</b> {user.get('balance', 0):.2f}₺

<b>📋 Şartlar:</b>
• Minimum çekim: {MIN_WITHDRAW}₺
• İşlem süresi: 24 saat
• Komisyon: Yok

<b>⚠️ ÖNEMLİ:</b>
• Sadece TRX (Tron) cüzdan adresi kabul edilir!
• Yanlış cüzdan adresi girerseniz para kaybolur!
• Sadece normal bakiyenizi çekebilirsiniz!

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}
"""
        
        if normal_balance >= MIN_WITHDRAW:
            markup = {
                'inline_keyboard': [
                    [
                        {'text': '💸 Çekim Yap', 'callback_data': 'start_withdraw'},
                        {'text': '🔙 Geri', 'callback_data': 'menu'}
                    ]
                ]
            }
        else:
            markup = {
                'inline_keyboard': [
                    [
                        {'text': '💰 Bakiye Yükle', 'callback_data': 'deposit'},
                        {'text': '🔙 Geri', 'callback_data': 'menu'}
                    ]
                ]
            }
        
        send_message(user_id, message, markup)
    
    def start_withdraw_process(self, user_id):
        """Para çekme işlemini başlat"""
        user = self.db.get_user(user_id)
        normal_balance = user.get('normal_balance', 0)
        
        if normal_balance < MIN_WITHDRAW:
            send_message(user_id, f"❌ Minimum çekim tutarı {MIN_WITHDRAW}₺!")
            self.show_withdraw_menu(user_id)
            return
        
        self.set_user_state(user_id, 'waiting_trx_address', {
            'amount': normal_balance,
            'step': 1
        })
        
        send_message(user_id, f"""
<b>💸 PARA ÇEKME İŞLEMİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 Çekilecek Tutar:</b> {normal_balance:.2f}₺
<b>⚠️ Minimum Çekim:</b> {MIN_WITHDRAW}₺

<b>📝 TRX (Tron) cüzdan adresinizi girin:</b>
• Örnek: TVJKGbdBQrbvQzq6WZhb3kaGa3LYgVrMSK
• Sadece TRX adresi kabul edilir!
• Yanlış adres girerseniz para kaybolur!

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<code>/cancel</code> iptal etmek için
""")
    
    def show_profile(self, user_id):
        user = self.db.get_user(user_id)
        
        # Referans durumu
        ref_status = "✅" if user.get('is_referred') else "❌"
        ref_info = ""
        if user.get('is_referred'):
            ref_info = f"\n<b>👥 Referans Durumu:</b> Referans ile kayıt oldu"
            if user.get('referred_by'):
                ref_info += f"\n<b>👤 Davet Eden:</b> Kullanıcı ID: {user['referred_by']}"
        
        # Reklamveren durumu
        advertiser_status = "✅ Aktif" if user.get('is_advertiser') else "❌ Kapalı"
        advertiser_info = ""
        if user.get('is_advertiser'):
            advertiser_info = f"""
<b>👑 Reklamveren Bilgileri:</b>
• Reklam Bakiye: {user.get('ads_balance', 0):.2f}₺
• Normal Bakiye: {user.get('normal_balance', 0):.2f}₺
• Toplam Bakiye: {user.get('balance', 0):.2f}₺
• Toplam Harcama: {user.get('total_spent_on_ads', 0):.2f}₺
"""
        
        message = f"""
<b>👤 PROFİL BİLGİLERİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👤 İsim:</b> {user.get('name', 'Kullanıcı')}
<b>🆔 Kullanıcı ID:</b> <code>{user_id}</code>
<b>🔗 Referans Durumu:</b> {ref_status}{ref_info}
<b>👑 Reklamveren:</b> {advertiser_status}{advertiser_info}

<b>💰 FİNANSAL DURUM</b>
• Normal Bakiye: {user.get('normal_balance', 0):.2f}₺
• Reklam Bakiye: {user.get('ads_balance', 0):.2f}₺
• Toplam Bakiye: {user.get('balance', 0):.2f}₺
• Toplam Kazanç: {user.get('total_earned', 0):.2f}₺

<b>📊 İSTATİSTİKLER</b>
• Tamamlanan Görev: {user.get('tasks_completed', 0)}
• Referans Sayısı: {user.get('referrals', 0)}
• Referans Kazancı: {user.get('ref_earned', 0):.2f}₺

<b>💳 İŞLEMLER</b>
• Toplam Yatırım: {user.get('total_deposited', 0):.2f}₺
• Toplam Bonus: {user.get('total_bonus', 0):.2f}₺
• Toplam Çekim: {user.get('total_withdrawn', 0):.2f}₺

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '💰 Bakiye Yükle', 'callback_data': 'deposit'},
                    {'text': '🏧 Para Çek', 'callback_data': 'withdraw'}
                ],
                [
                    {'text': '🔄 Bakiye Dönüştür', 'callback_data': 'convert_balance'},
                    {'text': '👥 Referans', 'callback_data': 'referral'}
                ],
                [
                    {'text': '📊 İstatistik', 'callback_data': 'stats'},
                    {'text': '🔙 Ana Menü', 'callback_data': 'menu'}
                ]
            ]
        }
        
        # Reklamveren butonu
        if user.get('is_advertiser'):
            markup['inline_keyboard'].insert(1, [
                {'text': '👑 Reklamveren', 'callback_data': 'advertiser_menu'}
            ])
        
        send_message(user_id, message, markup)
    
    def show_referral_menu(self, user_id):
        user = self.db.get_user(user_id)
        
        # Referans istatistiklerini getir
        self.db.cursor.execute('''
            SELECT COUNT(*) as total_refs, 
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_refs,
                   SUM(amount) as total_earned
            FROM referral_logs 
            WHERE referrer_id = ?
        ''', (user_id,))
        ref_stats = self.db.cursor.fetchone()
        
        total_refs = ref_stats['total_refs'] if ref_stats else 0
        completed_refs = ref_stats['completed_refs'] if ref_stats else 0
        total_earned = ref_stats['total_earned'] if ref_stats and ref_stats['total_earned'] else 0
        
        referral_link = f"https://t.me/GorevYapsamBot?start=ref_{user_id}"
        
        message = f"""
<b>👥 REFERANS SİSTEMİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 Referans İstatistikleri:</b>
• Toplam Referans: {total_refs}
• Başarılı Referans: {completed_refs}
• Referans Kazancı: {total_earned:.2f}₺

<b>💰 Kazanç Sistemi:</b>
• <b>İlk kayıt referansı:</b> 1₺ bonus
• <b>Geç katılım referansı:</b> 0.5₺ bonus
• <b>Depozit referansı:</b> %10 komisyon

<b>🔗 Referans Linkiniz:</b>
<code>{referral_link}</code>

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<b>💡 Nasıl Çalışır:</b>
1. Linkinizi arkadaşlarınızla paylaşın
2. Arkadaşlarınız linke tıklayarak kaydolur
3. <b>Hemen 1₺ bonus</b> alırsınız
4. Arkadaşınız depozit yaparsa <b>%10 komisyon</b> alırsınız
5. Sınırsız kazanç fırsatı!
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '📋 Linki Kopyala', 'callback_data': 'referral_copy'},
                    {'text': '📤 Paylaş', 'callback_data': 'referral_share'}
                ],
                [
                    {'text': '📊 Detaylı Rapor', 'callback_data': 'referral_details'},
                    {'text': '🔙 Geri', 'callback_data': 'menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def copy_referral_link(self, user_id):
        referral_link = f"https://t.me/GorevYapsamBot?start=ref_{user_id}"
        send_message(user_id, f"""
<b>🔗 REFERANS LİNKİNİZ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<code>{referral_link}</code>

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

📋 <b>Yukarıdaki linki kopyalayın ve paylaşın!</b>

💡 <b>Paylaşım Önerileri:</b>
• WhatsApp grupları
• Telegram grupları
• Sosyal medya
• Arkadaşlarınıza özel mesaj
""")
    
    def share_referral_link(self, user_id):
        referral_link = f"https://t.me/GorevYapsamBot?start=ref_{user_id}"
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '📱 WhatsApp', 'url': f'https://wa.me/?text=Görev Yapsam Bot ile para kazanın! {referral_link}'},
                    {'text': '✈️ Telegram', 'url': f'https://t.me/share/url?url={referral_link}&text=Görev Yapsam Bot ile para kazanın!'}
                ],
                [
                    {'text': '🔙 Geri', 'callback_data': 'referral'}
                ]
            ]
        }
        
        send_message(user_id, f"""
<b>📤 REFERANS LİNKİ PAYLAŞ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

👇 <b>Aşağıdaki butonlardan birine tıklayarak paylaşabilirsiniz:</b>
""", markup)
    
    def show_referral_details(self, user_id):
        user = self.db.get_user(user_id)
        
        self.db.cursor.execute('''
            SELECT * FROM referral_logs 
            WHERE referrer_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
        ''', (user_id,))
        ref_logs = self.db.cursor.fetchall()
        
        if not ref_logs:
            message = f"""
<b>📊 REFERANS DETAYLARI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📭 <b>Henüz referans kaydınız bulunmuyor</b>

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>Referans linkinizi paylaşarak kazanmaya başlayın!</b>
"""
        else:
            message = f"""
<b>📊 SON 10 REFERANS KAYDI</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            total_earned = 0
            
            for log in ref_logs:
                status = "✅" if log['status'] == 'completed' else "⏳" if log['status'] == 'pending' else "❌"
                reward_type = {
                    'welcome': 'Hoşgeldin',
                    'late_join': 'Geç Katılım',
                    'referral_deposit': 'Depozit Komisyonu'
                }.get(log['reward_type'], log['reward_type'] or 'Bilinmiyor')
                
                if log['status'] == 'completed':
                    total_earned += log['amount'] or 0
                
                message += f"""{status} <b>Referans #{log['log_id']}</b>
├ <b>Tür:</b> {reward_type}
├ <b>Tutar:</b> {log['amount']:.2f}₺
├ <b>Durum:</b> {log['status']}
└ <b>Tarih:</b> {log['created_at'][:16]}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            message += f"\n<b>💰 Toplam Kazanç:</b> {total_earned:.2f}₺"
        
        markup = {
            'inline_keyboard': [[
                {'text': '🔙 Geri', 'callback_data': 'referral'}
            ]]
        }
        
        send_message(user_id, message, markup)
    
    def show_help(self, user_id):
        message = f"""
<b>❓ YARDIM VE DESTEK</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🤖 BOT NASIL ÇALIŞIR?</b>
1. 💬 Sohbet kanalına katılın (@{MANDATORY_CHANNEL})
2. 🎯 Görev yapın veya 📢 reklam verin
3. 💰 Para kazanmaya başlayın!

<b>🎯 GÖREV YAPMA:</b>
1. "🎯 Görev Yap" butonuna tıklayın
2. Mevcut görevleri görün
3. Göreve katılın
4. Gruba/Kanala katılın
5. Reklamveren katılımınızı doğrulasın
6. Ödülünüz bakiyenize yüklensin

<b>📢 REKLAM VERME:</b>
1. "👑 Reklamveren Ol" butonuna tıklayın
2. "💰 Bakiye Yükle" ile reklam bakiyesi yükleyin
3. "📢 Görev Oluştur" ile görev oluşturun
4. Katılımcıların katılımını doğrulayın
5. Ödemeler otomatik olarak yapılsın

<b>🔄 BAKİYE DÖNÜŞTÜRME:</b>
1. "🔄 Bakiye Dönüştür" butonuna tıklayın
2. Reklam bakiyesini normal bakiyeye veya tam tersi dönüştürün
3. Normal bakiye ile görev yapın veya para çekin
4. Reklam bakiyesi ile reklam verin

<b>⚠️ ÖNEMLİ UYARILAR:</b>
• Grubu/Kanalı terk ederseniz ödülünüz geri alınır!
• Sohbet kanalından ayrılırsanız botu kullanamazsınız!
• Reklam bakiyesi sadece reklam vermek içindir!
• Minimum çekim: {MIN_WITHDRAW}₺

<b>📞 DESTEK:</b>
Sorularınız için @GorevYapsamBot yazın.

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}
"""
        
        markup = {
            'inline_keyboard': [[
                {'text': '🔙 Geri', 'callback_data': 'menu'}
            ]]
        }
        send_message(user_id, message, markup)
    
    def show_admin_panel(self, user_id):
        if user_id != ADMIN_ID:
            send_message(user_id, "❌ Yetkiniz yok!")
            return
        
        self.db.cursor.execute("SELECT COUNT(*) FROM users")
        total_users = self.db.cursor.fetchone()[0]
        
        self.db.cursor.execute("SELECT COUNT(*) FROM users WHERE is_advertiser = 1")
        total_advertisers = self.db.cursor.fetchone()[0]
        
        message = f"""
<b>👑 ADMIN PANELİ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 SİSTEM İSTATİSTİKLERİ</b>
• 👥 Toplam Kullanıcı: {total_users}
• 📢 Reklamverenler: {total_advertisers}

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<b>🛠️ YÖNETİM ARAÇLARI</b>
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '📊 İstatistik', 'callback_data': 'admin_stats'},
                    {'text': '👥 Kullanıcılar', 'callback_data': 'admin_users'}
                ],
                [
                    {'text': '📢 Reklamverenler', 'callback_data': 'admin_advertisers'},
                    {'text': '💰 Depozitler', 'callback_data': 'admin_deposits'}
                ],
                [
                    {'text': '💸 Çekimler', 'callback_data': 'admin_withdrawals'},
                    {'text': '🔙 Geri', 'callback_data': 'menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def show_admin_stats(self, user_id):
        if user_id != ADMIN_ID:
            return
        
        self.db.cursor.execute("SELECT COUNT(*) FROM users")
        total_users = self.db.cursor.fetchone()[0]
        
        self.db.cursor.execute("SELECT COUNT(*) FROM users WHERE is_advertiser = 1")
        total_advertisers = self.db.cursor.fetchone()[0]
        
        self.db.cursor.execute("SELECT COUNT(*) FROM tasks")
        total_tasks = self.db.cursor.fetchone()[0]
        
        self.db.cursor.execute("SELECT COUNT(*) FROM deposits WHERE status = 'completed'")
        total_deposits = self.db.cursor.fetchone()[0]
        
        self.db.cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'completed'")
        total_withdrawals = self.db.cursor.fetchone()[0]
        
        self.db.cursor.execute("SELECT SUM(amount_try) FROM deposits WHERE status = 'completed'")
        total_deposit_amount = self.db.cursor.fetchone()[0] or 0
        
        self.db.cursor.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'completed'")
        total_withdraw_amount = self.db.cursor.fetchone()[0] or 0
        
        message = f"""
<b>📊 DETAYLI İSTATİSTİKLER</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👥 KULLANICI İSTATİSTİKLERİ</b>
• Toplam Kullanıcı: {total_users}
• Reklamverenler: {total_advertisers}

<b>💰 FİNANSAL İSTATİSTİKLER</b>
• Toplam Yatırım: {total_deposits} adet, {total_deposit_amount:.2f}₺
• Toplam Çekim: {total_withdrawals} adet, {total_withdraw_amount:.2f}₺

<b>📢 GÖREV İSTATİSTİKLERİ</b>
• Toplam Görev: {total_tasks}

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

<b>⏰ SİSTEM DURUMU:</b> ✅ ÇALIŞIYOR
<b>🔄 SON KONTROL:</b> {get_turkey_time().strftime('%H:%M:%S')}
"""
        
        markup = {
            'inline_keyboard': [[
                {'text': '🔙 Geri', 'callback_data': 'admin_panel'}
            ]]
        }
        send_message(user_id, message, markup)
    
    def show_admin_advertisers(self, user_id):
        if user_id != ADMIN_ID:
            return
        
        self.db.cursor.execute('''
            SELECT * FROM users 
            WHERE is_advertiser = 1 
            ORDER BY created_at DESC 
            LIMIT 10
        ''')
        advertisers = self.db.cursor.fetchall()
        
        if not advertisers:
            message = "📢 <b>Henüz reklamveren bulunmuyor</b>"
        else:
            message = "<b>📢 SON 10 REKLAMVEREN</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for adv in advertisers:
                message += f"""👤 <b>{adv['name'][:15]}</b>
├ <b>Reklam Bakiyesi:</b> {adv['ads_balance']:.1f}₺
├ <b>Normal Bakiye:</b> {adv['normal_balance']:.1f}₺
├ <b>Toplam Harcama:</b> {adv['total_spent_on_ads']:.1f}₺
└ <b>Kayıt:</b> {adv['created_at'][:10]}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        markup = {
            'inline_keyboard': [[
                {'text': '🔙 Geri', 'callback_data': 'admin_panel'}
            ]]
        }
        send_message(user_id, message, markup)
    
    def show_admin_users(self, user_id):
        if user_id != ADMIN_ID:
            return
        
        self.db.cursor.execute('''
            SELECT * FROM users 
            ORDER BY created_at DESC 
            LIMIT 10
        ''')
        users = self.db.cursor.fetchall()
        
        if not users:
            message = "👥 <b>Hiç kullanıcı bulunmuyor</b>"
        else:
            message = "<b>👥 SON 10 KULLANICI</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for usr in users:
                referred = "✅" if usr['referred_by'] else "❌"
                advertiser = "👑" if usr['is_advertiser'] else "👤"
                message += f"""{advertiser} <b>{usr['name'][:15]}</b>
├ <b>Normal Bakiye:</b> {usr['normal_balance']:.1f}₺
├ <b>Reklam Bakiye:</b> {usr['ads_balance']:.1f}₺
├ <b>Referans:</b> {usr['referrals']} {referred}
├ <b>Reklamveren:</b> {'Evet' if usr['is_advertiser'] else 'Hayır'}
└ <b>Kayıt:</b> {usr['created_at'][:10]}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        markup = {
            'inline_keyboard': [[
                {'text': '🔙 Geri', 'callback_data': 'admin_panel'}
            ]]
        }
        send_message(user_id, message, markup)
    
    def show_admin_deposits(self, user_id):
        if user_id != ADMIN_ID:
            return
        
        self.db.cursor.execute('''
            SELECT * FROM deposits 
            ORDER BY created_at DESC 
            LIMIT 10
        ''')
        deposits = self.db.cursor.fetchall()
        
        if not deposits:
            message = "💰 <b>Hiç depozit bulunmuyor</b>"
        else:
            message = "<b>💰 SON 10 DEPOZİT</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for dep in deposits:
                status = "✅" if dep['status'] == 'completed' else "⏳" if dep['status'] == 'pending' else "❌"
                deposit_type = "👑 Reklamveren" if dep['deposit_type'] == 'advertiser' else "👤 Normal"
                message += f"""{status} <b>Depozit #{dep['deposit_id'][:8]}</b>
├ <b>Tutar:</b> {dep['amount_try']:.2f}₺
├ <b>Bonus:</b> {dep['bonus_amount']:.2f}₺
├ <b>Tür:</b> {deposit_type}
└ <b>Durum:</b> {dep['status']}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        markup = {
            'inline_keyboard': [[
                {'text': '🔙 Geri', 'callback_data': 'admin_panel'}
            ]]
        }
        send_message(user_id, message, markup)
    
    def show_admin_withdrawals(self, user_id):
        if user_id != ADMIN_ID:
            return
        
        self.db.cursor.execute('''
            SELECT w.*, u.name 
            FROM withdrawals w 
            LEFT JOIN users u ON w.user_id = u.user_id 
            ORDER BY w.created_at DESC 
            LIMIT 10
        ''')
        withdrawals = self.db.cursor.fetchall()
        
        if not withdrawals:
            message = "💸 <b>Henüz çekim talebi bulunmuyor</b>"
        else:
            message = "<b>💸 SON 10 ÇEKİM TALEBİ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for wd in withdrawals:
                status = "✅" if wd['status'] == 'completed' else "⏳" if wd['status'] == 'pending' else "❌"
                user_name = wd['name'] or "Anonim"
                message += f"""{status} <b>Talep #{wd['withdrawal_id'][:8]}</b>
├ <b>Kullanıcı:</b> {user_name[:15]}
├ <b>Tutar:</b> {wd['amount']:.2f}₺
├ <b>TRX Adresi:</b> <code>{wd['trx_address'][:20]}...</code>
└ <b>Durum:</b> {wd['status']}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        markup = {
            'inline_keyboard': [[
                {'text': '🔙 Geri', 'callback_data': 'admin_panel'}
            ]]
        }
        send_message(user_id, message, markup)
    
    def show_my_tasks(self, user_id):
        """Kullanıcının katıldığı görevleri göster"""
        self.db.cursor.execute('''
            SELECT tp.*, t.target_name, t.reward_amount, t.task_type
            FROM task_participations tp
            JOIN tasks t ON tp.task_id = t.task_id
            WHERE tp.user_id = ?
            ORDER BY tp.joined_at DESC
            LIMIT 10
        ''', (user_id,))
        participations = self.db.cursor.fetchall()
        
        if not participations:
            message = f"""
<b>📋 KATILDIĞIM GÖREVLER</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📭 <b>Henüz hiç göreve katılmadınız</b>

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>İlk görevinize katılarak para kazanmaya başlayın!</b>
"""
        else:
            message = f"""
<b>📋 SON 10 GÖREV KATILIMIM</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            total_earned = 0
            
            for part in participations:
                task_type = "👥 Grup" if part['task_type'] == 'group' else "📢 Kanal"
                status_icon = "✅" if part['status'] == 'verified' else "⏳" if part['status'] == 'pending' else "❌" if part['status'] == 'left' else "❓"
                status_text = {
                    'verified': 'Tamamlandı',
                    'pending': 'Bekliyor',
                    'left': 'Ayrıldı'
                }.get(part['status'], part['status'])
                
                if part['status'] == 'verified':
                    total_earned += part['reward_paid'] or 0
                
                message += f"""{status_icon} <b>{part['target_name'][:20]}</b>
├ <b>Tür:</b> {task_type}
├ <b>Ödül:</b> {part['reward_amount']:.2f}₺
├ <b>Durum:</b> {status_text}
└ <b>Tarih:</b> {part['joined_at'][:16]}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            message += f"\n<b>💰 Toplam Kazanç:</b> {total_earned:.2f}₺"
        
        markup = {
            'inline_keyboard': [[
                {'text': '🎯 Görev Yap', 'callback_data': 'tasks'},
                {'text': '🔙 Ana Menü', 'callback_data': 'menu'}
            ]]
        }
        
        send_message(user_id, message, markup)

# Arka Plan Kontrol Sistemi
class BackgroundChecker:
    def __init__(self, db):
        self.db = db
        self.running = False
    
    def start(self):
        self.running = True
        threading.Thread(target=self.run, daemon=True).start()
        print("🔄 Arka plan kontrol sistemi başlatıldı")
    
    def stop(self):
        self.running = False
    
    def run(self):
        while self.running:
            try:
                self.check_channel_memberships()
                time.sleep(60)  # Her 60 saniyede bir kontrol et
            except Exception as e:
                print(f"❌ Arka plan kontrol hatası: {e}")
                time.sleep(30)
    
    def check_channel_memberships(self):
        """Kullanıcıların zorunlu kanal üyeliklerini kontrol et"""
        try:
            # Son 24 saatte aktif olan kullanıcıları getir
            twenty_four_hours_ago = (get_turkey_time() - timedelta(hours=24)).isoformat()
            
            self.db.cursor.execute('''
                SELECT user_id, name, in_channel, last_join_check 
                FROM users 
                WHERE last_active > ? OR last_join_check IS NULL OR last_join_check < ?
            ''', (twenty_four_hours_ago, twenty_four_hours_ago))
            
            users = self.db.cursor.fetchall()
            
            for user in users:
                user_id = user['user_id']
                
                # Kanal üyeliğini kontrol et
                is_member = get_chat_member(f"@{MANDATORY_CHANNEL}", user_id)
                current_status = user['in_channel']
                
                if is_member and current_status == 0:
                    # Kullanıcı kanala katılmış
                    self.db.update_user(user_id, {
                        'in_channel': 1,
                        'last_join_check': get_turkey_time().isoformat()
                    })
                    print(f"✅ {user_id} kullanıcısı kanala katıldı")
                
                elif not is_member and current_status == 1:
                    # Kullanıcı kanaldan ayrılmış
                    self.db.update_user(user_id, {
                        'in_channel': 0,
                        'last_join_check': get_turkey_time().isoformat()
                    })
                    
                    # Kullanıcıya bildirim gönder
                    send_message(user_id, f"""
<b>⚠️ ZORUNLU KANALDAN AYRILDINIZ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ <b>@{MANDATORY_CHANNEL} kanalından ayrıldınız!</b>

📊 <b>Sonuçlar:</b>
• Botu kullanamazsınız
• Mevcut görevleriniz iptal edilebilir
• Kazançlarınız düşülebilir

💬 <b>Sohbet:</b> @{MANDATORY_CHANNEL}
📢 <b>Referans:</b> @{REFERENCE_GROUP}

💡 <b>Tekrar katılmak için:</b>
1. @{MANDATORY_CHANNEL} kanalına katılın
2. /start yazarak botu yeniden başlatın
""")
                    
                    print(f"⚠️ {user_id} kullanıcısı kanaldan ayrıldı")
            
            self.db.conn.commit()
            
        except Exception as e:
            print(f"❌ Kanal kontrol hatası: {e}")

# Ana Program
def main():
    print(f"""
    ╔════════════════════════════════════════════════════════════════╗
    ║                    GÖREV YAPSAM BOT v22.0                      ║
    ║   NORMAL + REKLAM BAKİYESİ + BAKİYE DÖNÜŞTÜRME +               ║
    ║   ZORUNLU KANAL KONTROLÜ + REFERANS GRUBU BİLDİRİMLERİ         ║
    ║   GERÇEK ZAMANLI BİLDİRİMLER + TÜM İŞLEMLER REFERANS GRUBUNDA  ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    bot = BotSystem()
    
    bot_thread = threading.Thread(target=bot.start_polling, daemon=True)
    bot_thread.start()
    
    print("✅ Bot başarıyla başlatıldı!")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"💬 Zorunlu Kanal: @{MANDATORY_CHANNEL}")
    print(f"📢 Referans Grubu: @{REFERENCE_GROUP}")
    print(f"₿ TRX Adresi: {TRX_ADDRESS}")
    print("💰 Min Depozit: 25₺, Max: 200₺")
    print(f"💸 Minimum Çekim: {MIN_WITHDRAW}₺")
    print("🎁 Bonuslar: %35 Normal Depozit")
    print("👥 Referans Bonusu: 1₺ her davet")
    print("📢 Görev Ücretleri: Grup 0.5₺, Kanal 1.25₺")
    print("⚠️ Terk Cezası: Grubu/Kanalı terk edenler ödülü kaybeder")
    print("🔄 Bakiye Dönüşümü: Reklam ↔ Normal bakiye")
    print("📊 Referans Grubu Bildirimleri: Aktif")
    print("🔄 Arka Plan Kontrol: Aktif")
    print("🔗 Telegram'da /start yazarak test edin")
    
    return app

if __name__ == "__main__":
    if TOKEN:
        main()
        port = int(os.environ.get('PORT', 8080))
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        print("❌ TELEGRAM_BOT_TOKEN gerekli!")

def create_app():
    bot = BotSystem()
    bot_thread = threading.Thread(target=bot.start_polling, daemon=True)
    bot_thread.start()
    return app
