"""TikTok upload via Content Posting API (Desktop Login Kit + PKCE)."""

from __future__ import annotations

import hashlib
import json
import secrets
import string
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable

import requests

from clipmaker.config_store import app_data_dir, load_settings, tiktok_token_path, update_settings

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INBOX_INIT = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
DIRECT_INIT = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

DEFAULT_SCOPES = "user.info.basic,video.upload"
DIRECT_SCOPES = "user.info.basic,video.upload,video.publish"
DEFAULT_REDIRECT = "http://127.0.0.1:8765/callback"


def _pkce_pair() -> tuple[str, str]:
    """TikTok Desktop PKCE: challenge = HEX(SHA256(verifier)), not base64url."""
    alphabet = string.ascii_letters + string.digits + "-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    challenge = hashlib.sha256(verifier.encode("utf-8")).hexdigest()
    return verifier, challenge


def _creds() -> tuple[str, str, str]:
    s = load_settings()
    key = (s.get("tiktok_client_key") or "").strip()
    secret = (s.get("tiktok_client_secret") or "").strip()
    redirect = (s.get("tiktok_redirect_uri") or DEFAULT_REDIRECT).strip()
    return key, secret, redirect


def is_configured() -> bool:
    key, secret, _ = _creds()
    return bool(key and secret)


def is_connected() -> bool:
    path = tiktok_token_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("access_token") or data.get("refresh_token"))
    except (OSError, json.JSONDecodeError):
        return False


def disconnect() -> None:
    path = tiktok_token_path()
    if path.exists():
        path.unlink()
    _clear_pending()


def setup_help() -> str:
    return (
        "TikTok Desktop -asetus:\n\n"
        "1) https://developers.tiktok.com/apps  ->  oma app\n"
        "2) Lisaa tuote: Login Kit (Desktop) + Content Posting API\n"
        "3) Login Kit -> Redirect URI (TARKALLEEN):\n"
        f"   {DEFAULT_REDIRECT}\n"
        "4) Scopes: user.info.basic, video.upload\n"
        "5) Kopioi Client Key + Client Secret ClipMakeriin -> Tallenna\n"
        "6) Paina Yhdista TikTok -> kirjaudu selaimessa\n"
        "7) Jos callback ei toimi: kopioi osoitepalkin URL ja\n"
        "   paina 'Liita callback-URL'\n"
    )


def _pending_path() -> Path:
    return app_data_dir() / "tiktok_oauth_pending.json"


def _save_pending(data: dict) -> None:
    _pending_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_pending() -> dict | None:
    path = _pending_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _clear_pending() -> None:
    path = _pending_path()
    if path.exists():
        path.unlink()


def _save_token(payload: dict) -> None:
    existing: dict = {}
    path = tiktok_token_path()
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    existing.update(payload)
    existing["saved_at"] = time.time()
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _exchange_token(**form: str) -> dict:
    key, secret, _ = _creds()
    data = {
        "client_key": key,
        "client_secret": secret,
        **form,
    }
    resp = requests.post(
        TOKEN_URL,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
        },
        timeout=60,
    )
    payload = resp.json() if resp.content else {}
    if resp.status_code >= 400 or (isinstance(payload.get("error"), str) and payload.get("error")):
        msg = payload.get("error_description") or payload.get("error") or resp.text
        raise RuntimeError(f"TikTok token-virhe: {msg}")
    if "access_token" not in payload and isinstance(payload.get("data"), dict):
        payload = payload["data"]
    if not payload.get("access_token"):
        raise RuntimeError(f"TikTok ei palauttanut access_tokenia: {payload}")
    _save_token(payload)
    return payload


def finish_from_redirect_url(url: str) -> str:
    """Complete OAuth by pasting the browser callback URL."""
    url = (url or "").strip().strip('"').strip("'")
    if not url:
        raise RuntimeError(
            "Liita ensin callback-URL (alkaa http://127.0.0.1:8765/callback?code=...)"
        )

    pending = _load_pending()
    if not pending:
        raise RuntimeError(
            "Ei kaynnissa olevaa TikTok-kirjautumista.\n"
            "Paina ensin Yhdista TikTok, kirjaudu, sitten liita callback-URL."
        )

    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    if "error" in qs:
        raise RuntimeError(qs.get("error_description", qs.get("error", ["error"]))[0])

    code = qs.get("code", [None])[0]
    state = qs.get("state", [None])[0]
    if not code:
        raise RuntimeError(
            "URL:ssa ei ole code-parametria.\n"
            "Kopioi koko osoite selaimesta kirjautumisen jalkeen."
        )
    if state != pending.get("state"):
        raise RuntimeError(
            "State ei tasmaa. Aloita Yhdista TikTok uudelleen ja kayta saman istunnon URL."
        )

    _exchange_token(
        grant_type="authorization_code",
        code=code,
        redirect_uri=pending.get("redirect_uri") or DEFAULT_REDIRECT,
        code_verifier=pending["code_verifier"],
    )
    _clear_pending()
    update_settings(tiktok_redirect_uri=pending.get("redirect_uri") or DEFAULT_REDIRECT)
    return "TikTok yhdistetty (callback-URL). Voit julkaista inbox-luonnoksia."


def connect(timeout_sec: int = 180, *, request_publish_scope: bool = False) -> str:
    """
    OAuth via local callback + Desktop PKCE.
    On timeout, pending PKCE state is kept so finish_from_redirect_url() still works.
    """
    key, secret, redirect = _creds()
    if not key or not secret:
        raise RuntimeError(setup_help())

    redirect = redirect or DEFAULT_REDIRECT
    update_settings(tiktok_redirect_uri=redirect)

    parsed = urllib.parse.urlparse(redirect)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765
    callback_path = parsed.path or "/callback"

    state = secrets.token_urlsafe(24)
    code_verifier, code_challenge = _pkce_pair()
    result: dict = {"code": None, "error": None, "done": False}

    _save_pending(
        {
            "state": state,
            "code_verifier": code_verifier,
            "redirect_uri": redirect,
            "started_at": time.time(),
        }
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.urlparse(self.path)
            if q.path.rstrip("/") != callback_path.rstrip("/"):
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(q.query)
            if qs.get("state", [None])[0] != state:
                result["error"] = "Virheellinen state (CSRF)."
            elif "error" in qs:
                result["error"] = qs.get("error_description", qs.get("error", ["error"]))[0]
            else:
                result["code"] = qs.get("code", [None])[0]
            result["done"] = True
            body = (
                b"<html><body style='font-family:sans-serif;padding:40px'>"
                b"<h2>ClipMaker</h2>"
                b"<p>TikTok-kirjautuminen valmis. Voit sulkea taman ikkunan "
                b"ja palata ClipMakeriin.</p>"
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A003
            return

    try:
        HTTPServer.allow_reuse_address = True
        server = HTTPServer((host, port), Handler)
    except OSError as exc:
        raise RuntimeError(
            f"Portti {port} on varattu ({exc}).\n"
            "Sulje vanha ClipMaker/python ja yrita uudelleen.\n"
            "Tai kirjaudu selaimessa, kopioi callback-URL ja kayta "
            "'Liita callback-URL'."
        ) from exc

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    scopes = DIRECT_SCOPES if request_publish_scope else DEFAULT_SCOPES
    params = {
        "client_key": key,
        "scope": scopes,
        "response_type": "code",
        "redirect_uri": redirect,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_link = AUTH_URL + "?" + urllib.parse.urlencode(params)
    webbrowser.open(auth_link)

    deadline = time.time() + timeout_sec
    try:
        while time.time() < deadline and not result["done"]:
            time.sleep(0.2)
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass

    if result["error"]:
        raise RuntimeError(
            f"TikTok-kirjautuminen epaonnistui: {result['error']}\n\n"
            f"Tarkista Redirect URI appissa:\n{redirect}"
        )
    if not result["code"]:
        # Keep pending state for manual paste
        raise RuntimeError(
            "Automaattinen callback ei tullut perille.\n\n"
            "TEE NAIN NYT:\n"
            "1) Kirjaudu TikTokiin selaimessa (jos et viela)\n"
            "2) Kopioi KOKO osoitepalkin URL\n"
            "   (http://127.0.0.1:8765/callback?code=...)\n"
            "3) ClipMaker: Liita callback-URL  TAI  aja:\n"
            "   python run.py connect-tiktok --callback \"URL\"\n\n"
            f"Redirect URI appissa pitaa olla:\n{redirect}"
        )

    _exchange_token(
        grant_type="authorization_code",
        code=result["code"],
        redirect_uri=redirect,
        code_verifier=code_verifier,
    )
    _clear_pending()
    update_settings(tiktok_redirect_uri=redirect)
    return "TikTok yhdistetty. Voit julkaista inbox-luonnoksia."


def _access_token() -> str:
    path = tiktok_token_path()
    if not path.is_file():
        raise RuntimeError("TikTok ei ole yhdistetty. Paina ensin 'Yhdista TikTok'.")
    data = json.loads(path.read_text(encoding="utf-8"))
    token = data.get("access_token")
    refresh = data.get("refresh_token")
    expires_in = float(data.get("expires_in") or 0)
    saved_at = float(data.get("saved_at") or 0)
    if refresh and saved_at and expires_in and time.time() > saved_at + expires_in - 3600:
        data = _exchange_token(grant_type="refresh_token", refresh_token=refresh)
        token = data.get("access_token")
    if not token:
        raise RuntimeError("TikTok-token puuttuu. Yhdista uudelleen.")
    return str(token)


def upload_video(
    video_path: str,
    *,
    title: str = "",
    direct_post: bool = False,
    privacy_level: str = "SELF_ONLY",
    on_progress: Callable[[float], None] | None = None,
) -> dict:
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"Videota ei loydy: {video_path}")

    size = path.stat().st_size
    chunk_size = size if size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
    total_chunks = max(1, (size + chunk_size - 1) // chunk_size)

    headers = {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    if direct_post:
        body = {
            "post_info": {
                "title": (title or path.stem)[:150],
                "privacy_level": privacy_level,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        }
        init_url = DIRECT_INIT
    else:
        body = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        }
        init_url = INBOX_INIT

    init = requests.post(init_url, headers=headers, json=body, timeout=60)
    init_json = init.json() if init.content else {}
    err_obj = init_json.get("error")
    err_code = err_obj.get("code") if isinstance(err_obj, dict) else None
    if init.status_code >= 400 or (err_code not in (None, "ok", "OK", 0)):
        raise RuntimeError(f"TikTok upload init epaonnistui: {err_obj or init_json}")

    data = init_json.get("data") or {}
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id")
    if not upload_url:
        raise RuntimeError(f"TikTok ei palauttanut upload_url: {init_json}")

    if on_progress:
        on_progress(0.05)

    with path.open("rb") as fh:
        for i in range(total_chunks):
            start = i * chunk_size
            end = min(size, start + chunk_size) - 1
            chunk = fh.read(end - start + 1)
            put_headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            }
            put = requests.put(upload_url, headers=put_headers, data=chunk, timeout=300)
            if put.status_code not in (200, 201, 206):
                raise RuntimeError(
                    f"TikTok chunk-upload epaonnistui ({put.status_code}): {put.text[:500]}"
                )
            if on_progress:
                on_progress(0.05 + 0.9 * ((i + 1) / total_chunks))

    status_text = "uploaded"
    if publish_id:
        for _ in range(20):
            st = requests.post(
                STATUS_URL,
                headers=headers,
                json={"publish_id": publish_id},
                timeout=30,
            )
            st_json = st.json() if st.content else {}
            status_text = (st_json.get("data") or {}).get("status") or status_text
            if str(status_text).upper() in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "FAILED"):
                break
            time.sleep(1.5)

    if on_progress:
        on_progress(1.0)

    return {
        "publish_id": publish_id,
        "status": status_text,
        "mode": "direct" if direct_post else "inbox",
        "message": (
            "Video julkaistu TikTokiin."
            if direct_post
            else "Video lahetetty TikTok-inboxiin — avaa TikTok ja julkaise luonnos."
        ),
    }
