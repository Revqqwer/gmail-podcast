"""
Gmail Podcast - Emaillerinizi sesli olarak özetler.
Kullanım: python gmail_podcast.py
"""

import os
import json
import base64
import datetime
import re
import anthropic
import openai
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"
OUTPUT_AUDIO = "email_ozet.mp3"

MAX_EMAILS = 20        # Kaç email özetlensin
MAX_BODY_CHARS = 1000  # Her emailden max kaç karakter alınsın


def gmail_authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print("HATA: credentials.json bulunamadı.")
                print("Lütfen KURULUM.md dosyasını okuyun.")
                raise SystemExit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def decode_body(payload):
    """Email body'sini çözer."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    break
            elif part["mimeType"] == "text/html" and not body:
                data = part["body"].get("data", "")
                if data:
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    body = re.sub(r"<[^>]+>", " ", html)
                    body = re.sub(r"\s+", " ", body).strip()
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body.strip()


def fetch_emails(service, max_results=MAX_EMAILS):
    """Son emailları Gmail'den çeker."""
    print(f"📬 Son {max_results} email alınıyor...")
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        labelIds=["INBOX"]
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for msg in messages:
        msg_data = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg_data["payload"]["headers"]}
        subject = headers.get("Subject", "(Konu yok)")
        sender = headers.get("From", "(Gönderen bilinmiyor)")
        date = headers.get("Date", "")
        body = decode_body(msg_data["payload"])
        body_short = body[:MAX_BODY_CHARS] + ("..." if len(body) > MAX_BODY_CHARS else "")

        emails.append({
            "from": sender,
            "subject": subject,
            "date": date,
            "body": body_short,
        })

    print(f"✅ {len(emails)} email alındı.")
    return emails


def build_email_text(emails):
    lines = []
    for i, e in enumerate(emails, 1):
        lines.append(f"--- Email {i} ---")
        lines.append(f"Gönderen: {e['from']}")
        lines.append(f"Konu: {e['subject']}")
        lines.append(f"Tarih: {e['date']}")
        if e["body"]:
            lines.append(f"İçerik: {e['body']}")
        lines.append("")
    return "\n".join(lines)


def summarize_with_claude(email_text):
    """Claude API ile Türkçe özet oluşturur."""
    print("🤖 Claude emaillerinizi özetliyor...")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    today = datetime.date.today().strftime("%d %B %Y")

    prompt = f"""Sen bir kişisel asistansın. Aşağıdaki email listesini analiz et ve kullanıcıya sesli podcast formatında, sıcak ve doğal bir Türkçe ile özetle.

Bugünün tarihi: {today}

Yapman gerekenler:
1. Kaç email var, genel atmosfer nedir kısaca belirt
2. Her önemli emaili 1-3 cümleyle özetle (kim göndermiş, ne istiyor/söylüyor)
3. Varsa acil/önemli emailler için uyar
4. Sona kısa bir kapanış ekle

Dikkat: Bu bir podcast metni. "Merhaba, bugün gelen emaillerinize bakıyorum..." gibi doğal bir giriş yap. Madde numaraları yerine akıcı cümleler kullan.

===== EMAİLLER =====
{email_text}
===================="""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    summary = message.content[0].text
    print("✅ Özet hazır.")
    return summary


def text_to_speech(text, output_path=OUTPUT_AUDIO):
    """OpenAI TTS ile sesi üretir."""
    print("🎙️ Ses oluşturuluyor...")
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text,
        speed=1.0,
    )
    response.stream_to_file(output_path)
    print(f"✅ Ses dosyası kaydedildi: {output_path}")
    return output_path


def play_audio(path):
    """Ses dosyasını oynatır."""
    print("▶️  Ses oynatılıyor...")
    abs_path = str(Path(path).resolve())
    os.startfile(abs_path)


def main():
    print("=" * 50)
    print("  📧 Gmail Podcast Asistanı")
    print("=" * 50)

    # Gerekli env değişkenleri kontrolü
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        if not os.environ.get(key):
            print(f"HATA: {key} ortam değişkeni eksik.")
            print("Lütfen .env dosyasına ekleyin.")
            raise SystemExit(1)

    service = gmail_authenticate()
    emails = fetch_emails(service)

    if not emails:
        print("Gelen kutunuzda email bulunamadı.")
        return

    email_text = build_email_text(emails)
    summary = summarize_with_claude(email_text)

    print("\n" + "=" * 50)
    print("ÖZET:")
    print("=" * 50)
    print(summary)
    print("=" * 50 + "\n")

    audio_path = text_to_speech(summary)
    play_audio(audio_path)

    print("\n✅ Tamamlandı!")


if __name__ == "__main__":
    main()
