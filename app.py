import os
import uuid
import time
import datetime
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
import gmail_client
import spotify_client
import ai_client

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "gmail-podcast-2024-secret")
app.permanent_session_lifetime = datetime.timedelta(days=30)

# Server-side store: session_id → {emails, episodes, context}
store = {}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


def get_store():
    sid = session.setdefault("sid", str(uuid.uuid4()))
    return store.setdefault(sid, {})


@app.context_processor
def inject_url_prefix():
    return {"url_prefix": os.environ.get("URL_PREFIX", "")}


# ──────────────────────────────────────────────────────────────────────────────
# Pages
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("index"))
    error = False
    if request.method == "POST":
        pwd = os.environ.get("APP_PASSWORD", "")
        if request.form.get("password") == pwd and pwd:
            session.permanent = True
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = True
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template(
        "index.html",
        spotify_connected="spotify_token" in session,
        gmail_ready=os.path.exists("token.json"),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Gmail
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/emails/fetch")
def api_emails_fetch():
    try:
        emails = gmail_client.fetch_emails(max_results=30)
        get_store()["emails"] = emails
        return jsonify({"ok": True, "emails": emails})
    except FileNotFoundError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/emails/summarize", methods=["POST"])
def api_emails_summarize():
    try:
        ids = request.json.get("ids", [])
        all_emails = get_store().get("emails", [])
        selected = [e for e in all_emails if e["id"] in ids]
        if not selected:
            return jsonify({"ok": False, "error": "Hiç email seçmediniz."}), 400

        summary, content = ai_client.summarize_emails(selected)
        audio = ai_client.text_to_speech(summary, f"email_{int(time.time())}.mp3")
        get_store()["context"] = {
            "type": "emails",
            "content": content,
            "summary": summary,
            "history": [],
        }
        try:
            ai_client.send_to_telegram(audio, "📧 Email Özeti")
        except Exception:
            pass
        return jsonify({"ok": True, "summary": summary, "audio": f"/static/audio/{audio}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Spotify
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/spotify/auth")
def api_spotify_auth():
    auth = spotify_client.get_auth_manager()
    return redirect(auth.get_authorize_url())


SPOTIFY_TOKEN_FILE = Path(__file__).parent / "spotify_token.json"

def _save_spotify_token(token_info):
    SPOTIFY_TOKEN_FILE.write_text(__import__("json").dumps(token_info))

@app.route("/callback/spotify")
def spotify_callback():
    auth = spotify_client.get_auth_manager()
    code = request.args.get("code")
    token_info = auth.get_access_token(code, as_dict=True)
    session["spotify_token"] = token_info
    _save_spotify_token(token_info)
    return redirect(url_for("index"))


@app.route("/api/spotify/disconnect")
def api_spotify_disconnect():
    session.pop("spotify_token", None)
    return redirect(url_for("index"))


@app.route("/api/podcasts/fetch")
def api_podcasts_fetch():
    # Önce session'dan, yoksa dosyadan oku
    token_info = session.get("spotify_token")
    if not token_info and SPOTIFY_TOKEN_FILE.exists():
        import json as _json
        token_info = _json.loads(SPOTIFY_TOKEN_FILE.read_text())
        session["spotify_token"] = token_info
    if not token_info:
        return jsonify({"ok": False, "error": "Spotify bağlı değil."}), 401
    try:
        episodes, token_info = spotify_client.fetch_new_episodes(token_info, days=14)
        session["spotify_token"] = token_info
        _save_spotify_token(token_info)
        get_store()["episodes"] = episodes
        return jsonify({"ok": True, "episodes": episodes})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/podcasts/summarize", methods=["POST"])
def api_podcasts_summarize():
    try:
        ids = request.json.get("ids", [])
        all_eps = get_store().get("episodes", [])
        selected = [e for e in all_eps if e["id"] in ids]
        if not selected:
            return jsonify({"ok": False, "error": "Hiç bölüm seçmediniz."}), 400

        summary, content = ai_client.summarize_podcasts(selected)
        audio = ai_client.text_to_speech(summary, f"podcast_{int(time.time())}.mp3")
        get_store()["context"] = {
            "type": "podcasts",
            "content": content,
            "summary": summary,
            "history": [],
        }
        try:
            ai_client.send_to_telegram(audio, "🎵 Podcast Özeti")
        except Exception:
            pass
        return jsonify({"ok": True, "summary": summary, "audio": f"/static/audio/{audio}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/emails/<email_id>/trash", methods=["POST"])
def api_email_trash(email_id):
    try:
        gmail_client.trash_email(email_id)
        s = get_store()
        s["emails"] = [e for e in s.get("emails", []) if e["id"] != email_id]
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/podcasts/transcript", methods=["POST"])
def api_podcast_transcript():
    try:
        body = request.json or {}
        episode_id = body.get("id")
        audio_url  = body.get("audio_url") or None   # opsiyonel override
        show_name    = body.get("show_name")
        episode_title = body.get("title")

        # JS'den gelmiyorsa store'a bak (fallback)
        if not show_name or not episode_title:
            all_eps = get_store().get("episodes", [])
            ep = next((e for e in all_eps if e["id"] == episode_id), None)
            if not ep:
                return jsonify({"ok": False, "error": "Episode bulunamadı, önce listeyi yükleyin."}), 400
            show_name = ep["show_name"]
            episode_title = ep["title"]

        transcript = ai_client.transcribe_podcast(
            show_name=show_name,
            episode_title=episode_title,
            audio_url=audio_url,
        )
        email_error = None
        try:
            gmail_client.send_email(
                to="hakandeveli24@gmail.com",
                subject=f"📝 Transkript: {episode_title}",
                body=transcript,
            )
        except Exception as mail_err:
            email_error = str(mail_err)
        return jsonify({"ok": True, "transcript": transcript, "title": episode_title, "email_error": email_error})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/podcasts/<episode_id>/listened", methods=["POST"])
def api_podcast_listened(episode_id):
    try:
        spotify_client.mark_listened(episode_id)
        for ep in get_store().get("episodes", []):
            if ep["id"] == episode_id:
                ep["listened"] = True
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/send-telegram", methods=["POST"])
def api_send_telegram():
    try:
        filename = request.json.get("filename", "").strip()
        caption = request.json.get("caption", "🎙️ Asistan Özeti")
        if not filename:
            return jsonify({"ok": False, "error": "Dosya adı eksik."}), 400
        ai_client.send_to_telegram(filename, caption)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/chat/context", methods=["POST"])
def api_chat_set_context():
    try:
        body = request.json
        type_ = body.get("type")
        ids = body.get("ids", [])

        if type_ == "emails":
            items = [e for e in get_store().get("emails", []) if e["id"] in ids]
            lines = []
            for i, e in enumerate(items, 1):
                lines += [f"--- Email {i} ---", f"Gönderen: {e['from']}",
                          f"Konu: {e['subject']}", f"Tarih: {e['date']}",
                          e.get("body", ""), ""]
            content = "\n".join(lines)
        else:
            items = [e for e in get_store().get("episodes", []) if e["id"] in ids]
            lines = []
            for i, ep in enumerate(items, 1):
                lines += [f"--- Bolum {i} ---", f"Podcast: {ep['show_name']}",
                          f"Bolum: {ep['title']}", f"Sure: {ep['duration_min']} dk",
                          ep.get("description", ""), ""]
            content = "\n".join(lines)

        if not items:
            return jsonify({"ok": False, "error": "Hic icerik secmediniz."}), 400

        get_store()["context"] = {"type": type_, "content": content, "summary": None, "history": []}
        return jsonify({"ok": True, "count": len(items)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Chat / Q&A
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        body = request.json
        question = body.get("question", "").strip()
        want_voice = body.get("voice", False)

        ctx = get_store().get("context")
        if not ctx:
            return jsonify({"ok": False, "error": "Önce email veya podcast özetleyin."}), 400
        if not question:
            return jsonify({"ok": False, "error": "Soru boş."}), 400

        answer = ai_client.answer_question(
            question, ctx["content"], ctx["type"], ctx["history"]
        )
        ctx["history"].append({"role": "user", "content": question})
        ctx["history"].append({"role": "assistant", "content": answer})

        result = {"ok": True, "answer": answer}
        if want_voice:
            audio = ai_client.text_to_speech(answer, f"chat_{int(time.time())}.mp3")
            result["audio"] = f"/static/audio/{audio}"

        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    Path("static/audio").mkdir(parents=True, exist_ok=True)
    print("▶  http://localhost:5000  adresini tarayıcıda açın")
    app.run(debug=False, port=5000)
