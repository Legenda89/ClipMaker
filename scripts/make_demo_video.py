"""Generate ClipMaker TikTok app-review demo (16:9, end-to-end scopes)."""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"E:\Projektit\ClipMaker")
ICON = ROOT / "assets" / "clipmaker-icon-1024.png"
OUT = ROOT / "docs" / "clipmaker-tiktok-demo.mp4"
OUT2 = ROOT / "assets" / "clipmaker-tiktok-demo.mp4"
OUT3 = ROOT / "site" / "clipmaker-tiktok-demo.mp4"

W, H, FPS = 1920, 1080, 30


def pick_font(bold: bool = True) -> str | None:
    cands = (
        (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\segoeui.ttf")
        if bold
        else (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf")
    )
    for p in cands:
        if Path(p).exists():
            return p
    return None


BOLD = pick_font(True)
REG = pick_font(False)


def font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    path = BOLD if bold else REG
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def bg(t: float) -> Image.Image:
    im = Image.new("RGB", (W, H), (12, 17, 24))
    d = ImageDraw.Draw(im, "RGBA")
    pulse = 0.5 + 0.5 * math.sin(t * 1.1)
    d.ellipse((-180, -120, 820, 620), fill=(46, 196, 182, int(30 + 12 * pulse)))
    d.ellipse((1100, 400, 2100, 1200), fill=(255, 122, 89, int(24 + 10 * pulse)))
    return im


def text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    s: str,
    size: int,
    fill=(232, 238, 246),
    bold: bool = True,
) -> None:
    draw.text(xy, s, font=font(size, bold), fill=fill)


def chip(draw: ImageDraw.ImageDraw, x: int, y: int, label: str) -> int:
    f = font(28, True)
    bbox = draw.textbbox((0, 0), label, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 16, 10
    draw.rounded_rectangle(
        (x, y, x + tw + pad_x * 2, y + th + pad_y * 2),
        radius=14,
        fill=(46, 196, 182, 40),
        outline=(46, 196, 182, 180),
        width=2,
    )
    draw.text((x + pad_x, y + pad_y - 2), label, font=f, fill=(126, 235, 223))
    return tw + pad_x * 2 + 12


def window_frame(im: Image.Image, title: str) -> ImageDraw.ImageDraw:
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((80, 70, W - 80, H - 70), radius=22, fill=(20, 28, 39, 235), outline=(232, 238, 246, 40), width=2)
    d.rounded_rectangle((80, 70, W - 80, 128), radius=22, fill=(15, 21, 30, 255))
    d.rectangle((80, 110, W - 80, 128), fill=(15, 21, 30, 255))
    for i, c in enumerate(((255, 95, 87), (255, 189, 46), (40, 200, 64))):
        d.ellipse((104 + i * 28, 90, 120 + i * 28, 106), fill=c)
    text(d, (200, 88), title, 26, fill=(154, 171, 191), bold=False)
    return d


def scene_website(t: float) -> Image.Image:
    im = bg(t)
    d = window_frame(im, "legenda89.github.io/ClipMaker/")
    text(d, (140, 170), "ClipMaker", 64)
    text(d, (140, 250), "Windows desktop app for music clips → Shorts & TikTok", 32, bold=False, fill=(154, 171, 191))
    text(d, (140, 330), "Website URL (fully developed product site)", 28, fill=(46, 196, 182))
    y = 400
    for label in ("How it works", "TikTok integration", "Privacy Policy", "Terms of Service"):
        d.rounded_rectangle((140, y, 520, y + 54), radius=12, fill=(46, 196, 182, 28), outline=(46, 196, 182, 120))
        text(d, (160, y + 12), label, 26, bold=False)
        y += 70
    text(d, (140, 720), "Reviewer note: Privacy Policy & Terms are linked in the top nav.", 26, bold=False, fill=(154, 171, 191))
    return im


def scene_open_app(t: float, icon: Image.Image) -> Image.Image:
    im = bg(t)
    d = window_frame(im, "ClipMaker.exe — Windows desktop")
    icon_s = icon.resize((160, 160), Image.Resampling.LANCZOS)
    im.paste(icon_s, (140, 180), icon_s)
    text(d, (330, 200), "ClipMaker", 56)
    text(d, (330, 270), "Open the desktop app (not a web login page)", 30, bold=False, fill=(154, 171, 191))
    # Fake UI panels
    d.rounded_rectangle((140, 400, 900, 900), radius=16, fill=(15, 21, 30, 255), outline=(232, 238, 246, 35))
    text(d, (170, 430), "Audio: song.wav", 28, bold=False)
    text(d, (170, 480), "Cover: artwork.png", 28, bold=False)
    text(d, (170, 530), "Duration: 30 s  ·  Preset: TikTok 9:16", 28, bold=False)
    d.rounded_rectangle((170, 600, 420, 660), radius=12, fill=(46, 196, 182, 220))
    text(d, (200, 615), "Create clip", 28, fill=(6, 34, 31))
    d.rounded_rectangle((980, 400, 1780, 900), radius=16, fill=(15, 21, 30, 255), outline=(232, 238, 246, 35))
    text(d, (1020, 430), "Accounts", 32)
    text(d, (1020, 490), "YouTube: connected", 28, bold=False, fill=(154, 171, 191))
    text(d, (1020, 540), "TikTok: not connected", 28, bold=False, fill=(255, 122, 89))
    d.rounded_rectangle((1020, 620, 1380, 680), radius=12, fill=(255, 122, 89, 220))
    text(d, (1060, 635), "Connect TikTok", 28, fill=(40, 16, 10))
    return im


def scene_login_kit(t: float) -> Image.Image:
    im = bg(t)
    d = window_frame(im, "TikTok Login Kit (Desktop) — OAuth")
    text(d, (140, 170), "Product: Login Kit", 48)
    text(d, (140, 240), "Scope demonstrated:", 30, bold=False, fill=(154, 171, 191))
    chip(d, 140, 290, "user.info.basic")
    d.rounded_rectangle((140, 380, 1780, 880), radius=16, fill=(15, 21, 30, 255), outline=(232, 238, 246, 35))
    text(d, (180, 420), "Browser authorization page", 34)
    text(d, (180, 480), "ClipMaker requests access to your TikTok account", 28, bold=False, fill=(154, 171, 191))
    text(d, (180, 540), "Redirect URI: http://127.0.0.1:8765/callback/", 28, bold=False, fill=(126, 235, 223))
    text(d, (180, 600), "User clicks Authorize → code returns to ClipMaker", 28, bold=False)
    d.rounded_rectangle((180, 700, 520, 770), radius=12, fill=(46, 196, 182, 220))
    text(d, (230, 718), "Authorize", 30, fill=(6, 34, 31))
    text(d, (560, 720), "→ tokens saved locally (AppData\\ClipMaker)", 26, bold=False, fill=(154, 171, 191))
    return im


def scene_create_clip(t: float) -> Image.Image:
    im = bg(t)
    d = window_frame(im, "ClipMaker — render 30s vertical clip")
    text(d, (140, 170), "Create clip (local render)", 48)
    text(d, (140, 240), "No TikTok API call yet — media stays on the PC", 28, bold=False, fill=(154, 171, 191))
    # Progress mock
    d.rounded_rectangle((140, 340, 1780, 420), radius=14, fill=(15, 21, 30, 255), outline=(232, 238, 246, 35))
    prog = 0.15 + 0.7 * ease((math.sin(t * 2) + 1) / 2)
    d.rounded_rectangle((150, 350, 150 + int(1610 * prog), 410), radius=10, fill=(46, 196, 182, 200))
    text(d, (160, 460), "Output: C:\\Users\\…\\Desktop\\track_tiktok.mp4  (9:16)", 28, bold=False)
    text(d, (160, 520), "Caption ready for TikTok title / description", 28, bold=False, fill=(154, 171, 191))
    d.rounded_rectangle((160, 600, 560, 670), radius=12, fill=(46, 196, 182, 220))
    text(d, (210, 618), "Clip ready", 30, fill=(6, 34, 31))
    return im


def scene_content_posting(t: float) -> Image.Image:
    im = bg(t)
    d = window_frame(im, "TikTok Content Posting API")
    text(d, (140, 160), "Product: Content Posting API", 46)
    text(d, (140, 230), "Scopes demonstrated:", 28, bold=False, fill=(154, 171, 191))
    x = 140
    x += chip(d, x, 280, "video.upload")
    chip(d, x, 280, "video.publish")

    # Two columns: inbox vs direct
    d.rounded_rectangle((140, 380, 920, 900), radius=16, fill=(15, 21, 30, 255), outline=(46, 196, 182, 100))
    text(d, (180, 420), "video.upload", 34, fill=(46, 196, 182))
    text(d, (180, 480), "Send MP4 to TikTok inbox", 28, bold=False)
    text(d, (180, 530), "(creator draft — open TikTok app", 26, bold=False, fill=(154, 171, 191))
    text(d, (180, 570), "to finish publishing)", 26, bold=False, fill=(154, 171, 191))
    d.rounded_rectangle((180, 680, 520, 750), radius=12, fill=(46, 196, 182, 50), outline=(46, 196, 182, 160))
    text(d, (220, 700), "Inbox mode", 28)

    d.rounded_rectangle((1000, 380, 1780, 900), radius=16, fill=(15, 21, 30, 255), outline=(255, 122, 89, 100))
    text(d, (1040, 420), "video.publish", 34, fill=(255, 122, 89))
    text(d, (1040, 480), "Direct post with caption", 28, bold=False)
    text(d, (1040, 530), "(Sandbox: SELF_ONLY / private", 26, bold=False, fill=(154, 171, 191))
    text(d, (1040, 570), "until production approval)", 26, bold=False, fill=(154, 171, 191))
    d.rounded_rectangle((1040, 680, 1480, 750), radius=12, fill=(255, 122, 89, 50), outline=(255, 122, 89, 160))
    text(d, (1100, 700), "Direct mode", 28)
    return im


def scene_publish_click(t: float) -> Image.Image:
    im = bg(t)
    d = window_frame(im, "ClipMaker — user clicks Publish")
    text(d, (140, 180), "End-to-end publish action", 48)
    text(d, (140, 260), "User must click — ClipMaker never auto-posts", 30, bold=False, fill=(154, 171, 191))
    d.rounded_rectangle((140, 360, 900, 820), radius=16, fill=(15, 21, 30, 255), outline=(232, 238, 246, 35))
    text(d, (180, 400), "Title / caption", 28, bold=False, fill=(154, 171, 191))
    text(d, (180, 450), "My new track — 30s clip", 32)
    text(d, (180, 520), "Mode: Direct post (video.publish)", 28, bold=False)
    text(d, (180, 570), "AI label: on (is_aigc)", 28, bold=False)
    pulse = 0.7 + 0.3 * math.sin(t * 6)
    d.rounded_rectangle((180, 660, 560, 740), radius=14, fill=(255, 122, 89, int(180 + 60 * pulse)))
    text(d, (230, 680), "Publish to TikTok", 30, fill=(40, 16, 10))

    d.rounded_rectangle((980, 360, 1780, 820), radius=16, fill=(15, 21, 30, 255), outline=(46, 196, 182, 120))
    text(d, (1040, 420), "API calls", 32)
    text(d, (1040, 490), "1) creator_info/query", 28, bold=False, fill=(154, 171, 191))
    text(d, (1040, 550), "2) post/publish/video/init", 28, bold=False, fill=(154, 171, 191))
    text(d, (1040, 610), "3) FILE_UPLOAD chunks", 28, bold=False, fill=(154, 171, 191))
    text(d, (1040, 670), "4) status/fetch → COMPLETE", 28, bold=False, fill=(46, 196, 182))
    return im


def scene_success(t: float) -> Image.Image:
    im = bg(t)
    d = window_frame(im, "ClipMaker — publish complete")
    text(d, (140, 200), "Success", 64, fill=(46, 196, 182))
    text(d, (140, 290), "Video published to the creator’s TikTok account", 34, bold=False)
    text(d, (140, 370), "Scopes used in this flow:", 30, bold=False, fill=(154, 171, 191))
    x = 140
    for s in ("user.info.basic", "video.upload", "video.publish"):
        x += chip(d, x, 430, s)
    text(d, (140, 540), "Products: Login Kit (Desktop) + Content Posting API", 30, bold=False)
    text(d, (140, 600), "Website: https://legenda89.github.io/ClipMaker/", 28, bold=False, fill=(126, 235, 223))
    text(d, (140, 660), "Sandbox demo — production unlocks public posting after approval", 26, bold=False, fill=(154, 171, 191))
    return im


def main() -> None:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    icon = Image.open(ICON).convert("RGBA")
    total_sec = 60
    nframes = total_sec * FPS

    def frame_at(i: int) -> Image.Image:
        t = i / FPS
        for start, end, fn in (
            (0, 6, scene_website),
            (6, 12, lambda tt: scene_open_app(tt, icon)),
            (12, 22, scene_login_kit),
            (22, 30, scene_create_clip),
            (30, 42, scene_content_posting),
            (42, 52, scene_publish_click),
            (52, 60, scene_success),
        ):
            if start <= t < end or (t >= 60 and end == 60):
                return fn(t)
        return scene_success(t)

    tmp = Path(tempfile.mkdtemp(prefix="clipmaker_demo_"))
    try:
        pattern = tmp / "f_%05d.png"
        for i in range(nframes):
            frame_at(i).save(tmp / f"f_{i:05d}.png")
            if i % (FPS * 5) == 0:
                print(f"frames {i}/{nframes}")

        cmd = [
            ff,
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(pattern),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            str(OUT),
        ]
        subprocess.check_call(cmd)
        OUT2.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT, OUT2)
        OUT3.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT, OUT3)
        size_mb = OUT.stat().st_size / (1024 * 1024)
        print(f"Wrote {OUT} ({size_mb:.1f} MB)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
