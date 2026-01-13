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
from forex_python.converter import CurrencyRates

# Telegram Ayarları
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "7904032877")

# Zorunlu Kanallar (Güncellenmiş)
MANDATORY_CHANNELS = {
    'main': {
        'username': 'EarnTether2026',
        'link': 'https://t.me/EarnTether2026',
        'name': 'Ana Kanal'
    },
    'instagram': {
        'username': 'instagramNewsBrazil',
        'link': 'https://t.me/instagramNewsBrazil',
        'name': 'Instagram Haberleri'
    },
    'binance': {
        'username': 'BinanceBrazilNews',
        'link': 'https://t.me/BinanceBrazilNews',
        'name': 'Binance Haberleri'
    },
    'stats': {
        'username': 'TaskizLive',
        'link': 'https://t.me/TaskizLive',
        'name': 'Canlı İstatistik'
    }
}

# İstatistik kanalı
STATS_CHANNEL = "TaskizLive"

if not TOKEN:
    raise ValueError("Bot token gerekli!")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Dil ve Para Birimi Ayarları
SUPPORTED_LANGUAGES = {
    'tr': {'name': 'Türkçe', 'flag': '🇹🇷', 'currency': 'TRY'},
    'en': {'name': 'English', 'flag': '🇺🇸', 'currency': 'USD'},
    'ru': {'name': 'Русский', 'flag': '🇷🇺', 'currency': 'RUB'},
    'bn': {'name': 'বাংলা', 'flag': '🇧🇩', 'currency': 'BDT'}
}

# Varsayılan dil
DEFAULT_LANGUAGE = 'tr'

# Türkiye saati için
TURKEY_TZ = pytz.timezone('Europe/Istanbul')

# TRX Ayarları
TRX_ADDRESS = "DEPOZIT_YAPILACAK_ADRES"
TRX_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=tron&vs_currencies=usd"
MIN_DEPOSIT_USD = 2.5
MAX_DEPOSIT_USD = 10.0
DEPOSIT_BONUS_PERCENT = 0

# Görev Ücretleri (USD cinsinden)
CHANNEL_TASK_PRICE = 0.03
GROUP_TASK_PRICE = 0.02
BOT_TASK_PRICE = 0.01

# Minimum çekim (USD)
MIN_WITHDRAW = 1.0

# Referans bonusları
REF_WELCOME_BONUS = 0.005
REF_TASK_COMMISSION = 0.25

# Flask App
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "online", "bot": "TaskizBot v2.0", "languages": list(SUPPORTED_LANGUAGES.keys())})

def get_turkey_time():
    """Türkiye saatini döndür"""
    return datetime.now(TURKEY_TZ)

# Dil Metinleri
LANGUAGE_TEXTS = {
    'tr': {
        'menu': {
            'welcome': "🤖 TASKİZBOT",
            'balance': "💰 Bakiye",
            'advertiser_balance': "👑 Reklamveren Bakiye",
            'tasks_completed': "🎯 Tamamlanan Görev",
            'referrals': "👥 Referans",
            'ref_earned': "👥 Referans Kazancı",
            'chat': "💬 Sohbet",
            'stats': "📊 İstatistik",
            'main_menu': "📋 ANA MENÜ",
            'back': "🔙 Geri",
            'cancel': "🚫 İptal",
            'help': "❓ Yardım",
            'profile': "👤 Profil",
            'channels': "📢 Zorunlu Kanallar",
            'join_channels': "📢 Kanallara Katıl"
        },
        'buttons': {
            'do_task': "🎯 Görev Yap",
            'load_balance': "💰 Bakiye Yükle",
            'withdraw': "🏧 Para Çek",
            'stats': "📊 İstatistik",
            'profile': "👤 Profil",
            'referral': "👥 Referans",
            'advertiser': "📢 Reklamveren",
            'become_advertiser': "👑 Reklamveren Ol",
            'advertiser_menu': "📢 Reklamveren Menüsü",
            'admin_panel': "👑 Admin Panel",
            'language': "🌐 Dil",
            'check_channels': "✅ Kanalları Kontrol Et",
            'join_all_channels': "📢 Tüm Kanallara Katıl"
        },
        'errors': {
            'not_in_channel': "❌ Tüm zorunlu kanallara katılmalısınız!",
            'insufficient_balance': "❌ Yetersiz bakiye!",
            'min_withdraw': "❌ Minimum çekim tutarı {amount}$!",
            'invalid_number': "❌ Geçersiz sayı!",
            'invalid_address': "❌ Geçersiz adres!",
            'already_joined': "❌ Zaten katıldınız!",
            'not_found': "❌ Bulunamadı!",
            'unauthorized': "❌ Yetkiniz yok!",
            'channel_not_joined': "❌ {channel_name} kanalına katılmadınız!"
        },
        'success': {
            'task_joined': "✅ Göreve katıldınız!",
            'deposit_received': "✅ Bakiye yüklendi!",
            'withdraw_requested': "✅ Para çekme talebi alındı!",
            'task_created': "✅ Görev oluşturuldu!",
            'task_verified': "✅ Görev doğrulandı!",
            'balance_added': "💰 Bakiye eklendi!",
            'all_channels_joined': "✅ Tüm kanallara katıldınız!",
            'channels_checked': "✅ Kanallar kontrol edildi!"
        },
        'channels': {
            'main': "📢 Ana Kanal",
            'instagram': "📸 Instagram Haberleri",
            'binance': "💰 Binance Haberleri",
            'stats': "📊 Canlı İstatistik",
            'mandatory': "Zorunlu Kanallar",
            'description': "Botu kullanmak için aşağıdaki kanalların tümüne katılmalısınız:"
        }
    },
    'en': {
        'menu': {
            'welcome': "🤖 TASKIZBOT",
            'balance': "💰 Balance",
            'advertiser_balance': "👑 Advertiser Balance",
            'tasks_completed': "🎯 Completed Tasks",
            'referrals': "👥 Referrals",
            'ref_earned': "👥 Referral Earnings",
            'chat': "💬 Chat",
            'stats': "📊 Statistics",
            'main_menu': "📋 MAIN MENU",
            'back': "🔙 Back",
            'cancel': "🚫 Cancel",
            'help': "❓ Help",
            'profile': "👤 Profile",
            'channels': "📢 Mandatory Channels",
            'join_channels': "📢 Join Channels"
        },
        'buttons': {
            'do_task': "🎯 Do Task",
            'load_balance': "💰 Load Balance",
            'withdraw': "🏧 Withdraw",
            'stats': "📊 Statistics",
            'profile': "👤 Profile",
            'referral': "👥 Referral",
            'advertiser': "📢 Advertiser",
            'become_advertiser': "👑 Become Advertiser",
            'advertiser_menu': "📢 Advertiser Menu",
            'admin_panel': "👑 Admin Panel",
            'language': "🌐 Language",
            'check_channels': "✅ Check Channels",
            'join_all_channels': "📢 Join All Channels"
        },
        'errors': {
            'not_in_channel': "❌ You must join all mandatory channels!",
            'insufficient_balance': "❌ Insufficient balance!",
            'min_withdraw': "❌ Minimum withdrawal amount {amount}$!",
            'invalid_number': "❌ Invalid number!",
            'invalid_address': "❌ Invalid address!",
            'already_joined': "❌ Already joined!",
            'not_found': "❌ Not found!",
            'unauthorized': "❌ Unauthorized!",
            'channel_not_joined': "❌ You didn't join {channel_name} channel!"
        },
        'success': {
            'task_joined': "✅ Joined the task!",
            'deposit_received': "✅ Balance loaded!",
            'withdraw_requested': "✅ Withdrawal request received!",
            'task_created': "✅ Task created!",
            'task_verified': "✅ Task verified!",
            'balance_added': "💰 Balance added!",
            'all_channels_joined': "✅ Joined all channels!",
            'channels_checked': "✅ Channels checked!"
        },
        'channels': {
            'main': "📢 Main Channel",
            'instagram': "📸 Instagram News",
            'binance': "💰 Binance News",
            'stats': "📊 Live Statistics",
            'mandatory': "Mandatory Channels",
            'description': "To use the bot, you must join all the channels below:"
        }
    },
    'ru': {
        'menu': {
            'welcome': "🤖 TASKIZBOT",
            'balance': "💰 Баланс",
            'advertiser_balance': "👑 Баланс рекламодателя",
            'tasks_completed': "🎯 Выполненные задания",
            'referrals': "👥 Рефералы",
            'ref_earned': "👥 Реферальный доход",
            'chat': "💬 Чат",
            'stats': "📊 Статистика",
            'main_menu': "📋 ГЛАВНОЕ МЕНЮ",
            'back': "🔙 Назад",
            'cancel': "🚫 Отмена",
            'help': "❓ Помощь",
            'profile': "👤 Профиль",
            'channels': "📢 Обязательные каналы",
            'join_channels': "📢 Присоединиться к каналам"
        },
        'buttons': {
            'do_task': "🎯 Выполнить задание",
            'load_balance': "💰 Пополнить баланс",
            'withdraw': "🏧 Вывести",
            'stats': "📊 Статистика",
            'profile': "👤 Профиль",
            'referral': "👥 Рефералы",
            'advertiser': "📢 Рекламодатель",
            'become_advertiser': "👑 Стать рекламодателем",
            'advertiser_menu': "📢 Меню рекламодателя",
            'admin_panel': "👑 Админ панель",
            'language': "🌐 Язык",
            'check_channels': "✅ Проверить каналы",
            'join_all_channels': "📢 Присоединиться ко всем каналам"
        },
        'errors': {
            'not_in_channel': "❌ Вы должны присоединиться ко всем обязательным каналам!",
            'insufficient_balance': "❌ Недостаточно средств!",
            'min_withdraw': "❌ Минимальная сумма вывода {amount}$!",
            'invalid_number': "❌ Неверный номер!",
            'invalid_address': "❌ Неверный адрес!",
            'already_joined': "❌ Уже присоединились!",
            'not_found': "❌ Не найдено!",
            'unauthorized': "❌ Неавторизован!",
            'channel_not_joined': "❌ Вы не присоединились к каналу {channel_name}!"
        },
        'success': {
            'task_joined': "✅ Присоединились к заданию!",
            'deposit_received': "✅ Баланс пополнен!",
            'withdraw_requested': "✅ Запрос на вывод получен!",
            'task_created': "✅ Задание создано!",
            'task_verified': "✅ Задание проверено!",
            'balance_added': "💰 Баланс добавлен!",
            'all_channels_joined': "✅ Присоединились ко всем каналам!",
            'channels_checked': "✅ Каналы проверены!"
        },
        'channels': {
            'main': "📢 Главный канал",
            'instagram': "📸 Новости Instagram",
            'binance': "💰 Новости Binance",
            'stats': "📊 Живая статистика",
            'mandatory': "Обязательные каналы",
            'description': "Чтобы использовать бота, вы должны присоединиться ко всем каналам ниже:"
        }
    },
    'bn': {
        'menu': {
            'welcome': "🤖 টাস্কিজবট",
            'balance': "💰 ব্যালেন্স",
            'advertiser_balance': "👑 বিজ্ঞাপনদাতার ব্যালেন্স",
            'tasks_completed': "🎯 সম্পন্ন টাস্ক",
            'referrals': "👥 রেফারেল",
            'ref_earned': "👥 রেফারেল আয়",
            'chat': "💬 চ্যাট",
            'stats': "📊 পরিসংখ্যান",
            'main_menu': "📋 প্রধান মেনু",
            'back': "🔙 পিছনে",
            'cancel': "🚫 বাতিল",
            'help': "❓ সাহায্য",
            'profile': "👤 প্রোফাইল",
            'channels': "📢 বাধ্যতামূলক চ্যানেল",
            'join_channels': "📢 চ্যানেলে যোগ দিন"
        },
        'buttons': {
            'do_task': "🎯 টাস্ক করুন",
            'load_balance': "💰 ব্যালেন্স লোড",
            'withdraw': "🏧 উত্তোলন",
            'stats': "📊 পরিসংখ্যান",
            'profile': "👤 প্রোফাইল",
            'referral': "👥 রেফারেল",
            'advertiser': "📢 বিজ্ঞাপনদাতা",
            'become_advertiser': "👑 বিজ্ঞাপনদাতা হন",
            'advertiser_menu': "📢 বিজ্ঞাপনদাতা মেনু",
            'admin_panel': "👑 অ্যাডমিন প্যানেল",
            'language': "🌐 ভাষা",
            'check_channels': "✅ চ্যানেল চেক করুন",
            'join_all_channels': "📢 সব চ্যানেলে যোগ দিন"
        },
        'errors': {
            'not_in_channel': "❌ আপনাকে সব বাধ্যতামূলক চ্যানেলে যোগ দিতে হবে!",
            'insufficient_balance': "❌ পর্যাপ্ত ব্যালেন্স নেই!",
            'min_withdraw': "❌ ন্যূনতম উত্তোলন পরিমাণ {amount}$!",
            'invalid_number': "❌ অবৈধ সংখ্যা!",
            'invalid_address': "❌ অবৈধ ঠিকানা!",
            'already_joined': "❌ ইতিমধ্যে যোগ দিয়েছেন!",
            'not_found': "❌ পাওয়া যায়নি!",
            'unauthorized': "❌ অননুমোদিত!",
            'channel_not_joined': "❌ আপনি {channel_name} চ্যানেলে যোগ দেননি!"
        },
        'success': {
            'task_joined': "✅ টাস্কে যোগ দিয়েছেন!",
            'deposit_received': "✅ ব্যালেন্স লোড হয়েছে!",
            'withdraw_requested': "✅ উত্তোলনের অনুরোধ পেয়েছেন!",
            'task_created': "✅ টাস্ক তৈরি হয়েছে!",
            'task_verified': "✅ টাস্ক যাচাই হয়েছে!",
            'balance_added': "💰 ব্যালেন্স যোগ হয়েছে!",
            'all_channels_joined': "✅ সব চ্যানেলে যোগ দিয়েছেন!",
            'channels_checked': "✅ চ্যানেল চেক করা হয়েছে!"
        },
        'channels': {
            'main': "📢 প্রধান চ্যানেল",
            'instagram': "📸 Instagram সংবাদ",
            'binance': "💰 Binance সংবাদ",
            'stats': "📊 লাইভ পরিসংখ্যান",
            'mandatory': "বাধ্যতামূলক চ্যানেল",
            'description': "বট ব্যবহার করতে, আপনাকে নিচের সব চ্যানেলে যোগ দিতে হবে:"
        }
    }
}

# Döviz kuru servisi
class CurrencyConverter:
    def __init__(self):
        self.c = CurrencyRates()
        self.cache = {}
        self.cache_time = {}
        self.cache_duration = 3600  # 1 saat
    
    def get_exchange_rate(self, from_currency, to_currency='USD'):
        """Döviz kuru al"""
        cache_key = f"{from_currency}_{to_currency}"
        now = time.time()
        
        if cache_key in self.cache and now - self.cache_time.get(cache_key, 0) < self.cache_duration:
            return self.cache[cache_key]
        
        try:
            # Sabit oranlar (geliştirme için)
            fixed_rates = {
                'TRY_USD': 0.033,  # 1 TRY = 0.033 USD
                'RUB_USD': 0.011,  # 1 RUB = 0.011 USD
                'BDT_USD': 0.0092, # 1 BDT = 0.0092 USD
                'USD_USD': 1.0
            }
            
            if cache_key in fixed_rates:
                rate = fixed_rates[cache_key]
            else:
                rate = self.c.get_rate(from_currency, to_currency)
            
            self.cache[cache_key] = rate
            self.cache_time[cache_key] = now
            return rate
            
        except Exception as e:
            print(f"❌ Döviz kuru hatası: {e}")
            # Varsayılan oranlar
            default_rates = {
                'TRY': 0.033,
                'RUB': 0.011,
                'BDT': 0.0092,
                'USD': 1.0
            }
            return default_rates.get(from_currency, 1.0)
    
    def convert_to_usd(self, amount, from_currency):
        """Belirtilen para biriminden USD'ye çevir"""
        if from_currency == 'USD':
            return amount
        
        rate = self.get_exchange_rate(from_currency, 'USD')
        return amount * rate
    
    def convert_from_usd(self, amount, to_currency):
        """USD'den belirtilen para birimine çevir"""
        if to_currency == 'USD':
            return amount
        
        rate = self.get_exchange_rate('USD', to_currency)
        return amount / rate if rate > 0 else amount
    
    def format_currency(self, amount, currency_code):
        """Para birimini formatla"""
        symbols = {
            'USD': '$',
            'TRY': '₺',
            'RUB': '₽',
            'BDT': '৳'
        }
        
        symbol = symbols.get(currency_code, currency_code)
        
        if currency_code == 'BDT':
            return f"{symbol}{amount:,.2f}"
        elif currency_code == 'RUB':
            return f"{symbol}{amount:,.2f}"
        elif currency_code == 'TRY':
            return f"{symbol}{amount:,.2f}"
        else:
            return f"{symbol}{amount:,.2f}"

# İstatistik Bildirim Sistemi
class StatsNotifier:
    def __init__(self, db):
        self.db = db
        self.last_stats_message_id = None
        self.running = False
        self.converter = CurrencyConverter()
    
    def start(self):
        self.running = True
        threading.Thread(target=self.run, daemon=True).start()
        print(f"📊 İstatistik bildirim sistemi başlatıldı: @{STATS_CHANNEL}")
    
    def run(self):
        time.sleep(10)
        
        while self.running:
            try:
                self.update_stats_channel()
                time.sleep(300)
            except Exception as e:
                print(f"❌ İstatistik güncelleme hatası: {e}")
                time.sleep(60)
    
    def update_stats_channel(self):
        """İstatistik kanalını güncelle"""
        try:
            stats_message = self.generate_stats_message()
            
            if self.last_stats_message_id:
                try:
                    response = edit_message_text(f"@{STATS_CHANNEL}", self.last_stats_message_id, stats_message)
                    if not response or not response.get('ok'):
                        self.send_new_stats_message(stats_message)
                except:
                    self.send_new_stats_message(stats_message)
            else:
                self.send_new_stats_message(stats_message)
                
        except Exception as e:
            print(f"❌ İstatistik kanalı güncelleme hatası: {e}")
    
    def send_new_stats_message(self, message):
        """Yeni istatistik mesajı gönder"""
        response = send_message(f"@{STATS_CHANNEL}", message)
        if response and response.get('ok'):
            self.last_stats_message_id = response['result']['message_id']
    
    def generate_stats_message(self):
        """İstatistik mesajı oluştur"""
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
        
        # Toplam bakiye (USD)
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
        today_withdrawals = 0
        today_withdraw_amount = 0
        
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
        
        message = f"""
<b>📊 TASKİZBOT STATISTICS</b>
<b>⏰ Last Update:</b> {now.strftime('%d.%m.%Y %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👥 USER STATISTICS</b>
├ <b>Total Users:</b> {total_users}
├ <b>Active Users (24h):</b> {active_users}
├ <b>Advertisers:</b> {total_advertisers}

<b>💰 FINANCIAL STATISTICS</b>
├ <b>Total Balance:</b> {total_balance:.2f}$
├ <b>Advertiser Balance:</b> {total_ad_balance:.2f}$
├ <b>Total Deposit:</b> {total_deposit_amount:.2f}$

<b>📈 TODAY'S STATISTICS ({now.strftime('%d.%m.%Y')})</b>
├ <b>Deposits:</b> {today_deposits} pcs, {today_deposit_amount:.2f}$
├ <b>Tasks:</b> {today_tasks} pcs, {today_tasks_spent:.2f}$
└ <b>Earnings:</b> {today_earnings:.2f}$
"""
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>💡 REFERRAL SYSTEM ACTIVE!</b>
<b>🎁 Referral Bonus:</b> {REF_WELCOME_BONUS}$
<b>📈 Task Commission:</b> %{REF_TASK_COMMISSION*100}
<b>🤖 Bot:</b> @TaskizBot
<b>📢 Required Channels:</b>
• @EarnTether2026 (Main)
• @instagramNewsBrazil
• @BinanceBrazilNews
<b>📊 Statistics:</b> @{STATS_CHANNEL}
"""
        
        return message

# Database
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot.db', check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.converter = CurrencyConverter()
        self.init_db()
    
    def init_db(self):
        # Kullanıcılar (kanal durumları için yeni alanlar)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                username TEXT,
                balance REAL DEFAULT 0.0,
                ads_balance REAL DEFAULT 2.5,
                total_earned REAL DEFAULT 0.0,
                tasks_completed INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                ref_earned REAL DEFAULT 0.0,
                daily_streak INTEGER DEFAULT 0,
                last_daily TEXT,
                in_main_channel INTEGER DEFAULT 0,
                in_instagram_channel INTEGER DEFAULT 0,
                in_binance_channel INTEGER DEFAULT 0,
                in_stats_channel INTEGER DEFAULT 0,
                created_at TEXT,
                welcome_bonus INTEGER DEFAULT 0,
                total_deposited REAL DEFAULT 0.0,
                deposit_count INTEGER DEFAULT 0,
                total_bonus REAL DEFAULT 0.0,
                language TEXT DEFAULT 'tr',
                currency TEXT DEFAULT 'USD',
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
                is_advertiser INTEGER DEFAULT 1,
                advertiser_balance REAL DEFAULT 2.5,
                total_spent_on_ads REAL DEFAULT 0.0,
                active_group_id TEXT,
                active_channel_id TEXT,
                last_join_check TEXT,
                task_credits_channel INTEGER DEFAULT 0,
                task_credits_group INTEGER DEFAULT 0,
                task_credits_bot INTEGER DEFAULT 0,
                ref_messages_enabled INTEGER DEFAULT 1,
                pending_ref_commission REAL DEFAULT 0.0,
                total_ref_commission REAL DEFAULT 0.0
            )
        ''')
        
        # Diğer tablolar
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                advertiser_id TEXT,
                task_type TEXT,
                task_subtype TEXT,
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
                is_paid INTEGER DEFAULT 0,
                payment_ratio TEXT DEFAULT '3/1'
            )
        ''')
        
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
                commission_paid REAL DEFAULT 0.0,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
            )
        ''')
        
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
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS commission_logs (
                commission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id TEXT,
                referred_id TEXT,
                task_id TEXT,
                amount REAL DEFAULT 0.0,
                commission_rate REAL DEFAULT 0.25,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                completed_at TEXT,
                FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                FOREIGN KEY (referred_id) REFERENCES users (user_id),
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                withdrawal_id TEXT PRIMARY KEY,
                user_id TEXT,
                amount REAL,
                trx_address TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                completed_at TEXT,
                admin_notes TEXT
            )
        ''')
        
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
        
        self.conn.commit()
        print("✅ Veritabanı hazır")
    
    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = self.cursor.fetchone()
        
        if not user:
            now = get_turkey_time().isoformat()
            referral_code = f"ref_{user_id[-8:]}"
            self.cursor.execute('''
                INSERT INTO users (user_id, name, balance, ads_balance, advertiser_balance, 
                                 created_at, language, currency, last_active, referral_code, 
                                 last_notification_time, is_advertiser)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, '', 0.0, 2.5, 2.5, now, DEFAULT_LANGUAGE, 'USD', now, referral_code, now, 1))
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
    
    def check_all_channels(self, user_id):
        """Kullanıcının tüm kanallarda olup olmadığını kontrol et"""
        user = self.get_user(user_id)
        
        # Tüm kanalların durumunu kontrol et
        channels_status = {
            'main': bool(user.get('in_main_channel', 0)),
            'instagram': bool(user.get('in_instagram_channel', 0)),
            'binance': bool(user.get('in_binance_channel', 0)),
            'stats': bool(user.get('in_stats_channel', 0))
        }
        
        # Tüm kanallarda mı?
        all_joined = all(channels_status.values())
        
        return all_joined, channels_status
    
    def update_channel_status(self, user_id, channel_type, status):
        """Kanal durumunu güncelle"""
        channel_field = f"in_{channel_type}_channel"
        self.update_user(user_id, {channel_field: 1 if status else 0})
    
    def get_user_balance_display(self, user_id):
        """Kullanıcının bakiyesini seçili para biriminde göster"""
        user = self.get_user(user_id)
        balance_usd = user.get('balance', 0)
        currency = user.get('currency', 'USD')
        
        if currency == 'USD':
            return balance_usd, currency
        
        converted_amount = self.converter.convert_from_usd(balance_usd, currency)
        return converted_amount, currency
    
    def get_advertiser_balance_display(self, user_id):
        """Reklamveren bakiyesini seçili para biriminde göster"""
        user = self.get_user(user_id)
        balance_usd = user.get('advertiser_balance', 0)
        currency = user.get('currency', 'USD')
        
        if currency == 'USD':
            return balance_usd, currency
        
        converted_amount = self.converter.convert_from_usd(balance_usd, currency)
        return converted_amount, currency
    
    def convert_to_user_currency(self, amount_usd, user_id):
        """USD'yi kullanıcının para birimine çevir"""
        user = self.get_user(user_id)
        currency = user.get('currency', 'USD')
        
        if currency == 'USD':
            return amount_usd
        
        return self.converter.convert_from_usd(amount_usd, currency)
    
    def convert_from_user_currency(self, amount, user_id):
        """Kullanıcının para biriminden USD'ye çevir"""
        user = self.get_user(user_id)
        currency = user.get('currency', 'USD')
        
        if currency == 'USD':
            return amount
        
        return self.converter.convert_to_usd(amount, currency)

# Bot Sistemi
class BotSystem:
    def __init__(self):
        self.db = Database()
        self.stats_notifier = StatsNotifier(self.db)
        self.user_states = {}
        self.trx_price = 0.12
        self.converter = CurrencyConverter()
        self.update_trx_price()
        self.background_checker = BackgroundChecker(self.db)
        self.background_checker.start()
        self.stats_notifier.start()
        print("🤖 TaskizBot sistemi başlatıldı")
    
    def update_trx_price(self):
        try:
            response = requests.get(TRX_PRICE_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.trx_price = data.get('tron', {}).get('usd', 0.12)
        except: 
            pass
    
    def get_text(self, user_id, key_path, default=None, **kwargs):
        """Kullanıcının diline göre metin al"""
        user = self.db.get_user(user_id)
        language = user.get('language', DEFAULT_LANGUAGE)
        
        parts = key_path.split('.')
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS[DEFAULT_LANGUAGE])
        
        for part in parts:
            texts = texts.get(part, {})
            if not isinstance(texts, dict):
                break
        
        if isinstance(texts, dict) and default:
            result = default
        else:
            result = texts if texts else default
        
        if isinstance(result, str) and kwargs:
            try:
                result = result.format(**kwargs)
            except:
                pass
        
        return result or key_path
    
    def check_all_channels_membership(self, user_id):
        """Kullanıcının tüm kanallarda olup olmadığını kontrol et"""
        all_joined, channels_status = self.db.check_all_channels(user_id)
        
        # Eğer veritabanında tüm kanallar katılım gösteriyorsa kontrol etmeden dön
        if all_joined:
            return True, channels_status
        
        # Gerçek zamanlı kontrol
        user_id_int = int(user_id)
        channels_to_check = [
            ('main', MANDATORY_CHANNELS['main']['username']),
            ('instagram', MANDATORY_CHANNELS['instagram']['username']),
            ('binance', MANDATORY_CHANNELS['binance']['username']),
            ('stats', MANDATORY_CHANNELS['stats']['username'])
        ]
        
        updated_status = {}
        all_joined_now = True
        
        for channel_type, channel_username in channels_to_check:
            is_member = get_chat_member(f"@{channel_username}", user_id_int)
            updated_status[channel_type] = is_member
            
            # Veritabanını güncelle
            self.db.update_channel_status(user_id, channel_type, is_member)
            
            if not is_member:
                all_joined_now = False
        
        return all_joined_now, updated_status
    
    def show_channel_check(self, user_id):
        """Kanal kontrol ekranını göster"""
        all_joined, channels_status = self.check_all_channels_membership(user_id)
        
        if all_joined:
            # Tüm kanallara katılmış, ana menüye yönlendir
            self.show_main_menu(user_id)
            return
        
        user = self.db.get_user(user_id)
        language = user.get('language', DEFAULT_LANGUAGE)
        
        # Kanal durumlarını göster
        message = f"""
<b>{self.get_text(user_id, 'channels.mandatory')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

{self.get_text(user_id, 'channels.description')}
"""
        
        # Her kanal için durum
        channel_list = [
            ('main', self.get_text(user_id, 'channels.main')),
            ('instagram', self.get_text(user_id, 'channels.instagram')),
            ('binance', self.get_text(user_id, 'channels.binance')),
            ('stats', self.get_text(user_id, 'channels.stats'))
        ]
        
        for channel_type, channel_name in channel_list:
            status = "✅" if channels_status.get(channel_type) else "❌"
            message += f"\n{status} <b>{channel_name}</b>"
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>⚠️ {self.get_text(user_id, 'errors.not_in_channel')}</b>

<b>💡 {self.get_text(user_id, 'success.all_channels_joined').replace('katıldınız', 'katılın')}:</b>
1. {self.get_text(user_id, 'buttons.join_all_channels')} butonuna tıklayın
2. Her kanala teker teker katılın
3. {self.get_text(user_id, 'buttons.check_channels')} butonu ile kontrol edin
"""
        
        # Butonlar
        buttons = []
        
        # Her kanal için katıl butonu
        for channel_type in ['main', 'instagram', 'binance', 'stats']:
            channel_info = MANDATORY_CHANNELS[channel_type]
            if not channels_status.get(channel_type):
                buttons.append([
                    {'text': f"📢 {channel_info['name']}", 'url': channel_info['link']}
                ])
        
        # Kontrol ve tümüne katıl butonları
        buttons.append([
            {'text': self.get_text(user_id, 'buttons.check_channels'), 'callback_data': 'check_channels'},
            {'text': self.get_text(user_id, 'buttons.join_all_channels'), 'callback_data': 'join_all_channels'}
        ])
        
        markup = {'inline_keyboard': buttons}
        send_message(user_id, message, markup)
    
    def show_main_menu(self, user_id):
        # Önce tüm kanal kontrollerini yap
        all_joined, _ = self.check_all_channels_membership(user_id)
        
        if not all_joined:
            self.show_channel_check(user_id)
            return
        
        user = self.db.get_user(user_id)
        
        # Bakiyeleri kullanıcının para biriminde göster
        balance_display, currency = self.db.get_user_balance_display(user_id)
        advertiser_balance_display, _ = self.db.get_advertiser_balance_display(user_id)
        
        # Referans durumu
        ref_text = f"\n<b>{self.get_text(user_id, 'menu.ref_earned')}:</b> {user.get('ref_earned', 0):.3f}$" if user.get('is_referred', 0) else ""
        
        message = f"""
<b>{self.get_text(user_id, 'menu.welcome')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👤 {self.get_text(user_id, 'menu.welcome').split(' ')[-1]}</b> {user.get('name', 'Kullanıcı')}!
<b>{self.get_text(user_id, 'menu.balance')}:</b> <code>{self.converter.format_currency(balance_display, currency)}</code>

<b>{self.get_text(user_id, 'menu.advertiser_balance')}:</b> <code>{self.converter.format_currency(advertiser_balance_display, currency)}</code>

<b>{self.get_text(user_id, 'menu.tasks_completed')}:</b> {user.get('tasks_completed', 0)}
<b>{self.get_text(user_id, 'menu.referrals')}:</b> {user.get('referrals', 0)}{ref_text}

📢 <b>{self.get_text(user_id, 'menu.channels')}:</b> ✅ Tamam
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}
🌐 <b>Dil:</b> {SUPPORTED_LANGUAGES[user.get('language', DEFAULT_LANGUAGE)]['flag']} {SUPPORTED_LANGUAGES[user.get('language', DEFAULT_LANGUAGE)]['name']}

━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>{self.get_text(user_id, 'menu.main_menu')}</b>
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': self.get_text(user_id, 'buttons.do_task'), 'callback_data': 'tasks'},
                    {'text': self.get_text(user_id, 'buttons.load_balance'), 'callback_data': 'deposit'}
                ],
                [
                    {'text': self.get_text(user_id, 'buttons.withdraw'), 'callback_data': 'withdraw'},
                    {'text': self.get_text(user_id, 'buttons.stats'), 'callback_data': 'stats'}
                ],
                [
                    {'text': self.get_text(user_id, 'buttons.profile'), 'callback_data': 'profile'},
                    {'text': self.get_text(user_id, 'buttons.referral'), 'callback_data': 'referral'}
                ],
                [
                    {'text': '🌐 ' + self.get_text(user_id, 'buttons.language'), 'callback_data': 'change_language'},
                    {'text': '💰 ' + self.get_text(user_id, 'menu.balance') + ' Seç', 'callback_data': 'change_currency'}
                ],
                [
                    {'text': '📢 ' + self.get_text(user_id, 'buttons.check_channels'), 'callback_data': 'check_channels'}
                ]
            ]
        }
        
        # Reklamveren butonu
        if user.get('is_advertiser', 0):
            markup['inline_keyboard'].insert(3, [
                {'text': self.get_text(user_id, 'buttons.advertiser'), 'callback_data': 'advertiser_menu'}
            ])
        else:
            markup['inline_keyboard'].insert(3, [
                {'text': self.get_text(user_id, 'buttons.become_advertiser'), 'callback_data': 'toggle_advertiser'}
            ])
        
        # Yardım ve admin butonları
        markup['inline_keyboard'].append([
            {'text': '❓ ' + self.get_text(user_id, 'menu.help'), 'callback_data': 'help'},
            {'text': '📋 ' + self.get_text(user_id, 'menu.main_menu'), 'callback_data': 'menu'}
        ])
        
        if user_id == ADMIN_ID:
            markup['inline_keyboard'].append([
                {'text': self.get_text(user_id, 'buttons.admin_panel'), 'callback_data': 'admin_panel'}
            ])
        
        send_message(user_id, message, markup)
    
    def show_language_menu(self, user_id):
        """Dil seçim menüsünü göster"""
        user = self.db.get_user(user_id)
        current_language = user.get('language', DEFAULT_LANGUAGE)
        
        message = f"""
<b>🌐 DİL SEÇİMİ / LANGUAGE SELECTION</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Mevcut Dil / Current Language:</b>
{SUPPORTED_LANGUAGES[current_language]['flag']} {SUPPORTED_LANGUAGES[current_language]['name']}

<b>Lütfen bir dil seçin / Please select a language:</b>
"""
        
        buttons = []
        for lang_code, lang_info in SUPPORTED_LANGUAGES.items():
            is_current = " ✅" if lang_code == current_language else ""
            buttons.append([
                {'text': f"{lang_info['flag']} {lang_info['name']}{is_current}", 
                 'callback_data': f'select_language_{lang_code}'}
            ])
        
        buttons.append([
            {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
        ])
        
        markup = {'inline_keyboard': buttons}
        send_message(user_id, message, markup)
    
    def show_currency_menu(self, user_id):
        """Para birimi seçim menüsünü göster"""
        user = self.db.get_user(user_id)
        current_currency = user.get('currency', 'USD')
        
        message = f"""
<b>💰 PARA BİRİMİ SEÇİMİ / CURRENCY SELECTION</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Mevcut Para Birimi / Current Currency:</b>
{current_currency} ({self.converter.format_currency(1, current_currency)})

<b>Lütfen bir para birimi seçin / Please select a currency:</b>

💡 <b>Not:</b> Tüm işlemler USD bazında yapılır. Seçtiğiniz para birimi sadece görüntüleme içindir.
"""
        
        currencies = [
            ('USD', '$ Dolar (USD)'),
            ('TRY', '₺ Türk Lirası (TRY)'),
            ('RUB', '₽ Rus Rublesi (RUB)'),
            ('BDT', '৳ Bangladeş Takası (BDT)')
        ]
        
        buttons = []
        for currency_code, currency_name in currencies:
            is_current = " ✅" if currency_code == current_currency else ""
            buttons.append([
                {'text': f"{currency_name}{is_current}", 
                 'callback_data': f'select_currency_{currency_code}'}
            ])
        
        buttons.append([
            {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
        ])
        
        markup = {'inline_keyboard': buttons}
        send_message(user_id, message, markup)
    
    def change_language(self, user_id, language_code):
        """Kullanıcının dilini değiştir"""
        if language_code in SUPPORTED_LANGUAGES:
            self.db.update_user(user_id, {'language': language_code})
            
            lang_name = SUPPORTED_LANGUAGES[language_code]['name']
            message = f"""
✅ <b>Dil değiştirildi / Language changed!</b>

🌐 <b>Yeni Dil / New Language:</b>
{SUPPORTED_LANGUAGES[language_code]['flag']} {lang_name}

💡 <b>Artık bot {lang_name} dilinde görüntülenecek.</b>
"""
            send_message(user_id, message)
            time.sleep(1)
            self.show_main_menu(user_id)
    
    def change_currency(self, user_id, currency_code):
        """Kullanıcının para birimini değiştir"""
        valid_currencies = ['USD', 'TRY', 'RUB', 'BDT']
        
        if currency_code in valid_currencies:
            self.db.update_user(user_id, {'currency': currency_code})
            
            currency_symbols = {
                'USD': '$',
                'TRY': '₺',
                'RUB': '₽',
                'BDT': '৳'
            }
            
            message = f"""
✅ <b>Para birimi değiştirildi / Currency changed!</b>

💰 <b>Yeni Para Birimi / New Currency:</b>
{currency_code} ({currency_symbols.get(currency_code, currency_code)})

💡 <b>Not:</b> Tüm işlemler USD bazında yapılır. Seçtiğiniz para birimi sadece görüntüleme içindir.
"""
            send_message(user_id, message)
            time.sleep(1)
            self.show_main_menu(user_id)
    
    def process_callback(self, callback):
        try:
            user_id = str(callback['from']['id'])
            data = callback['data']
            callback_id = callback['id']
            
            answer_callback(callback_id, "⏳ İşleniyor...")
            
            # Kanal kontrol işlemleri
            if data == 'check_channels':
                self.show_channel_check(user_id)
            elif data == 'join_all_channels':
                self.show_join_all_channels(user_id)
            
            # Dil ve para birimi işlemleri
            elif data == 'change_language':
                self.show_language_menu(user_id)
            elif data == 'change_currency':
                self.show_currency_menu(user_id)
            elif data.startswith('select_language_'):
                language_code = data.replace('select_language_', '')
                self.change_language(user_id, language_code)
            elif data.startswith('select_currency_'):
                currency_code = data.replace('select_currency_', '')
                self.change_currency(user_id, currency_code)
            
            # Diğer callback işlemleri
            elif data == 'menu':
                self.show_main_menu(user_id)
            elif data == 'back':
                self.show_main_menu(user_id)
            elif data == 'cancel':
                self.clear_user_state(user_id)
                self.show_main_menu(user_id)
            
            # Ana menü butonları
            elif data == 'tasks':
                self.show_available_tasks(user_id)
            elif data == 'deposit':
                self.show_deposit_menu(user_id)
            elif data == 'withdraw':
                self.show_withdraw_menu(user_id)
            elif data == 'stats':
                self.show_user_stats(user_id)
            elif data == 'profile':
                self.show_profile(user_id)
            elif data == 'referral':
                self.show_referral_menu(user_id)
            elif data == 'help':
                self.show_help(user_id)
            
            # Reklamveren butonları
            elif data == 'advertiser_menu':
                self.show_advertiser_menu(user_id)
            elif data == 'advertiser_deposit':
                self.show_advertiser_deposit_menu(user_id)
            elif data == 'toggle_advertiser':
                self.toggle_advertiser_mode(user_id)
            
            # Admin butonları
            elif data == 'admin_panel':
                self.show_admin_panel(user_id)
            
        except Exception as e:
            print(f"❌ Callback hatası: {e}")
            send_message(user_id, "❌ Bir hata oluştu!")
    
    def show_join_all_channels(self, user_id):
        """Tüm kanallara katılma ekranı"""
        message = f"""
<b>📢 {self.get_text(user_id, 'buttons.join_all_channels')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

{self.get_text(user_id, 'channels.description')}
"""
        
        buttons = []
        
        # Her kanal için buton
        for channel_type, channel_info in MANDATORY_CHANNELS.items():
            channel_name = self.get_text(user_id, f'channels.{channel_type}')
            buttons.append([
                {'text': f"📢 {channel_name}", 'url': channel_info['link']}
            ])
        
        # Kontrol butonu
        buttons.append([
            {'text': self.get_text(user_id, 'buttons.check_channels'), 'callback_data': 'check_channels'},
            {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
        ])
        
        markup = {'inline_keyboard': buttons}
        send_message(user_id, message, markup)
    
    def handle_start(self, user_id, text):
        """Başlangıç komutu"""
        # Önce kanal kontrollerini yap
        self.show_channel_check(user_id)
        
        # Referans kodu kontrolü (mevcut koddan)
        if ' ' in text:
            parts = text.split()
            if len(parts) > 1 and parts[1].startswith('ref_'):
                ref_code = parts[1]
                referrer_id = parts[1].replace('ref_', '')
                
                if referrer_id and referrer_id != user_id:
                    user = self.db.get_user(user_id)
                    if not user.get('ref_link_used'):
                        referrer = self.db.get_user(referrer_id)
                        if referrer:
                            # Referans işlemleri (mevcut kod)
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
    
    def process_message(self, message):
        try:
            if 'from' not in message: 
                return
            
            user_id = str(message['from']['id'])
            
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
                elif text == '/kanallar':
                    self.show_channel_check(user_id)
                    return
            
            user_state = self.get_user_state(user_id)
            
            user = self.db.get_user(user_id)
            if not user.get('name'):
                self.db.update_user(user_id, {
                    'name': message['from'].get('first_name', 'Kullanıcı'),
                    'username': message['from'].get('username', '')
                })
            
            if user_state['state']:
                self.handle_user_state(user_id, message, user_state)
                return
        
        except Exception as e:
            print(f"❌ Mesaj hatası: {e}")
    
    def process_chat_member_update(self, chat_member_update):
        """Kullanıcı grup/kanal üyelik değişikliklerini işle"""
        try:
            if 'old_chat_member' in chat_member_update and 'new_chat_member' in chat_member_update:
                user_id = str(chat_member_update['new_chat_member']['user']['id'])
                chat_id = str(chat_member_update['chat']['id'])
                
                old_status = chat_member_update['old_chat_member']['status']
                new_status = chat_member_update['new_chat_member']['status']
                
                # Zorunlu kanallardan ayrılma kontrolü
                for channel_type, channel_info in MANDATORY_CHANNELS.items():
                    if f"@{channel_info['username']}" in chat_id or channel_info['username'] in chat_id:
                        if old_status in ['member', 'administrator', 'creator'] and new_status == 'left':
                            print(f"⚠️ Kullanıcı {user_id} zorunlu kanaldan ayrıldı: {channel_info['username']}")
                            self.db.update_channel_status(user_id, channel_type, False)
                            
                            # Kullanıcıya bildirim
                            channel_name = channel_info['name']
                            send_message(user_id, f"""
<b>⚠️ ZORUNLU KANALDAN AYRILDINIZ!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ <b>{channel_name} kanalından ayrıldınız!</b>

📊 <b>Sonuçlar:</b>
• Botu kullanamazsınız
• Görev yapamazsınız
• Mevcut görevleriniz iptal edilebilir

💡 <b>Tekrar katılmak için:</b>
1. @{channel_info['username']} kanalına katılın
2. /menu yazarak botu yeniden başlatın
""")
                        elif old_status == 'left' and new_status in ['member', 'administrator', 'creator']:
                            print(f"✅ Kullanıcı {user_id} zorunlu kanala katıldı: {channel_info['username']}")
                            self.db.update_channel_status(user_id, channel_type, True)
        
        except Exception as e:
            print(f"❌ Chat member update hatası: {e}")
    
    # Diğer metodlar (show_deposit_menu, show_withdraw_menu, vb.) mevcut koddan aynen gelecek
    # Burada sadece yeni eklenen kısımları gösterdim
    
    def show_deposit_menu(self, user_id):
        """Normal kullanıcı depozit menüsü (para birimine göre)"""
        self.update_trx_price()
        user = self.db.get_user(user_id)
        currency = user.get('currency', 'USD')
        
        min_deposit_display = self.db.convert_from_user_currency(MIN_DEPOSIT_USD, user_id)
        max_deposit_display = self.db.convert_from_user_currency(MAX_DEPOSIT_USD, user_id)
        
        message = f"""
<b>💰 {self.get_text(user_id, 'buttons.load_balance')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>₿ TRX {self.get_text(user_id, 'menu.balance').split(':')[0] if ':' in self.get_text(user_id, 'menu.balance') else 'Fiyatı'}:</b> {self.trx_price:.3f}$
<b>💰 {self.get_text(user_id, 'errors.min_withdraw', amount=MIN_DEPOSIT_USD).replace('çekim', 'yatırım')}:</b> {self.converter.format_currency(min_deposit_display, currency)}
<b>💰 {self.get_text(user_id, 'menu.balance').split(':')[0] if ':' in self.get_text(user_id, 'menu.balance') else 'Maksimum'}:</b> {self.converter.format_currency(max_deposit_display, currency)}

💬 <b>{self.get_text(user_id, 'menu.chat')}:</b> @{MANDATORY_CHANNELS['main']['username']}
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

<b>👇 {self.get_text(user_id, 'buttons.load_balance')}:</b>
"""
        
        amounts_usd = [2.5, 5, 7.5, 10]
        buttons = []
        
        for i in range(0, len(amounts_usd), 2):
            row = []
            for amount_usd in amounts_usd[i:i+2]:
                amount_display = self.db.convert_from_user_currency(amount_usd, user_id)
                row.append({
                    'text': f"{self.converter.format_currency(amount_display, currency)}",
                    'callback_data': f'deposit_amount_{amount_usd}_user'
                })
            buttons.append(row)
        
        buttons.append([
            {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
        ])
        
        markup = {'inline_keyboard': buttons}
        send_message(user_id, message, markup)
    
    def show_withdraw_menu(self, user_id):
        user = self.db.get_user(user_id)
        currency = user.get('currency', 'USD')
        
        balance_display, _ = self.db.get_user_balance_display(user_id)
        min_withdraw_display = self.db.convert_from_user_currency(MIN_WITHDRAW, user_id)
        
        message = f"""
<b>🏧 {self.get_text(user_id, 'buttons.withdraw')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 {self.get_text(user_id, 'menu.balance')}:</b> {self.converter.format_currency(balance_display, currency)}

<b>📋 {self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Şartlar')}:</b>
• {self.get_text(user_id, 'errors.min_withdraw', amount=self.converter.format_currency(min_withdraw_display, currency))}
• {self.get_text(user_id, 'success.withdraw_requested').replace('alındı', 'süresi')}: 24 {self.get_text(user_id, 'menu.stats').lower()}
• {self.get_text(user_id, 'menu.balance').split(':')[0] if ':' in self.get_text(user_id, 'menu.balance') else 'Komisyon'}: {self.get_text(user_id, 'errors.not_found').replace('Bulunamadı', 'Yok')}

<b>⚠️ {self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'ÖNEMLİ')}:</b>
• {self.get_text(user_id, 'errors.invalid_address').replace('adres', 'TRX (Tron) cüzdan adresi')}!
• {self.get_text(user_id, 'errors.unauthorized').replace('Yetkiniz', 'Yanlış cüzdan')} {self.get_text(user_id, 'errors.not_found').replace('Bulunamadı', 'kaybolur')}!

💬 <b>{self.get_text(user_id, 'menu.chat')}:</b> @{MANDATORY_CHANNELS['main']['username']}
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}
"""
        
        if user.get('balance', 0) >= MIN_WITHDRAW:
            markup = {
                'inline_keyboard': [
                    [
                        {'text': '💸 ' + self.get_text(user_id, 'buttons.withdraw'), 'callback_data': 'start_withdraw'},
                        {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                    ]
                ]
            }
        else:
            markup = {
                'inline_keyboard': [
                    [
                        {'text': '💰 ' + self.get_text(user_id, 'buttons.load_balance'), 'callback_data': 'deposit'},
                        {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                    ]
                ]
            }
        
        send_message(user_id, message, markup)
    
    def show_available_tasks(self, user_id):
        """Kullanıcılar için mevcut görevleri göster"""
        # Tüm kanal kontrollerini yap
        all_joined, _ = self.check_all_channels_membership(user_id)
        
        if not all_joined:
            self.show_channel_check(user_id)
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
<b>🎯 {self.get_text(user_id, 'buttons.do_task')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📭 <b>{self.get_text(user_id, 'errors.not_found').replace('Bulunamadı', 'Şu anda aktif görev bulunmuyor')}</b>

💬 <b>{self.get_text(user_id, 'menu.chat')}:</b> @{MANDATORY_CHANNELS['main']['username']}
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

💡 <b>Yeni görevler eklendiğinde bildirim alacaksınız!</b>
"""
            markup = {
                'inline_keyboard': [[
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                ]]
            }
        else:
            message = f"""
<b>🎯 {self.get_text(user_id, 'buttons.do_task')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 <b>{self.get_text(user_id, 'menu.chat')}:</b> @{MANDATORY_CHANNELS['main']['username']}
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            for task in tasks:
                if task['task_type'] == 'channel':
                    task_type = "📢 Kanal"
                elif task['task_type'] == 'group':
                    task_type = "👥 Grup"
                else:
                    task_type = "🤖 Bot"
                
                reward = task['reward_amount']
                
                self.db.cursor.execute('''
                    SELECT * FROM task_participations 
                    WHERE task_id = ? AND user_id = ?
                ''', (task['task_id'], user_id))
                participation = self.db.cursor.fetchone()
                
                status = "✅ Katıldınız" if participation else "🟢 Katıl"
                
                message += f"""{task_type} <b>{task.get('target_name', 'Bot Görevi')[:20]}</b>
├ <b>Ödül:</b> {reward:.3f}$
├ <b>Katılımcı:</b> {task['current_participants']}/{task['max_participants']}
└ <b>Durum:</b> {status}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
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
                                {'text': f'🎯 {self.get_text(user_id, "success.task_joined").replace("katıldınız", "Katıl")} ({first_task["reward_amount"]:.3f}$)', 
                                 'callback_data': f'join_task_{first_task["task_id"]}'}
                            ],
                            [
                                {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                            ]
                        ]
                    }
                else:
                    markup = {
                        'inline_keyboard': [[
                            {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                        ]]
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
<b>👑 {self.get_text(user_id, 'buttons.become_advertiser').upper()}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ <b>{self.get_text(user_id, 'buttons.become_advertiser').replace('Ol', 'moduna geçtiniz')}!</b>

📊 <b>{self.get_text(user_id, 'success.task_created').replace('Görev', 'Artık şunları')}:</b>
• 📢 {self.get_text(user_id, 'buttons.advertiser').replace('Reklamveren', 'Görev oluşturabilirsiniz')}
• 💰 {self.get_text(user_id, 'buttons.load_balance').replace('Yükle', 'Reklamveren bakiyesi yükleyebilirsiniz')}
• 📈 {self.get_text(user_id, 'menu.stats').replace('İstatistik', 'Reklamlarınızı takip edebilirsiniz')}

💬 <b>{self.get_text(user_id, 'menu.chat')}:</b> @{MANDATORY_CHANNELS['main']['username']}
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

💡 <b>"{self.get_text(user_id, 'buttons.advertiser')}" {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'butonuna tıklayarak işlemlerinize başlayın')}!</b>
"""
            markup = {
                'inline_keyboard': [[
                    {'text': self.get_text(user_id, 'buttons.advertiser_menu'), 'callback_data': 'advertiser_menu'},
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                ]]
            }
        else:
            message = f"""
<b>👑 {self.get_text(user_id, 'buttons.become_advertiser').upper().replace('OL', 'MODU KAPALI')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

ℹ️ <b>{self.get_text(user_id, 'buttons.become_advertiser').replace('Ol', 'modunu kapattınız')}!</b>

📊 <b>{self.get_text(user_id, 'success.task_created').replace('Görev', 'Artık normal kullanıcı modundasınız')}:</b>
• 🎯 {self.get_text(user_id, 'buttons.do_task')}
• 💰 {self.get_text(user_id, 'buttons.load_balance').replace('Yükle', 'Normal bakiye yükleyebilirsiniz')}
• 💸 {self.get_text(user_id, 'buttons.withdraw').replace('Para Çek', 'Kazançlarınızı çekebilirsiniz')}

💬 <b>{self.get_text(user_id, 'menu.chat')}:</b> @{MANDATORY_CHANNELS['main']['username']}
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

💡 <b>{self.get_text(user_id, 'buttons.become_advertiser')} {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'butonuna tıklayın')}!</b>
"""
            markup = {
                'inline_keyboard': [[
                    {'text': self.get_text(user_id, 'buttons.become_advertiser'), 'callback_data': 'toggle_advertiser'},
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                ]]
            }
        
        send_message(user_id, message, markup)
    
    def show_advertiser_menu(self, user_id):
        user = self.db.get_user(user_id)
        
        if not user.get('is_advertiser', 0):
            send_message(user_id, self.get_text(user_id, 'errors.unauthorized').replace('Yetkiniz', 'Reklamveren modunda değilsiniz') + "!")
            self.show_main_menu(user_id)
            return
        
        advertiser_balance_display, currency = self.db.get_advertiser_balance_display(user_id)
        
        message = f"""
<b>👑 {self.get_text(user_id, 'buttons.advertiser_menu').upper()}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 {self.get_text(user_id, 'menu.advertiser_balance')}:</b> {self.converter.format_currency(advertiser_balance_display, currency)}
<b>📈 {self.get_text(user_id, 'menu.stats').replace('İstatistik', 'Toplam Harcama')}:</b> {user.get('total_spent_on_ads', 0):.3f}$

💬 <b>{self.get_text(user_id, 'menu.chat')}:</b> @{MANDATORY_CHANNELS['main']['username']}
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>📋 {self.get_text(user_id, 'menu.main_menu').replace('ANA MENÜ', 'İŞLEMLER')}</b>
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '📢 ' + self.get_text(user_id, 'success.task_created').replace('Görev', 'Görev Oluştur'), 'callback_data': 'advertiser_create_task'},
                    {'text': '💰 ' + self.get_text(user_id, 'buttons.load_balance'), 'callback_data': 'advertiser_deposit'}
                ],
                [
                    {'text': '📊 ' + self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'Görevlerim'), 'callback_data': 'advertiser_my_tasks'},
                    {'text': '💰 ' + self.get_text(user_id, 'menu.balance'), 'callback_data': 'advertiser_balance'}
                ],
                [
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'},
                    {'text': '🚫 ' + self.get_text(user_id, 'buttons.become_advertiser').replace('Ol', 'liği Kapat'), 'callback_data': 'toggle_advertiser'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def show_advertiser_deposit_menu(self, user_id):
        self.update_trx_price()
        user = self.db.get_user(user_id)
        currency = user.get('currency', 'USD')
        
        message = f"""
<b>💰 {self.get_text(user_id, 'buttons.load_balance').replace('Bakiye', 'REKLAMVEREN BAKİYESİ')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>₿ TRX {self.get_text(user_id, 'menu.balance').split(':')[0] if ':' in self.get_text(user_id, 'menu.balance') else 'Fiyatı'}:</b> {self.trx_price:.3f}$
<b>⚠️ {self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Not')}:</b> {self.get_text(user_id, 'menu.advertiser_balance').replace('Bakiye', 'bakiyesi sadece reklam vermek için kullanılır')}
<b>💰 {self.get_text(user_id, 'menu.balance').split(':')[0] if ':' in self.get_text(user_id, 'menu.balance') else 'Maksimum Depozit'}:</b> {self.converter.format_currency(self.db.convert_from_user_currency(MAX_DEPOSIT_USD, user_id), currency)}

<b>👇 {self.get_text(user_id, 'buttons.load_balance')}:</b>
"""
        
        amounts_usd = [2.5, 5, 7.5, 10]
        buttons = []
        
        for i in range(0, len(amounts_usd), 2):
            row = []
            for amount_usd in amounts_usd[i:i+2]:
                amount_display = self.db.convert_from_user_currency(amount_usd, user_id)
                row.append({
                    'text': f"{self.converter.format_currency(amount_display, currency)}",
                    'callback_data': f'deposit_amount_{amount_usd}_advertiser'
                })
            buttons.append(row)
        
        buttons.append([
            {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'advertiser_menu'}
        ])
        
        markup = {'inline_keyboard': buttons}
        send_message(user_id, message, markup)
    
    def show_advertiser_balance(self, user_id):
        user = self.db.get_user(user_id)
        
        balance_display, currency = self.db.get_user_balance_display(user_id)
        advertiser_balance_display, _ = self.db.get_advertiser_balance_display(user_id)
        
        message = f"""
<b>💰 {self.get_text(user_id, 'menu.advertiser_balance').replace('Bakiye', 'BAKİYE DETAYLARI')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Bakiye Bilgileri')}:</b>
• {self.get_text(user_id, 'menu.advertiser_balance')}: {self.converter.format_currency(advertiser_balance_display, currency)}
• {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Normal Bakiye')}: {self.converter.format_currency(balance_display, currency)}
• {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Toplam Yatırım')}: {user.get('total_deposited', 0):.3f}$
• {self.get_text(user_id, 'menu.stats').replace('İstatistik', 'Toplam Harcama')}: {user.get('total_spent_on_ads', 0):.3f}$

<b>💡 {self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Not')}:</b>
• {self.get_text(user_id, 'menu.advertiser_balance').replace('Bakiye', 'bakiyesi sadece reklam vermek için kullanılır')}
• {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Normal bakiye kazanılan paradır ve çekilebilir')}
• {self.get_text(user_id, 'menu.advertiser_balance').replace('Bakiye', 'Reklamveren bakiyesi çekilemez, sadece reklamlarda kullanılır')}

💬 <b>{self.get_text(user_id, 'menu.chat')}:</b> @{MANDATORY_CHANNELS['main']['username']}
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '💰 ' + self.get_text(user_id, 'buttons.load_balance'), 'callback_data': 'advertiser_deposit'},
                    {'text': '📢 ' + self.get_text(user_id, 'success.task_created').replace('Görev', 'Görev Oluştur'), 'callback_data': 'advertiser_create_task'}
                ],
                [
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'advertiser_menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def show_user_stats(self, user_id):
        """Kullanıcı istatistiklerini göster"""
        user = self.db.get_user(user_id)
        
        today_start = get_turkey_time().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        self.db.cursor.execute('''
            SELECT SUM(reward_paid) 
            FROM task_participations 
            WHERE user_id = ? AND paid_at > ? AND status = 'verified'
        ''', (user_id, today_start))
        today_earnings_result = self.db.cursor.fetchone()
        today_earnings = today_earnings_result[0] or 0
        
        week_start = (get_turkey_time() - timedelta(days=7)).isoformat()
        self.db.cursor.execute('''
            SELECT SUM(reward_paid) 
            FROM task_participations 
            WHERE user_id = ? AND paid_at > ? AND status = 'verified'
        ''', (user_id, week_start))
        weekly_earnings_result = self.db.cursor.fetchone()
        weekly_earnings = weekly_earnings_result[0] or 0
        
        month_start = (get_turkey_time() - timedelta(days=30)).isoformat()
        self.db.cursor.execute('''
            SELECT SUM(reward_paid) 
            FROM task_participations 
            WHERE user_id = ? AND paid_at > ? AND status = 'verified'
        ''', (user_id, month_start))
        monthly_earnings_result = self.db.cursor.fetchone()
        monthly_earnings = monthly_earnings_result[0] or 0
        
        self.db.cursor.execute('''
            SELECT COUNT(*) 
            FROM task_participations 
            WHERE user_id = ? AND paid_at > ? AND status = 'verified'
        ''', (user_id, today_start))
        today_tasks_result = self.db.cursor.fetchone()
        today_tasks = today_tasks_result[0] or 0
        
        self.db.cursor.execute('''
            SELECT COUNT(*) as total_refs, SUM(amount) as total_ref_earned
            FROM referral_logs 
            WHERE referrer_id = ? AND status = 'completed'
        ''', (user_id,))
        ref_stats = self.db.cursor.fetchone()
        total_refs = ref_stats['total_refs'] if ref_stats else 0
        total_ref_earned = ref_stats['total_ref_earned'] if ref_stats and ref_stats['total_ref_earned'] else 0
        
        self.db.cursor.execute('''
            SELECT SUM(amount) as total_commission
            FROM commission_logs 
            WHERE referrer_id = ? AND status = 'completed'
        ''', (user_id,))
        commission_stats = self.db.cursor.fetchone()
        total_commission = commission_stats['total_commission'] if commission_stats else 0
        
        balance_display, currency = self.db.get_user_balance_display(user_id)
        advertiser_balance_display, _ = self.db.get_advertiser_balance_display(user_id)
        
        message = f"""
<b>📊 {self.get_text(user_id, 'menu.stats').upper()}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👤 {self.get_text(user_id, 'menu.profile').replace('Profil', 'Kullanıcı')}:</b> {user.get('name', 'Kullanıcı')}
<b>🆔 ID:</b> <code>{user_id}</code>

<b>💰 {self.get_text(user_id, 'success.balance_added').replace('eklendi', 'KAZANÇ İSTATİSTİKLERİ')}</b>
├ <b>{self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Bugünkü Kazanç')}:</b> {today_earnings:.3f}$
├ <b>{self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Haftalık Kazanç')}:</b> {weekly_earnings:.3f}$
├ <b>{self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Aylık Kazanç')}:</b> {monthly_earnings:.3f}$
└ <b>{self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Toplam Kazanç')}:</b> {user.get('total_earned', 0):.3f}$

<b>🎯 {self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'GÖREV İSTATİSTİKLERİ')}</b>
├ <b>{self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'Bugünkü Görev')}:</b> {today_tasks}
└ <b>{self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'Toplam Görev')}:</b> {user.get('tasks_completed', 0)}

<b>👥 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'REFERANS İSTATİSTİKLERİ')}</b>
├ <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Toplam Referans')}:</b> {total_refs}
├ <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans Bonusu')}:</b> {total_ref_earned:.3f}$
├ <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Görev Komisyonu')}:</b> {total_commission:.3f}$
└ <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Toplam Referans Kazancı')}:</b> {total_ref_earned + total_commission:.3f}$

<b>💡 {self.get_text(user_id, 'buttons.advertiser').replace('Reklamveren', 'REKLAMVEREN İSTATİSTİKLERİ')}</b>
"""
        
        if user.get('is_advertiser', 0):
            message += f"""
├ <b>{self.get_text(user_id, 'menu.advertiser_balance')}:</b> {self.converter.format_currency(advertiser_balance_display, currency)}
├ <b>{self.get_text(user_id, 'menu.stats').replace('İstatistik', 'Toplam Harcama')}:</b> {user.get('total_spent_on_ads', 0):.3f}$
└ <b>{self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Toplam Yatırım')}:</b> {user.get('total_deposited', 0):.3f}$
"""
        else:
            message += "└ <i>" + self.get_text(user_id, 'buttons.advertiser').replace('Reklamveren', 'Reklamveren modu kapalı') + "</i>"
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>📈 {self.get_text(user_id, 'menu.stats').replace('İstatistik', 'GERÇEK ZAMANLI İSTATİSTİKLER')}</b>
📢 <b>{self.get_text(user_id, 'menu.channels')}:</b> ✅ Tamam
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': self.get_text(user_id, 'buttons.do_task'), 'callback_data': 'tasks'},
                    {'text': self.get_text(user_id, 'buttons.load_balance'), 'callback_data': 'deposit'}
                ],
                [
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def show_profile(self, user_id):
        user = self.db.get_user(user_id)
        
        ref_status = "✅" if user.get('is_referred') else "❌"
        ref_info = ""
        if user.get('is_referred'):
            ref_info = f"\n<b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans Durumu')}:</b> {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans ile kayıt oldu')}"
            if user.get('referred_by'):
                ref_info += f"\n<b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Davet Eden')}:</b> {self.get_text(user_id, 'menu.profile').replace('Profil', 'Kullanıcı')} ID: {user['referred_by']}"
        
        advertiser_status = f"✅ {self.get_text(user_id, 'success.task_created').replace('Görev', 'Aktif')}" if user.get('is_advertiser') else f"❌ {self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Kapalı')}"
        advertiser_info = ""
        if user.get('is_advertiser'):
            advertiser_balance_display, currency = self.db.get_advertiser_balance_display(user_id)
            advertiser_info = f"""
<b>👑 {self.get_text(user_id, 'buttons.advertiser').replace('Reklamveren', 'Reklamveren Bilgileri')}:</b>
• {self.get_text(user_id, 'menu.advertiser_balance')}: {self.converter.format_currency(advertiser_balance_display, currency)}
• {self.get_text(user_id, 'menu.stats').replace('İstatistik', 'Toplam Harcama')}: {user.get('total_spent_on_ads', 0):.3f}$
"""
        
        balance_display, currency = self.db.get_user_balance_display(user_id)
        
        message = f"""
<b>👤 {self.get_text(user_id, 'menu.profile').upper()}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>{self.get_text(user_id, 'menu.profile').replace('Profil', 'İsim')}:</b> {user.get('name', 'Kullanıcı')}
<b>🆔 {self.get_text(user_id, 'menu.profile').replace('Profil', 'Kullanıcı ID')}:</b> <code>{user_id}</code>
<b>🔗 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans Durumu')}:</b> {ref_status}{ref_info}
<b>👑 {self.get_text(user_id, 'buttons.advertiser').replace('Reklamveren', 'Reklamveren')}:</b> {advertiser_status}{advertiser_info}

<b>💰 {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Finansal Durum')}:</b>
• {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Normal Bakiye')}: {self.converter.format_currency(balance_display, currency)}
• {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Reklam Bakiye')}: {user.get('ads_balance', 0):.3f}$
• {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Toplam Kazanç')}: {user.get('total_earned', 0):.3f}$

<b>📊 {self.get_text(user_id, 'menu.stats').replace('İstatistik', 'İstatistikler')}:</b>
• {self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'Tamamlanan Görev')}: {user.get('tasks_completed', 0)}
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans Sayısı')}: {user.get('referrals', 0)}
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans Kazancı')}: {user.get('ref_earned', 0):.3f}$
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Komisyon Kazancı')}: {user.get('total_ref_commission', 0):.3f}$

<b>💳 {self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'İşlemler')}:</b>
• {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Toplam Yatırım')}: {user.get('total_deposited', 0):.3f}$
• {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Toplam Çekim')}: {user.get('total_withdrawn', 0):.3f}$

📢 <b>{self.get_text(user_id, 'menu.channels')}:</b> ✅ Tamam
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '💰 ' + self.get_text(user_id, 'buttons.load_balance'), 'callback_data': 'deposit'},
                    {'text': '🏧 ' + self.get_text(user_id, 'buttons.withdraw'), 'callback_data': 'withdraw'}
                ],
                [
                    {'text': '👥 ' + self.get_text(user_id, 'buttons.referral'), 'callback_data': 'referral'},
                    {'text': '📊 ' + self.get_text(user_id, 'buttons.stats'), 'callback_data': 'stats'}
                ],
                [
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                ]
            ]
        }
        
        if user.get('is_advertiser'):
            markup['inline_keyboard'].insert(1, [
                {'text': '👑 ' + self.get_text(user_id, 'buttons.advertiser'), 'callback_data': 'advertiser_menu'}
            ])
        
        send_message(user_id, message, markup)
    
    def show_referral_menu(self, user_id):
        user = self.db.get_user(user_id)
        
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
        
        self.db.cursor.execute('''
            SELECT SUM(amount) as total_commission
            FROM commission_logs 
            WHERE referrer_id = ? AND status = 'completed'
        ''', (user_id,))
        commission_stats = self.db.cursor.fetchone()
        total_commission = commission_stats['total_commission'] if commission_stats else 0
        
        referral_link = f"https://t.me/TaskizBot?start=ref_{user_id}"
        
        message = f"""
<b>👥 {self.get_text(user_id, 'buttons.referral').upper()}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans İstatistikleri')}:</b>
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Toplam Referans')}: {total_refs}
• {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Başarılı Referans')}: {completed_refs}
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans Bonusu')}: {total_earned:.3f}$
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Görev Komisyonu')}: {total_commission:.3f}$
• <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Toplam Kazanç')}: {total_earned + total_commission:.3f}$</b>

<b>💰 {self.get_text(user_id, 'success.balance_added').replace('eklendi', 'KAZANÇ SİSTEMİ')}:</b>
• <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'İlk kayıt referansı')}:</b> {REF_WELCOME_BONUS}$ {self.get_text(user_id, 'success.balance_added').replace('eklendi', 'bonus')}
• <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Görev komisyonu')}:</b> %{REF_TASK_COMMISSION*100} {self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'her görev başı')}
• <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Depozit komisyonu')}:</b> %10 {self.get_text(user_id, 'buttons.load_balance').replace('Yükle', 'her depozit')}

<b>🔗 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans Linkiniz')}:</b>
<code>{referral_link}</code>

📢 <b>{self.get_text(user_id, 'menu.channels')}:</b> ✅ Tamam
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

<b>💡 {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Nasıl Çalışır')}:</b>
1. {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Linkinizi arkadaşlarınızla paylaşın')}
2. {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Arkadaşlarınız linke tıklayarak kaydolur')}
3. <b>{self.get_text(user_id, 'success.balance_added').replace('eklendi', 'Hemen')} {REF_WELCOME_BONUS}$ {self.get_text(user_id, 'success.balance_added').replace('eklendi', 'bonus')}</b> {self.get_text(user_id, 'success.balance_added').replace('eklendi', 'alırsınız')}
4. {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Arkadaşınız görev yaparsa')} <b>%{REF_TASK_COMMISSION*100} {self.get_text(user_id, 'buttons.referral').replace('Referans', 'komisyon')}</b> {self.get_text(user_id, 'success.balance_added').replace('eklendi', 'alırsınız')}
5. {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Arkadaşınız depozit yaparsa')} <b>%10 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'komisyon')}</b> {self.get_text(user_id, 'success.balance_added').replace('eklendi', 'alırsınız')}
6. {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Sınırsız kazanç fırsatı')}!
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '📋 ' + self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Linki Kopyala'), 'callback_data': 'referral_copy'},
                    {'text': '📤 ' + self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Paylaş'), 'callback_data': 'referral_share'}
                ],
                [
                    {'text': '📊 ' + self.get_text(user_id, 'menu.stats').replace('İstatistik', 'Detaylı Rapor'), 'callback_data': 'referral_details'},
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def show_help(self, user_id):
        message = f"""
<b>❓ {self.get_text(user_id, 'menu.help').upper()} {self.get_text(user_id, 'menu.main_menu').replace('ANA MENÜ', 'VE DESTEK')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🤖 {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'BOT NASIL ÇALIŞIR')}?</b>
1. 📢 {self.get_text(user_id, 'menu.channels')} {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'katılın')} (@{MANDATORY_CHANNELS['main']['username']})
2. 🎯 {self.get_text(user_id, 'buttons.do_task')} {self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'veya')} 📢 {self.get_text(user_id, 'buttons.advertiser').replace('Reklamveren', 'reklam verin')}
3. 💰 {self.get_text(user_id, 'success.balance_added').replace('eklendi', 'Para kazanmaya başlayın')}!

<b>🎯 {self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'GÖREV YAPMA')}:</b>
1. "{self.get_text(user_id, 'buttons.do_task')}" {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'butonuna tıklayın')}
2. {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Mevcut görevleri görün')}
3. {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Göreve katılın')}
4. {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Gruba/Kanala katılın veya botu kullanın')}
5. {self.get_text(user_id, 'buttons.advertiser').replace('Reklamveren', 'Reklamveren katılımınızı doğrulasın')}
6. {self.get_text(user_id, 'success.balance_added').replace('eklendi', 'Ödülünüz bakiyenize yüklensin')}
7. <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referansınız varsa %')}{REF_TASK_COMMISSION*100} {self.get_text(user_id, 'buttons.referral').replace('Referans', 'komisyon kazanın')}!</b>

<b>📢 {self.get_text(user_id, 'buttons.advertiser').replace('Reklamveren', 'REKLAM VERME')}:</b>
1. "{self.get_text(user_id, 'buttons.become_advertiser')}" {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'butonuna tıklayın')}
2. "{self.get_text(user_id, 'buttons.load_balance')}" {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'ile reklamveren bakiyesi yükleyin')}
3. "{self.get_text(user_id, 'success.task_created').replace('Görev', 'Görev Oluştur')}" {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'ile görev oluşturun')}
4. {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Katılımcıların katılımını doğrulayın')}
5. {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Ödemeler otomatik olarak yapılsın')}

<b>👥 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'REFERANS SİSTEMİ')}:</b>
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Her referans')}: {REF_WELCOME_BONUS}$
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Görev komisyonu')}: %{REF_TASK_COMMISSION*100}
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Depozit komisyonu')}: %10
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Sınırsız kazanç')}!

<b>⚠️ {self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'ÖNEMLİ UYARILAR')}:</b>
• {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Grubu/Kanalı terk ederseniz ödülünüz geri alınır')}!
• {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Zorunlu kanallardan ayrılırsanız botu kullanamazsınız')}!
• {self.get_text(user_id, 'menu.advertiser_balance')} {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'sadece reklam vermek içindir')}!
• {self.get_text(user_id, 'errors.min_withdraw', amount=MIN_WITHDRAW)}!

<b>💰 {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'FİYATLAR')}:</b>
• {self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'Kanal görevi')}: {CHANNEL_TASK_PRICE:.3f}$
• {self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'Grup görevi')}: {GROUP_TASK_PRICE:.3f}$
• {self.get_text(user_id, 'buttons.do_task').replace('Görev Yap', 'Bot görevi')}: {BOT_TASK_PRICE:.3f}$
• {self.get_text(user_id, 'errors.min_withdraw', amount=MIN_DEPOSIT_USD).replace('çekim', 'yatırım')}
• {self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Maksimum depozit')}: {MAX_DEPOSIT_USD}$

<b>📢 {self.get_text(user_id, 'menu.channels')}:</b>
• @{MANDATORY_CHANNELS['main']['username']} ({self.get_text(user_id, 'channels.main')})
• @{MANDATORY_CHANNELS['instagram']['username']} ({self.get_text(user_id, 'channels.instagram')})
• @{MANDATORY_CHANNELS['binance']['username']} ({self.get_text(user_id, 'channels.binance')})
• @{STATS_CHANNEL} ({self.get_text(user_id, 'channels.stats')})

<b>📞 {self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'DESTEK')}:</b>
{self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Sorularınız için')} @TaskizBot {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'yazın')}.
"""
        
        markup = {
            'inline_keyboard': [[
                {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
            ]]
        }
        send_message(user_id, message, markup)
    
    def show_admin_panel(self, user_id):
        if user_id != ADMIN_ID:
            send_message(user_id, self.get_text(user_id, 'errors.unauthorized') + "!")
            return
        
        self.db.cursor.execute("SELECT COUNT(*) FROM users")
        total_users = self.db.cursor.fetchone()[0]
        
        self.db.cursor.execute("SELECT COUNT(*) FROM users WHERE is_advertiser = 1")
        total_advertisers = self.db.cursor.fetchone()[0]
        
        message = f"""
<b>👑 {self.get_text(user_id, 'buttons.admin_panel').upper()}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 {self.get_text(user_id, 'menu.stats').replace('İstatistik', 'SİSTEM İSTATİSTİKLERİ')}</b>
• 👥 {self.get_text(user_id, 'menu.stats').replace('İstatistik', 'Toplam Kullanıcı')}: {total_users}
• 📢 {self.get_text(user_id, 'buttons.advertiser').replace('Reklamveren', 'Reklamverenler')}: {total_advertisers}

📢 <b>{self.get_text(user_id, 'menu.channels')}:</b> ✅ Tamam
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

<b>🛠️ {self.get_text(user_id, 'menu.main_menu').replace('ANA MENÜ', 'YÖNETİM ARAÇLARI')}</b>
"""
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '📊 ' + self.get_text(user_id, 'menu.stats'), 'callback_data': 'admin_stats'},
                    {'text': '👥 ' + self.get_text(user_id, 'menu.profile').replace('Profil', 'Kullanıcılar'), 'callback_data': 'admin_users'}
                ],
                [
                    {'text': '📢 ' + self.get_text(user_id, 'buttons.advertiser'), 'callback_data': 'admin_advertisers'},
                    {'text': '💰 ' + self.get_text(user_id, 'buttons.load_balance').replace('Yükle', 'Depozitler'), 'callback_data': 'admin_deposits'}
                ],
                [
                    {'text': '💸 ' + self.get_text(user_id, 'buttons.withdraw').replace('Para Çek', 'Çekimler'), 'callback_data': 'admin_withdrawals'},
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'menu'}
                ]
            ]
        }
        
        send_message(user_id, message, markup)
    
    def copy_referral_link(self, user_id):
        referral_link = f"https://t.me/TaskizBot?start=ref_{user_id}"
        send_message(user_id, f"""
<b>🔗 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'REFERANS LİNKİNİZ')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<code>{referral_link}</code>

📢 <b>{self.get_text(user_id, 'menu.channels')}:</b> ✅ Tamam
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

📋 <b>{self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Yukarıdaki linki kopyalayın ve paylaşın')}!</b>

💰 <b>{self.get_text(user_id, 'success.balance_added').replace('eklendi', 'Kazançlar')}:</b>
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Her referans')}: {REF_WELCOME_BONUS}$
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Görev komisyonu')}: %{REF_TASK_COMMISSION*100}
• {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Depozit komisyonu')}: %10

💡 <b>{self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Paylaşım Önerileri')}:</b>
• WhatsApp {self.get_text(user_id, 'menu.profile').replace('Profil', 'grupları')}
• Telegram {self.get_text(user_id, 'menu.profile').replace('Profil', 'grupları')}
• {self.get_text(user_id, 'menu.stats').replace('İstatistik', 'Sosyal medya')}
• {self.get_text(user_id, 'menu.profile').replace('Profil', 'Arkadaşlarınıza özel mesaj')}
""")
    
    def share_referral_link(self, user_id):
        referral_link = f"https://t.me/TaskizBot?start=ref_{user_id}"
        
        markup = {
            'inline_keyboard': [
                [
                    {'text': '📱 WhatsApp', 'url': f'https://wa.me/?text=TaskizBot ile para kazanın! Her referans {REF_WELCOME_BONUS}$, görev komisyonu %{REF_TASK_COMMISSION*100}. {referral_link}'},
                    {'text': '✈️ Telegram', 'url': f'https://t.me/share/url?url={referral_link}&text=TaskizBot ile para kazanın! Her referans {REF_WELCOME_BONUS}$, görev komisyonu %{REF_TASK_COMMISSION*100}.'}
                ],
                [
                    {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'referral'}
                ]
            ]
        }
        
        send_message(user_id, f"""
<b>📤 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'REFERANS LİNKİ PAYLAŞ')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📢 <b>{self.get_text(user_id, 'menu.channels')}:</b> ✅ Tamam
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

👇 <b>{self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Aşağıdaki butonlardan birine tıklayarak paylaşabilirsiniz')}:</b>
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
        
        self.db.cursor.execute('''
            SELECT cl.*, u.name as referred_name
            FROM commission_logs cl
            LEFT JOIN users u ON cl.referred_id = u.user_id
            WHERE cl.referrer_id = ? 
            ORDER BY cl.created_at DESC 
            LIMIT 10
        ''', (user_id,))
        commission_logs = self.db.cursor.fetchall()
        
        if not ref_logs and not commission_logs:
            message = f"""
<b>📊 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'REFERANS DETAYLARI')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📭 <b>{self.get_text(user_id, 'errors.not_found').replace('Bulunamadı', 'Henüz referans kaydınız bulunmuyor')}</b>

📢 <b>{self.get_text(user_id, 'menu.channels')}:</b> ✅ Tamam
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

💡 <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans linkinizi paylaşarak kazanmaya başlayın')}!</b>
"""
        else:
            message = f"""
<b>📊 {self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'SON 10 REFERANS KAYDI')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📢 <b>{self.get_text(user_id, 'menu.channels')}:</b> ✅ Tamam
📊 <b>{self.get_text(user_id, 'menu.stats')}:</b> @{STATS_CHANNEL}

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            total_earned = 0
            
            if ref_logs:
                message += f"\n<b>🎁 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'REFERANS BONUSLARI')}:</b>\n"
                for log in ref_logs:
                    status = "✅" if log['status'] == 'completed' else "⏳" if log['status'] == 'pending' else "❌"
                    reward_type = {
                        'welcome': self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Hoşgeldin'),
                        'late_join': self.get_text(user_id, 'success.task_joined').replace('katıldınız', 'Geç Katılım'),
                        'referral_deposit': self.get_text(user_id, 'buttons.referral').replace('Referans', 'Depozit Komisyonu')
                    }.get(log['reward_type'], log['reward_type'] or self.get_text(user_id, 'errors.not_found').replace('Bulunamadı', 'Bilinmiyor'))
                    
                    if log['status'] == 'completed':
                        total_earned += log['amount'] or 0
                    
                    message += f"""{status} <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Referans')} #{log['log_id']}</b>
├ <b>{self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Tür')}:</b> {reward_type}
├ <b>{self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Tutar')}:</b> {log['amount']:.3f}$
├ <b>{self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Durum')}:</b> {log['status']}
└ <b>{self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Tarih')}:</b> {log['created_at'][:16]}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            if commission_logs:
                message += f"\n<b>💰 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'GÖREV KOMİSYONLARI')}:</b>\n"
                for log in commission_logs:
                    status = "✅" if log['status'] == 'completed' else "⏳"
                    referred_name = log['referred_name'] or self.get_text(user_id, 'errors.not_found').replace('Bulunamadı', 'Anonim')
                    
                    if log['status'] == 'completed':
                        total_earned += log['amount'] or 0
                    
                    message += f"""{status} <b>{self.get_text(user_id, 'buttons.referral').replace('Referans', 'Komisyon')} #{log['commission_id']}</b>
├ <b>{self.get_text(user_id, 'menu.profile').replace('Profil', 'Kullanıcı')}:</b> {referred_name[:15]}
├ <b>{self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Tutar')}:</b> {log['amount']:.3f}$
├ <b>{self.get_text(user_id, 'menu.balance').replace('Bakiye', 'Oran')}:</b> %{log['commission_rate']*100}
└ <b>{self.get_text(user_id, 'menu.main_menu').replace('MENÜ', 'Tarih')}:</b> {log['created_at'][:16]}
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            message += f"\n<b>💰 {self.get_text(user_id, 'buttons.referral').replace('Referans', 'Toplam Kazanç')}:</b> {total_earned:.3f}$"
        
        markup = {
            'inline_keyboard': [[
                {'text': self.get_text(user_id, 'menu.back'), 'callback_data': 'referral'}
            ]]
        }
        
        send_message(user_id, message, markup)

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
        last_daily_stats = None
        
        while self.running:
            try:
                now = get_turkey_time()
                
                if now.hour == 9 and (last_daily_stats is None or last_daily_stats.date() != now.date()):
                    self.send_daily_stats()
                    last_daily_stats = now
                
                self.check_channel_memberships()
                time.sleep(60)
                
            except Exception as e:
                print(f"❌ Arka plan kontrol hatası: {e}")
                time.sleep(30)
    
    def check_channel_memberships(self):
        """Kullanıcıların zorunlu kanal üyeliklerini kontrol et"""
        try:
            twenty_four_hours_ago = (get_turkey_time() - timedelta(hours=24)).isoformat()
            
            self.db.cursor.execute('''
                SELECT user_id, name, in_main_channel, in_instagram_channel, 
                       in_binance_channel, in_stats_channel, last_join_check 
                FROM users 
                WHERE last_active > ? OR last_join_check IS NULL OR last_join_check < ?
            ''', (twenty_four_hours_ago, twenty_four_hours_ago))
            
            users = self.db.cursor.fetchall()
            
            for user in users:
                user_id = user['user_id']
                user_id_int = int(user_id)
                
                # Her kanalı kontrol et
                channels_to_check = [
                    ('main', MANDATORY_CHANNELS['main']['username']),
                    ('instagram', MANDATORY_CHANNELS['instagram']['username']),
                    ('binance', MANDATORY_CHANNELS['binance']['username']),
                    ('stats', MANDATORY_CHANNELS['stats']['username'])
                ]
                
                for channel_type, channel_username in channels_to_check:
                    channel_field = f"in_{channel_type}_channel"
                    current_status = user[channel_field]
                    
                    is_member = get_chat_member(f"@{channel_username}", user_id_int)
                    
                    if is_member and current_status == 0:
                        self.db.update_channel_status(user_id, channel_type, True)
                        print(f"✅ {user_id} kullanıcısı {channel_username} kanalına katıldı")
                    
                    elif not is_member and current_status == 1:
                        self.db.update_channel_status(user_id, channel_type, False)
                        print(f"⚠️ {user_id} kullanıcısı {channel_username} kanalından ayrıldı")
                
                # Son kontrol zamanını güncelle
                self.db.cursor.execute('''
                    UPDATE users SET last_join_check = ? WHERE user_id = ?
                ''', (get_turkey_time().isoformat(), user_id))
            
            self.db.conn.commit()
            
        except Exception as e:
            print(f"❌ Kanal kontrol hatası: {e}")
    
    def send_daily_stats(self):
        """Günlük istatistikleri gönder"""
        try:
            now = get_turkey_time()
            
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            self.db.cursor.execute('''
                SELECT COUNT(*) as total, 
                       SUM(CASE WHEN is_referred = 1 THEN 1 ELSE 0 END) as referred
                FROM users 
                WHERE created_at > ?
            ''', (today_start,))
            
            stats = self.db.cursor.fetchone()
            total_today = stats['total'] or 0
            referred_today = stats['referred'] or 0
            
            self.db.cursor.execute('''
                SELECT COUNT(*) as total_users,
                       SUM(CASE WHEN is_referred = 1 THEN 1 ELSE 0 END) as total_referred
                FROM users
            ''')
            
            total_stats = self.db.cursor.fetchone()
            total_users = total_stats['total_users'] or 0
            total_referred = total_stats['total_referred'] or 0
            
            self.db.cursor.execute('''
                SELECT COUNT(*) as total_tasks,
                       SUM(total_spent) as total_spent
                FROM tasks 
                WHERE created_at > ?
            ''', (today_start,))
            
            task_stats = self.db.cursor.fetchone()
            today_tasks = task_stats['total_tasks'] or 0
            today_spent = task_stats['total_spent'] or 0
            
            message = f"""
<b>📊 GÜNLÜK İSTATİSTİKLER</b>
<b>📅 Tarih:</b> {now.strftime('%d.%m.%Y')}
<b>⏰ Saat:</b> {now.strftime('%H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>👥 BUGÜN KAYITLAR</b>
├ <b>Toplam Kayıt:</b> {total_today}
├ <b>Referans ile:</b> {referred_today}
└ <b>Normal Kayıt:</b> {total_today - referred_today}

<b>📢 BUGÜN GÖREVLER</b>
├ <b>Toplam Görev:</b> {today_tasks}
└ <b>Toplam Harcama:</b> {today_spent:.3f}$

<b>📈 TOPLAM İSTATİSTİKLER</b>
├ <b>Toplam Kullanıcı:</b> {total_users}
├ <b>Referanslı Kullanıcı:</b> {total_referred}
└ <b>Referans Oranı:</b> {(total_referred/total_users*100 if total_users > 0 else 0):.1f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>💰 REFERANS SİSTEMİ</b>
├ <b>Referans Bonusu:</b> {REF_WELCOME_BONUS}$
├ <b>Görev Komisyonu:</b> %{REF_TASK_COMMISSION*100}
└ <b>Depozit Komisyonu:</b> %10

<b>📢 ZORUNLU KANALLAR:</b>
• @EarnTether2026 (Ana Kanal)
• @instagramNewsBrazil (Instagram)
• @BinanceBrazilNews (Binance)
• @{STATS_CHANNEL} (İstatistik)

💡 <b>Referans sistemi aktif!</b>
"""
            
            send_message(f"@{STATS_CHANNEL}", message)
            
        except Exception as e:
            print(f"❌ Günlük istatistik hatası: {e}")

# Ana Program
def main():
    print(f"""
    ╔════════════════════════════════════════════════════════════════╗
    ║                    TASKİZBOT v2.0 - ÇOK DİLLİ                  ║
    ║   TRX DEPOZİT + OTOMATİK GÖREV + REKLAMVEREN SİSTEMİ           ║
    ║   + GRUP/KANAL TERK CEZASI + ZORUNLU KANAL KONTROLÜ           ║
    ║   + GERÇEK ZAMANLI İSTATİSTİK + REFERANS SİSTEMİ              ║
    ║   + ÇOK DİL DESTEĞİ + PARA BİRİMİ SEÇİMİ                     ║
    ║   + 4 ZORUNLU KANAL SİSTEMİ                                   ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    bot = BotSystem()
    
    bot_thread = threading.Thread(target=bot.start_polling, daemon=True)
    bot_thread.start()
    
    print("✅ Bot başarıyla başlatıldı!")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"📢 Zorunlu Kanallar:")
    for channel_type, channel_info in MANDATORY_CHANNELS.items():
        print(f"   • {channel_info['name']}: @{channel_info['username']}")
    print(f"📊 İstatistik Kanalı: @{STATS_CHANNEL}")
    print(f"🌐 Desteklenen Diller: {', '.join([f'{info[\"flag\"]} {info[\"name\"]}' for info in SUPPORTED_LANGUAGES.values()])}")
    print(f"💰 Desteklenen Para Birimleri: USD, TRY, RUB, BDT")
    print(f"₿ TRX Adresi: {TRX_ADDRESS}")
    print("💰 Min Depozit: 2.5$, Max: 10$")
    print(f"💸 Minimum Çekim: {MIN_WITHDRAW}$")
    print("📢 Görev Ücretleri: Kanal 0.03$, Grup 0.02$, Bot 0.01$")
    print("👥 Referans Bonusu: 0.005$ her davet")
    print("💰 Görev Komisyonu: %25 her görev başı")
    print("⚠️ Terk Cezası: Grubu/Kanalı terk edenler ödülü kaybeder")
    print("🎯 Reklamveren Sistemi: Aktif (varsayılan 2.5$ bakiye)")
    print("📊 İstatistik Bildirimleri: Aktif")
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
