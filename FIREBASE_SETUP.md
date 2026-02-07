# Firebase Kurulum ve Güvenlik Rehberi (Kısa)

## 1) Ortam Değişkenleri (ENV)
Sunucunda şu değişkenleri **tek satır** olarak ekle:

- `FIREBASE_CREDENTIALS_JSON` → Service Account JSON içeriği (tek satır)
- `FIREBASE_PROJECT_ID` → Firestore proje ID
- `FIREBASE_DATABASE_URL` → Realtime DB URL (Realtime kullanıyorsan)

> **Not:** JSON dosyasını repoya koyma. Sadece env içinde tut.

### Kopyala/Yapıştır ENV Şablonu
```
export FIREBASE_CREDENTIALS_JSON='{"type":"service_account","project_id":"YOUR_PROJECT_ID","private_key_id":"YOUR_PRIVATE_KEY_ID","private_key":"-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY\n-----END PRIVATE KEY-----\n","client_email":"YOUR_CLIENT_EMAIL","client_id":"YOUR_CLIENT_ID","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/YOUR_CLIENT_EMAIL_ENCODED"}'
export FIREBASE_PROJECT_ID='YOUR_PROJECT_ID'
export FIREBASE_DATABASE_URL='https://YOUR_PROJECT_ID-default-rtdb.firebaseio.com'
```

**Alternatif (Base64):**
```
export FIREBASE_CREDENTIALS_BASE64='BASE64_JSON_HERE'
```

## 2) Firestore Rules (Gelişmiş ve Daha Güvenli)
> Aşağıdaki örnek, temel koleksiyonları daha kontrollü erişimle korur.  
> **Not:** Koleksiyon/alan adlarını kendi yapına göre güncelle.

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    function isSignedIn() {
      return request.auth != null;
    }
    function isAdmin() {
      return isSignedIn() && request.auth.token.admin == true;
    }
    function isOwner(userId) {
      return isSignedIn() && request.auth.uid == userId;
    }
    function validString(field, min, max) {
      return field is string && field.size() >= min && field.size() <= max;
    }
    function validAmount(amount, min, max) {
      return amount is number && amount >= min && amount <= max;
    }

    // Users
    match /users/{userId} {
      allow read: if isOwner(userId) || isAdmin();
      allow create: if isOwner(userId);
      allow update: if isOwner(userId) &&
        request.resource.data.diff(resource.data).changedKeys().hasOnly([
          "username", "first_name", "last_name", "language", "last_active"
        ]);
      allow delete: if false;
    }

    // Tasks (public read, admin write)
    match /tasks/{taskId} {
      allow read: if isSignedIn();
      allow create, update, delete: if isAdmin();
    }

    // Task participations (user create, admin update)
    match /task_participations/{participationId} {
      allow read: if isAdmin() || (isSignedIn() && resource.data.user_id == request.auth.uid);
      allow create: if isSignedIn() &&
        request.resource.data.user_id == request.auth.uid &&
        validString(request.resource.data.task_id, 1, 128);
      allow update: if isAdmin();
      allow delete: if false;
    }

    // Deposits (user create, admin update)
    match /deposits/{depositId} {
      allow read: if isAdmin() || (isSignedIn() && resource.data.user_id == request.auth.uid);
      allow create: if isSignedIn() &&
        request.resource.data.user_id == request.auth.uid &&
        validAmount(request.resource.data.amount, 1, 1000000) &&
        validString(request.resource.data.txid, 4, 128);
      allow update: if isAdmin();
      allow delete: if false;
    }

    // Withdrawals (admin only for now)
    match /withdrawals/{withdrawalId} {
      allow read, write: if isAdmin();
    }

    // Stats (read-only for admin)
    match /stats/{statId} {
      allow read: if isAdmin();
      allow write: if isAdmin();
    }
  }
}
```

## 3) Realtime DB Rules (Gelişmiş)
> Admin ayrıcalıkları için `admin` custom claim kullanır.  
> Kullanıcılar sadece kendi kayıtlarını okuyabilir/yazabilir.

```
{
  "rules": {
    ".read": "auth != null",
    ".write": "auth != null",
    "users": {
      "$uid": {
        ".read": "auth != null && auth.uid === $uid",
        ".write": "auth != null && auth.uid === $uid"
      }
    },
    "tasks": {
      ".read": "auth != null",
      ".write": "auth != null && auth.token.admin === true"
    },
    "task_participations": {
      "$id": {
        ".read": "auth != null && (data.child('user_id').val() === auth.uid || auth.token.admin === true)",
        ".write": "auth != null && (newData.child('user_id').val() === auth.uid || auth.token.admin === true)"
      }
    },
    "deposits": {
      "$id": {
        ".read": "auth != null && (data.child('user_id').val() === auth.uid || auth.token.admin === true)",
        ".write": "auth != null && (newData.child('user_id').val() === auth.uid || auth.token.admin === true)"
      }
    },
    "withdrawals": {
      ".read": "auth != null && auth.token.admin === true",
      ".write": "auth != null && auth.token.admin === true"
    },
    "stats": {
      ".read": "auth != null && auth.token.admin === true",
      ".write": "auth != null && auth.token.admin === true"
    }
  }
}
```
