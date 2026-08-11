"""FFmpeg helpers for ClipMaker."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import imageio_ffmpeg

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".opus"}


@dataclass(frozen=True)
class ExportPreset:
    key: str
    label: str
    width: int
    height: int
    fps: int = 30


PRESETS: dict[str, ExportPreset] = {
    "tiktok": ExportPreset("tiktok", "TikTok / Shorts / Snap (9:16)", 1080, 1920),
    "youtube": ExportPreset("youtube", "YouTube vaakakuva (16:9)", 1920, 1080),
    "square": ExportPreset("square", "Neliö (1:1)", 1080, 1080),
}


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(cmd: list[str], on_progress: Callable[[float], None] | None = None) -> None:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    assert proc.stderr is not None
    duration = 0.0
    time_re = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
    dur_re = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")

    err_lines: list[str] = []
    for line in proc.stderr:
        err_lines.append(line)
        if duration <= 0:
            m = dur_re.search(line)
            if m:
                h, mi, s = m.groups()
                duration = int(h) * 3600 + int(mi) * 60 + float(s)
        if on_progress and duration > 0:
            m = time_re.search(line)
            if m:
                h, mi, s = m.groups()
                t = int(h) * 3600 + int(mi) * 60 + float(s)
                on_progress(min(0.99, t / duration))

    code = proc.wait()
    if code != 0:
        tail = "".join(err_lines[-40:]).strip()
        raise RuntimeError(tail or f"FFmpeg epäonnistui (koodi {code})")
    if on_progress:
        on_progress(1.0)


def probe_duration(path: str | Path) -> float:
    """Return media duration in seconds via ffmpeg -i."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-i", str(path)]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m:02d}:{s:05.2f}"


def parse_timestamp(text: str) -> float:
    text = text.strip().replace(",", ".")
    if not text:
        return 0.0
    if ":" in text:
        parts = text.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return float(text)


def is_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def scale_crop_filter(width: int, height: int) -> str:
    """Cover-fit: scale then center-crop to exact size."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )


def export_clip(
    *,
    audio_path: str,
    visual_path: str,
    output_path: str,
    start_sec: float,
    duration_sec: float,
    preset: ExportPreset,
    fade_sec: float = 0.5,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    if duration_sec < 1:
        raise ValueError("Keston pitää olla vähintään 1 sekunti")
    if start_sec < 0:
        raise ValueError("Aloituskohta ei voi olla negatiivinen")

    audio_dur = probe_duration(audio_path)
    if audio_dur > 0 and start_sec >= audio_dur:
        raise ValueError("Aloituskohta on musiikin lopun jälkeen")
    if audio_dur > 0:
        duration_sec = min(duration_sec, max(0.1, audio_dur - start_sec))

    fade = min(fade_sec, duration_sec / 3) if fade_sec > 0 else 0.0
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    w, h, fps = preset.width, preset.height, preset.fps
    vf = scale_crop_filter(w, h)
    af_parts = [f"atrim=start={start_sec}:duration={duration_sec}", "asetpts=PTS-STARTPTS"]
    if fade > 0:
        af_parts.append(f"afade=t=in:st=0:d={fade}")
        af_parts.append(f"afade=t=out:st={max(0.0, duration_sec - fade)}:d={fade}")
    af = ",".join(af_parts)

    common_out = [
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        "-movflags", "+faststart",
        "-shortest",
        "-y",
        str(out),
    ]

    if is_image(visual_path):
        # Still image looped for clip length
        cmd = [
            ffmpeg_exe(),
            "-hide_banner",
            "-loop", "1",
            "-framerate", str(fps),
            "-i", visual_path,
            "-i", audio_path,
            "-filter_complex",
            f"[0:v]{vf},fps={fps},trim=duration={duration_sec},setpts=PTS-STARTPTS[v];"
            f"[1:a]{af}[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-t", f"{duration_sec}",
            *common_out,
        ]
    elif is_video(visual_path):
        vis_dur = probe_duration(visual_path)
        # Loop video if shorter than audio clip
        loop_needed = vis_dur > 0 and vis_dur < duration_sec
        inputs: list[str] = []
        if loop_needed:
            inputs = ["-stream_loop", "-1", "-i", visual_path]
        else:
            inputs = ["-i", visual_path]
        inputs += ["-i", audio_path]

        cmd = [
            ffmpeg_exe(),
            "-hide_banner",
            *inputs,
            "-filter_complex",
            f"[0:v]{vf},fps={fps},trim=duration={duration_sec},setpts=PTS-STARTPTS[v];"
            f"[1:a]{af}[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-t", f"{duration_sec}",
            *common_out,
        ]
    else:
        raise ValueError("Visuaalin pitää olla kuva tai video")

    _run(cmd, on_progress=on_progress)


def default_output_name(audio_path: str, preset_key: str) -> str:
    stem = Path(audio_path).stem
    safe = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_") or "clip"
    return f"{safe}_{preset_key}.mp4"
