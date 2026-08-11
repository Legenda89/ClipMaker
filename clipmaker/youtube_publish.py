"""YouTube Shorts upload via YouTube Data API v3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from clipmaker.config_store import app_data_dir, load_settings, update_settings, youtube_token_path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
HELP_URL = "https://console.cloud.google.com/apis/credentials"
API_ENABLE_URL = "https://console.cloud.google.com/apis/library/youtube.googleapis.com"
CONSENT_URL = "https://console.cloud.google.com/apis/credentials/consent"


def generated_secrets_path() -> Path:
    return app_data_dir() / "youtube_client_secrets.json"


def save_client_secrets_from_fields(client_id: str, client_secret: str) -> Path:
    """Build a Desktop OAuth client_secrets.json from Console fields."""
    client_id = client_id.strip()
    client_secret = client_secret.strip()
    if not client_id or not client_secret:
        raise ValueError("Tarvitaan sekä Client ID että Client Secret.")
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise ValueError(
            "Client ID näyttää väärältä. Sen pitäisi päättyä: .apps.googleusercontent.com"
        )

    payload = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
    }
    path = generated_secrets_path()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    update_settings(
        youtube_client_secrets=str(path),
        youtube_client_id=client_id,
        youtube_client_secret=client_secret,
    )
    return path


def _client_secrets_path() -> Path | None:
    settings = load_settings()
    raw = (settings.get("youtube_client_secrets") or "").strip()
    if raw:
        path = Path(raw)
        if path.is_file():
            return path
    # Auto-build from saved id/secret if present
    cid = (settings.get("youtube_client_id") or "").strip()
    csec = (settings.get("youtube_client_secret") or "").strip()
    if cid and csec:
        try:
            return save_client_secrets_from_fields(cid, csec)
        except ValueError:
            return None
    gen = generated_secrets_path()
    return gen if gen.is_file() else None


def is_configured() -> bool:
    return _client_secrets_path() is not None


def is_connected() -> bool:
    token = youtube_token_path()
    if not token.is_file():
        return False
    try:
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
        return bool(creds and (creds.valid or creds.refresh_token))
    except Exception:  # noqa: BLE001
        return False


def disconnect() -> None:
    token = youtube_token_path()
    if token.exists():
        token.unlink()


def missing_config_message() -> str:
    return (
        "YouTubea ei ole vielä asetettu.\n\n"
        "TEE NÄIN (Google Cloud):\n"
        "1) Avaa: APIs & Services → Library → ota käyttöön YouTube Data API v3\n"
        "2) OAuth consent screen → External → täytä App name → Save\n"
        "   → Test users → lisää oma Gmail\n"
        "3) Credentials → + Create credentials → OAuth client ID\n"
        "4) Application type: Desktop app → Create\n"
        "5) Kopioi Client ID ja Client secret ClipMakeriin\n"
        "   TAI paina Download JSON ja valitse tiedosto Selaa…\n\n"
        "JSON-lataus: Credentials-listassa klikkaa asiakasta → "
        "Download JSON (nuoli alas -ikoni)."
    )


def connect() -> str:
    """Run OAuth browser flow and save token."""
    secrets = _client_secrets_path()
    if secrets is None:
        raise RuntimeError(missing_config_message())
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    creds = flow.run_local_server(
        port=0,
        prompt="consent",
        open_browser=True,
        success_message="ClipMaker: YouTube yhdistetty. Voit sulkea tämän välilehden.",
    )
    youtube_token_path().write_text(creds.to_json(), encoding="utf-8")
    return "YouTube yhdistetty. Voit nyt julkaista Shortseja."


def _credentials() -> Credentials:
    token = youtube_token_path()
    if not token.is_file():
        raise RuntimeError("YouTube ei ole yhdistetty. Paina ensin 'Yhdistä YouTube'.")
    creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds.valid:
        if creds.refresh_token:
            creds.refresh(Request())
            token.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError("YouTube-istunto vanhentui. Yhdistä uudelleen.")
    return creds


def upload_short(
    video_path: str,
    *,
    title: str,
    description: str = "",
    privacy_status: str = "public",
    on_progress: Callable[[float], None] | None = None,
) -> dict:
    """Upload vertical short. Include #Shorts in title/description for Shorts shelf."""
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"Videota ei löydy: {video_path}")

    title = (title or path.stem).strip()[:100]
    if "#shorts" not in title.lower() and "#shorts" not in description.lower():
        title = f"{title} #Shorts".strip()[:100]
    if "#Shorts" not in description and "#shorts" not in description.lower():
        description = (description + "\n\n#Shorts").strip()

    youtube = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and on_progress:
            on_progress(min(0.99, float(status.progress())))
    if on_progress:
        on_progress(1.0)

    video_id = response.get("id", "")
    return {
        "id": video_id,
        "url": f"https://youtu.be/{video_id}" if video_id else "",
        "raw": response,
    }
