# Gmail & Podcast Asistanı — Kurulum Rehberi

## Hızlı Başlangıç

```powershell
cd "C:\Users\hakan\OneDrive\Masaüstü\gmail-podcast"
pip install -r requirements.txt   # zaten kuruldu
Copy-Item .env.example .env       # .env oluştur, sonra düzenle
python app.py                     # sunucuyu başlat → http://localhost:5000
```

---

## 1. API Anahtarları (.env)

`.env` dosyasını aç ve şunları doldur:

| Değişken | Nereden |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `SPOTIFY_CLIENT_ID` | Aşağıdaki Adım 3 |
| `SPOTIFY_CLIENT_SECRET` | Aşağıdaki Adım 3 |
| `FLASK_SECRET` | Rastgele bir şey yaz (örn: `abc123xyz`) |

---

## 2. Gmail API (credentials.json)

1. https://console.cloud.google.com → Yeni proje oluştur
2. **APIs & Services → Library → "Gmail API" → Enable**
3. **Credentials → + CREATE CREDENTIALS → OAuth client ID**
   - Application type: **Desktop app**
   - İndir → `credentials.json` olarak bu klasöre koy
4. **OAuth consent screen → External → Test users** → kendi Gmail adresini ekle

İlk çalıştırmada tarayıcı açılır, izin verirsin. Sonra `token.json` oluşur.

---

## 3. Spotify API

1. https://developer.spotify.com/dashboard → **Create App**
   - App name: Gmail Podcast
   - Redirect URI: `http://localhost:5000/callback/spotify` ← **tam bu değer**
2. **Settings → Client ID ve Client Secret** → `.env`'e yaz

---

## 4. Çalıştır

```powershell
cd "C:\Users\hakan\OneDrive\Masaüstü\gmail-podcast"
python app.py
```

Tarayıcıda http://localhost:5000 açılır.

---

## Nasıl Kullanılır

### Email Özeti
1. **Emailler** sekmesi → **Getir**
2. Özetlemek istediğin emailleri tıkla (checkbox)
3. **Seçilenleri Özetle** → Sesli özet otomatik oynar

### Podcast Özeti
1. **Podcastler** sekmesi → **Spotify ile Giriş Yap** (ilk seferinde)
2. **Getir** → Son 30 günün yeni bölümleri listelenir
3. İstediğin bölümleri seç → **Seçilenleri Özetle**

### Sohbet / Q&A
- Herhangi bir özetten sonra **Sohbet** sekmesine geç
- "Acil email var mı?", "İlk bölümde kim konuştu?" gibi sorular sor
- **Sesli yanıt** kutusunu işaretlersen cevabı da sesli alırsın
