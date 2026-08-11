"""ClipMaker CLI — agent-friendly one-shot clip + publish."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from clipmaker import tiktok_publish, youtube_publish
from clipmaker.audio_analyze import find_best_clip_start
from clipmaker.ffmpeg_worker import PRESETS, default_output_name, export_clip, probe_duration


def _progress(label: str):
    def cb(p: float) -> None:
        pct = int(p * 100)
        print(f"\r{label}: {pct}%", end="", flush=True)
        if p >= 1.0:
            print()

    return cb


def cmd_make(args: argparse.Namespace) -> int:
    audio = Path(args.audio)
    visual = Path(args.image or args.visual or "")
    if not audio.is_file():
        print(f"Virhe: musiikkia ei löydy: {audio}", file=sys.stderr)
        return 1
    if not visual.is_file():
        print(f"Virhe: kansikuvaa/videota ei löydy: {visual}", file=sys.stderr)
        return 1

    duration = float(args.duration)
    preset_key = args.preset
    if preset_key not in PRESETS:
        print(f"Virhe: tuntematon preset '{preset_key}'", file=sys.stderr)
        return 1
    preset = PRESETS[preset_key]

    if args.output:
        out = Path(args.output)
    else:
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            desktop = Path.home() / "Työpöytä"
        if not desktop.exists():
            desktop = Path.home()
        out = desktop / default_output_name(str(audio), preset_key)

    total = probe_duration(str(audio))
    if args.start is not None:
        start = float(args.start)
        print(f"Aloitus (käsin): {start:.2f}s")
    else:
        print("Etsitaan parasta kohtaa...")
        suggestion = find_best_clip_start(str(audio), duration, total_duration=total or None)
        start = suggestion.start_sec
        print(f"Paras kohta: {start:.2f}s ({duration:.0f}s clip)")

    title = args.title or audio.stem
    print(f"Renderoidaan -> {out}")
    export_clip(
        audio_path=str(audio),
        visual_path=str(visual),
        output_path=str(out),
        start_sec=start,
        duration_sec=duration,
        preset=preset,
        fade_sec=0.5 if not args.no_fade else 0.0,
        on_progress=_progress("Render"),
    )
    print(f"Video valmis: {out}")

    result: dict = {
        "video": str(out),
        "start_sec": start,
        "duration_sec": duration,
        "title": title,
        "youtube": None,
        "tiktok": None,
    }

    platforms = {p.strip().lower() for p in (args.publish or "").split(",") if p.strip()}
    # aliases
    if "shorts" in platforms:
        platforms.add("youtube")
    if "reels" in platforms or "tt" in platforms:
        platforms.add("tiktok")

    if "youtube" in platforms:
        if not youtube_publish.is_connected():
            print("Virhe: YouTube ei ole yhdistetty. Avaa ClipMaker GUI → Yhdistä YouTube.", file=sys.stderr)
            return 2
        print("Julkaistaan YouTube Shorts…")
        yt = youtube_publish.upload_short(
            str(out),
            title=title,
            description=args.description or "",
            privacy_status=args.privacy,
            on_progress=_progress("YouTube"),
        )
        result["youtube"] = {"id": yt.get("id"), "url": yt.get("url")}
        print(f"YouTube: {yt.get('url')}")

    if "tiktok" in platforms:
        if not tiktok_publish.is_connected():
            print("Virhe: TikTok ei ole yhdistetty. Avaa ClipMaker GUI → Yhdistä TikTok.", file=sys.stderr)
            return 2
        direct = args.tiktok_mode == "direct"
        print(f"Julkaistaan TikTok ({'suora' if direct else 'inbox'})…")
        tt = tiktok_publish.upload_video(
            str(out),
            title=title,
            direct_post=direct,
            privacy_level="SELF_ONLY",
            on_progress=_progress("TikTok"),
        )
        result["tiktok"] = {
            "publish_id": tt.get("publish_id"),
            "status": tt.get("status"),
            "mode": tt.get("mode"),
            "message": tt.get("message"),
        }
        print(tt.get("message") or "TikTok OK")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    print(
        json.dumps(
            {
                "youtube_configured": youtube_publish.is_configured(),
                "youtube_connected": youtube_publish.is_connected(),
                "tiktok_configured": tiktok_publish.is_configured(),
                "tiktok_connected": tiktok_publish.is_connected(),
            },
            indent=2,
        )
    )
    return 0


def cmd_connect_tiktok(args: argparse.Namespace) -> int:
    if getattr(args, "callback", None):
        try:
            msg = tiktok_publish.finish_from_redirect_url(args.callback)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: {exc}", flush=True)
            return 1
        print(msg, flush=True)
        print(json.dumps({"tiktok_connected": tiktok_publish.is_connected()}, indent=2), flush=True)
        return 0

    print(tiktok_publish.setup_help(), flush=True)
    if not tiktok_publish.is_configured():
        print("ERROR: Client Key/Secret puuttuu. Tallenna ne ClipMaker-GUI:ssa ensin.", flush=True)
        return 1
    print("Selain aukeaa — kirjaudu TikTokiin ja hyvaksy oikeudet...", flush=True)
    print(f"Redirect URI pitaa olla: {tiktok_publish.DEFAULT_REDIRECT}", flush=True)
    print(
        "Jos sivu ei palaa ClipMakeriin: kopioi osoitepalkin URL ja aja:\n"
        '  python run.py connect-tiktok --callback "http://127.0.0.1:8765/callback?code=..."',
        flush=True,
    )
    try:
        msg = tiktok_publish.connect(timeout_sec=120)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", flush=True)
        return 1
    print(msg, flush=True)
    print(json.dumps({"tiktok_connected": tiktok_publish.is_connected()}, indent=2), flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clipmaker",
        description="ClipMaker CLI — paras kohta + kansikuva + YouTube Shorts / TikTok",
    )
    sub = p.add_subparsers(dest="command", required=True)

    make = sub.add_parser("make", help="Luo 20–60s clip ja valinnaisesti julkaise")
    make.add_argument("--audio", "-a", required=True, help="Musiikkitiedosto")
    make.add_argument("--image", "-i", help="Kansikuva (jpg/png/…)")
    make.add_argument("--visual", "-v", help="Kuva tai video (sama kuin --image)")
    make.add_argument("--duration", "-d", type=float, default=30.0, help="Clipin kesto sekunteina (oletus 30)")
    make.add_argument("--start", type=float, default=None, help="Aloitus sekunteina (jos ei: auto-paras)")
    make.add_argument("--preset", default="tiktok", choices=list(PRESETS.keys()))
    make.add_argument("--output", "-o", help="Tulostiedosto .mp4")
    make.add_argument("--title", "-t", help="Julkaisun otsikko")
    make.add_argument("--description", help="YouTube-kuvaus")
    make.add_argument(
        "--publish",
        default="",
        help="Julkaisualustat pilkulla: youtube,tiktok (aliases: shorts, reels)",
    )
    make.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    make.add_argument(
        "--tiktok-mode",
        default="inbox",
        choices=["inbox", "direct"],
        help="inbox = luonnos TikTokissa (suositus), direct = suora julkaisu",
    )
    make.add_argument("--no-fade", action="store_true")
    make.add_argument("--json", action="store_true", help="Tulosta tulos JSON-muodossa")
    make.set_defaults(func=cmd_make)

    st = sub.add_parser("status", help="Nayta YouTube/TikTok-yhteyksien tila")
    st.set_defaults(func=cmd_status)

    ct = sub.add_parser("connect-tiktok", help="Yhdista TikTok (avaa selain + PKCE)")
    ct.add_argument(
        "--callback",
        help="Liita selainosoite callbackin jalkeen (http://127.0.0.1:8765/callback?code=...)",
    )
    ct.set_defaults(func=cmd_connect_tiktok)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
