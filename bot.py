# bot.py
import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore, db as realtime_db
import uuid

# 🔧 AYARLAR
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "")
SUPPORT_USERNAME = "@AlperenTHE"
BOT_USERNAME = "TaskizBot"

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

# 🚀 TELEGRAM FONKSİYONLARI
def send_msg(chat_id, text, buttons=None, markup_type="inline"):
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
            payload["reply_markup"] = {"keyboard": buttons, "resize_keyboard": True}
    
    requests.post(url, json=payload)

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

def check_member(chat_id, user_id):
    url = f"https://api.telegram.org/bot{TOKEN}/getChatMember"
    payload = {"chat_id": chat_id, "user_id": user_id}
    r = requests.post(url, json=payload).json()
    if r.get("ok"):
        status = r["result"]["status"]
        return status in ["member", "administrator", "creator"]
    return False

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
        "last_active": datetime.now().isoformat()
    }
    
    db.collection("users").document(str(user_id)).set(user_data)
    
    # Referans bonusu
    if referred_by:
        ref_user = get_user(referred_by)
        if ref_user:
            new_balance = ref_user.get("balance", 0) + REF_BONUS
            db.collection("users").document(str(referred_by)).update({
                "balance": new_balance,
                "total_earned": ref_user.get("total_earned", 0) + REF_BONUS
            })
            
            # Bildirim
            send_msg(STATS_CHANNEL, f"""
👥 <b>YENİ REFERANS</b>
━━━━━━━━━━━━
👤 Referans: <code>{referred_by}</code>
🆕 Yeni: <code>{user_id}</code>
💰 Bonus: <code>${REF_BONUS}</code>
            """)
    
    return user_data

def update_balance(user_id, amount, reason=""):
    user = get_user(user_id)
    if user:
        new_balance = user.get("balance", 0) + amount
        new_earned = user.get("total_earned", 0) + max(amount, 0)
        
        db.collection("users").document(str(user_id)).update({
            "balance": new_balance,
            "total_earned": new_earned,
            "last_active": datetime.now().isoformat()
        })
        
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
    tasks = []
    docs = db.collection("tasks").where("status", "==", "active").stream()
    
    for doc in docs:
        task = doc.to_dict()
        task["id"] = doc.id
        
        # Kullanıcı katıldı mı?
        if user_id:
            participation = db.collection("participations").where("task_id", "==", doc.id)\
                .where("user_id", "==", user_id).limit(1).stream()
            if list(participation):
                continue
        
        # Katılım limiti
        participants = db.collection("participations").where("task_id", "==", doc.id).stream()
        task["current"] = len(list(participants))
        
        if task["current"] < task.get("max_participants", 10):
            tasks.append(task)
    
    return tasks

def create_task(creator_id, task_type, title, target_link, reward, max_participants=10):
    task_data = {
        "creator_id": creator_id,
        "type": task_type,
        "title": title,
        "target_link": target_link,
        "reward": reward,
        "max_participants": max_participants,
        "current_participants": 0,
        "status": "active",
        "created_at": datetime.now().isoformat()
    }
    
    task_ref = db.collection("tasks").add(task_data)
    return task_ref[1].id

def complete_task(user_id, task_id):
    # Görevi al
    task_doc = db.collection("tasks").document(task_id).get()
    if not task_doc.exists:
        return None
    
    task = task_doc.to_dict()
    
    # Zaten katıldı mı?
    existing = db.collection("participations").where("task_id", "==", task_id)\
        .where("user_id", "==", user_id).limit(1).stream()
    if list(existing):
        return None
    
    # Katılım kaydı
    db.collection("participations").add({
        "user_id": user_id,
        "task_id": task_id,
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "reward": task["reward"]
    })
    
    # Bakiye ekle
    update_balance(user_id, task["reward"], "task_reward")
    
    # Görev istatistik güncelle
    user = get_user(user_id)
    db.collection("users").document(str(user_id)).update({
        "tasks_completed": user.get("tasks_completed", 0) + 1
    })
    
    # Task katılımcı sayısı
    participants = db.collection("participations").where("task_id", "==", task_id).stream()
    current = len(list(participants))
    
    db.collection("tasks").document(task_id).update({
        "current_participants": current
    })
    
    # Limit dolduysa durdur
    if current >= task["max_participants"]:
        db.collection("tasks").document(task_id).update({"status": "completed"})
    
    return task["reward"]

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
        
        # Admin komutları
        if str(user_id) == ADMIN_ID and text.startswith("/admin"):
            self.show_admin(user_id)
            return
        
        # Referans kontrolü
        referred_by = None
        if text.startswith("/start"):
            parts = text.split()
            if len(parts) > 1:
                ref_code = parts[1]
                # Ref koduyla eşleşen kullanıcıyı bul
                docs = db.collection("users").where("referral_code", "==", ref_code).limit(1).stream()
                for doc in docs:
                    referred_by = doc.to_dict()["user_id"]
                    break
        
        user = get_user(user_id)
        
        # Yeni kullanıcı
        if not user:
            username = msg["from"].get("username", "")
            first_name = msg["from"].get("first_name", "")
            last_name = msg["from"].get("last_name", "")
            
            user = create_user(user_id, username, first_name, last_name, referred_by)
            
            # Bildirim
            send_msg(STATS_CHANNEL, f"""
👤 <b>YENİ ÜYE</b>
━━━━━━━━━━━━
🎉 {first_name} {last_name or ''}
🆔 <code>{user_id}</code>
📅 {datetime.now().strftime('%H:%M')}
            """)
            
            self.show_main_menu(user_id)
            return
        
        # State kontrolü
        if user_id in self.user_states:
            state = self.user_states[user_id]
            action = state.get("action")
            
            if action == "waiting_task_type":
                self.handle_task_type(user_id, text)
            elif action == "waiting_task_link":
                self.handle_task_link(user_id, text)
            elif action == "waiting_task_title":
                self.handle_task_title(user_id, text)
            elif action == "waiting_deposit_amount":
                self.handle_deposit_amount(user_id, text)
            elif action == "waiting_withdraw_amount":
                self.handle_withdraw_amount(user_id, text)
            elif action == "waiting_withdraw_address":
                self.handle_withdraw_address(user_id, text)
            return
        
        # Normal komutlar
        if text == "/start" or text == "🏠 Ana Menü":
            self.show_main_menu(user_id)
        elif text == "🎯 Görevler":
            self.show_tasks(user_id)
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
        elif text == "⚙️ Ayarlar":
            self.show_settings(user_id)
        elif text == "➕ Görev Oluştur" and str(user_id) == ADMIN_ID:
            self.start_create_task(user_id)
    
    def handle_callback(self, callback):
        data = callback["data"]
        user_id = callback["from"]["id"]
        msg_id = callback["message"]["message_id"]
        callback_id = callback["id"]
        
        try:
            if data == "main_menu":
                self.show_main_menu(user_id)
            elif data == "refresh_tasks":
                self.show_tasks(user_id)
                answer_callback(callback_id, "🔄 Yenilendi")
            elif data.startswith("join_task_"):
                task_id = data.split("_")[2]
                self.join_task(user_id, task_id, callback_id)
            elif data == "start_create_task":
                self.start_create_task(user_id)
                answer_callback(callback_id)
            elif data.startswith("select_task_type_"):
                task_type = data.split("_")[3]
                self.select_task_type(user_id, task_type)
                answer_callback(callback_id)
            elif data == "cancel_action":
                if user_id in self.user_states:
                    del self.user_states[user_id]
                send_msg(user_id, "❌ İşlem iptal edildi.")
                answer_callback(callback_id)
            elif data == "view_ads":
                self.show_random_ad(user_id)
                answer_callback(callback_id)
            elif data.startswith("ad_reward_"):
                ad_id = data.split("_")[2]
                self.claim_ad_reward(user_id, ad_id, callback_id)
            elif data == "create_ad":
                self.start_create_ad(user_id)
                answer_callback(callback_id)
            elif data == "my_ads":
                self.show_my_ads(user_id)
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
            ["⚙️ Ayarlar"]
        ]
        
        if str(user_id) == ADMIN_ID:
            buttons.append(["➕ Görev Oluştur"])
        
        send_msg(user_id, text, buttons, "keyboard")
    
    # 🎯 GÖREVLER
    def show_tasks(self, user_id):
        tasks = get_active_tasks(user_id)
        
        if not tasks:
            text = """
📭 <b>Görev Bulunamadı</b>

Şu anda aktif görev yok.
Yeni görevler için bekle veya
kendi görevini oluştur!
            """
            buttons = [[
                {"text": "🔄 Yenile", "callback_data": "refresh_tasks"},
                {"text": "➕ Görev Oluştur", "callback_data": "start_create_task"}
            ], [
                {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
            ]]
            
            send_msg(user_id, text, buttons)
            return
        
        text = f"""
🎯 <b>Mevcut Görevler</b> ({len(tasks)})

<i>Bir görev seç ve hemen başla!</i>
        """
        
        buttons = []
        for task in tasks[:8]:  # Max 8 görev
            reward = task.get("reward", 0)
            current = task.get("current", 0)
            max_p = task.get("max_participants", 10)
            
            emoji = {
                "kanal": "📢",
                "grup": "👥",
                "post": "📝",
                "bot": "🤖"
            }.get(task.get("type", ""), "🎯")
            
            btn_text = f"{emoji} ${reward:.4f} ({current}/{max_p})"
            buttons.append([{
                "text": btn_text,
                "callback_data": f"join_task_{task['id']}"
            }])
        
        buttons.append([
            {"text": "🔄 Yenile", "callback_data": "refresh_tasks"},
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ])
        
        send_msg(user_id, text, buttons)
    
    def join_task(self, user_id, task_id, callback_id):
        task_doc = db.collection("tasks").document(task_id).get()
        if not task_doc.exists:
            answer_callback(callback_id, "❌ Görev bulunamadı!", True)
            return
        
        task = task_doc.to_dict()
        
        # Üyelik kontrolü
        if task["type"] == "kanal":
            if not check_member(task["target_link"].replace("@", ""), user_id):
                answer_callback(callback_id, f"❌ Önce {task['target_link']} kanalına katıl!", True)
                return
        
        # Görevi tamamla
        reward = complete_task(user_id, task_id)
        
        if reward:
            text = f"""
✅ <b>Görev Tamamlandı!</b>

🎯 {task['title']}
💰 <b>Kazanç:</b> <code>${reward:.4f}</code>
⚡ <b>Bakiyene eklendi!</b>
            """
            
            answer_callback(callback_id, f"✅ +${reward:.4f} eklendi!")
            send_msg(user_id, text)
        else:
            answer_callback(callback_id, "❌ Zaten katıldın veya görev doldu!", True)
    
    # ➕ GÖREV OLUŞTURMA
    def start_create_task(self, user_id):
        text = """
➕ <b>Görev Oluştur</b>

Önce görev türünü seç:
        """
        
        buttons = [[
            {"text": "📢 Kanal", "callback_data": "select_task_type_kanal"},
            {"text": "👥 Grup", "callback_data": "select_task_type_grup"}
        ], [
            {"text": "📝 Post", "callback_data": "select_task_type_post"},
            {"text": "🤖 Bot", "callback_data": "select_task_type_bot"}
        ], [
            {"text": "❌ İptal", "callback_data": "cancel_action"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def select_task_type(self, user_id, task_type):
        self.user_states[user_id] = {
            "action": "waiting_task_link",
            "task_type": task_type
        }
        
        examples = {
            "kanal": "@kanal_username",
            "grup": "@grup_username veya grup linki",
            "post": "post linki",
            "bot": "@bot_username"
        }
        
        text = f"""
🔗 <b>Hedef Link</b>

Görevin hedef linkini gönder:
<i>Örnek: {examples[task_type]}</i>

❌ İptal için: /cancel
        """
        
        send_msg(user_id, text)
    
    def handle_task_link(self, user_id, text):
        if text == "/cancel":
            if user_id in self.user_states:
                del self.user_states[user_id]
            send_msg(user_id, "❌ İptal edildi.")
            return
        
        self.user_states[user_id] = {
            "action": "waiting_task_title",
            "task_type": self.user_states[user_id]["task_type"],
            "target_link": text
        }
        
        text = """
📝 <b>Görev Başlığı</b>

Görev için kısa bir başlık yaz:
<i>Örnek: Kanalımıza Katılın!</i>

❌ İptal için: /cancel
        """
        
        send_msg(user_id, text)
    
    def handle_task_title(self, user_id, text):
        if text == "/cancel":
            if user_id in self.user_states:
                del self.user_states[user_id]
            send_msg(user_id, "❌ İptal edildi.")
            return
        
        state = self.user_states[user_id]
        task_type = state["task_type"]
        target_link = state["target_link"]
        
        reward = TASK_REWARDS.get(task_type, 0.001)
        
        # Görevi oluştur
        task_id = create_task(
            creator_id=user_id,
            task_type=task_type,
            title=text,
            target_link=target_link,
            reward=reward,
            max_participants=10
        )
        
        # State'i temizle
        del self.user_states[user_id]
        
        text = f"""
✅ <b>Görev Oluşturuldu!</b>

🎯 {text}
🔗 {target_link}
💰 <b>Ödül:</b> <code>${reward:.4f}</code>
👥 <b>Katılım:</b> 0/10
🆔 <code>{task_id[:8]}...</code>

<i>Artık görevler listesinde görünecek.</i>
        """
        
        send_msg(user_id, text)
    
    # 💰 BAKİYE
    def show_balance(self, user_id):
        user = get_user(user_id)
        if not user:
            return
        
        ads_ref = db.collection("ads").where("owner_id", "==", user_id)\
            .where("status", "==", "active").stream()
        ad_budget = sum(ad.to_dict().get("remaining_budget", 0) for ad in ads_ref)
        
        text = f"""
💰 <b>Bakiye Durumu</b>
━━━━━━━━━━━━━━━━
💵 <b>Mevcut:</b> <code>${user.get('balance', 0):.4f}</code>
📢 <b>Reklam Bütçesi:</b> <code>${ad_budget:.4f}</code>
━━━━━━━━━━━━━━━━

🎯 <b>Toplam Görev:</b> {user.get('tasks_completed', 0)}
📈 <b>Toplam Kazanç:</b> <code>${user.get('total_earned', 0):.4f}</code>

💡 <b>Minimum Çekim:</b> <code>${MIN_WITHDRAW}</code>
        """
        
        buttons = [[
            {"text": "💳 Yükle", "callback_data": "show_deposit"},
            {"text": "🏧 Çek", "callback_data": "show_withdraw"}
        ], [
            {"text": "📢 Reklam", "callback_data": "view_ads"},
            {"text": "🎯 Görevler", "callback_data": "refresh_tasks"}
        ], [
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def show_deposit(self, user_id):
        text = f"""
💳 <b>Bakiye Yükle</b>

ℹ️ <b>Manuel yükleme için:</b>
👉 {SUPPORT_USERNAME}

<i>Bize yaz, işlemi hızlıca tamamlayalım.</i>

💰 <b>Minimum:</b> Yok
⏱️ <b>Süre:</b> 5-15 dakika
        """
        
        buttons = [[
            {"text": "📞 Destek", "url": f"https://t.me/{SUPPORT_USERNAME[1:]}"}
        ], [
            {"text": "💰 Bakiye", "callback_data": "show_balance"},
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def show_withdraw(self, user_id):
        user = get_user(user_id)
        if not user:
            return
        
        balance = user.get("balance", 0)
        
        if balance < MIN_WITHDRAW:
            text = f"""
🏧 <b>Para Çekme</b>

❌ <b>Bakiye Yetersiz!</b>

💰 <b>Mevcut:</b> <code>${balance:.4f}</code>
📊 <b>Gerekli:</b> <code>${MIN_WITHDRAW}</code>
⬇️ <b>Eksik:</b> <code>${MIN_WITHDRAW - balance:.4f}</code>

<i>Görevler yaparak veya yükleme yaparak bakiyeni artır.</i>
            """
        else:
            text = f"""
🏧 <b>Para Çekme</b>

💰 <b>Mevcut:</b> <code>${balance:.4f}</code>
📊 <b>Minimum:</b> <code>${MIN_WITHDRAW}</code>

<i>Çekim talebi oluşturmak için:</i>
👉 {SUPPORT_USERNAME}

🔗 <b>TRX adresinizi gönderin.</b>
            """
        
        buttons = [[
            {"text": "📞 Destek", "url": f"https://t.me/{SUPPORT_USERNAME[1:]}"}
        ], [
            {"text": "💰 Bakiye", "callback_data": "show_balance"},
            {"text": "🎯 Görevler", "callback_data": "refresh_tasks"},
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
💰 <b>Bonus Kazancın:</b> <code>${ref_count * REF_BONUS:.4f}</code>
━━━━━━━━━━━━━━━━

🎁 <b>Her referans için:</b>
<code>${REF_BONUS}</code> bonus veriyoruz!

🔗 <b>Referans Linkin:</b>
<code>{ref_link}</code>

📋 <b>Referans Kodun:</b>
<code>{ref_code}</code>

💡 <b>Arkadaşlarını davet et, hem sen kazan hem onlar!</b>
        """
        
        buttons = [[
            {"text": "📋 Kodu Kopyala", "callback_data": "copy_ref"}
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

Reklam ver veya izleyerek para kazan!

✨ <b>Özellikler:</b>
• Kendi reklamını oluştur
• İzleyerek para kazan
• Bütçeni yönet
• Detaylı istatistikler
        """
        
        buttons = [[
            {"text": "👁️ Reklam İzle", "callback_data": "view_ads"},
            {"text": "➕ Reklam Ver", "callback_data": "create_ad"}
        ], [
            {"text": "📊 Reklamlarım", "callback_data": "my_ads"}
        ], [
            {"text": "💰 Bakiye", "callback_data": "show_balance"},
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def show_random_ad(self, user_id):
        # Rastgele aktif reklam bul
        ads = db.collection("ads").where("status", "==", "active")\
            .where("remaining_budget", ">", 0).stream()
        
        ads_list = []
        for ad_doc in ads:
            ad = ad_doc.to_dict()
            ad["id"] = ad_doc.id
            if ad.get("owner_id") != user_id:
                ads_list.append(ad)
        
        if not ads_list:
            text = """
📭 <b>Reklam Yok</b>

Şu anda izlenecek reklam bulunmuyor.
Daha sonra tekrar dene!
            """
            buttons = [[{"text": "🔄 Yenile", "callback_data": "view_ads"}]]
            send_msg(user_id, text, buttons)
            return
        
        import random
        ad = random.choice(ads_list)
        
        reward = min(ad["remaining_budget"] * 0.5, 0.01)
        
        text = f"""
📢 <b>REKLAM</b>
━━━━━━━━━━━━━━━━
{ad.get('text', 'Reklam metni')}
━━━━━━━━━━━━━━━━

💰 <b>Ödül:</b> <code>${reward:.4f}</code>

<i>Linke gidip 10 saniye bekle,
ardından ödülü al!</i>
        """
        
        buttons = [[
            {"text": "🔗 Linke Git", "url": ad["link"]}
        ], [
            {"text": "✅ Ödülü Al", "callback_data": f"ad_reward_{ad['id']}"}
        ], [
            {"text": "↩️ Başka Reklam", "callback_data": "view_ads"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    def claim_ad_reward(self, user_id, ad_id, callback_id):
        ad_doc = db.collection("ads").document(ad_id).get()
        if not ad_doc.exists:
            answer_callback(callback_id, "❌ Reklam bulunamadı!", True)
            return
        
        ad = ad_doc.to_dict()
        
        # Zaten izlendi mi?
        viewed = db.collection("ad_views").where("ad_id", "==", ad_id)\
            .where("user_id", "==", user_id).limit(1).stream()
        if list(viewed):
            answer_callback(callback_id, "❌ Bu reklamı zaten izledin!", True)
            return
        
        reward = min(ad["remaining_budget"] * 0.5, 0.01)
        
        # Bakiye ekle
        update_balance(user_id, reward, "ad_reward")
        
        # İzleme kaydı
        db.collection("ad_views").add({
            "ad_id": ad_id,
            "user_id": user_id,
            "reward": reward,
            "viewed_at": datetime.now().isoformat()
        })
        
        # Reklam bütçesini düş
        new_budget = ad["remaining_budget"] - reward
        db.collection("ads").document(ad_id).update({
            "remaining_budget": new_budget
        })
        
        # Bütçe biterse durdur
        if new_budget <= 0:
            db.collection("ads").document(ad_id).update({"status": "completed"})
        
        answer_callback(callback_id, f"✅ ${reward:.4f} eklendi!", True)
    
    def start_create_ad(self, user_id):
        user = get_user(user_id)
        if not user:
            return
        
        text = """
➕ <b>Reklam Oluştur</b>

Reklam bütçen: <code>${balance:.4f}</code>

Önce reklam linkini gönder:
<i>Örnek: https://t.me/kanal</i>

❌ İptal için: /cancel
        """.format(balance=user.get("balance", 0))
        
        self.user_states[user_id] = {"action": "waiting_ad_link"}
        send_msg(user_id, text)
    
    def show_my_ads(self, user_id):
        ads = db.collection("ads").where("owner_id", "==", user_id).stream()
        
        text = """
📊 <b>Reklamlarım</b>

<i>Aktif reklamların:</i>
        """
        
        buttons = []
        for ad_doc in ads:
            ad = ad_doc.to_dict()
            status = "✅" if ad["status"] == "active" else "⏸️"
            text += f"\n{status} ${ad.get('remaining_budget', 0):.4f} - {ad.get('text', 'Reklam')[:20]}..."
        
        if not buttons:
            text += "\n\n📭 <i>Henüz reklamın yok.</i>"
        
        buttons.append([{"text": "➕ Yeni Reklam", "callback_data": "create_ad"}])
        buttons.append([{"text": "🏠 Ana Menü", "callback_data": "main_menu"}])
        
        send_msg(user_id, text, buttons)
    
    # ⚙️ AYARLAR
    def show_settings(self, user_id):
        user = get_user(user_id)
        if not user:
            return
        
        text = f"""
⚙️ <b>Ayarlar</b>

👤 <b>ID:</b> <code>{user_id}</code>
📅 <b>Kayıt Tarihi:</b> {user.get('created_at', '')[:10]}
🌐 <b>Kullanıcı Adı:</b> @{user.get('username', 'yok')}

🔧 <b>Hızlı İşlemler:</b>
        """
        
        buttons = [[
            {"text": "🔄 Yenile", "callback_data": "refresh_tasks"},
            {"text": "📞 Destek", "url": f"https://t.me/{SUPPORT_USERNAME[1:]}"}
        ], [
            {"text": "💰 Bakiye", "callback_data": "show_balance"},
            {"text": "👥 Davet", "callback_data": "show_referral"}
        ], [
            {"text": "🏠 Ana Menü", "callback_data": "main_menu"}
        ]]
        
        send_msg(user_id, text, buttons)
    
    # 👑 ADMIN
    def show_admin(self, admin_id):
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
