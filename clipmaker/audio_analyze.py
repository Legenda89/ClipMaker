"""Find the most energetic / hook-like section of a track."""

from __future__ import annotations

import math
import os
import struct
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from clipmaker.ffmpeg_worker import ffmpeg_exe, probe_duration


@dataclass(frozen=True)
class ClipSuggestion:
    start_sec: float
    score: float
    label: str


def _decode_mono_wav(audio_path: str) -> tuple[Path, list[float], int]:
    """Decode audio to mono WAV and return path, normalized samples, sample rate."""
    fd, tmp_name = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    tmp = Path(tmp_name)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = [
        ffmpeg_exe(),
        "-hide_banner",
        "-y",
        "-i",
        audio_path,
        "-ac",
        "1",
        "-ar",
        "11025",
        "-f",
        "wav",
        str(tmp),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Äänen analysointi epäonnistui")

    try:
        with wave.open(str(tmp), "rb") as wf:
            rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            width = wf.getsampwidth()
            if width == 2:
                count = len(frames) // 2
                ints = struct.unpack(f"<{count}h", frames)
                samples = [v / 32768.0 for v in ints]
            elif width == 1:
                ints = struct.unpack(f"{len(frames)}B", frames)
                samples = [(v - 128) / 128.0 for v in ints]
            else:
                raise RuntimeError(f"Tuntematon näytteen leveys: {width}")
    finally:
        tmp.unlink(missing_ok=True)

    return tmp, samples, rate


def _rms_envelope(samples: list[float], sample_rate: int, window_sec: float = 0.5) -> tuple[list[float], list[float]]:
    window = max(1, int(sample_rate * window_sec))
    hop = max(1, window // 2)
    times: list[float] = []
    energies: list[float] = []
    for i in range(0, len(samples) - window, hop):
        chunk = samples[i : i + window]
        mean_sq = sum(s * s for s in chunk) / len(chunk)
        times.append(i / sample_rate)
        energies.append(math.sqrt(mean_sq))
    return times, energies


def _window_score(energies: list[float], start_idx: int, end_idx: int, global_max: float) -> float:
    if start_idx >= end_idx or not energies:
        return 0.0
    window = energies[start_idx:end_idx]
    avg = sum(window) / len(window)
    peak = max(window)
    floor = min(window)

    if global_max <= 0:
        return 0.0

    # Penalize very quiet sections (intro/outro).
    if avg < global_max * 0.12:
        return avg * 0.2

    # Chorus-like: loud average, strong peak, not too uneven at the bottom.
    score = avg * 0.55 + peak * 0.30 + floor * 0.15

    # Bonus if energy rises in the first ~4 s of the clip (build into hook).
    rise_len = min(len(window), max(1, len(window) // 8))
    if rise_len >= 2 and window[rise_len - 1] > window[0] * 1.15:
        score *= 1.08

    return score


def find_best_clip_start(
    audio_path: str,
    duration_sec: float,
    *,
    total_duration: float | None = None,
) -> ClipSuggestion:
    """
    Pick a start time where the track is most energetic for the given clip length.
    Works well for pop/EDM hooks; ballads may pick the loudest chorus instead.
    """
    duration_sec = max(1.0, float(duration_sec))
    total = total_duration if total_duration is not None else probe_duration(audio_path)
    if total <= 0:
        return ClipSuggestion(0.0, 0.0, "Ei voitu analysoida")

    if total <= duration_sec + 1:
        return ClipSuggestion(0.0, 1.0, "Kappale lyhyempi kuin clip")

    _, samples, rate = _decode_mono_wav(audio_path)
    times, energies = _rms_envelope(samples, rate)
    if len(energies) < 2:
        return ClipSuggestion(0.0, 0.0, "Liian vähän dataa")

    global_max = max(energies) or 1.0
    step_sec = 0.5
    step_idx = max(1, int(step_sec / (times[1] - times[0]) if len(times) > 1 else 1))
    win_len = max(2, int(duration_sec / (times[1] - times[0]) if len(times) > 1 else duration_sec))

    best_start = 0.0
    best_score = -1.0

    max_start_sec = max(0.0, total - duration_sec)
    for start_idx in range(0, len(energies) - win_len, step_idx):
        start_sec = times[start_idx]
        if start_sec > max_start_sec:
            break
        end_idx = min(len(energies), start_idx + win_len)
        score = _window_score(energies, start_idx, end_idx, global_max)
        if score > best_score:
            best_score = score
            best_start = start_sec

    # Snap to half-second for cleaner cuts.
    best_start = round(best_start * 2) / 2
    best_start = min(best_start, max(0.0, total - duration_sec))

    return ClipSuggestion(best_start, best_score, "Paras kohta löytyi")
