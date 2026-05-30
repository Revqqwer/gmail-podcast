import os
import json
import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from pathlib import Path

SCOPES = "user-library-read user-read-playback-position"
REDIRECT_URI = os.environ.get("REDIRECT_BASE_URL", "http://127.0.0.1:5000") + "/callback/spotify"
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
LISTENED_FILE = BASE_DIR / "listened_episodes.json"


def get_listened_ids():
    if LISTENED_FILE.exists():
        return set(json.loads(LISTENED_FILE.read_text()))
    return set()


def mark_listened(episode_id):
    ids = get_listened_ids()
    ids.add(episode_id)
    LISTENED_FILE.write_text(json.dumps(list(ids)))


def get_auth_manager():
    return SpotifyOAuth(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        open_browser=False,
        cache_path=None,
    )


def get_spotify(token_info):
    return spotipy.Spotify(auth=token_info["access_token"])


def refresh_if_expired(token_info):
    auth = get_auth_manager()
    if auth.is_token_expired(token_info):
        return auth.refresh_access_token(token_info["refresh_token"])
    return token_info


def fetch_new_episodes(token_info, days=30):
    token_info = refresh_if_expired(token_info)
    sp = get_spotify(token_info)

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    episodes = []
    listened_ids = get_listened_ids()

    offset = 0
    while True:
        shows_result = sp.current_user_saved_shows(limit=50, offset=offset)
        items = shows_result.get("items", [])
        if not items:
            break

        for show_item in items:
            show = show_item["show"]
            try:
                eps_result = sp.show_episodes(show["id"], limit=5)
                for ep in eps_result.get("items", []):
                    if not ep:
                        continue
                    try:
                        release = datetime.datetime.strptime(
                            ep["release_date"], "%Y-%m-%d"
                        ).replace(tzinfo=datetime.timezone.utc)
                        if release < cutoff:
                            continue
                    except Exception:
                        pass

                    # Spotify'da zaten dinlendi olarak işaretlenmişse atla
                    resume = ep.get("resume_point", {})
                    if resume.get("fully_played", False):
                        continue

                    episodes.append({
                        "id": ep["id"],
                        "show_name": show["name"],
                        "show_id": show["id"],
                        "title": ep["name"],
                        "description": (ep.get("description") or ep.get("html_description") or "")[:3000],
                        "release_date": ep.get("release_date", ""),
                        "duration_ms": ep.get("duration_ms", 0),
                        "duration_min": round(ep.get("duration_ms", 0) / 60000),
                        "listened": ep["id"] in listened_ids,
                    })
            except Exception:
                continue

        if not shows_result.get("next"):
            break
        offset += 50

    episodes.sort(key=lambda x: x["release_date"], reverse=True)
    return episodes, token_info
