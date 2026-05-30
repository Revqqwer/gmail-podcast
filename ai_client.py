import os
import time
import datetime
import anthropic
import openai
import requests
from pathlib import Path

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
