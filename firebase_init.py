import firebase_admin
from firebase_admin import credentials, firestore, db as realtime_db
from datetime import datetime

# Firebase bağlantısı (kalıcı ana veri kaynağı)
cred = credentials.Certificate("taskiz-2db5a-firebase-adminsdk-fbsvc-98e0792e57.json")
firebase_admin.initialize_app(cred, {
    'projectId': 'taskiz-2db5a',
    'databaseURL': 'https://taskiz-2db5a-default-rtdb.firebaseio.com/'
})

fs = firestore.client()
rtdb = realtime_db.reference()


def init_database():
    """Firestore + Realtime başlangıç verisini tek seferde oluşturur."""

    sample_tasks = [
        {
            "type": "kanal",
            "title": "Ana Kanalımıza Katılın",
            "target_link": "https://t.me/TaskizLive",
            "reward": 0.0025,
            "max_participants": 10,
            "current_participants": 0,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "creator_id": "admin"
        },
        {
            "type": "grup",
            "title": "Grup Sohbetimize Katıl",
            "target_link": "https://t.me/+xxx",
            "reward": 0.0015,
            "max_participants": 10,
            "current_participants": 0,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "creator_id": "admin"
        },
        {
            "type": "bot",
            "title": "Yardımcı Botumuzu Başlat",
            "target_link": "https://t.me/TaskizHelperBot",
            "reward": 0.0010,
            "max_participants": 10,
            "current_participants": 0,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "creator_id": "admin"
        }
    ]

    for task in sample_tasks:
        doc_ref = fs.collection("tasks").add(task)[1]
        rtdb.child("tasks").child(doc_ref.id).set(task)

    rtdb.child("stats").set({
        "total_users": 0,
        "total_tasks": len(sample_tasks),
        "total_participations": 0,
        "total_withdrawals": 0,
        "total_deposits": 0,
        "last_updated": datetime.now().isoformat()
    })

    print("✅ Veritabanı başlatıldı!")
    print(f"📊 {len(sample_tasks)} örnek görev eklendi")
    print("🎯 Bot hazır!")


if __name__ == "__main__":
    init_database()
