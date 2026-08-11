"""Generate ClipMaker TikTok demo video (9:16)."""

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

W, H, FPS = 1080, 1920, 30
TOTAL = 18 * FPS


def pick_font(bold: bool = True) -> str | None:
    if bold:
        for p in (
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\calibrib.ttf",
        ):
            if Path(p).exists():
                return p
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
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


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def bg_frame(t: float) -> Image.Image:
    im = Image.new("RGB", (W, H), (12, 17, 24))
    draw = ImageDraw.Draw(im, "RGBA")
    pulse = 0.5 + 0.5 * math.sin(t * 1.2)
    draw.ellipse((-200, -100, 700, 700), fill=(46, 196, 182, int(28 + 10 * pulse)))
    draw.ellipse((500, 1100, 1400, 2100), fill=(255, 122, 89, int(22 + 8 * pulse)))
    return im


def paste_center(base: Image.Image, overlay: Image.Image, y: int, scale: float = 1.0, alpha: float = 1.0) -> None:
    ow = max(1, int(overlay.width * scale))
    oh = max(1, int(overlay.height * scale))
    layer = overlay.resize((ow, oh), Image.Resampling.LANCZOS)
    if alpha < 1:
        a = layer.split()[-1].point(lambda p: int(p * alpha))
        layer.putalpha(a)
    x = (W - ow) // 2
    base.paste(layer, (x, int(y)), layer)


def main() -> None:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    icon = Image.open(ICON).convert("RGBA")
    tmpdir = Path(tempfile.mkdtemp(prefix="cmvid_"))
    try:
        for i in range(TOTAL):
            t = i / FPS
            frame = bg_frame(t)
            draw = ImageDraw.Draw(frame)

            if t < 5:
                p = ease(min(1, t / 1.2))
                paste_center(frame, icon, int(lerp(520, 420, p)), scale=lerp(0.55, 0.72, p), alpha=p)
                title_a = ease(max(0, min(1, (t - 1.0) / 0.8)))
                if title_a > 0:
                    title = "ClipMaker"
                    f = font(96)
                    bbox = draw.textbbox((0, 0), title, font=f)
                    tw = bbox[2] - bbox[0]
                    draw.text(((W - tw) / 2, 1180), title, font=f, fill=(232, 238, 246, int(255 * title_a)))
                sub_a = ease(max(0, min(1, (t - 1.8) / 0.8)))
                if sub_a > 0:
                    sub = "Musiikista valmis someclip sekunneissa"
                    f2 = font(34, bold=False)
                    bbox = draw.textbbox((0, 0), sub, font=f2)
                    tw = bbox[2] - bbox[0]
                    draw.text(((W - tw) / 2, 1300), sub, font=f2, fill=(154, 171, 191, int(255 * sub_a)))
            elif t < 12:
                paste_center(frame, icon, 180, scale=0.38, alpha=1)
                header = "Näin se toimii"
                fh = font(64)
                bbox = draw.textbbox((0, 0), header, font=fh)
                draw.text(((W - (bbox[2] - bbox[0])) / 2, 520), header, font=fh, fill=(232, 238, 246))
                items = [
                    "1. Valitse musiikki + kansikuva",
                    "2. Etsii parhaan kohdan",
                    "3. 20-60 s pystyclip valmiina",
                    "4. Julkaise Shorts / TikTok",
                ]
                local = t - 5
                fitem = font(40, bold=False)
                for idx, text in enumerate(items):
                    appear = ease(max(0, min(1, (local - idx * 1.2) / 0.55)))
                    if appear <= 0:
                        continue
                    y = 660 + idx * 120
                    bbox = draw.textbbox((0, 0), text, font=fitem)
                    tw = bbox[2] - bbox[0]
                    pad = 28
                    draw.rounded_rectangle(
                        ((W - tw) / 2 - pad, y - 18, (W + tw) / 2 + pad, y + 58),
                        radius=28,
                        fill=(20, 28, 39, int(200 * appear)),
                    )
                    draw.text(((W - tw) / 2, y), text, font=fitem, fill=(232, 238, 246, int(255 * appear)))
            else:
                local = t - 12
                p = ease(min(1, local / 0.8))
                paste_center(frame, icon, int(lerp(500, 360, p)), scale=lerp(0.5, 0.7, p), alpha=1)
                lines = [
                    ("ClipMaker", font(88), (232, 238, 246)),
                    ("Windows · Shorts · TikTok", font(36, bold=False), (46, 196, 182)),
                    ("legenda89.github.io/ClipMaker", font(32, bold=False), (154, 171, 191)),
                ]
                y = 1180
                for text, fnt, col in lines:
                    a = ease(max(0, min(1, (local - 0.4) / 0.7)))
                    bbox = draw.textbbox((0, 0), text, font=fnt)
                    tw = bbox[2] - bbox[0]
                    draw.text(((W - tw) / 2, y), text, font=fnt, fill=(*col, int(255 * a)))
                    y += 70

            frame.save(tmpdir / f"f_{i:05d}.png")
            if i % 60 == 0:
                print(f"frame {i}/{TOTAL}", flush=True)

        cmd = [
            ff,
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(tmpdir / "f_%05d.png"),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=196:duration=18,volume=0.03",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(OUT),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr[-800:])
        shutil.copy2(OUT, OUT2)
        print("VIDEO", OUT, OUT.stat().st_size, flush=True)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
