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
import random
import re
from typing import Optional, Dict, List, Tuple, Any
from forex_python.converter import CurrencyRates
from contextlib import closing

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
TRX_ADDRESS = os.environ.get("TRX_ADDRESS", "DEPOZIT_YAPILACAK_ADRES")
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
    return jsonify({"status": "online", "bot": "TaskizBot v3.0", "languages": list(SUPPORTED_LANGUAGES.keys())})

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    bot.handle_update(update)
    return jsonify({"status": "ok"})

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
            'join_channels': "📢 Kanallara Katıl",
            'create_task': "➕ Görev Oluştur",
            'my_tasks': "📋 Görevlerim"
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
            'join_all_channels': "📢 Tüm Kanallara Katıl",
            'create_task': "➕ Görev Oluştur",
            'my_tasks': "📋 Görevlerim",
            'advertiser_stats': "📈 Reklam İstatistik",
            'earner_menu': "👤 Para Kazanan Menü",
            'switch_to_earner': "👤 Para Kazanan Ol",
            'switch_to_advertiser': "📢 Reklamveren Ol",
            'change_language': "🌐 Dil Değiştir",
            'change_user_type': "🔄 Tür Değiştir"
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
            'channel_not_joined': "❌ {channel_name} kanalına katılmadınız!",
            'user_type_required': "❌ Önce kullanıcı türünüzü seçmelisiniz!",
            'min_balance_for_advertiser': "❌ Reklamveren olmak için minimum {amount}$ bakiyeniz olmalı!",
            'active_tasks_exist': "❌ Aktif görevleriniz varken tür değiştiremezsiniz!"
        },
        'success': {
            'task_joined': "✅ Göreve katıldınız!",
            'deposit_received': "✅ Bakiye yüklendi!",
            'withdraw_requested': "✅ Para çekme talebi alındı!",
            'task_created': "✅ Görev oluşturuldu!",
            'task_verified': "✅ Görev doğrulandı!",
            'balance_added': "💰 Bakiye eklendi!",
            'all_channels_joined': "✅ Tüm kanallara katıldınız!",
            'channels_checked': "✅ Kanallar kontrol edildi!",
            'user_type_set': "✅ Kullanıcı türünüz kaydedildi!",
            'language_set': "✅ Dil tercihiniz kaydedildi!",
            'profile_updated': "✅ Profil güncellendi!",
            'user_type_changed': "✅ Kullanıcı türünüz değiştirildi!"
        },
        'channels': {
            'main': "📢 Ana Kanal",
            'instagram': "📸 Instagram Haberleri",
            'binance': "💰 Binance Haberleri",
            'stats': "📊 Canlı İstatistik",
            'mandatory': "Zorunlu Kanallar",
            'description': "Botu kullanmak için aşağıdaki kanalların tümüne katılmalısınız:"
        },
        'registration': {
            'welcome': "🎯 *Hoş Geldiniz!*\nLütfen kullanıcı türünüzü seçin:",
            'earner_description': "👤 *Para Kazanan*\n• Görev yaparak para kazan\n• Reklam izle, kanallara katıl\n• Günlük bonuslar al",
            'advertiser_description': "📢 *Reklamveren*\n• Görev oluştur ve yayınla\n• Reklam bütçesi yükle\n• Kitleye ulaş ve ürününü tanıt",
            'select_type': "Hangi tür kullanıcı olmak istiyorsunuz?",
            'language_selection': "🌍 *Lütfen dilinizi seçin*",
            'registration_complete': "✅ *Kayıt Tamamlandı!*",
            'current_type': "👤 Kullanıcı Türü: {type}",
            'current_language': "🌐 Dil: {language}"
        },
        'profile': {
            'title': "👤 *PROFİL AYARLARI*",
            'user_id': "• Kullanıcı ID: {id}",
            'user_type': "• Tür: {type}",
            'language': "• Dil: {language}",
            'registration_date': "• Kayıt Tarihi: {date}",
            'balance': "• Bakiye: {balance}",
            'tasks_completed': "• Tamamlanan Görev: {count}",
            'change_type': "🔄 Tür Değiştir",
            'change_language': "🌐 Dil Değiştir"
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
            'join_channels': "📢 Join Channels",
            'create_task': "➕ Create Task",
            'my_tasks': "📋 My Tasks"
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
            'join_all_channels': "📢 Join All Channels",
            'create_task': "➕ Create Task",
            'my_tasks': "📋 My Tasks",
            'advertiser_stats': "📈 Ad Stats",
            'earner_menu': "👤 Earner Menu",
            'switch_to_earner': "👤 Switch to Earner",
            'switch_to_advertiser': "📢 Switch to Advertiser",
            'change_language': "🌐 Change Language",
            'change_user_type': "🔄 Change User Type"
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
            'channel_not_joined': "❌ You didn't join {channel_name} channel!",
            'user_type_required': "❌ You must select your user type first!",
            'min_balance_for_advertiser': "❌ You need minimum {amount}$ balance to become advertiser!",
            'active_tasks_exist': "❌ Cannot change type while you have active tasks!"
        },
        'success': {
            'task_joined': "✅ Joined the task!",
            'deposit_received': "✅ Balance loaded!",
            'withdraw_requested': "✅ Withdrawal request received!",
            'task_created': "✅ Task created!",
            'task_verified': "✅ Task verified!",
            'balance_added': "💰 Balance added!",
            'all_channels_joined': "✅ Joined all channels!",
            'channels_checked': "✅ Channels checked!",
            'user_type_set': "✅ User type saved!",
            'language_set': "✅ Language preference saved!",
            'profile_updated': "✅ Profile updated!",
            'user_type_changed': "✅ User type changed!"
        },
        'channels': {
            'main': "📢 Main Channel",
            'instagram': "📸 Instagram News",
            'binance': "💰 Binance News",
            'stats': "📊 Live Statistics",
            'mandatory': "Mandatory Channels",
            'description': "To use the bot, you must join all the channels below:"
        },
        'registration': {
            'welcome': "🎯 *Welcome!*\nPlease select your user type:",
            'earner_description': "👤 *Earner*\n• Earn money by completing tasks\n• Watch ads, join channels\n• Get daily bonuses",
            'advertiser_description': "📢 *Advertiser*\n• Create and publish tasks\n• Load advertising budget\n• Reach audience and promote your product",
            'select_type': "What type of user do you want to be?",
            'language_selection': "🌍 *Please select your language*",
            'registration_complete': "✅ *Registration Complete!*",
            'current_type': "👤 User Type: {type}",
            'current_language': "🌐 Language: {language}"
        },
        'profile': {
            'title': "👤 *PROFILE SETTINGS*",
            'user_id': "• User ID: {id}",
            'user_type': "• Type: {type}",
            'language': "• Language: {language}",
            'registration_date': "• Registration Date: {date}",
            'balance': "• Balance: {balance}",
            'tasks_completed': "• Completed Tasks: {count}",
            'change_type': "🔄 Change Type",
            'change_language': "🌐 Change Language"
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
            'join_channels': "📢 Присоединиться к каналам",
            'create_task': "➕ Создать задание",
            'my_tasks': "📋 Мои задания"
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
            'join_all_channels': "📢 Присоединиться ко всем каналам",
            'create_task': "➕ Создать задание",
            'my_tasks': "📋 Мои задания",
            'advertiser_stats': "📈 Статистика рекламы",
            'earner_menu': "👤 Меню зарабатывающего",
            'switch_to_earner': "👤 Перейти к зарабатывающему",
            'switch_to_advertiser': "📢 Перейти к рекламодателю",
            'change_language': "🌐 Изменить язык",
            'change_user_type': "🔄 Изменить тип пользователя"
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
            'channel_not_joined': "❌ Вы не присоединились к каналу {channel_name}!",
            'user_type_required': "❌ Сначала выберите тип пользователя!",
            'min_balance_for_advertiser': "❌ Вам нужно минимум {amount}$ баланса, чтобы стать рекламодателем!",
            'active_tasks_exist': "❌ Нельзя изменить тип, пока у вас есть активные задания!"
        },
        'success': {
            'task_joined': "✅ Присоединились к заданию!",
            'deposit_received': "✅ Баланс пополнен!",
            'withdraw_requested': "✅ Запрос на вывод получен!",
            'task_created': "✅ Задание создано!",
            'task_verified': "✅ Задание проверено!",
            'balance_added': "💰 Баланс добавлен!",
            'all_channels_joined': "✅ Присоединились ко всем каналам!",
            'channels_checked': "✅ Каналы проверены!",
            'user_type_set': "✅ Тип пользователя сохранен!",
            'language_set': "✅ Языковые настройки сохранены!",
            'profile_updated': "✅ Профиль обновлен!",
            'user_type_changed': "✅ Тип пользователя изменен!"
        },
        'channels': {
            'main': "📢 Главный канал",
            'instagram': "📸 Новости Instagram",
            'binance': "💰 Новости Binance",
            'stats': "📊 Живая статистика",
            'mandatory': "Обязательные каналы",
            'description': "Чтобы использовать бота, вы должны присоединиться ко всем каналам ниже:"
        },
        'registration': {
            'welcome': "🎯 *Добро пожаловать!*\nПожалуйста, выберите тип пользователя:",
            'earner_description': "👤 *Зарабатывающий*\n• Зарабатывайте деньги, выполняя задания\n• Смотрите рекламу, присоединяйтесь к каналам\n• Получайте ежедневные бонусы",
            'advertiser_description': "📢 *Рекламодатель*\n• Создавайте и публикуйте задания\n• Пополняйте рекламный бюджет\n• Достигайте аудиторию и продвигайте свой продукт",
            'select_type': "Каким типом пользователя вы хотите быть?",
            'language_selection': "🌍 *Пожалуйста, выберите ваш язык*",
            'registration_complete': "✅ *Регистрация завершена!*",
            'current_type': "👤 Тип пользователя: {type}",
            'current_language': "🌐 Язык: {language}"
        },
        'profile': {
            'title': "👤 *НАСТРОЙКИ ПРОФИЛЯ*",
            'user_id': "• ID пользователя: {id}",
            'user_type': "• Тип: {type}",
            'language': "• Язык: {language}",
            'registration_date': "• Дата регистрации: {date}",
            'balance': "• Баланс: {balance}",
            'tasks_completed': "• Выполнено заданий: {count}",
            'change_type': "🔄 Изменить тип",
            'change_language': "🌐 Изменить язык"
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
            'join_channels': "📢 চ্যানেলে যোগ দিন",
            'create_task': "➕ টাস্ক তৈরি করুন",
            'my_tasks': "📋 আমার টাস্ক"
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
            'join_all_channels': "📢 সব চ্যানেলে যোগ দিন",
            'create_task': "➕ টাস্ক তৈরি করুন",
            'my_tasks': "📋 আমার টাস্ক",
            'advertiser_stats': "📈 বিজ্ঞাপন পরিসংখ্যান",
            'earner_menu': "👤 আয়কারী মেনু",
            'switch_to_earner': "👤 আয়কারীতে স্যুইচ করুন",
            'switch_to_advertiser': "📢 বিজ্ঞাপনদাতায় স্যুইচ করুন",
            'change_language': "🌐 ভাষা পরিবর্তন করুন",
            'change_user_type': "🔄 ব্যবহারকারীর ধরণ পরিবর্তন করুন"
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
            'channel_not_joined': "❌ আপনি {channel_name} চ্যানেলে যোগ দেননি!",
            'user_type_required': "❌ প্রথমে আপনাকে আপনার ব্যবহারকারীর ধরণ নির্বাচন করতে হবে!",
            'min_balance_for_advertiser': "❌ বিজ্ঞাপনদাতা হতে আপনার ন্যূনতম {amount}$ ব্যালেন্স প্রয়োজন!",
            'active_tasks_exist': "❌ আপনার সক্রিয় টাস্ক থাকলে ধরণ পরিবর্তন করতে পারবেন না!"
        },
        'success': {
            'task_joined': "✅ টাস্কে যোগ দিয়েছেন!",
            'deposit_received': "✅ ব্যালেন্স লোড হয়েছে!",
            'withdraw_requested': "✅ উত্তোলনের অনুরোধ পেয়েছেন!",
            'task_created': "✅ টাস্ক তৈরি হয়েছে!",
            'task_verified': "✅ টাস্ক যাচাই হয়েছে!",
            'balance_added': "💰 ব্যালেন্স যোগ হয়েছে!",
            'all_channels_joined': "✅ সব চ্যানেলে যোগ দিয়েছেন!",
            'channels_checked': "✅ চ্যানেল চেক করা হয়েছে!",
            'user_type_set': "✅ ব্যবহারকারীর ধরণ সংরক্ষিত!",
            'language_set': "✅ ভাষা পছন্দ সংরক্ষিত!",
            'profile_updated': "✅ প্রোফাইল আপডেট হয়েছে!",
            'user_type_changed': "✅ ব্যবহারকারীর ধরণ পরিবর্তিত হয়েছে!"
        },
        'channels': {
            'main': "📢 প্রধান চ্যানেল",
            'instagram': "📸 Instagram সংবাদ",
            'binance': "💰 Binance সংবাদ",
            'stats': "📊 লাইভ পরিসংখ্যান",
            'mandatory': "বাধ্যতামূলক চ্যানেল",
            'description': "বট ব্যবহার করতে, আপনাকে নিচের সব চ্যানেলে যোগ দিতে হবে:"
        },
        'registration': {
            'welcome': "🎯 *স্বাগতম!*\nঅনুগ্রহ করে আপনার ব্যবহারকারীর ধরণ নির্বাচন করুন:",
            'earner_description': "👤 *আয়কারী*\n• টাস্ক সম্পূর্ণ করে অর্থ উপার্জন করুন\n• বিজ্ঞাপন দেখুন, চ্যানেলে যোগ দিন\n• দৈনিক বোনাস পান",
            'advertiser_description': "📢 *বিজ্ঞাপনদাতা*\n• টাস্ক তৈরি করুন এবং প্রকাশ করুন\n• বিজ্ঞাপন বাজেট লোড করুন\n• দর্শকদের কাছে পৌঁছান এবং আপনার পণ্য প্রচার করুন",
            'select_type': "আপনি কি ধরণের ব্যবহারকারী হতে চান?",
            'language_selection': "🌍 *অনুগ্রহ করে আপনার ভাষা নির্বাচন করুন*",
            'registration_complete': "✅ *নিবন্ধন সম্পূর্ণ!*",
            'current_type': "👤 ব্যবহারকারীর ধরণ: {type}",
            'current_language': "🌐 ভাষা: {language}"
        },
        'profile': {
            'title': "👤 *প্রোফাইল সেটিংস*",
            'user_id': "• ব্যবহারকারী ID: {id}",
            'user_type': "• ধরণ: {type}",
            'language': "• ভাষা: {language}",
            'registration_date': "• নিবন্ধনের তারিখ: {date}",
            'balance': "• ব্যালেন্স: {balance}",
            'tasks_completed': "• সম্পন্ন টাস্ক: {count}",
            'change_type': "🔄 ধরণ পরিবর্তন করুন",
            'change_language': "🌐 ভাষা পরিবর্তন করুন"
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

# Telegram API Fonksiyonları
def send_message(chat_id, text, reply_markup=None, parse_mode='Markdown'):
    """Telegram mesaj gönder"""
    url = BASE_URL + "sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }
    
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"❌ Mesaj gönderme hatası: {e}")
        return None

def edit_message_text(chat_id, message_id, text, reply_markup=None, parse_mode='Markdown'):
    """Telegram mesajını düzenle"""
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
    """Callback query'yi yanıtla"""
    url = BASE_URL + "answerCallbackQuery"
    payload = {
        'callback_query_id': callback_query_id
    }
    
    if text:
        payload['text'] = text
    if show_alert:
        payload['show_alert'] = show_alert
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"❌ Callback yanıtlama hatası: {e}")

def get_chat_member(chat_id, user_id):
    """Kullanıcının kanal üyeliğini kontrol et"""
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
        print(f"❌ Üyelik kontrol hatası: {e}")
        return False

def delete_message(chat_id, message_id):
    """Mesaj sil"""
    url = BASE_URL + "deleteMessage"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id
    }
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"❌ Mesaj silme hatası: {e}")

# Database Sınıfı
class Database:
    def __init__(self, db_path='taskizbot.db'):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.setup_database()
    
    def setup_database(self):
        """Veritabanı tablolarını oluştur"""
        # Kullanıcılar tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT DEFAULT 'tr',
                balance REAL DEFAULT 0,
                advertiser_balance REAL DEFAULT 0,
                is_advertiser INTEGER DEFAULT 0,
                user_type TEXT DEFAULT 'earner',
                referral_code TEXT UNIQUE,
                referred_by TEXT,
                tasks_completed INTEGER DEFAULT 0,
                total_earned REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Depozitler tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount_usd REAL,
                amount_try REAL,
                trx_amount REAL,
                address TEXT,
                tx_hash TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Çekimler tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount_usd REAL,
                address TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Görevler tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertiser_id INTEGER,
                task_type TEXT,
                title TEXT,
                description TEXT,
                link TEXT,
                participants_needed INTEGER,
                participants_current INTEGER DEFAULT 0,
                reward_per_user REAL,
                total_spent REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (advertiser_id) REFERENCES users (user_id)
            )
        ''')
        
        # Görev katılımları tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_participations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                screenshot TEXT,
                reward_paid REAL DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMP,
                paid_at TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Referanslar tablosu
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                earned_amount REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                FOREIGN KEY (referred_id) REFERENCES users (user_id)
            )
        ''')
        
        # Kanal kontrol kayıtları
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id TEXT,
                channel_name TEXT,
                status INTEGER DEFAULT 0,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.connection.commit()
    
    def get_user(self, user_id):
        """Kullanıcı bilgilerini getir"""
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def create_user(self, user_id, username, first_name, last_name, user_type='earner', language='tr'):
        """Yeni kullanıcı oluştur"""
        referral_code = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8].upper()
        
        self.cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, user_type, language, referral_code, is_advertiser)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, user_type, language, referral_code, 1 if user_type == 'advertiser' else 0))
        
        self.connection.commit()
        return self.get_user(user_id)
    
    def update_user_language(self, user_id, language):
        """Kullanıcı dilini güncelle"""
        self.cursor.execute('''
            UPDATE users SET language = ? WHERE user_id = ?
        ''', (language, user_id))
        self.connection.commit()
    
    def update_user_type(self, user_id, user_type):
        """Kullanıcı türünü güncelle"""
        is_advertiser = 1 if user_type == 'advertiser' else 0
        self.cursor.execute('''
            UPDATE users SET user_type = ?, is_advertiser = ? WHERE user_id = ?
        ''', (user_type, is_advertiser, user_id))
        self.connection.commit()
    
    def update_user_balance(self, user_id, amount, is_advertiser_balance=False):
        """Kullanıcı bakiyesini güncelle"""
        column = 'advertiser_balance' if is_advertiser_balance else 'balance'
        self.cursor.execute(f'''
            UPDATE users SET {column} = {column} + ? WHERE user_id = ?
        ''', (amount, user_id))
        
        if not is_advertiser_balance and amount > 0:
            self.cursor.execute('''
                UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?
            ''', (amount, user_id))
        
        self.connection.commit()
    
    def update_last_active(self, user_id):
        """Son aktif zamanını güncelle"""
        now = datetime.now().isoformat()
        self.cursor.execute('''
            UPDATE users SET last_active = ? WHERE user_id = ?
        ''', (now, user_id))
        self.connection.commit()
    
    def create_deposit(self, user_id, amount_usd, amount_try, trx_amount, address):
        """Depozit kaydı oluştur"""
        self.cursor.execute('''
            INSERT INTO deposits 
            (user_id, amount_usd, amount_try, trx_amount, address, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (user_id, amount_usd, amount_try, trx_amount, address))
        self.connection.commit()
        return self.cursor.lastrowid
    
    def create_withdrawal(self, user_id, amount_usd, address):
        """Çekim kaydı oluştur"""
        self.cursor.execute('''
            INSERT INTO withdrawals 
            (user_id, amount_usd, address, status)
            VALUES (?, ?, ?, 'pending')
        ''', (user_id, amount_usd, address))
        self.connection.commit()
        return self.cursor.lastrowid
    
    def create_task(self, advertiser_id, task_type, title, description, link, participants_needed, reward_per_user):
        """Görev oluştur"""
        total_spent = reward_per_user * participants_needed
        
        self.cursor.execute('''
            INSERT INTO tasks 
            (advertiser_id, task_type, title, description, link, participants_needed, reward_per_user, total_spent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (advertiser_id, task_type, title, description, link, participants_needed, reward_per_user, total_spent))
        
        task_id = self.cursor.lastrowid
        
        # Reklamveren bakiyesinden düş
        self.update_user_balance(advertiser_id, -total_spent, is_advertiser_balance=True)
        
        self.connection.commit()
        return task_id
    
    def join_task(self, task_id, user_id):
        """Göreve katıl"""
        # Önce katılıp katılmadığını kontrol et
        self.cursor.execute('''
            SELECT COUNT(*) FROM task_participations 
            WHERE task_id = ? AND user_id = ?
        ''', (task_id, user_id))
        
        if self.cursor.fetchone()[0] > 0:
            return False, "already_joined"
        
        # Görev detaylarını al
        self.cursor.execute('''
            SELECT participants_needed, participants_current, reward_per_user
            FROM tasks WHERE id = ? AND status = 'active'
        ''', (task_id,))
        
        task = self.cursor.fetchone()
        if not task:
            return False, "task_not_found"
        
        if task['participants_current'] >= task['participants_needed']:
            return False, "task_full"
        
        # Katılım kaydı oluştur
        self.cursor.execute('''
            INSERT INTO task_participations (task_id, user_id, status)
            VALUES (?, ?, 'pending')
        ''', (task_id, user_id))
        
        # Görev katılımcı sayısını güncelle
        self.cursor.execute('''
            UPDATE tasks SET participants_current = participants_current + 1 
            WHERE id = ?
        ''', (task_id,))
        
        self.connection.commit()
        return True, "success"
    
    def verify_task_participation(self, participation_id):
        """Görev katılımını doğrula"""
        self.cursor.execute('''
            SELECT tp.*, t.reward_per_user, t.advertiser_id
            FROM task_participations tp
            JOIN tasks t ON tp.task_id = t.id
            WHERE tp.id = ?
        ''', (participation_id,))
        
        participation = self.cursor.fetchone()
        if not participation:
            return False
        
        now = datetime.now().isoformat()
        
        # Katılımı doğrula
        self.cursor.execute('''
            UPDATE task_participations 
            SET status = 'verified', verified_at = ?, paid_at = ?, reward_paid = ?
            WHERE id = ?
        ''', (now, now, participation['reward_per_user'], participation_id))
        
        # Kullanıcıya ödeme yap
        self.update_user_balance(participation['user_id'], participation['reward_per_user'])
        
        # Görev tamamlanma sayısını artır
        self.cursor.execute('''
            UPDATE users SET tasks_completed = tasks_completed + 1 
            WHERE user_id = ?
        ''', (participation['user_id'],))
        
        self.connection.commit()
        return True

# Bot Sınıfı
class TaskizBot:
    def __init__(self):
        self.db = Database()
        self.converter = CurrencyConverter()
        self.stats_notifier = StatsNotifier(self.db)
        self.user_states = {}  # Kullanıcı durumlarını takip et
        self.stats_notifier.start()
        print("🤖 TaskizBot başlatıldı!")
    
    def handle_update(self, update):
        """Gelen update'i işle"""
        try:
            if 'message' in update:
                self.handle_message(update['message'])
            elif 'callback_query' in update:
                self.handle_callback_query(update['callback_query'])
        except Exception as e:
            print(f"❌ Update işleme hatası: {e}")
    
    def handle_message(self, message):
        """Gelen mesajı işle"""
        if 'text' not in message:
            return
        
        user_id = message['from']['id']
        text = message['text']
        
        # Kullanıcıyı veritabanında ara veya oluştur
        user = self.db.get_user(user_id)
        
        if not user:
            # Yeni kullanıcı kayıt akışı
            self.welcome_new_user(message)
            return
        
        # Son aktif zamanını güncelle
        self.db.update_last_active(user_id)
        
        # Kullanıcı tipini kontrol et
        if not user.get('user_type'):
            self.ask_user_type(user_id)
            return
        
        # Zorunlu kanalları kontrol et
        if not self.check_mandatory_channels(user_id):
            self.show_mandatory_channels(user_id, user.get('language', 'tr'))
            return
        
        # Komutları işle
        self.process_command(user_id, text, user)
    
    def welcome_new_user(self, message):
        """Yeni kullanıcıyı karşıla"""
        user_id = message['from']['id']
        username = message['from'].get('username', '')
        first_name = message['from'].get('first_name', '')
        last_name = message['from'].get('last_name', '')
        
        # Kullanıcıyı oluştur (varsayılan tür: earner)
        user = self.db.create_user(user_id, username, first_name, last_name)
        
        # Kullanıcı tipi seçme ekranını göster
        self.ask_user_type(user_id)
    
    def ask_user_type(self, user_id):
        """Kullanıcıdan tipini seçmesini iste"""
        # İlk önce dil seçeneği sun (çok dilli mesaj)
        welcome_text = """
🎯 *Welcome! Please select your user type:*
        
👤 *Earner (Para Kazanan)*
• Earn money by completing tasks
• Watch ads, join channels
• Get daily bonuses
        
📢 *Advertiser (Reklamveren)*
• Create and publish tasks
• Load advertising budget
• Reach audience and promote your product
        
*Hoş Geldiniz! Lütfen kullanıcı türünüzü seçin:*
        
👤 *Para Kazanan*
• Görev yaparak para kazan
• Reklam izle, kanallara katıl
• Günlük bonuslar al
        
📢 *Reklamveren*
• Görev oluştur ve yayınla
• Reklam bütçesi yükle
• Kitleye ulaş ve ürününü tanıt
        
*Добро пожаловать! Пожалуйста, выберите тип пользователя:*
        
👤 *Зарабатывающий*
• Зарабатывайте деньги, выполняя задания
• Смотрите рекламу, присоединяйтесь к каналам
• Получайте ежедневные бонусы
        
📢 *Рекламодатель*
• Создавайте и публикуйте задания
• Пополняйте рекламный бюджет
• Достигайте аудиторию и продвигайте свой продукт
        
*স্বাগতম! অনুগ্রহ করে আপনার ব্যবহারকারীর ধরণ নির্বাচন করুন:*
        
👤 *আয়কারী*
• টাস্ক সম্পূর্ণ করে অর্থ উপার্জন করুন
• বিজ্ঞাপন দেখুন, চ্যানেলে যোগ দিন
• দৈনিক বোনাস পান
        
📢 *বিজ্ঞাপনদাতা*
• টাস্ক তৈরি করুন এবং প্রকাশ করুন
• বিজ্ঞাপন বাজেট লোড করুন
• দর্শকদের কাছে পৌঁছান এবং আপনার পণ্য প্রচার করুন
        
What type of user do you want to be?
Hangi tür kullanıcı olmak istiyorsunuz?
Каким типом пользователя вы хотите быть?
আপনি কি ধরণের ব্যবহারকারী হতে চান?
        """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '👤 Earner / Para Kazanan', 'callback_data': 'user_type_earner'},
                    {'text': '📢 Advertiser / Reklamveren', 'callback_data': 'user_type_advertiser'}
                ]
            ]
        }
        
        send_message(user_id, welcome_text, reply_markup=keyboard)
    
    def ask_language_selection(self, user_id, user_type):
        """Kullanıcı tipinden sonra dil seçtir"""
        user = self.db.get_user(user_id)
        current_lang = user.get('language', 'tr') if user else 'tr'
        
        # Kullanıcının mevcut dili varsa o dilde mesaj gönder
        if user and current_lang in LANGUAGE_TEXTS:
            texts = LANGUAGE_TEXTS[current_lang]
            text = texts['registration']['language_selection']
        else:
            # Çok dilli mesaj
            text = """
🌍 *Please select your language*
Lütfen dilinizi seçin
Пожалуйста, выберите ваш язык
অনুগ্রহ করে আপনার ভাষা নির্বাচন করুন
            """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '🇹🇷 Türkçe', 'callback_data': f'lang_tr_{user_type}'},
                    {'text': '🇺🇸 English', 'callback_data': f'lang_en_{user_type}'}
                ],
                [
                    {'text': '🇷🇺 Русский', 'callback_data': f'lang_ru_{user_type}'},
                    {'text': '🇧🇩 বাংলা', 'callback_data': f'lang_bn_{user_type}'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_callback_query(self, callback_query):
        """Callback query'leri işle"""
        data = callback_query['data']
        user_id = callback_query['from']['id']
        message_id = callback_query['message']['message_id']
        chat_id = callback_query['message']['chat']['id']
        
        try:
            if data.startswith('user_type_'):
                user_type = data.split('_')[2]
                self.handle_user_type_selection(user_id, user_type, callback_query['id'])
                
            elif data.startswith('lang_'):
                parts = data.split('_')
                if len(parts) >= 3:
                    language = parts[1]
                    user_type = parts[2]
                    self.handle_language_selection(user_id, language, user_type, callback_query['id'])
            
            elif data == 'change_user_type':
                self.handle_change_user_type(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data == 'change_language':
                self.handle_change_language(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data == 'back_to_main':
                user = self.db.get_user(user_id)
                if user:
                    self.show_main_menu(user_id, user.get('language', 'tr'), user.get('user_type', 'earner'))
                answer_callback_query(callback_query['id'])
                
            elif data == 'back_to_profile':
                self.show_profile_settings(user_id)
                answer_callback_query(callback_query['id'])
                
            elif data.startswith('set_lang_'):
                language = data.split('_')[2]
                self.db.update_user_language(user_id, language)
                
                user = self.db.get_user(user_id)
                texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
                
                # Onay mesajı
                answer_callback_query(callback_query['id'], texts['success']['language_set'])
                
                # Profil sayfasına geri dön
                time.sleep(0.5)
                self.show_profile_settings(user_id)
                
            elif data.startswith('confirm_change_to_'):
                new_type = data.split('_')[3]  # earner veya advertiser
                self.confirm_user_type_change(user_id, new_type, callback_query['id'])
        
        except Exception as e:
            print(f"❌ Callback işleme hatası: {e}")
            answer_callback_query(callback_query['id'], "❌ Bir hata oluştu!")
    
    def handle_user_type_selection(self, user_id, user_type, callback_id):
        """Kullanıcı tipi seçimini işle"""
        # Kullanıcı tipini kaydet
        self.db.update_user_type(user_id, user_type)
        
        # Dil seçimine geç
        self.ask_language_selection(user_id, user_type)
        
        answer_callback_query(callback_id, "✅ User type selected! / Kullanıcı türü seçildi!")
    
    def handle_language_selection(self, user_id, language, user_type, callback_id):
        """Dil seçimini işle"""
        # Dil ve kullanıcı tipini kaydet
        self.db.update_user_language(user_id, language)
        self.db.update_user_type(user_id, user_type)
        
        # Onay mesajı
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Zorunlu kanalları kontrol et
        if not self.check_mandatory_channels(user_id):
            answer_callback_query(callback_id, texts['success']['user_type_set'])
            time.sleep(0.5)
            self.show_mandatory_channels(user_id, language)
        else:
            answer_callback_query(callback_id, texts['success']['registration_complete'])
            time.sleep(0.5)
            self.show_main_menu(user_id, language, user_type)
    
    def check_mandatory_channels(self, user_id):
        """Kullanıcının zorunlu kanallara katılıp katılmadığını kontrol et"""
        for channel_key, channel_info in MANDATORY_CHANNELS.items():
            if not get_chat_member(f"@{channel_info['username']}", user_id):
                return False
        return True
    
    def show_mandatory_channels(self, user_id, language='tr'):
        """Zorunlu kanalları göster"""
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        message = f"""
{texts['channels']['description']}

"""
        
        buttons = []
        for channel_key, channel_info in MANDATORY_CHANNELS.items():
            channel_name_key = channel_key
            if channel_name_key in texts['channels']:
                display_name = texts['channels'][channel_name_key]
            else:
                display_name = channel_info['name']
            
            message += f"{display_name}: @{channel_info['username']}\n"
            
            buttons.append([
                {
                    'text': f"✅ {display_name}",
                    'url': channel_info['link']
                }
            ])
        
        # Kontrol butonu
        buttons.append([
            {
                'text': texts['buttons']['check_channels'],
                'callback_data': 'check_channels'
            },
            {
                'text': texts['buttons']['join_all_channels'],
                'url': MANDATORY_CHANNELS['main']['link']
            }
        ])
        
        keyboard = {'inline_keyboard': buttons}
        
        send_message(user_id, message, reply_markup=keyboard)
    
    def process_command(self, user_id, text, user):
        """Komutları işle"""
        language = user.get('language', 'tr')
        user_type = user.get('user_type', 'earner')
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        if text == '/start':
            self.show_main_menu(user_id, language, user_type)
        
        elif text == texts['buttons']['profile'] or text == '/profile':
            self.show_profile_settings(user_id)
        
        elif text == texts['buttons']['do_task']:
            if user_type != 'earner':
                send_message(user_id, texts['errors']['unauthorized'])
            else:
                self.show_available_tasks(user_id, language)
        
        elif text == texts['buttons']['create_task']:
            if user_type != 'advertiser':
                send_message(user_id, texts['errors']['unauthorized'])
            else:
                self.start_create_task(user_id, language)
        
        elif text == texts['buttons']['balance']:
            self.show_balance(user_id, language)
        
        elif text == texts['buttons']['load_balance']:
            self.show_deposit_options(user_id, language)
        
        elif text == texts['buttons']['withdraw']:
            self.start_withdrawal(user_id, language)
        
        elif text == texts['buttons']['stats']:
            self.show_stats(user_id, language)
        
        elif text == texts['buttons']['referral']:
            self.show_referral_info(user_id, language)
        
        elif text == '/help' or text == texts['buttons']['help']:
            self.show_help(user_id, language)
        
        elif text == '/channels' or text == texts['buttons']['check_channels']:
            self.show_mandatory_channels(user_id, language)
        
        else:
            # Özel durumları kontrol et (state-based işlemler)
            if user_id in self.user_states:
                state = self.user_states[user_id]
                if state['action'] == 'waiting_deposit_amount':
                    self.handle_deposit_amount(user_id, text, language)
                elif state['action'] == 'waiting_withdrawal_amount':
                    self.handle_withdrawal_amount(user_id, text, language)
                elif state['action'] == 'waiting_withdrawal_address':
                    self.handle_withdrawal_address(user_id, text, language)
                elif state['action'] == 'waiting_task_title':
                    self.handle_task_title(user_id, text, language)
                # Diğer state'ler...
            else:
                # Bilinmeyen komut
                send_message(user_id, texts['errors']['not_found'])
    
    def show_main_menu(self, user_id, language='tr', user_type='earner'):
        """Ana menüyü göster"""
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        if user_type == 'advertiser':
            # REKLAMVEREN MENÜSÜ
            keyboard = {
                'keyboard': [
                    [texts['buttons']['create_task']],
                    [texts['buttons']['advertiser_balance'], texts['buttons']['load_balance']],
                    [texts['buttons']['my_tasks'], texts['buttons']['stats']],
                    [texts['buttons']['profile'], texts['buttons']['help']]
                ],
                'resize_keyboard': True
            }
            
            text = f"""
📢 *{texts['menu']['advertiser_balance']}*
            
Hoş geldiniz! Görev oluşturup kitleye ulaşabilirsiniz.
            """
        
        else:
            # PARA KAZANAN MENÜSÜ
            keyboard = {
                'keyboard': [
                    [texts['buttons']['do_task']],
                    [texts['buttons']['balance'], texts['buttons']['withdraw']],
                    [texts['buttons']['referral'], texts['buttons']['stats']],
                    [texts['buttons']['profile'], texts['buttons']['help']]
                ],
                'resize_keyboard': True
            }
            
            text = f"""
👤 *{texts['menu']['welcome']}*
            
Hoş geldiniz! Görevleri tamamlayarak para kazanabilirsiniz.
            """
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_profile_settings(self, user_id):
        """Profil ayarlarını göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user.get('language', 'tr')
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Kullanıcı türü metni
        user_type_text = ''
        if user['user_type'] == 'advertiser':
            user_type_text = '📢 Reklamveren'
            if language == 'en':
                user_type_text = '📢 Advertiser'
            elif language == 'ru':
                user_type_text = '📢 Рекламодатель'
            elif language == 'bn':
                user_type_text = '📢 বিজ্ঞাপনদাতা'
        else:
            user_type_text = '👤 Para Kazanan'
            if language == 'en':
                user_type_text = '👤 Earner'
            elif language == 'ru':
                user_type_text = '👤 Зарабатывающий'
            elif language == 'bn':
                user_type_text = '👤 আয়কারী'
        
        # Dil metni
        lang_info = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES['tr'])
        language_text = f"{lang_info['name']} {lang_info['flag']}"
        
        # Bakiye
        balance = user['balance']
        currency_code = lang_info['currency']
        formatted_balance = self.converter.format_currency(balance, currency_code)
        
        text = f"""
{texts['profile']['title']}

{texts['profile']['user_id'].format(id=user_id)}
{texts['profile']['user_type'].format(type=user_type_text)}
{texts['profile']['language'].format(language=language_text)}
{texts['profile']['registration_date'].format(date=user['created_at'][:10] if user['created_at'] else '-')}
{texts['profile']['balance'].format(balance=formatted_balance)}
{texts['profile']['tasks_completed'].format(count=user['tasks_completed'])}
        """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': texts['buttons']['change_language'], 'callback_data': 'change_language'},
                    {'text': texts['buttons']['change_user_type'], 'callback_data': 'change_user_type'}
                ],
                [
                    {'text': texts['buttons']['back'], 'callback_data': 'back_to_main'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def handle_change_user_type(self, user_id):
        """Kullanıcı türünü değiştirme ekranı"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user.get('language', 'tr')
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        current_type = user.get('user_type', 'earner')
        current_type_text = 'Reklamveren' if current_type == 'advertiser' else 'Para Kazanan'
        if language == 'en':
            current_type_text = 'Advertiser' if current_type == 'advertiser' else 'Earner'
        elif language == 'ru':
            current_type_text = 'Рекламодатель' if current_type == 'advertiser' else 'Зарабатывающий'
        elif language == 'bn':
            current_type_text = 'বিজ্ঞাপনদাতা' if current_type == 'advertiser' else 'আয়কারী'
        
        text = f"""
🔄 *{texts['buttons']['change_user_type']}*
        
{texts['profile']['user_type'].format(type=current_type_text)}
        
⚠️ {texts['errors']['active_tasks_exist'] if 'active_tasks_exist' in texts['errors'] else 'Cannot change type while you have active tasks!'}
        
Yeni türünüzü seçin:
        """
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '👤 Para Kazanan', 'callback_data': 'confirm_change_to_earner'},
                    {'text': '📢 Reklamveren', 'callback_data': 'confirm_change_to_advertiser'}
                ],
                [
                    {'text': texts['buttons']['back'], 'callback_data': 'back_to_profile'}
                ]
            ]
        }
        
        # Dil bazında buton metinleri
        if language == 'en':
            keyboard['inline_keyboard'][0][0]['text'] = '👤 Earner'
            keyboard['inline_keyboard'][0][1]['text'] = '📢 Advertiser'
        elif language == 'ru':
            keyboard['inline_keyboard'][0][0]['text'] = '👤 Зарабатывающий'
            keyboard['inline_keyboard'][0][1]['text'] = '📢 Рекламодатель'
        elif language == 'bn':
            keyboard['inline_keyboard'][0][0]['text'] = '👤 আয়কারী'
            keyboard['inline_keyboard'][0][1]['text'] = '📢 বিজ্ঞাপনদাতা'
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def confirm_user_type_change(self, user_id, new_type, callback_id):
        """Kullanıcı türü değişimini onayla"""
        user = self.db.get_user(user_id)
        if not user:
            answer_callback_query(callback_id, "❌ Kullanıcı bulunamadı!")
            return
        
        language = user.get('language', 'tr')
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Aktif görev kontrolü
        self.db.cursor.execute('''
            SELECT COUNT(*) FROM task_participations 
            WHERE user_id = ? AND status = 'active'
        ''', (user_id,))
        active_tasks = self.db.cursor.fetchone()[0]
        
        if active_tasks > 0:
            answer_callback_query(callback_id, texts['errors']['active_tasks_exist'], show_alert=True)
            return
        
        # Reklamveren olmak için bakiye kontrolü
        if new_type == 'advertiser' and user['balance'] < 10.0:
            min_amount = self.converter.format_currency(10.0, SUPPORTED_LANGUAGES[language]['currency'])
            error_msg = texts['errors']['min_balance_for_advertiser'].format(amount=min_amount)
            answer_callback_query(callback_id, error_msg, show_alert=True)
            return
        
        # Türü değiştir
        self.db.update_user_type(user_id, new_type)
        
        # Onay mesajı
        new_type_text = 'Reklamveren' if new_type == 'advertiser' else 'Para Kazanan'
        if language == 'en':
            new_type_text = 'Advertiser' if new_type == 'advertiser' else 'Earner'
        elif language == 'ru':
            new_type_text = 'Рекламодатель' if new_type == 'advertiser' else 'Зарабатывающий'
        elif language == 'bn':
            new_type_text = 'বিজ্ঞাপনদাতা' if new_type == 'advertiser' else 'আয়কারী'
        
        success_msg = f"✅ {texts['success']['user_type_changed']}\n\nYeni tür: {new_type_text}"
        answer_callback_query(callback_id, success_msg, show_alert=True)
        
        # Ana menüyü göster
        time.sleep(1)
        self.show_main_menu(user_id, language, new_type)
    
    def handle_change_language(self, user_id):
        """Dil değiştirme ekranı"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        language = user.get('language', 'tr')
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = texts['registration']['language_selection']
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '🇹🇷 Türkçe', 'callback_data': 'set_lang_tr'},
                    {'text': '🇺🇸 English', 'callback_data': 'set_lang_en'}
                ],
                [
                    {'text': '🇷🇺 Русский', 'callback_data': 'set_lang_ru'},
                    {'text': '🇧🇩 বাংলা', 'callback_data': 'set_lang_bn'}
                ],
                [
                    {'text': texts['buttons']['back'], 'callback_data': 'back_to_profile'}
                ]
            ]
        }
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def show_balance(self, user_id, language='tr'):
        """Bakiye bilgisini göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        lang_info = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES['tr'])
        
        # Bakiye bilgileri
        balance = user['balance']
        advertiser_balance = user['advertiser_balance']
        
        # Formatla
        currency_code = lang_info['currency']
        formatted_balance = self.converter.format_currency(balance, currency_code)
        formatted_ad_balance = self.converter.format_currency(advertiser_balance, currency_code)
        
        text = f"""
💰 *{texts['menu']['balance']}*

{texts['menu']['balance']}: {formatted_balance}
{texts['menu']['advertiser_balance']}: {formatted_ad_balance}
{texts['menu']['tasks_completed']}: {user['tasks_completed']}
{texts['menu']['total_earned']}: {self.converter.format_currency(user['total_earned'], currency_code)}
        """
        
        send_message(user_id, text)
    
    def show_deposit_options(self, user_id, language='tr'):
        """Depozit seçeneklerini göster"""
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
💰 *{texts['buttons']['load_balance']}*

Minimum depozit: ${MIN_DEPOSIT_USD}
Maximum depozit: ${MAX_DEPOSIT_USD}

Lütfen yüklemek istediğiniz USD miktarını girin:
        """
        
        # Kullanıcı durumunu ayarla
        self.user_states[user_id] = {
            'action': 'waiting_deposit_amount',
            'data': {}
        }
        
        send_message(user_id, text)
    
    def handle_deposit_amount(self, user_id, text, language):
        """Depozit miktarını işle"""
        try:
            amount = float(text)
            
            if amount < MIN_DEPOSIT_USD:
                error_text = f"Minimum depozit ${MIN_DEPOSIT_USD}"
                send_message(user_id, f"❌ {error_text}")
                return
            
            if amount > MAX_DEPOSIT_USD:
                error_text = f"Maximum depozit ${MAX_DEPOSIT_USD}"
                send_message(user_id, f"❌ {error_text}")
                return
            
            # TRX miktarını hesapla (basit bir oranla)
            trx_amount = amount * 100  # 1 USD = 100 TRX varsayalım
            
            texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
            
            response_text = f"""
✅ *Depozit Talebi*

Miktar: ${amount:.2f}
TRX Miktarı: {trx_amount:.2f} TRX

Lütfen {trx_amount:.2f} TRX'yi aşağıdaki adrese gönderin:

`{TRX_ADDRESS}`

⚠️ Sadece TRX (Tron) gönderin!
⚠️ Farklı coin gönderirseniz kaybolur!
            """
            
            # Durumu temizle
            if user_id in self.user_states:
                del self.user_states[user_id]
            
            send_message(user_id, response_text)
            
        except ValueError:
            texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
            send_message(user_id, texts['errors']['invalid_number'])
    
    def start_withdrawal(self, user_id, language='tr'):
        """Para çekme işlemini başlat"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Minimum çekim kontrolü
        if user['balance'] < MIN_WITHDRAW:
            min_amount = self.converter.format_currency(MIN_WITHDRAW, SUPPORTED_LANGUAGES[language]['currency'])
            error_msg = texts['errors']['min_withdraw'].format(amount=min_amount)
            send_message(user_id, f"❌ {error_msg}")
            return
        
        text = f"""
🏧 *{texts['buttons']['withdraw']}*

Mevcut bakiye: ${user['balance']:.2f}
Minimum çekim: ${MIN_WITHDRAW:.2f}

Lütfen çekmek istediğiniz USD miktarını girin:
        """
        
        # Kullanıcı durumunu ayarla
        self.user_states[user_id] = {
            'action': 'waiting_withdrawal_amount',
            'data': {}
        }
        
        send_message(user_id, text)
    
    def handle_withdrawal_amount(self, user_id, text, language):
        """Çekim miktarını işle"""
        try:
            amount = float(text)
            user = self.db.get_user(user_id)
            
            if not user:
                return
            
            # Minimum kontrol
            if amount < MIN_WITHDRAW:
                min_amount = self.converter.format_currency(MIN_WITHDRAW, SUPPORTED_LANGUAGES[language]['currency'])
                texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
                error_msg = texts['errors']['min_withdraw'].format(amount=min_amount)
                send_message(user_id, f"❌ {error_msg}")
                return
            
            # Bakiye kontrolü
            if amount > user['balance']:
                texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
                send_message(user_id, texts['errors']['insufficient_balance'])
                return
            
            # Durumu güncelle
            self.user_states[user_id] = {
                'action': 'waiting_withdrawal_address',
                'data': {'amount': amount}
            }
            
            texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
            
            prompt_text = f"""
✅ Miktar: ${amount:.2f}

Şimdi TRX (Tron) cüzdan adresinizi girin:

⚠️ Adresi dikkatli kontrol edin!
⚠️ Yanlış adres gönderim kaybına neden olur!
            """
            
            send_message(user_id, prompt_text)
            
        except ValueError:
            texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
            send_message(user_id, texts['errors']['invalid_number'])
    
    def handle_withdrawal_address(self, user_id, text, language):
        """Çekim adresini işle"""
        if user_id not in self.user_states:
            return
        
        address = text.strip()
        amount = self.user_states[user_id]['data']['amount']
        
        # Basit adres validasyonu (gerçek uygulamada daha detaylı olmalı)
        if len(address) < 20:
            texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
            send_message(user_id, texts['errors']['invalid_address'])
            return
        
        # Çekim kaydı oluştur
        self.db.create_withdrawal(user_id, amount, address)
        
        # Durumu temizle
        del self.user_states[user_id]
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        response_text = f"""
✅ *{texts['success']['withdraw_requested']}*

Miktar: ${amount:.2f}
Adres: `{address[:10]}...{address[-10:]}`

Çekim talebiniz alındı. 24 saat içinde işleme alınacaktır.
        """
        
        send_message(user_id, response_text)
        
        # Admin'e bildir
        admin_text = f"""
⚠️ *YENİ ÇEKİM TALEBİ*

Kullanıcı: @{self.db.get_user(user_id)['username'] or user_id}
Miktar: ${amount:.2f}
Adres: {address}
        """
        send_message(ADMIN_ID, admin_text)
    
    def show_available_tasks(self, user_id, language='tr'):
        """Mevcut görevleri göster"""
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Aktif görevleri getir
        self.db.cursor.execute('''
            SELECT * FROM tasks 
            WHERE status = 'active' 
            AND participants_current < participants_needed
            ORDER BY created_at DESC
            LIMIT 10
        ''')
        
        tasks = self.db.cursor.fetchall()
        
        if not tasks:
            text = """
🎯 *Görevler*

Şu anda mevcut görev bulunmuyor.

Daha sonra tekrar kontrol edin veya reklamveren olup kendi görevlerinizi oluşturun!
            """
            send_message(user_id, text)
            return
        
        text = "🎯 *Mevcut Görevler*\n\n"
        
        keyboard_buttons = []
        
        for task in tasks:
            reward_usd = task['reward_per_user']
            lang_info = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES['tr'])
            reward_local = self.converter.convert_from_usd(reward_usd, lang_info['currency'])
            formatted_reward = self.converter.format_currency(reward_local, lang_info['currency'])
            
            text += f"""
🔸 *{task['title']}*
📝 {task['description'][:50]}...
💰 Ödül: {formatted_review}
👥 {task['participants_current']}/{task['participants_needed']} kişi
            """
            
            keyboard_buttons.append([
                {
                    'text': f"✅ Katıl: {task['title'][:20]}...",
                    'callback_data': f'join_task_{task["id"]}'
                }
            ])
        
        keyboard = {'inline_keyboard': keyboard_buttons}
        
        send_message(user_id, text, reply_markup=keyboard)
    
    def start_create_task(self, user_id, language='tr'):
        """Görev oluşturmayı başlat"""
        user = self.db.get_user(user_id)
        if not user or user['user_type'] != 'advertiser':
            return
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Reklamveren bakiyesini kontrol et
        if user['advertiser_balance'] < 1.0:  # Minimum görev maliyeti
            text = f"""
❌ *Yetersiz Reklam Bütçesi*

Mevcut reklam bakiyeniz: ${user['advertiser_balance']:.2f}
Minimum görev oluşturmak için: $1.00

Lütfen önce bakiye yükleyin.
            """
            send_message(user_id, text)
            return
        
        text = f"""
➕ *{texts['buttons']['create_task']}*

Mevcut reklam bakiyeniz: ${user['advertiser_balance']:.2f}

Lütfen görev başlığını girin:
        """
        
        # Kullanıcı durumunu ayarla
        self.user_states[user_id] = {
            'action': 'waiting_task_title',
            'data': {'step': 1}
        }
        
        send_message(user_id, text)
    
    def handle_task_title(self, user_id, text, language):
        """Görev başlığını işle"""
        if user_id not in self.user_states:
            return
        
        title = text.strip()
        
        if len(title) < 5:
            send_message(user_id, "❌ Başlık en az 5 karakter olmalıdır!")
            return
        
        # Durumu güncelle
        self.user_states[user_id]['data']['title'] = title
        self.user_states[user_id]['data']['step'] = 2
        self.user_states[user_id]['action'] = 'waiting_task_description'
        
        send_message(user_id, "📝 Şimdi görev açıklamasını girin:")
    
    def show_stats(self, user_id, language='tr'):
        """İstatistikleri göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Toplam kullanıcı
        self.db.cursor.execute("SELECT COUNT(*) FROM users")
        total_users = self.db.cursor.fetchone()[0]
        
        # Aktif kullanıcılar (son 24 saat)
        yesterday = (datetime.now() - timedelta(hours=24)).isoformat()
        self.db.cursor.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (yesterday,))
        active_users = self.db.cursor.fetchone()[0]
        
        # Toplam bakiye
        self.db.cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = self.db.cursor.fetchone()[0] or 0
        
        # Bugünkü görevler
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        self.db.cursor.execute('''
            SELECT COUNT(*), SUM(total_spent) 
            FROM tasks 
            WHERE created_at > ?
        ''', (today_start,))
        today_tasks_result = self.db.cursor.fetchone()
        today_tasks = today_tasks_result[0] or 0
        today_tasks_spent = today_tasks_result[1] or 0
        
        text = f"""
📊 *{texts['menu']['stats']}*

👥 Toplam Kullanıcı: {total_users}
📈 Aktif Kullanıcılar (24s): {active_users}
💰 Toplam Sistem Bakiyesi: ${total_balance:.2f}
🎯 Bugünkü Görevler: {today_tasks}
💸 Bugünkü Harcama: ${today_tasks_spent:.2f}
        """
        
        send_message(user_id, text)
    
    def show_referral_info(self, user_id, language='tr'):
        """Referans bilgilerini göster"""
        user = self.db.get_user(user_id)
        if not user:
            return
        
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        # Referans sayısı
        self.db.cursor.execute('''
            SELECT COUNT(*) FROM referrals WHERE referrer_id = ?
        ''', (user_id,))
        referral_count = self.db.cursor.fetchone()[0]
        
        # Toplam referans kazancı
        self.db.cursor.execute('''
            SELECT SUM(earned_amount) FROM referrals WHERE referrer_id = ?
        ''', (user_id,))
        total_earned = self.db.cursor.fetchone()[0] or 0
        
        referral_code = user['referral_code']
        referral_link = f"https://t.me/{(TOKEN.split(':')[0])}?start={referral_code}"
        
        text = f"""
👥 *{texts['menu']['referrals']}*

🔗 Referans Linkiniz:
`{referral_link}`

📊 Referans Kodunuz: `{referral_code}`
👥 Toplam Referans: {referral_count}
💰 Referans Kazancı: ${total_earned:.2f}

💡 *Nasıl Çalışır?*
1. Linkinizi paylaşın
2. Arkadaşlarınız botu kullanmaya başlasın
3. Onlar görev yaptıkça siz kazanın!
        """
        
        send_message(user_id, text)
    
    def show_help(self, user_id, language='tr'):
        """Yardım mesajını göster"""
        texts = LANGUAGE_TEXTS.get(language, LANGUAGE_TEXTS['tr'])
        
        text = f"""
❓ *{texts['menu']['help']}*

🤖 *TaskizBot Nedir?*
TaskizBot, görev tamamlayarak para kazanabileceğiniz veya reklam vererek kitlenize ulaşabileceğiniz bir platformdur.

🎯 *Para Kazananlar İçin:*
• Görevleri tamamlayarak para kazanın
• Kanallara katılın, reklam izleyin
• Referanslarınızı davet edin, onlar kazandıkça siz de kazanın

📢 *Reklamverenler İçin:*
• Görev oluşturun, kitlenize ulaşın
• Bütçenizi yönetin
• Kampanyalarınızın performansını takip edin

💰 *Ödemeler:*
• Minimum çekim: ${MIN_WITHDRAW}
• TRX (Tron) cüzdanınıza ödeme
• Hızlı ve güvenli işlemler

⚠️ *Önemli Kurallar:*
• Sahte görev tamamlamak yasaktır
• Aynı göreve birden fazla kez katılamazsınız
• Kurallara uymayanlar banlanır

📞 *Destek:*
Sorularınız için @EarnTether2026 kanalına mesaj atın.
        """
        
        send_message(user_id, text)

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
                time.sleep(300)  # 5 dakika
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
        
        # Bugünkü görevler
        today_tasks = 0
        today_tasks_spent = 0
        
        # Bugünkü kazanç
        today_earnings = 0
        
        message = f"""
📊 *TASKIZBOT CANLI İSTATİSTİKLER*
⏰ {now.strftime('%d.%m.%Y %H:%M')} (TR)

👥 Toplam Kullanıcı: {total_users}
📈 Aktif Kullanıcılar: {active_users}
📢 Reklamverenler: {total_advertisers}

💰 Toplam Bakiye: ${total_balance:.2f}
🎯 Reklam Bütçesi: ${total_ad_balance:.2f}

📥 Bugünkü Yüklemeler: {today_deposits}
💸 Bugünkü Harcama: ${today_tasks_spent:.2f}
🎁 Bugünkü Kazanç: ${today_earnings:.2f}

🤖 @{(TOKEN.split(':')[0])}
📢 @EarnTether2026
        """
        
        return message

# Botu başlat
bot = TaskizBot()

# Flask server'ı başlat
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
