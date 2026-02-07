# firebase_init.py (Firebase kurulum scripti)
import firebase_admin
from firebase_admin import credentials, firestore
import json

# Firebase bağlantısı
cred = credentials.Certificate("taskiz-2db5a-firebase-adminsdk-fbsvc-98e0792e57.json")
firebase_admin.initialize_app(cred, {
    'projectId': 'taskiz-2db5a',
    'databaseURL': 'https://taskiz-2db5a-default-rtdb.firebaseio.com/'
})

db = firestore.client()

# Örnek veriler oluştur
def create_sample_data():
    # Örnek görevler
    sample_tasks = [
        {
            "type": "kanal",
            "title": "Kanalımıza Katılın!",
            "target_link": "@TaskizLive",
            "reward": 0.0025,
            "max_participants": 10,
            "status": "active"
        },
        {
            "type": "grup",
            "title": "Grup sohbetimize katıl",
            "target_link": "@TaskizChat",
            "reward": 0.0015,
            "max_participants": 10,
            "status": "active"
        },
        {
            "type": "bot",
            "title": "Botumuzu başlatın",
            "target_link": "@TaskizHelperBot",
            "reward": 0.0010,
            "max_participants": 10,
            "status": "active"
        }
    ]
    
    for task in sample_tasks:
        db.collection("tasks").add(task)
    
    print("✅ Örnek veriler oluşturuldu!")

if __name__ == "__main__":
    create_sample_data()
