# bot.py
import os
import json
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore, db as realtime_db
import uuid
import hashlib
import threading
import time

# 🔧 AYARLAR
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "7904032877")
SUPPORT_USERNAME = "@AlperenTHE"
BOT_USERNAME = "TaskizBot"
STATS_CHANNEL = "@TaskizLive"

# 📊 FIREBASE
cred = credentials.Certificate("taskiz-2db5a-firebase-adminsdk-fbsvc-98e0792e57.json")
firebase_admin.initialize_app(cred, {
    'projectId': 'taskiz-2db5a',
    'databaseURL': 'https://taskiz-2db5a-default-rtdb.firebaseio.com/'
})
db = firestore.client()
rtdb = realtime_db.reference()

# 🌍 DİL SİSTEMİ
LANGUAGES = {
    'tr': {
        'name': 'Türkçe',
        'flag': '🇹🇷',
        'strings': {
            # Ana menü
            'welcome': '🌟 <b>Hoş Geldin {name}!</b>\n\n💰 <b>Bakiyen:</b> <code>${balance:.4f}</code>\n🎯 <b>Görevler:</b> <code>{tasks}</code>\n👥 <b>Referans:</b> <code>{refs}</code>\n🚀 <b>Seviye:</b> {level}\n\n<i>Hemen görevlere başla ve kazan!</i>',
            'menu_tasks': '🎯 Görevler',
            'menu_balance': '💰 Bakiye',
            'menu_deposit': '💳 Yükle',
            'menu_withdraw': '🏧 Çek',
            'menu_referral': '👥 Davet',
            'menu_ads': '📢 Reklam',
            'menu_create_task': '➕ Görev Oluştur',
            'menu_admin': '👑 Admin',
            'menu_settings': '⚙️ Ayarlar',
            
            # Görevler
            'task_types': '🎯 <b>Görev Türleri</b>\n\nHangi tür görev yapmak istersin?',
            'task_channel': '📢 Kanal',
            'task_group': '👥 Grup',
            'task_post': '📝 Post',
            'task_bot': '🤖 Bot',
            'refresh': '🔄 Yenile',
            'no_tasks': '📭 <b>{type} Görevleri</b>\n\nBu türde aktif görev bulunmuyor.',
            
            # Bakiye
            'balance_title': '💰 <b>Bakiye Durumu</b>\n━━━━━━━━━━━━━━━━\n💵 <b>Mevcut:</b> <code>${balance:.4f}</code>\n━━━━━━━━━━━━━━━━\n\n🎯 <b>Toplam Görev:</b> {tasks}\n📈 <b>Toplam Kazanç:</b> <code>${earned:.4f}</code>\n👥 <b>Ref Bonus:</b> <code>${ref_bonus:.4f}</code>\n\n💡 <b>Minimum Çekim:</b> <code>${min_withdraw}</code>',
            
            # Referans
            'referral_title': '👥 <b>Referans Sistemi</b>\n━━━━━━━━━━━━━━━━\n👤 <b>Referansların:</b> <code>{ref_count}</code>\n💰 <b>Toplam Bonus:</b> <code>${total_bonus:.4f}</code>\n🚀 <b>Seviyen:</b> {level}\n━━━━━━━━━━━━━━━━\n\n🎁 <b>Her referans:</b> <code>${ref_bonus}</code>\n💸 <b>Görev komisyonu:</b> %25\n\n🔗 <b>Referans Linkin:</b>\n<code>{ref_link}</code>\n\n📋 <b>Referans Kodun:</b>\n<code>{ref_code}</code>',
            
            # Butonlar
            'back': '🔙 Geri',
            'home': '🏠 Ana Menü',
            'copy_ref': '📋 Linki Kopyala',
            'join': '✅ Katıl',
            'completed': '✅ Tamamladım',
            'cancel': '❌ İptal',
            
            # Mesajlar
            'task_joined': '✅ <b>Göreve Katıldın!</b>\n\n🎯 {title}\n💰 <b>Ödül:</b> <code>${reward:.4f}</code>\n\n📋 <b>Şimdi şunları yap:</b>\n1. Linke tıkla: {link}\n2. Talimatları uygula\n3. Tamamladığında butona bas\n\n⏳ <b>Süre:</b> 24 saat',
            'task_completed': '🎉 <b>Görev Tamamlandı!</b>\n\n💰 <b>Kazanç:</b> <code>${reward:.4f}</code>\n✅ <b>Bakiyene eklendi!</b>\n\n<i>Yeni görevler için görevlere dön.</i>',
            
            # Zorunlu kanal
            'channel_check': '🚫 <b>Zorunlu Kanal Kontrolü</b>\n\nDevam etmek için kanallara katıl:\n{channels}\n\n✅ Katıldıktan sonra <b>Kontrol Et</b> butonuna bas.',
            'check_button': '✅ Kontrol Et',
            
            # Dil seçimi
            'select_language': '🌍 <b>DİL SEÇİMİ / LANGUAGE SELECTION</b>\n\nLütfen kullanmak istediğiniz dili seçiniz.\nPlease select your preferred language.',
            'language_selected': '✅ Dil seçildi!',
        }
    },
    'en': {
        'name': 'English',
        'flag': '🇺🇸',
        'strings': {
            # Main menu
            'welcome': '🌟 <b>Welcome {name}!</b>\n\n💰 <b>Balance:</b> <code>${balance:.4f}</code>\n🎯 <b>Tasks:</b> <code>{tasks}</code>\n👥 <b>Referrals:</b> <code>{refs}</code>\n🚀 <b>Level:</b> {level}\n\n<i>Start tasks and earn now!</i>',
            'menu_tasks': '🎯 Tasks',
            'menu_balance': '💰 Balance',
            'menu_deposit': '💳 Deposit',
            'menu_withdraw': '🏧 Withdraw',
            'menu_referral': '👥 Referral',
            'menu_ads': '📢 Ads',
            'menu_create_task': '➕ Create Task',
            'menu_admin': '👑 Admin',
            'menu_settings': '⚙️ Settings',
            
            # Tasks
            'task_types': '🎯 <b>Task Types</b>\n\nWhich task type do you want?',
            'task_channel': '📢 Channel',
            'task_group': '👥 Group',
            'task_post': '📝 Post',
            'task_bot': '🤖 Bot',
            'refresh': '🔄 Refresh',
            'no_tasks': '📭 <b>{type} Tasks</b>\n\nNo active tasks in this category.',
            
            # Balance
            'balance_title': '💰 <b>Balance Status</b>\n━━━━━━━━━━━━━━━━\n💵 <b>Current:</b> <code>${balance:.4f}</code>\n━━━━━━━━━━━━━━━━\n\n🎯 <b>Total Tasks:</b> {tasks}\n📈 <b>Total Earned:</b> <code>${earned:.4f}</code>\n👥 <b>Ref Bonus:</b> <code>${ref_bonus:.4f}</code>\n\n💡 <b>Min Withdrawal:</b> <code>${min_withdraw}</code>',
            
            # Referral
            'referral_title': '👥 <b>Referral System</b>\n━━━━━━━━━━━━━━━━\n👤 <b>Your Referrals:</b> <code>{ref_count}</code>\n💰 <b>Total Bonus:</b> <code>${total_bonus:.4f}</code>\n🚀 <b>Your Level:</b> {level}\n━━━━━━━━━━━━━━━━\n\n🎁 <b>Per referral:</b> <code>${ref_bonus}</code>\n💸 <b>Task commission:</b> 25%\n\n🔗 <b>Your Referral Link:</b>\n<code>{ref_link}</code>\n\n📋 <b>Your Referral Code:</b>\n<code>{ref_code}</code>',
            
            # Buttons
            'back': '🔙 Back',
            'home': '🏠 Main Menu',
            'copy_ref': '📋 Copy Link',
            'join': '✅ Join',
            'completed': '✅ Completed',
            'cancel': '❌ Cancel',
            
            # Messages
            'task_joined': '✅ <b>Task Joined!</b>\n\n🎯 {title}\n💰 <b>Reward:</b> <code>${reward:.4f}</code>\n\n📋 <b>Now do this:</b>\n1. Click link: {link}\n2. Follow instructions\n3. Click button when done\n\n⏳ <b>Time:</b> 24 hours',
            'task_completed': '🎉 <b>Task Completed!</b>\n\n💰 <b>Earned:</b> <code>${reward:.4f}</code>\n✅ <b>Added to balance!</b>\n\n<i>Return to tasks for more.</i>',
            
            # Channel check
            'channel_check': '🚫 <b>Mandatory Channel Check</b>\n\nJoin these channels to continue:\n{channels}\n\n✅ After joining, tap <b>Check</b> button.',
            'check_button': '✅ Check',
            
            # Language selection
            'select_language': '🌍 <b>DİL SEÇİMİ / LANGUAGE SELECTION</b>\n\nLütfen kullanmak istediğiniz dili seçiniz.\nPlease select your preferred language.',
            'language_selected': '✅ Language selected!',
        }
    }
}

# ⚙️ SİSTEM AYARLARI
TASK_REWARDS = {
    "kanal": 0.0025,
    "grup": 0.0015,
    "post": 0.0005,
    "bot": 0.0010
}

MIN_WITHDRAW = 0.30
REF_BONUS = 0.005
TASK_COMMISSION = 0.25

# 📢 ZORUNLU KANALLAR
MANDATORY_CHANNELS = [
    {"username": "TaskizLive", "link": "https://t.me/TaskizLive", "name": "Ana Kanal", "emoji": "📢"}
]

# 🚀 TELEGRAM FONKSİYONLARI
def send_msg(chat_id, text, buttons=None, markup_type="inline", photo=None, lang='tr'):
    if photo:
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        payload = {
            "chat_id": chat_id,
            "photo": photo,
            "caption": text,
            "parse_mode": "HTML"
        }
    else:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
    
    if buttons:
        if markup_type == "inline":
            payload["reply_markup"] = {"inline_keyboard": buttons}
        else:
            payload["reply_markup"] = {"keyboard": buttons, "resize_keyboard": True, "one_time_keyboard": False}
    
    try:
        return requests.post(url, json=payload).json()
    except:
        return None

def edit_msg(chat_id, msg_id, text, buttons=None):
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": msg_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    
    requests.post(url, json=payload)

def answer_callback(callback_id, text=None, alert=False):
    url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_id}
    if text: payload["text"] = text
    if alert: payload["show_alert"] = True
    requests.post(url, json=payload)

def check_member(channel_username, user_id):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getChatMember"
        payload = {"chat_id": f"@{channel_username}", "user_id": user_id}
        r = requests.post(url, json=payload).json()
        if r.get("ok"):
            status = r["result"]["status"]
            return status in ["member", "administrator", "creator"]
        return False
    except:
        return False

# 🌍 DİL FONKSİYONLARI
def get_text(key, lang='tr', **kwargs):
    """Dil metnini getir"""
    if lang not in LANGUAGES:
        lang = 'tr'
    
    text = LANGUAGES[lang]['strings'].get(key, '')
    if text and kwargs:
        try:
            return text.format(**kwargs)
        except:
            return text
    return text

def show_language_selection(user_id):
    """Dil seçimini göster"""
    text = get_text('select_language', 'tr')
    
    buttons = [[
        {"text": "🇹🇷 Türkçe", "callback_data": "lang_tr"},
        {"text": "🇺🇸 English", "callback_data": "lang_en"}
    ]]
    
    send_msg(user_id, text, buttons)

def enforce_channels(user_id, lang='tr'):
    """Zorunlu kanal kontrolü"""
    missing = []
    for channel in MANDATORY_CHANNELS:
        if not check_member(channel["username"], user_id):
            missing.append(channel)
    
    if not missing:
        return True
    
    # Kanal listesini oluştur
    channel_text = ""
    for channel in missing:
        channel_text += f"\n{channel['emoji']} {channel['name']}: @{channel['username']}"
    
    text = get_text('channel_check', lang, channels=channel_text)
    
    buttons = []
    for channel in missing:
        buttons.append([{"text": f"{channel['emoji']} {channel['name']}", "url": channel["link"]}])
    
    buttons.append([{"text": get_text('check_button', lang), "callback_data": "check_channels"}])
    buttons.append([{"text": get_text('home', lang), "callback_data": "main_menu"}])
    
    send_msg(user_id, text, buttons)
    return False

# 🗄️ FIREBASE FONKSİYONLARI
def get_user(user_id):
    doc = db.collection("users").document(str(user_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None

def create_user(user_id, username, first_name, last_name, referred_by=None, lang='tr'):
    ref_code = str(uuid.uuid4())[:8].upper()
    
    user_data = {
        "user_id": user_id,
        "username": username or "",
        "first_name": first_name or "",
        "last_name": last_name or "",
        "balance": 0.0,
        "tasks_completed": 0,
        "referral_code": ref_code,
        "referred_by": referred_by,
        "total_earned": 0.0,
        "total_ref_bonus": 0.0,
        "language": lang,
        "created_at": datetime.now().isoformat(),
        "last_active": datetime.now().isoformat(),
        "status": "active"
    }
    
    # Firestore
    db.collection("users").document(str(user_id)).set(user_data)
    
    # Realtime
    rtdb.child("users").child(str(user_id)).set({
        "balance": 0.0,
        "username": username or "",
        "ref_code": ref_code,
        "ref_by": referred_by or "",
        "language": lang
    })
    
    # 📈 İstatistik
    rtdb.child("stats").child("total_users").transaction(lambda x: (x or 0) + 1)
    
    # Referans bonusu
    if referred_by:
        add_referral_bonus(referred_by, user_id)
    
    return user_data

def add_referral_bonus(referrer_id, referred_id):
    referrer = get_user(referrer_id)
    if referrer:
        new_balance = referrer.get("balance", 0) + REF_BONUS
        total_ref_bonus = referrer.get("total_ref_bonus", 0) + REF_BONUS
        
        db.collection("users").document(str(referrer_id)).update({
            "balance": new_balance,
            "total_earned": referrer.get("total_earned", 0) + REF_BONUS,
            "total_ref_bonus": total_ref_bonus
        })
        
        rtdb.child("users").child(str(referrer_id)).update({"balance": new_balance})
        
        db.collection("referrals").add({
            "referrer_id": referrer_id,
            "referred_id": referred_id,
            "bonus": REF_BONUS,
            "date": datetime.now().isoformat()
        })

def get_ref_count(user_id):
    refs = db.collection("users").where("referred_by", "==", user_id).stream()
    return len(list(refs))

def get_ref_level(count, lang='tr'):
    if lang == 'tr':
        if count >= 50: return "👑 Kral"
        elif count >= 25: return "⭐ Yıldız"
        elif count >= 10: return "🚀 Ace"
        elif count >= 5: return "🔥 Aktif"
        else: return "🌱 Yeni"
    else:
        if count >= 50: return "👑 King"
        elif count >= 25: return "⭐ Star"
        elif count >= 10: return "🚀 Ace"
        elif count >= 5: return "🔥 Active"
        else: return "🌱 New"

def update_balance(user_id, amount, reason=""):
    user = get_user(user_id)
    if user:
        new_balance = user.get("balance", 0) + amount
        
        updates = {"balance": new_balance, "last_active": datetime.now().isoformat()}
        if amount > 0:
            updates["total_earned"] = user.get("total_earned", 0) + amount
        
        db.collection("users").document(str(user_id)).update(updates)
        rtdb.child("users").child(str(user_id)).update({"balance": new_balance})
        
        db.collection("transactions").add({
            "user_id": user_id,
            "amount": amount,
            "type": reason,
            "date": datetime.now().isoformat(),
            "balance_after": new_balance
        })
        
        return True
    return False

def get_active_tasks(user_id=None):
    tasks = []
    docs = db.collection("tasks").where("status", "==", "active").stream()
    
    for doc in docs:
        task = doc.to_dict()
        task["id"] = doc.id
        
        if user_id:
            participated = db.collection("task_participants")\
                .where("task_id", "==", doc.id)\
                .where("user_id", "==", user_id).limit(1).stream()
            if list(participated):
                continue
        
        participants = db.collection("task_participants")\
            .where("task_id", "==", doc.id).stream()
        task["current"] = len(list(participants))
        
        if task["current"] < task.get("max_participants", 10):
            tasks.append(task)
    
    return tasks

def add_task_participant(user_id, task_id):
    existing = db.collection("task_participants")\
        .where("task_id", "==", task_id)\
        .where("user_id", "==", user_id).limit(1).stream()
    
    if list(existing):
        return False
    
    db.collection("task_participants").add({
        "user_id": user_id,
        "task_id": task_id,
        "joined_at": datetime.now().isoformat(),
        "status": "joined"
    })
    
    task_ref = db.collection("tasks").document(task_id)
    task_ref.update({"current_participants": firestore.Increment(1)})
    
    return True

def complete_task_participation(user_id, task_id, proof_url=None):
    task_doc = db.collection("tasks").document(task_id).get()
    if not task_doc.exists:
        return None
    
    task = task_doc.to_dict()
    
    participant_docs = db.collection("task_participants")\
        .where("task_id", "==", task_id)\
        .where("user_id", "==", user_id).stream()
    
    if not list(participant_docs):
        return None
    
    for doc in participant_docs:
        doc_ref = db.collection("task_participants").document(doc.id)
        doc_ref.update({
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "proof_url": proof_url
        })
    
    reward = task["reward"]
    update_balance(user_id, reward, "task_reward")
    
    user = get_user(user_id)
    db.collection("users").document(str(user_id)).update({
        "tasks_completed": user.get("tasks_completed", 0) + 1
    })
    
    if user and user.get("referred_by"):
        commission = reward * TASK_COMMISSION
        update_balance(user["referred_by"], commission, "referral_commission")
    
    return reward

def create_task_from_user(creator_id, task_data):
    user = get_user(creator_id)
    if not user:
        return None, "User not found"
    
    budget = task_data.get("budget", 0)
    if user.get("balance", 0) < budget:
        return None, "Insufficient balance"
    
    update_balance(creator_id, -budget, "create_task")
    
    task_ref = db.collection("tasks").add(task_data)
    task_id = task_ref[1].id
    
    rtdb.child("tasks").child(task_id).set(task_data)
    
    return task_id, "Success"

# 📢 BİLDİRİM FONKSİYONLARI
def notify_channel(text):
    try:
        send_msg(STATS_CHANNEL, text)
    except:
        pass

def notify_admin(text):
    try:
        send_msg(ADMIN_ID, text)
    except:
        pass

def notify_new_user(user_id, username, first_name, referred_by=None):
    ref_text = ""
    if referred_by:
        ref_user = get_user(referred_by)
        ref_name = ref_user.get('first_name', '') if ref_user else str(referred_by)
        ref_count = get_ref_count(referred_by)
        ref_text = f"""👥 <b>Referans:</b> <code>{referred_by}</code> ({ref_name})
📊 <b>Toplam Ref:</b> <code>{ref_count}</code>
"""
    
    text = f"""
👤 <b>YENİ ÜYE KATILDI</b>
━━━━━━━━━━━━━━━━
🎉 <b>Ad:</b> {first_name}
🆔 <b>ID:</b> <code>{user_id}</code>
{ref_text}📅 <b>Saat:</b> {datetime.now().strftime('%H:%M')}
━━━━━━━━━━━━━━━━
<i>Hoş geldin! 🎯</i>
    """
    notify_channel(text)

# 🎯 BOT SINIFI
class TaskizBot:
    def __init__(self):
        self.user_states = {}
        print("🤖 TaskizBot aktif!")
    
    def handle_update(self, update):
        if "message" in update:
            self.handle_message(update["message"])
        elif "callback_query" in update:
            self.handle_callback(update["callback_query"])
    
    def handle_message(self, msg):
        user_id = msg["from"]["id"]
        text = msg.get("text", "")
        
        # 🎯 START komutu
        if text.startswith("/start"):
            parts = text.split()
            referred_by = None
            
            if len(parts) > 1:
                ref_code = parts[1]
                docs = db.collection("users").where("referral_code", "==", ref_code).limit(1).stream()
                for doc in docs:
                    referred_by = doc.to_dict()["user_id"]
                    break
            
            user = get_user(user_id)
            
            if not user:
                username = msg["from"].get("username", "")
                first_name = msg["from"].get("first_name", "")
                last_name = msg["from"].get("last_name", "")
                
                # Önce dil seçimi göster
                show_language_selection(user_id)
                
                # State'e kaydet
                self.user_states[user_id] = {
                    "action": "waiting_language",
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "referred_by": referred_by
                }
                return
            
            # Kullanıcı varsa dilini al
            lang = user.get("language", "tr")
            
            # Zorunlu kanal kontrolü
            if not enforce_channels(user_id, lang):
                return
            
            self.show_main_menu(user_id, lang)
            return
        
        # 👑 ADMIN
        if str(user_id) == ADMIN_ID and text.startswith("/"):
            if text == "/admin":
                self.show_admin_panel(user_id)
            return
        
        # State kontrolü
        if user_id in self.user_states:
            state = self.user_states[user_id]
            action = state.get("action")
            
            if action == "waiting_language":
                # Dil seçimi handle_callback'da yapılacak
                return
            elif action == "waiting_post_image":
                self.process_post_image(user_id, msg)
                return
        
        # Kullanıcı var mı kontrol et
        user = get_user(user_id)
        if not user:
            # Dil seçimi göster
            show_language_selection(user_id)
            return
        
        # Dil ayarı
        lang = user.get("language", "tr")
        
        # Zorunlu kanal kontrolü
        if not enforce_channels(user_id, lang):
            return
        
        # 📱 Ana butonlar
        if text == get_text('home', lang):
            self.show_main_menu(user_id, lang)
        elif text == get_text('menu_tasks', lang):
            self.show_task_types(user_id, lang)
        elif text == get_text('menu_balance', lang):
            self.show_balance(user_id, lang)
        elif text == get_text('menu_deposit', lang):
            self.show_deposit(user_id, lang)
        elif text == get_text('menu_withdraw', lang):
            self.show_withdraw(user_id, lang)
        elif text == get_text('menu_referral', lang):
            self.show_referral(user_id, lang)
        elif text == get_text('menu_create_task', lang):
            self.start_post_task(user_id, lang)
        elif text == get_text('menu_admin', lang) and str(user_id) == ADMIN_ID:
            self.show_admin_panel(user_id)
    
    def handle_callback(self, callback):
        data = callback["data"]
        user_id = callback["from"]["id"]
        callback_id = callback["id"]
        
        try:
            # Dil seçimi
            if data.startswith("lang_"):
                lang = data.split("_")[1]
                
                if user_id in self.user_states and self.user_states[user_id].get("action") == "waiting_language":
                    # Yeni kullanıcı oluştur
                    state = self.user_states[user_id]
                    user = create_user(
                        user_id, 
                        state["username"],
                        state["first_name"],
                        state["last_name"],
                        state["referred_by"],
                        lang
                    )
                    
                    # State'i temizle
                    del self.user_states[user_id]
                    
                    # Bildirim
                    notify_new_user(user_id, state["username"], state["first_name"], state["referred_by"])
                    
                    answer_callback(callback_id, get_text('language_selected', lang))
                    
                    # Zorunlu kanal kontrolü
                    if not enforce_channels(user_id, lang):
                        return
                    
                    self.show_main_menu(user_id, lang)
                else:
                    # Mevcut kullanıcı dil güncelleme
                    db.collection("users").document(str(user_id)).update({"language": lang})
                    rtdb.child("users").child(str(user_id)).update({"language": lang})
                    
                    answer_callback(callback_id, get_text('language_selected', lang))
                    self.show_main_menu(user_id, lang)
                return
            
            elif data == "main_menu":
                user = get_user(user_id)
                lang = user.get("language", "tr") if user else "tr"
                self.show_main_menu(user_id, lang)
            
            elif data == "check_channels":
                user = get_user(user_id)
                lang = user.get("language", "tr") if user else "tr"
                if enforce_channels(user_id, lang):
                    answer_callback(callback_id, "✅ Tüm kanallara katıldın!")
                    self.show_main_menu(user_id, lang)
                else:
                    answer_callback(callback_id, "❌ Hala katılmadığın kanallar var!")
            
            elif data.startswith("task_type_"):
                task_type = data.split("_")[2]
                user = get_user(user_id)
                lang = user.get("language", "tr") if user else "tr"
                self.show_tasks_of_type(user_id, task_type, lang)
                answer_callback(callback_id)
            
            elif data.startswith("join_task_"):
                task_id = data.split("_")[2]
                self.join_task(user_id, task_id, callback_id)
            
            elif data.startswith("view_task_"):
                task_id = data.split("_")[2]
                user = get_user(user_id)
                lang = user.get("language", "tr") if user else "tr"
                self.view_task_details(user_id, task_id, lang)
                answer_callback(callback_id)
            
            elif data == "refresh_tasks":
                user = get_user(user_id)
                lang = user.get("language", "tr") if user else "tr"
                self.show_task_types(user_id, lang)
                answer_callback(callback_id, get_text('refresh', lang))
            
            elif data == "create_post_task":
                user = get_user(user_id)
                lang = user.get("language", "tr") if user else "tr"
                self.start_post_task(user_id, lang)
                answer_callback(callback_id)
            
            elif data == "start_deposit":
                user = get_user(user_id)
                lang = user.get("language", "tr") if user else "tr"
                self.show_deposit(user_id, lang)
                answer_callback(callback_id)
            
            elif data == "start_withdraw":
                user = get_user(user_id)
                lang = user.get("language", "tr") if user else "tr"
                self.show_withdraw(user_id, lang)
                answer_callback(callback_id)
            
            elif data.startswith("complete_task_"):
                task_id = data.split("_")[2]
                self.complete_task(user_id, task_id, callback_id)
            
            elif data == "cancel_action":
                if user_id in self.user_states:
                    del self.user_states[user_id]
                user = get_user(user_id)
                lang = user.get("language", "tr") if user else "tr"
                send_msg(user_id, get_text('cancel', lang))
                answer_callback(callback_id)
            
        except Exception as e:
            print(f"Callback error: {e}")
            answer_callback(callback_id, "❌ Hata!")
    
    # 🏠 ANA MENÜ
    def show_main_menu(self, user_id, lang='tr'):
        user = get_user(user_id)
        if not user:
            return
        
        ref_count = get_ref_count(user_id)
        level = get_ref_level(ref_count, lang)
        
        text = get_text('welcome', lang, 
                       name=user['first_name'],
                       balance=user.get('balance', 0),
                       tasks=user.get('tasks_completed', 0),
                       refs=ref_count,
                       level=level)
        
        buttons = [
            [get_text('menu_tasks', lang), get_text('menu_balance', lang)],
            [get_text('menu_deposit', lang), get_text('menu_withdraw', lang)],
            [get_text('menu_referral', lang), get_text('menu_ads', lang)],
            [get_text('menu_create_task', lang)]
        ]
        
        if str(user_id) == ADMIN_ID:
            buttons.append([get_text('menu_admin', lang)])
        
        send_msg(user_id, text, buttons, "keyboard")
    
    # 🎯 GÖREV SİSTEMİ
    def show_task_types(self, user_id, lang='tr'):
        text = get_text('task_types', lang)
        
        buttons = [[
            {"text": get_text('task_channel', lang), "callback_data": "task_type_kanal"},
            {"text": get_text('task_group', lang), "callback_data": "task_type_grup"}
        ], [
            {"text": get_text('task_post', lang), "callback_data": "task_type_post"},
            {"text": get_text('task_bot', lang), "callback_data": "task_type_bot"}
        ], [
            {"text": get_text('refresh', lang), "callback_data": "refresh_tasks"},
            {"text": get_text('menu_create_task', lang), "callback_data": "create_post_task"}
        ], [
            {"text": get_text('home', lang), "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def show_tasks_of_type(self, user_id, task_type, lang='tr'):
        tasks = get_active_tasks(user_id)
        type_tasks = [t for t in tasks if t.get("type") == task_type]
        
        if not type_tasks:
            type_name = get_text(f'task_{task_type}', lang)
            text = get_text('no_tasks', lang, type=type_name)
            buttons = [[
                {"text": get_text('back', lang), "callback_data": "refresh_tasks"},
                {"text": get_text('menu_create_task', lang), "callback_data": "create_post_task"}
            ]]
        else:
            type_name = get_text(f'task_{task_type}', lang)
            text = f"🎯 <b>{type_name} Görevleri</b> ({len(type_tasks)})\n\nAşağıdaki görevlerden birini seç:"
            
            buttons = []
            for task in type_tasks[:5]:
                btn_text = f"${task['reward']:.4f} ({task.get('current', 0)}/{task.get('max_participants', 10)})"
                buttons.append([{
                    "text": btn_text,
                    "callback_data": f"view_task_{task['id']}"
                }])
            
            buttons.append([
                {"text": get_text('back', lang), "callback_data": "refresh_tasks"},
                {"text": get_text('refresh', lang), "callback_data": f"task_type_{task_type}"}
            ])
        
        buttons.append([{"text": get_text('home', lang), "callback_data": "main_menu"}])
        
        send_msg(user_id, text, buttons)
    
    def view_task_details(self, user_id, task_id, lang='tr'):
        task_doc = db.collection("tasks").document(task_id).get()
        if not task_doc.exists:
            send_msg(user_id, "❌ Görev bulunamadı!")
            return
        
        task = task_doc.to_dict()
        
        participated = db.collection("task_participants")\
            .where("task_id", "==", task_id)\
            .where("user_id", "==", user_id).stream()
        
        has_participated = bool(list(participated))
        
        text = f"""
🎯 <b>Görev Detayı</b>

📝 <b>{task['title']}</b>
💰 <b>Ödül:</b> <code>${task['reward']:.4f}</code>
👥 <b>Katılım:</b> {task.get('current_participants', 0)}/{task.get('max_participants', 10)}

📢 <b>Reklam Bütçesi:</b> <code>${task.get('budget', 0):.4f}</code>
🎯 <b>Kalan Katılım:</b> {task.get('max_participants', 10) - task.get('current_participants', 0)} kişi

💡 <b>Talimatlar:</b>
"""
        
        if task["type"] == "kanal":
            text += "• Kanalı aç\n• Katıl butonuna bas\n• 10 saniye bekle"
        elif task["type"] == "grup":
            text += "• Grubu aç\n• Katıl butonuna bas\n• Mesaj gönder"
        elif task["type"] == "post":
            if task.get("image_url"):
                text += "• Postu aç\n• Like/beğen\n• Yorum yap"
                send_msg(user_id, text, photo=task.get("image_url"))
                return
        elif task["type"] == "bot":
            text += "• Botu aç\n• /start yaz\n• Bekle"
        
        buttons = []
        
        if not has_participated:
            buttons.append([{"text": get_text('join', lang), "callback_data": f"join_task_{task_id}"}])
        else:
            buttons.append([{"text": get_text('completed', lang), "callback_data": f"complete_task_{task_id}"}])
        
        buttons.append([
            {"text": get_text('back', lang), "callback_data": f"task_type_{task['type']}"},
            {"text": get_text('home', lang), "callback_data": "main_menu"}
        ])
        
        send_msg(user_id, text, buttons)
    
    def join_task(self, user_id, task_id, callback_id):
        task_doc = db.collection("tasks").document(task_id).get()
        if not task_doc.exists:
            answer_callback(callback_id, "❌ Görev bulunamadı!", True)
            return
        
        task = task_doc.to_dict()
        
        if task["type"] in ["kanal", "grup"]:
            channel_username = task["target_link"].replace("https://t.me/", "").replace("@", "")
            if not check_member(channel_username, user_id):
                answer_callback(callback_id, f"❌ Önce @{channel_username} katılmalısın!", True)
                return
        
        if add_task_participant(user_id, task_id):
            user = get_user(user_id)
            lang = user.get("language", "tr") if user else "tr"
            
            text = get_text('task_joined', lang, 
                          title=task['title'],
                          reward=task['reward'],
                          link=task['target_link'])
            
            buttons = [[
                {"text": "🔗 Linke Git", "url": task['target_link']},
                {"text": get_text('completed', lang), "callback_data": f"complete_task_{task_id}"}
            ], [
                {"text": get_text('back', lang), "callback_data": f"task_type_{task['type']}"}
            ]]
            
            answer_callback(callback_id, "✅ Göreve katıldın!")
            send_msg(user_id, text, buttons)
        else:
            answer_callback(callback_id, "❌ Zaten katıldın!", True)
    
    def complete_task(self, user_id, task_id, callback_id):
        reward = complete_task_participation(user_id, task_id)
        
        if reward:
            user = get_user(user_id)
            lang = user.get("language", "tr") if user else "tr"
            
            text = get_text('task_completed', lang, reward=reward)
            
            buttons = [[
                {"text": get_text('menu_tasks', lang), "callback_data": "refresh_tasks"},
                {"text": get_text('menu_balance', lang), "callback_data": "start_deposit"}
            ]]
            
            answer_callback(callback_id, f"✅ ${reward:.4f} kazandın!")
            send_msg(user_id, text, buttons)
        else:
            answer_callback(callback_id, "❌ Görev tamamlanamadı!", True)
    
    # 📝 POST GÖREV OLUŞTURMA
    def start_post_task(self, user_id, lang='tr'):
        self.user_states[user_id] = {"action": "waiting_post_image", "lang": lang}
        
        if lang == 'tr':
            text = """
➕ <b>POST GÖREVİ OLUŞTUR</b>

1️⃣ <b>Adım:</b> Post görselini gönder
<i>(Fotoğraf veya video)</i>

❌ İptal için: /cancel
            """
        else:
            text = """
➕ <b>CREATE POST TASK</b>

1️⃣ <b>Step:</b> Send post image
<i>(Photo or video)</i>

❌ Cancel: /cancel
            """
        
        send_msg(user_id, text)
    
    def process_post_image(self, user_id, msg):
        if user_id not in self.user_states:
            return
        
        state = self.user_states[user_id]
        lang = state.get("lang", "tr")
        
        if "photo" in msg:
            photo = msg["photo"][-1]["file_id"]
        elif "video" in msg:
            photo = msg["video"]["file_id"]
        else:
            send_msg(user_id, "❌ Lütfen fotoğraf veya video gönder!")
            return
        
        self.user_states[user_id] = {
            "action": "waiting_post_title",
            "image_url": photo,
            "lang": lang
        }
        
        if lang == 'tr':
            text = """
2️⃣ <b>Adım:</b> Post başlığını yaz
<i>(Örnek: Yeni Ürünümüzü Beğenin!)</i>
            """
        else:
            text = """
2️⃣ <b>Step:</b> Write post title
<i>(Example: Like Our New Product!)</i>
            """
        
        send_msg(user_id, text)
    
    # 💰 BAKİYE
    def show_balance(self, user_id, lang='tr'):
        user = get_user(user_id)
        if not user:
            return
        
        text = get_text('balance_title', lang,
                       balance=user.get('balance', 0),
                       tasks=user.get('tasks_completed', 0),
                       earned=user.get('total_earned', 0),
                       ref_bonus=user.get('total_ref_bonus', 0),
                       min_withdraw=MIN_WITHDRAW)
        
        buttons = [[
            {"text": get_text('menu_deposit', lang), "callback_data": "start_deposit"},
            {"text": get_text('menu_withdraw', lang), "callback_data": "start_withdraw"}
        ], [
            {"text": get_text('menu_tasks', lang), "callback_data": "refresh_tasks"},
            {"text": get_text('home', lang), "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def show_deposit(self, user_id, lang='tr'):
        if lang == 'tr':
            text = f"""
💳 <b>Bakiye Yükle</b>

ℹ️ <b>Manuel yükleme:</b>
👉 {SUPPORT_USERNAME}

💰 <b>Bize yaz, hızlıca yükleyelim!</b>
            """
        else:
            text = f"""
💳 <b>Deposit</b>

ℹ️ <b>Manual deposit:</b>
👉 {SUPPORT_USERNAME}

💰 <b>Contact us, we'll deposit quickly!</b>
            """
        
        buttons = [[
            {"text": "📞 Destek", "url": f"https://t.me/{SUPPORT_USERNAME[1:]}"}
        ], [
            {"text": get_text('menu_balance', lang), "callback_data": "start_deposit"},
            {"text": get_text('home', lang), "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def show_withdraw(self, user_id, lang='tr'):
        user = get_user(user_id)
        balance = user.get("balance", 0)
        
        if lang == 'tr':
            if balance < MIN_WITHDRAW:
                text = f"""
🏧 <b>Para Çekme</b>

❌ <b>Bakiye Yetersiz!</b>

💰 <b>Mevcut:</b> <code>${balance:.4f}</code>
📊 <b>Gerekli:</b> <code>${MIN_WITHDRAW}</code>
                """
            else:
                text = f"""
🏧 <b>Para Çekme</b>

✅ <b>Çekim Yapılabilir!</b>

💰 <b>Mevcut:</b> <code>${balance:.4f}</code>
📊 <b>Minimum:</b> <code>${MIN_WITHDRAW}</code>

ℹ️ <b>Destek ile iletişime geç:</b>
👉 {SUPPORT_USERNAME}
                """
        else:
            if balance < MIN_WITHDRAW:
                text = f"""
🏧 <b>Withdraw</b>

❌ <b>Insufficient Balance!</b>

💰 <b>Current:</b> <code>${balance:.4f}</code>
📊 <b>Required:</b> <code>${MIN_WITHDRAW}</code>
                """
            else:
                text = f"""
🏧 <b>Withdraw</b>

✅ <b>Withdrawal Available!</b>

💰 <b>Current:</b> <code>${balance:.4f}</code>
📊 <b>Minimum:</b> <code>${MIN_WITHDRAW}</code>

ℹ️ <b>Contact support:</b>
👉 {SUPPORT_USERNAME}
                """
        
        buttons = [[
            {"text": "📞 Destek", "url": f"https://t.me/{SUPPORT_USERNAME[1:]}"}
        ], [
            {"text": get_text('menu_balance', lang), "callback_data": "start_deposit"},
            {"text": get_text('menu_tasks', lang), "callback_data": "refresh_tasks"}
        ], [
            {"text": get_text('home', lang), "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    # 👥 REFERANS
    def show_referral(self, user_id, lang='tr'):
        user = get_user(user_id)
        if not user:
            return
        
        ref_code = user.get("referral_code", "N/A")
        ref_link = f"https://t.me/{BOT_USERNAME}?start={ref_code}"
        ref_count = get_ref_count(user_id)
        total_bonus = ref_count * REF_BONUS
        level = get_ref_level(ref_count, lang)
        
        text = get_text('referral_title', lang,
                       ref_count=ref_count,
                       total_bonus=total_bonus,
                       level=level,
                       ref_bonus=REF_BONUS,
                       ref_link=ref_link,
                       ref_code=ref_code)
        
        buttons = [[
            {"text": get_text('copy_ref', lang), "callback_data": "copy_ref"}
        ], [
            {"text": get_text('menu_balance', lang), "callback_data": "start_deposit"},
            {"text": get_text('menu_tasks', lang), "callback_data": "refresh_tasks"}
        ], [
            {"text": get_text('home', lang), "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    # 👑 ADMIN PANEL
    def show_admin_panel(self, admin_id):
        users = db.collection("users").stream()
        user_count = len(list(users))
        
        tasks = db.collection("tasks").where("status", "==", "active").stream()
        task_count = len(list(tasks))
        
        total_balance = 0
        for user in db.collection("users").stream():
            total_balance += user.to_dict().get("balance", 0)
        
        text = f"""
👑 <b>ADMIN PANEL</b>
━━━━━━━━━━━━━━━━
👥 <b>Users:</b> {user_count}
🎯 <b>Active Tasks:</b> {task_count}
💰 <b>Total Balance:</b> ${total_balance:.2f}
━━━━━━━━━━━━━━━━

<b>Commands:</b>
• /broadcast MESSAGE
• /addbalance ID AMOUNT
• /stats - Details
        """
        
        send_msg(admin_id, text)

# 🚀 FLASK APP
app = Flask(__name__)
bot = TaskizBot()

@app.route('/')
def home():
    return "🤖 TaskizBot Aktif!"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    bot.handle_update(update)
    return jsonify({"ok": True})

@app.route('/setwebhook')
def set_webhook():
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if webhook_url:
        url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}/webhook"
        r = requests.get(url).json()
        return r
    return "WEBHOOK_URL gerekli"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
