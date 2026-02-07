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

# ⚙️ SİSTEM AYARLARI
TASK_REWARDS = {
    "kanal": 0.0025,
    "grup": 0.0015,
    "post": 0.0005,
    "bot": 0.0010
}

MIN_WITHDRAW = 0.30
REF_BONUS = 0.005
TASK_COMMISSION = 0.25  # %25 referans komisyonu

# 📢 ZORUNLU KANALLAR
MANDATORY_CHANNELS = [
    {"username": "TaskizLive", "link": "https://t.me/TaskizLive", "name": "Ana Kanal", "emoji": "📢"}
]

# 🚀 TELEGRAM FONKSİYONLARI
def send_msg(chat_id, text, buttons=None, markup_type="inline", photo=None):
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
    """Kanal/grup üyeliğini kontrol et"""
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

def enforce_channels(user_id):
    """Zorunlu kanal kontrolü"""
    missing = []
    for channel in MANDATORY_CHANNELS:
        if not check_member(channel["username"], user_id):
            missing.append(channel)
    
    if missing:
        text = "🚫 <b>Zorunlu Kanal Kontrolü</b>\n\n"
        text += "Devam etmek için kanallara katıl:\n"
        
        buttons = []
        for channel in missing:
            text += f"\n{channel['emoji']} {channel['name']}: @{channel['username']}"
            buttons.append([{"text": f"{channel['emoji']} {channel['name']}", "url": channel["link"]}])
        
        buttons.append([{"text": "✅ Kontrol Et", "callback_data": "check_channels"}])
        buttons.append([{"text": "🏠 Ana Menü", "callback_data": "main_menu"}])
        
        send_msg(user_id, text, buttons)
        return False
    return True

# 🗄️ FIREBASE FONKSİYONLARI
def get_user(user_id):
    doc = db.collection("users").document(str(user_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None

def create_user(user_id, username, first_name, last_name, referred_by=None):
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
        "created_at": datetime.now().isoformat(),
        "last_active": datetime.now().isoformat(),
        "status": "active"
    }
    
    # Firestore
    db.collection("users").document(str(user_id)).set(user_data)
    
    # Realtime (hızlı erişim)
    rtdb.child("users").child(str(user_id)).set({
        "balance": 0.0,
        "username": username or "",
        "ref_code": ref_code
    })
    
    # Referans bonusu
    if referred_by:
        add_referral_bonus(referred_by, user_id)
    
    # İstatistik
    rtdb.child("stats").child("total_users").transaction(lambda x: (x or 0) + 1)
    
    return user_data

def add_referral_bonus(referrer_id, referred_id):
    referrer = get_user(referrer_id)
    if referrer:
        # Bonus ekle
        new_balance = referrer.get("balance", 0) + REF_BONUS
        db.collection("users").document(str(referrer_id)).update({
            "balance": new_balance,
            "total_earned": referrer.get("total_earned", 0) + REF_BONUS
        })
        
        rtdb.child("users").child(str(referrer_id)).update({"balance": new_balance})
        
        # Referans kaydı
        db.collection("referrals").add({
            "referrer_id": referrer_id,
            "referred_id": referred_id,
            "bonus": REF_BONUS,
            "date": datetime.now().isoformat()
        })

def update_balance(user_id, amount, reason=""):
    user = get_user(user_id)
    if user:
        new_balance = user.get("balance", 0) + amount
        
        # Firestore
        updates = {"balance": new_balance, "last_active": datetime.now().isoformat()}
        if amount > 0:
            updates["total_earned"] = user.get("total_earned", 0) + amount
        
        db.collection("users").document(str(user_id)).update(updates)
        
        # Realtime
        rtdb.child("users").child(str(user_id)).update({"balance": new_balance})
        
        # İşlem kaydı
        db.collection("transactions").add({
            "user_id": user_id,
            "amount": amount,
            "type": reason,
            "date": datetime.now().isoformat()
        })
        
        return True
    return False

def get_active_tasks(user_id=None):
    """Kullanıcının katılmadığı aktif görevler"""
    tasks = []
    docs = db.collection("tasks").where("status", "==", "active").stream()
    
    for doc in docs:
        task = doc.to_dict()
        task["id"] = doc.id
        
        # Katılım kontrolü
        if user_id:
            participated = db.collection("task_participants")\
                .where("task_id", "==", doc.id)\
                .where("user_id", "==", user_id).limit(1).stream()
            if list(participated):
                continue
        
        # Limit kontrolü
        participants = db.collection("task_participants")\
            .where("task_id", "==", doc.id).stream()
        task["current"] = len(list(participants))
        
        if task["current"] < task.get("max_participants", 10):
            tasks.append(task)
    
    return tasks

def add_task_participant(user_id, task_id):
    """Göreve katılım kaydı"""
    # Zaten katıldı mı?
    existing = db.collection("task_participants")\
        .where("task_id", "==", task_id)\
        .where("user_id", "==", user_id).limit(1).stream()
    
    if list(existing):
        return False
    
    # Katılım kaydı
    db.collection("task_participants").add({
        "user_id": user_id,
        "task_id": task_id,
        "joined_at": datetime.now().isoformat(),
        "status": "joined"
    })
    
    # Görev katılımcı sayısını artır
    task_ref = db.collection("tasks").document(task_id)
    task_ref.update({"current_participants": firestore.Increment(1)})
    
    # İstatistik
    rtdb.child("stats").child("total_participations").transaction(lambda x: (x or 0) + 1)
    
    return True

def complete_task_participation(user_id, task_id, proof_url=None):
    """Görev tamamlama"""
    # Görevi al
    task_doc = db.collection("tasks").document(task_id).get()
    if not task_doc.exists:
        return None
    
    task = task_doc.to_dict()
    
    # Katılım kaydını bul
    participant_docs = db.collection("task_participants")\
        .where("task_id", "==", task_id)\
        .where("user_id", "==", user_id).stream()
    
    if not list(participant_docs):
        return None
    
    # Tamamlandı olarak işaretle
    for doc in participant_docs:
        doc_ref = db.collection("task_participants").document(doc.id)
        doc_ref.update({
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "proof_url": proof_url
        })
    
    # Ödül ver
    reward = task["reward"]
    update_balance(user_id, reward, "task_reward")
    
    # Kullanıcı istatistikleri
    user = get_user(user_id)
    db.collection("users").document(str(user_id)).update({
        "tasks_completed": user.get("tasks_completed", 0) + 1
    })
    
    # Referans komisyonu
    if user and user.get("referred_by"):
        commission = reward * TASK_COMMISSION
        update_balance(user["referred_by"], commission, "referral_commission")
    
    return reward

def create_task_from_user(creator_id, task_type, title, target_link, budget, max_participants=10):
    """Kullanıcı görev oluşturma"""
    reward = TASK_REWARDS.get(task_type, 0.001)
    
    # Bakiye kontrolü
    user = get_user(creator_id)
    if user.get("balance", 0) < budget:
        return None, "Bakiye yetersiz"
    
    # Görev oluştur
    task_data = {
        "creator_id": creator_id,
        "type": task_type,
        "title": title,
        "target_link": target_link,
        "reward": reward,
        "budget": budget,
        "remaining_budget": budget,
        "max_participants": max_participants,
        "current_participants": 0,
        "status": "active",
        "created_at": datetime.now().isoformat()
    }
    
    # Bakiye düş
    update_balance(creator_id, -budget, "create_task")
    
    # Görevi kaydet
    task_ref = db.collection("tasks").add(task_data)
    task_id = task_ref[1].id
    
    # Realtime'a ekle
    rtdb.child("tasks").child(task_id).set(task_data)
    
    return task_id, "Başarılı"

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
        
        # 🎯 START komutu (referans kontrolü)
        if text.startswith("/start"):
            parts = text.split()
            referred_by = None
            
            if len(parts) > 1:
                ref_code = parts[1]
                # Ref kodu ara
                docs = db.collection("users").where("referral_code", "==", ref_code).limit(1).stream()
                for doc in docs:
                    referred_by = doc.to_dict()["user_id"]
                    break
            
            user = get_user(user_id)
            
            if not user:
                username = msg["from"].get("username", "")
                first_name = msg["from"].get("first_name", "")
                last_name = msg["from"].get("last_name", "")
                
                user = create_user(user_id, username, first_name, last_name, referred_by)
            
            # Zorunlu kanal kontrolü
            if not enforce_channels(user_id):
                return
            
            self.show_main_menu(user_id)
            return
        
        # 👑 ADMIN komutları
        if str(user_id) == ADMIN_ID:
            if text == "/admin":
                self.show_admin_panel(user_id)
                return
            elif text.startswith("/addbalance"):
                self.admin_add_balance(text)
                return
            elif text.startswith("/stats"):
                self.admin_stats(user_id)
                return
        
        # Kullanıcı state kontrolü
        if user_id in self.user_states:
            state = self.user_states[user_id]
            action = state.get("action")
            
            if action == "waiting_task_type":
                self.process_task_type(user_id, text)
            elif action == "waiting_task_link":
                self.process_task_link(user_id, text)
            elif action == "waiting_task_title":
                self.process_task_title(user_id, text)
            elif action == "waiting_task_budget":
                self.process_task_budget(user_id, text)
            elif action == "waiting_deposit_amount":
                self.process_deposit_amount(user_id, text)
            elif action == "waiting_post_proof":
                self.process_post_proof(user_id, msg)
            return
        
        # 📱 Ana butonlar
        user = get_user(user_id)
        if not user:
            return
        
        if not enforce_channels(user_id):
            return
        
        if text == "🏠 Ana Menü":
            self.show_main_menu(user_id)
        elif text == "🎯 Görevler":
            self.show_task_types(user_id)
        elif text == "💰 Bakiye":
            self.show_balance(user_id)
        elif text == "💳 Yükle":
            self.show_deposit(user_id)
        elif text == "🏧 Çek":
            self.show_withdraw(user_id)
        elif text == "👥 Davet":
            self.show_referral(user_id)
        elif text == "📢 Reklam":
            self.show_ads(user_id)
        elif text == "➕ Görev Oluştur":
            self.start_create_task(user_id)
        elif text == "👑 Admin" and str(user_id) == ADMIN_ID:
            self.show_admin_panel(user_id)
    
    def handle_callback(self, callback):
        data = callback["data"]
        user_id = callback["from"]["id"]
        callback_id = callback["id"]
        
        try:
            if data == "main_menu":
                self.show_main_menu(user_id)
            elif data == "check_channels":
                if enforce_channels(user_id):
                    answer_callback(callback_id, "✅ Tüm kanallara katıldın!")
                    self.show_main_menu(user_id)
                else:
                    answer_callback(callback_id, "❌ Hala katılmadığın kanallar var!")
            elif data.startswith("task_type_"):
                task_type = data.split("_")[2]
                self.show_tasks_of_type(user_id, task_type)
                answer_callback(callback_id)
            elif data.startswith("join_task_"):
                task_id = data.split("_")[2]
                self.join_task(user_id, task_id, callback_id)
            elif data.startswith("view_task_"):
                task_id = data.split("_")[2]
                self.view_task_details(user_id, task_id)
                answer_callback(callback_id)
            elif data == "refresh_tasks":
                self.show_task_types(user_id)
                answer_callback(callback_id, "🔄 Yenilendi")
            elif data == "create_task":
                self.start_create_task(user_id)
                answer_callback(callback_id)
            elif data == "start_deposit":
                self.start_deposit(user_id)
                answer_callback(callback_id)
            elif data == "start_withdraw":
                self.start_withdraw(user_id)
                answer_callback(callback_id)
            elif data.startswith("complete_task_"):
                task_id = data.split("_")[2]
                self.complete_task(user_id, task_id, callback_id)
            elif data == "cancel_action":
                if user_id in self.user_states:
                    del self.user_states[user_id]
                send_msg(user_id, "❌ İşlem iptal edildi.")
                answer_callback(callback_id)
            
        except Exception as e:
            print(f"Callback error: {e}")
            answer_callback(callback_id, "❌ Hata!")
    
    # 🏠 ANA MENÜ
    def show_main_menu(self, user_id):
        user = get_user(user_id)
        if not user:
            return
        
        text = f"""
🌟 <b>Hoş Geldin {user['first_name']}!</b>

💰 <b>Bakiyen:</b> <code>${user.get('balance', 0):.4f}</code>
🎯 <b>Görevler:</b> <code>{user.get('tasks_completed', 0)}</code>
👥 <b>Referans:</b> <code>{self.get_ref_count(user_id)}</code>

<i>Hemen görevlere başla ve kazan!</i>
        """
        
        buttons = [
            ["🎯 Görevler", "💰 Bakiye"],
            ["💳 Yükle", "🏧 Çek"],
            ["👥 Davet", "📢 Reklam"],
            ["➕ Görev Oluştur"]
        ]
        
        if str(user_id) == ADMIN_ID:
            buttons.append(["👑 Admin"])
        
        send_msg(user_id, text, buttons, "keyboard")
    
    # 🎯 GÖREV SİSTEMİ
    def show_task_types(self, user_id):
        text = """
🎯 <b>Görev Türleri</b>

Hangi tür görev yapmak istersin?
        """
        
        buttons = [[
            {"text": "📢 Kanal", "callback_data": "task_type_kanal"},
            {"text": "👥 Grup", "callback_data": "task_type_grup"}
        ], [
            {"text": "📝 Post", "callback_data": "task_type_post"},
            {"text": "🤖 Bot", "callback_data": "task_type_bot"}
        ], [
            {"text": "🔄 Yenile", "callback_data": "refresh_tasks"},
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def show_tasks_of_type(self, user_id, task_type):
        tasks = get_active_tasks(user_id)
        type_tasks = [t for t in tasks if t.get("type") == task_type]
        
        if not type_tasks:
            text = f"""
📭 <b>{task_type.capitalize()} Görevleri</b>

Bu türde aktif görev bulunmuyor.
            """
            buttons = [[
                {"text": "🔙 Geri", "callback_data": "refresh_tasks"},
                {"text": "➕ Yeni Oluştur", "callback_data": "create_task"}
            ]]
        else:
            text = f"""
🎯 <b>{task_type.capitalize()} Görevleri</b> ({len(type_tasks)})

Aşağıdaki görevlerden birini seç:
            """
            
            buttons = []
            for task in type_tasks[:5]:  # Max 5 görev
                btn_text = f"${task['reward']:.4f} ({task.get('current', 0)}/{task.get('max_participants', 10)})"
                buttons.append([{
                    "text": btn_text,
                    "callback_data": f"view_task_{task['id']}"
                }])
            
            buttons.append([
                {"text": "🔙 Geri", "callback_data": "refresh_tasks"},
                {"text": "🔄 Yenile", "callback_data": f"task_type_{task_type}"}
            ])
        
        buttons.append([{"text": "🏠 Ana Menü", "callback_data": "main_menu"}])
        
        send_msg(user_id, text, buttons)
    
    def view_task_details(self, user_id, task_id):
        task_doc = db.collection("tasks").document(task_id).get()
        if not task_doc.exists:
            send_msg(user_id, "❌ Görev bulunamadı!")
            return
        
        task = task_doc.to_dict()
        
        # Katılım kontrolü
        participated = db.collection("task_participants")\
            .where("task_id", "==", task_id)\
            .where("user_id", "==", user_id).stream()
        
        has_participated = bool(list(participated))
        
        text = f"""
🎯 <b>Görev Detayı</b>

📝 <b>{task['title']}</b>
💰 <b>Ödül:</b> <code>${task['reward']:.4f}</code>
👥 <b>Katılım:</b> {task.get('current_participants', 0)}/{task.get('max_participants', 10)}

🔗 <b>Link:</b> {task['target_link']}

💡 <b>Talimatlar:</b>
"""
        
        if task["type"] == "kanal":
            text += "• Kanalı aç\n• Katıl butonuna bas\n• 10 saniye bekle"
        elif task["type"] == "grup":
            text += "• Grubu aç\n• Katıl butonuna bas\n• Mesaj gönder"
        elif task["type"] == "post":
            text += "• Postu aç\n• Like/beğen\n• Yorum yap"
        elif task["type"] == "bot":
            text += "• Botu aç\n• /start yaz\n• Bekle"
        
        buttons = []
        
        if not has_participated:
            buttons.append([{"text": "✅ Katıl", "callback_data": f"join_task_{task_id}"}])
        else:
            buttons.append([{"text": "✅ Tamamladım", "callback_data": f"complete_task_{task_id}"}])
        
        buttons.append([
            {"text": "🔙 Geri", "callback_data": f"task_type_{task['type']}"},
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ])
        
        send_msg(user_id, text, buttons)
    
    def join_task(self, user_id, task_id, callback_id):
        task_doc = db.collection("tasks").document(task_id).get()
        if not task_doc.exists:
            answer_callback(callback_id, "❌ Görev bulunamadı!", True)
            return
        
        task = task_doc.to_dict()
        
        # Üyelik kontrolü (kanal/grup için)
        if task["type"] in ["kanal", "grup"]:
            channel_username = task["target_link"].replace("https://t.me/", "").replace("@", "")
            if not check_member(channel_username, user_id):
                answer_callback(callback_id, f"❌ Önce @{channel_username} katılmalısın!", True)
                return
        
        # Katılım kaydı
        if add_task_participant(user_id, task_id):
            text = f"""
✅ <b>Göreve Katıldın!</b>

🎯 {task['title']}
💰 <b>Ödül:</b> <code>${task['reward']:.4f}</code>

📋 <b>Şimdi şunları yap:</b>
1. Linke tıkla: {task['target_link']}
2. Talimatları uygula
3. Tamamladığında 'Tamamladım' butonuna bas

⏳ <b>Süre:</b> 24 saat
            """
            
            buttons = [[
                {"text": "🔗 Linke Git", "url": task['target_link']},
                {"text": "✅ Tamamladım", "callback_data": f"complete_task_{task_id}"}
            ], [
                {"text": "🔙 Görevlere Dön", "callback_data": f"task_type_{task['type']}"}
            ]]
            
            answer_callback(callback_id, "✅ Göreve katıldın!")
            send_msg(user_id, text, buttons)
        else:
            answer_callback(callback_id, "❌ Zaten katıldın!", True)
    
    def complete_task(self, user_id, task_id, callback_id):
        task_doc = db.collection("tasks").document(task_id).get()
        if not task_doc.exists:
            answer_callback(callback_id, "❌ Görev bulunamadı!", True)
            return
        
        task = task_doc.to_dict()
        
        if task["type"] == "post":
            # Post görevi için proof bekliyoruz
            self.user_states[user_id] = {
                "action": "waiting_post_proof",
                "task_id": task_id
            }
            
            answer_callback(callback_id, "📸 Şimdi kanıt fotoğrafını gönder!")
            send_msg(user_id, "📸 <b>Post Görevi Kanıtı</b>\n\nLike/beğenme veya yorumunun ekran görüntüsünü gönder:")
            return
        
        # Diğer görev türleri için otomatik onay
        reward = complete_task_participation(user_id, task_id)
        
        if reward:
            text = f"""
🎉 <b>Görev Tamamlandı!</b>

🎯 {task['title']}
💰 <b>Kazanç:</b> <code>${reward:.4f}</code>
✅ <b>Bakiyene eklendi!</b>

<i>Yeni görevler için görevlere dön.</i>
            """
            
            buttons = [[
                {"text": "🎯 Yeni Görev", "callback_data": "refresh_tasks"},
                {"text": "💰 Bakiye", "callback_data": "show_balance"}
            ]]
            
            answer_callback(callback_id, f"✅ ${reward:.4f} kazandın!")
            send_msg(user_id, text, buttons)
        else:
            answer_callback(callback_id, "❌ Görev tamamlanamadı!", True)
    
    def process_post_proof(self, user_id, msg):
        if user_id not in self.user_states:
            return
        
        state = self.user_states[user_id]
        task_id = state.get("task_id")
        
        # Fotoğraf kontrolü
        if "photo" not in msg:
            send_msg(user_id, "❌ Lütfen ekran görüntüsü (fotoğraf) gönder!")
            return
        
        # En büyük boyutlu fotoğrafı al
        photo = msg["photo"][-1]["file_id"]
        
        # Görevi tamamla
        reward = complete_task_participation(user_id, task_id, photo)
        
        if reward:
            # State'i temizle
            del self.user_states[user_id]
            
            text = f"""
🎉 <b>Post Görevi Tamamlandı!</b>

📸 <b>Kanıt onaylandı</b>
💰 <b>Kazanç:</b> <code>${reward:.4f}</code>
✅ <b>Bakiyene eklendi!</b>
            """
            
            send_msg(user_id, text)
        else:
            send_msg(user_id, "❌ Görev tamamlanamadı!")
    
    # ➕ GÖREV OLUŞTURMA
    def start_create_task(self, user_id):
        text = """
➕ <b>Görev Oluştur</b>

Hangi tür görev oluşturmak istersin?
        """
        
        buttons = [[
            {"text": "📢 Kanal", "callback_data": "create_kanal"},
            {"text": "👥 Grup", "callback_data": "create_grup"}
        ], [
            {"text": "📝 Post", "callback_data": "create_post"},
            {"text": "🤖 Bot", "callback_data": "create_bot"}
        ], [
            {"text": "❌ İptal", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def process_task_type(self, user_id, text):
        task_types = {"kanal": "📢 Kanal", "grup": "👥 Grup", "post": "📝 Post", "bot": "🤖 Bot"}
        
        if text not in task_types:
            send_msg(user_id, "❌ Geçersiz görev türü! Lütfen listeden seç.")
            return
        
        task_type = [k for k, v in task_types.items() if v == text][0]
        
        self.user_states[user_id] = {
            "action": "waiting_task_link",
            "task_type": task_type
        }
        
        examples = {
            "kanal": "@kanal_username",
            "grup": "@grup_username veya grup linki",
            "post": "post linki (t.me/kanal/123)",
            "bot": "@bot_username"
        }
        
        send_msg(user_id, f"🔗 <b>{task_types[text]} Görev Linki</b>\n\nLinki gönder:\n<i>Örnek: {examples[task_type]}</i>")
    
    def process_task_link(self, user_id, text):
        if text.lower() == "iptal":
            if user_id in self.user_states:
                del self.user_states[user_id]
            send_msg(user_id, "❌ İptal edildi.")
            return
        
        self.user_states[user_id] = {
            "action": "waiting_task_title",
            "task_type": self.user_states[user_id]["task_type"],
            "link": text
        }
        
        send_msg(user_id, "📝 <b>Görev Başlığı</b>\n\nGörev için kısa başlık yaz:\n<i>Örnek: Kanalımıza Katılın!</i>")
    
    def process_task_title(self, user_id, text):
        if text.lower() == "iptal":
            if user_id in self.user_states:
                del self.user_states[user_id]
            send_msg(user_id, "❌ İptal edildi.")
            return
        
        self.user_states[user_id] = {
            "action": "waiting_task_budget",
            "task_type": self.user_states[user_id]["task_type"],
            "link": self.user_states[user_id]["link"],
            "title": text
        }
        
        user = get_user(user_id)
        balance = user.get("balance", 0)
        
        send_msg(user_id, f"💰 <b>Görev Bütçesi</b>\n\nNe kadar bütçe ayırmak istersin?\n\n💰 <b>Mevcut bakiye:</b> <code>${balance:.4f}</code>\n\n<i>Sayı gönder (Örnek: 0.05)</i>")
    
    def process_task_budget(self, user_id, text):
        try:
            budget = float(text)
            if budget <= 0:
                send_msg(user_id, "❌ Geçersiz miktar!")
                return
        except:
            send_msg(user_id, "❌ Geçersiz miktar! Sayı gönder.")
            return
        
        state = self.user_states[user_id]
        
        # Görevi oluştur
        task_id, result = create_task_from_user(
            creator_id=user_id,
            task_type=state["task_type"],
            title=state["title"],
            target_link=state["link"],
            budget=budget
        )
        
        # State'i temizle
        del self.user_states[user_id]
        
        if task_id:
            text = f"""
✅ <b>Görev Oluşturuldu!</b>

🎯 {state['title']}
🔗 {state['link']}
💰 <b>Bütçe:</b> <code>${budget:.4f}</code>
👥 <b>Katılım:</b> 0/10
🆔 <code>{task_id[:8]}...</code>

<i>Görevler listesinde görünecek.</i>
            """
            
            # Admin bildirimi
            if str(user_id) != ADMIN_ID:
                send_msg(ADMIN_ID, f"➕ <b>Yeni Görev Oluşturuldu</b>\n\nKullanıcı: {user_id}\nGörev: {state['title']}\nBütçe: ${budget:.4f}")
        else:
            text = f"❌ <b>Hata:</b> {result}"
        
        send_msg(user_id, text)
    
    # 💰 BAKİYE
    def show_balance(self, user_id):
        user = get_user(user_id)
        if not user:
            return
        
        text = f"""
💰 <b>Bakiye Durumu</b>
━━━━━━━━━━━━━━━━
💵 <b>Mevcut:</b> <code>${user.get('balance', 0):.4f}</code>
━━━━━━━━━━━━━━━━

🎯 <b>Toplam Görev:</b> {user.get('tasks_completed', 0)}
📈 <b>Toplam Kazanç:</b> <code>${user.get('total_earned', 0):.4f}</code>

💡 <b>Minimum Çekim:</b> <code>${MIN_WITHDRAW}</code>
        """
        
        buttons = [[
            {"text": "💳 Yükle", "callback_data": "start_deposit"},
            {"text": "🏧 Çek", "callback_data": "start_withdraw"}
        ], [
            {"text": "🎯 Görevler", "callback_data": "refresh_tasks"},
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def start_deposit(self, user_id):
        text = f"""
💳 <b>Bakiye Yükle</b>

ℹ️ <b>Manuel yükleme:</b>
👉 {SUPPORT_USERNAME}

💰 <b>Bize yaz, hızlıca yükleyelim!</b>

<i>Minimum: $0.01</i>
        """
        
        buttons = [[
            {"text": "📞 Destek", "url": f"https://t.me/{SUPPORT_USERNAME[1:]}"}
        ], [
            {"text": "💰 Bakiye", "callback_data": "show_balance"},
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def start_withdraw(self, user_id):
        user = get_user(user_id)
        balance = user.get("balance", 0)
        
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

<i>TRX adresinizi gönderin.</i>
            """
        
        buttons = [[
            {"text": "📞 Destek", "url": f"https://t.me/{SUPPORT_USERNAME[1:]}"}
        ], [
            {"text": "💰 Bakiye", "callback_data": "show_balance"},
            {"text": "🎯 Görevler", "callback_data": "refresh_tasks"}
        ], [
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    # 👥 REFERANS
    def show_referral(self, user_id):
        user = get_user(user_id)
        if not user:
            return
        
        ref_code = user.get("referral_code", "N/A")
        ref_link = f"https://t.me/{BOT_USERNAME}?start={ref_code}"
        
        # Referans sayısı
        refs = db.collection("users").where("referred_by", "==", user_id).stream()
        ref_count = len(list(refs))
        
        text = f"""
👥 <b>Referans Sistemi</b>
━━━━━━━━━━━━━━━━
👤 <b>Referansların:</b> <code>{ref_count}</code>
💰 <b>Toplam Bonus:</b> <code>${ref_count * REF_BONUS:.4f}</code>
━━━━━━━━━━━━━━━━

🎁 <b>Her referans:</b> <code>${REF_BONUS}</code>
💸 <b>Görev komisyonu:</b> %25

🔗 <b>Referans Linkin:</b>
<code>{ref_link}</code>

📋 <b>Referans Kodun:</b>
<code>{ref_code}</code>
        """
        
        buttons = [[
            {"text": "📋 Linki Kopyala", "callback_data": "copy_ref"}
        ], [
            {"text": "💰 Bakiye", "callback_data": "show_balance"},
            {"text": "🎯 Görevler", "callback_data": "refresh_tasks"}
        ], [
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def get_ref_count(self, user_id):
        refs = db.collection("users").where("referred_by", "==", user_id).stream()
        return len(list(refs))
    
    # 📢 REKLAMLAR
    def show_ads(self, user_id):
        text = """
📢 <b>Reklam Sistemi</b>

✨ <b>Özellikler:</b>
• Kendi reklamını oluştur
• İzleyerek para kazan
• Bütçeni yönet
• Detaylı istatistikler

<i>Yakında aktif!</i>
        """
        
        buttons = [[
            {"text": "💰 Bakiye", "callback_data": "show_balance"},
            {"text": "🎯 Görevler", "callback_data": "refresh_tasks"}
        ], [
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    # 👑 ADMIN PANEL
    def show_admin_panel(self, admin_id):
        # İstatistikler
        users = db.collection("users").stream()
        user_count = len(list(users))
        
        tasks = db.collection("tasks").where("status", "==", "active").stream()
        task_count = len(list(tasks))
        
        # Toplam bakiye
        total_balance = 0
        for user in db.collection("users").stream():
            total_balance += user.to_dict().get("balance", 0)
        
        text = f"""
👑 <b>ADMIN PANEL</b>
━━━━━━━━━━━━━━━━
👥 <b>Kullanıcılar:</b> {user_count}
🎯 <b>Aktif Görev:</b> {task_count}
💰 <b>Toplam Bakiye:</b> ${total_balance:.2f}
━━━━━━━━━━━━━━━━

<b>Komutlar:</b>
• /addbalance USER_ID AMOUNT
• /createtask TYPE LINK TITLE
• /stats - Detaylı istatistik
• /broadcast MESAJ - Duyuru yap
        """
        
        send_msg(admin_id, text)
    
    def admin_add_balance(self, text):
        try:
            parts = text.split()
            if len(parts) < 3:
                return
            
            target_id = parts[1]
            amount = float(parts[2])
            
            if update_balance(int(target_id), amount, "admin_add"):
                send_msg(ADMIN_ID, f"✅ Bakiye eklendi!\nKullanıcı: {target_id}\nMiktar: ${amount}")
                send_msg(int(target_id), f"🎉 Admin bakiyene ${amount:.4f} ekledi!")
        except:
            pass
    
    def admin_stats(self, admin_id):
        # Detaylı istatistikler
        users = db.collection("users").stream()
        
        today = datetime.now().date()
        new_today = 0
        active_today = 0
        
        for user in users:
            user_data = user.to_dict()
            created = datetime.fromisoformat(user_data.get("created_at", "")).date()
            last_active = datetime.fromisoformat(user_data.get("last_active", "")).date()
            
            if created == today:
                new_today += 1
            
            if last_active == today:
                active_today += 1
        
        text = f"""
📊 <b>Detaylı İstatistikler</b>
━━━━━━━━━━━━━━━━
👥 <b>Toplam Kullanıcı:</b> {len(list(db.collection("users").stream()))}
🆕 <b>Bugün Kayıt:</b> {new_today}
🟢 <b>Bugün Aktif:</b> {active_today}
🎯 <b>Aktif Görev:</b> {len(list(db.collection("tasks").where("status", "==", "active").stream()))}
━━━━━━━━━━━━━━━━
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
    if WEBHOOK_URL:
        url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={WEBHOOK_URL}/webhook"
        r = requests.get(url).json()
        return r
    return "WEBHOOK_URL gerekli"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
