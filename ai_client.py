import os
import io
import time
import datetime
import anthropic
import openai
import requests
from pathlib import Path
try:
    import feedparser
except ImportError:
    feedparser = None
try:
    from groq import Groq as _Groq
except ImportError:
    _Groq = None

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = BASE_DIR / "static" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def _claude():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def summarize_emails(emails):
    client = _claude()
    today = datetime.date.today().strftime("%d %B %Y")

    lines = []
    for i, e in enumerate(emails, 1):
        lines.append(f"--- Email {i} ---")
        lines.append(f"Gönderen: {e['from']}")
        lines.append(f"Konu: {e['subject']}")
        lines.append(f"Tarih: {e['date']}")
        if e.get("body"):
            lines.append(f"İçerik: {e['body']}")
        lines.append("")
    email_text = "\n".join(lines)

    subjects = ", ".join(f'"{e["subject"]}"' for e in emails)

    prompt = f"""Sen bir kişisel asistansın. Aşağıdaki {len(emails)} emaili analiz et ve podcast formatında, sıcak ve doğal Türkçe ile özetle.

Bugünün tarihi: {today}

Talimatlar:
- İlk cümle olarak şu emailleri özetleyeceğini söyle, isimlerini bire bire sırala: {subjects}
- Sonra her emaili 2-4 cümleyle özetle: kimden, ne hakkında, önemli bir aksiyon var mı?
- Varsa acil / yanıt bekleyen emailler için özellikle belirt
- Kısa sıcak bir kapanışla bitir
- SADECE konuşma dili kullan, başlık/madde/sembol KULLANMA

===== SEÇİLEN EMAİLLER =====
{email_text}
============================"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text, email_text


def summarize_podcasts(episodes):
    client = _claude()

    lines = []
    for i, ep in enumerate(episodes, 1):
        lines.append(f"--- Bölüm {i} ---")
        lines.append(f"Podcast: {ep['show_name']}")
        lines.append(f"Bölüm adı: {ep['title']}")
        lines.append(f"Süre: {ep['duration_min']} dakika")
        lines.append(f"Tarih: {ep['release_date']}")
        if ep.get("description"):
            lines.append(f"Açıklama:\n{ep['description']}")
        lines.append("")
    content_text = "\n".join(lines)

    titles = ", ".join(f'"{ep["title"]}" ({ep["show_name"]})' for ep in episodes)

    prompt = f"""Sen bir podcast özet asistanısın. Seçilen {len(episodes)} podcast bölümünü analiz et ve sanki bir arkadaşın sana anlatıyor gibi, doğal ve samimi Türkçe ile özetle.

İlk cümle olarak hangi bölümleri özetleyeceğini söyle, isimlerini sırala: {titles}

Her bölüm için:
- Bölüm ne hakkında? (1 sıcak cümle)
- En kritik 2-3 konu veya insight nedir? (somut, spesifik ol — "genel şeyler konuşuldu" değil)
- Bu bölümü atlamak olur mu, kaçırılmamalı mı? Neden?

Sonunda en acil dinlenmesi gereken bölümü önermeni istiyorum.

SADECE konuşma dili. Başlık, madde numarası, tire, sembol KULLANMA. Akıcı paragraflar yaz.

===== SEÇİLEN BÖLÜMLER =====
{content_text}
==========================="""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text, content_text


def answer_question(question, context_content, context_type, chat_history):
    client = _claude()
    label = "emailler" if context_type == "emails" else "podcast bölümleri"

    messages = [
        {
            "role": "user",
            "content": (
                f"Aşağıdaki {label} hakkında sorulara kısa, net Türkçe cevaplar ver. "
                f"İçerikte yoksa dürüstçe söyle.\n\nİÇERİK:\n{context_content[:8000]}"
            ),
        },
        {"role": "assistant", "content": "Anladım, sorularını bekliyorum."},
    ]

    for h in chat_history[-8:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=messages,
    )
    return msg.content[0].text


def send_to_telegram(audio_filename, caption="🎙️ Asistan Özeti"):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID eksik.")
    path = AUDIO_DIR / audio_filename
    with open(path, "rb") as f:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendAudio",
            data={"chat_id": chat_id, "caption": caption, "title": "Asistan"},
            files={"audio": ("ozet.mp3", f, "audio/mpeg")},
            timeout=60,
        )
    if not r.ok:
        raise RuntimeError(r.text)


def text_to_speech(text, filename=None):
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    if not filename:
        filename = f"tts_{int(time.time())}.mp3"
    path = AUDIO_DIR / filename
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text,
        speed=1.0,
    )
    response.stream_to_file(str(path))
    return filename


# ── Podcast Transkript (Groq Whisper) ─────────────────────────────────────────

def _find_podcast_rss(show_name: str) -> str | None:
    """iTunes Search API ile podcast RSS feed URL'ini bul."""
    try:
        r = requests.get(
            "https://itunes.apple.com/search",
            params={"term": show_name, "media": "podcast", "limit": 5},
            timeout=10,
        )
        results = r.json().get("results", [])
        if results:
            return results[0].get("feedUrl")
    except Exception:
        pass
    return None


def _find_episode_audio_url(rss_url: str, episode_title: str) -> str | None:
    """RSS feed'inden episode başlığıyla eşleşen MP3 URL'ini bul."""
    if not feedparser:
        return None
    try:
        feed = feedparser.parse(rss_url)
        title_lower = episode_title.lower()
        for entry in feed.entries:
            if title_lower in entry.get("title", "").lower():
                for link in entry.get("enclosures", []):
                    if "audio" in link.get("type", "") or link.get("href", "").endswith(".mp3"):
                        return link["href"]
                # Bazı feed'lerde link direkt
                if hasattr(entry, "link") and entry.link.endswith(".mp3"):
                    return entry.link
    except Exception:
        pass
    return None


def transcribe_podcast(show_name: str, episode_title: str, audio_url: str | None = None) -> str:
    """
    Groq Whisper ile podcast episode transkriptini çıkar.
    audio_url verilmezse RSS üzerinden bulunmaya çalışılır.
    """
    if _Groq is None:
        raise RuntimeError("groq paketi yüklü değil: pip install groq")

    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY eksik")

    # Ses URL'ini bul
    if not audio_url:
        rss_url = _find_podcast_rss(show_name)
        if not rss_url:
            raise RuntimeError(f"'{show_name}' için RSS feed bulunamadı")
        audio_url = _find_episode_audio_url(rss_url, episode_title)
        if not audio_url:
            raise RuntimeError(f"'{episode_title}' için ses dosyası bulunamadı")

    # Sesi indir (max 25 MB — Groq limiti)
    r = requests.get(audio_url, stream=True, timeout=30)
    r.raise_for_status()
    MAX_BYTES = 24 * 1024 * 1024  # 24 MB
    audio_bytes = b""
    for chunk in r.iter_content(chunk_size=1024 * 1024):
        audio_bytes += chunk
        if len(audio_bytes) >= MAX_BYTES:
            break

    # Groq Whisper'a gönder
    client = _Groq(api_key=groq_key)
    fname = episode_title[:40].replace(" ", "_") + ".mp3"
    result = client.audio.transcriptions.create(
        file=(fname, io.BytesIO(audio_bytes), "audio/mpeg"),
        model="whisper-large-v3",
        language="tr",
        response_format="text",
    )
    return result if isinstance(result, str) else result.text
