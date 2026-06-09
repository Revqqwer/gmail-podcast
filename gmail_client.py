import os
import base64
import re
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
MAX_BODY_CHARS = 2000


def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        # Force re-auth if scopes changed
        if creds and creds.scopes and not all(s in creds.scopes for s in SCOPES):
            creds = None
            os.remove(TOKEN_FILE)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError("credentials.json bulunamadı. KURULUM.md'yi okuyun.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def send_email(to, subject, body):
    service = authenticate()
    msg = MIMEText(body, "plain", "utf-8")
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def trash_email(email_id):
    service = authenticate()
    service.users().messages().trash(userId="me", id=email_id).execute()


def decode_body(payload):
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    break
            elif "parts" in part:
                body = decode_body(part)
                if body:
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


def fetch_emails(max_results=30):
    service = authenticate()
    results = service.users().messages().list(
        userId="me", maxResults=max_results, labelIds=["INBOX"]
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for msg in messages:
        msg_data = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg_data["payload"]["headers"]}
        body = decode_body(msg_data["payload"])

        emails.append({
            "id": msg["id"],
            "from": headers.get("From", "Bilinmiyor"),
            "subject": headers.get("Subject", "(Konu yok)"),
            "date": headers.get("Date", ""),
            "body": body[:MAX_BODY_CHARS],
            "snippet": msg_data.get("snippet", ""),
        })

    return emails
