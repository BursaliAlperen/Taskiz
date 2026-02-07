# Taskiz

## Firebase Veritabanı Rehberi (Kullanıcı Dostu)

Taskiz botunu **SQLite** yerine **Firebase** ile daha hızlı, ölçeklenebilir ve güvenli hale getirebilirsiniz. **Firestore** (önerilen) veya **Realtime DB** kullanılabilir. Kısa ve net rehber aşağıdadır.

### 1) Firebase Projesi Oluştur
1. https://console.firebase.google.com/ adresine gir  
2. **Yeni proje** oluştur  
3. **Firestore** veya **Realtime DB**’i etkinleştir  

### 2) Service Account (JSON) Al
1. **Project Settings → Service accounts**  
2. **Generate new private key** butonuyla JSON indir  
3. JSON’u güvenli bir yerde sakla  

### 3) Ortam Değişkenleri
Sunucunda şu değişkenleri ayarla:

- `FIREBASE_CREDENTIALS_JSON` → JSON içeriği (tek satır halde)
- `FIREBASE_PROJECT_ID` → Firebase proje ID (Firestore için)
- `FIREBASE_DATABASE_URL` → Realtime DB URL (Realtime kullanacaksan)

### 4) Kurulum
```bash
pip install firebase-admin
```

### 5) Firestore Bağlantı (Önerilen)
```python
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate(json.loads(os.environ["FIREBASE_CREDENTIALS_JSON"]))
firebase_admin.initialize_app(cred, {
    "projectId": os.environ["FIREBASE_PROJECT_ID"]
})
db = firestore.client()
```

### 5B) Realtime DB Bağlantısı (Opsiyonel)
```python
import firebase_admin
from firebase_admin import credentials, db
import json

cred = credentials.Certificate(json.loads(os.environ["FIREBASE_CREDENTIALS_JSON"]))
firebase_admin.initialize_app(cred, {
    "databaseURL": os.environ["FIREBASE_DATABASE_URL"]
})
ref = db.reference("/")
```

### 6) Koleksiyonlar (Öneri)
`users`, `tasks`, `task_participations`, `withdrawals`, `stats`

### 7) Firestore Rules (Basit)
```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if request.auth != null;
    }
  }
}
```
