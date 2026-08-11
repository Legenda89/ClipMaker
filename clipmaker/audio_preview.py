"""Preview the selected audio clip on Windows."""

from __future__ import annotations

import os
import subprocess
import tempfile
import winsound
from pathlib import Path

from clipmaker.ffmpeg_worker import ffmpeg_exe, probe_duration


class AudioPreview:
    def __init__(self) -> None:
        self._temp_path: Path | None = None
        self.playing = False

    def stop(self) -> None:
        winsound.PlaySound(None, winsound.SND_PURGE)
        self._cleanup_temp()
        self.playing = False

    def _cleanup_temp(self) -> None:
        if self._temp_path and self._temp_path.exists():
            try:
                self._temp_path.unlink()
            except OSError:
                pass
        self._temp_path = None

    def play(
        self,
        audio_path: str,
        start_sec: float,
        duration_sec: float,
        *,
        fade_sec: float = 0.0,
    ) -> float:
        """Extract and play clip; returns actual playback length in seconds."""
        self.stop()

        audio_dur = probe_duration(audio_path)
        duration = float(duration_sec)
        start = max(0.0, float(start_sec))
        if audio_dur > 0:
            duration = min(duration, max(0.1, audio_dur - start))

        fade = min(fade_sec, duration / 3) if fade_sec > 0 else 0.0
        fd, tmp_name = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        tmp = Path(tmp_name)
        self._temp_path = tmp

        af_parts = ["asetpts=PTS-STARTPTS"]
        if fade > 0:
            af_parts.append(f"afade=t=in:st=0:d={fade}")
            af_parts.append(f"afade=t=out:st={max(0.0, duration - fade)}:d={fade}")
        af = ",".join(af_parts)

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        cmd = [
            ffmpeg_exe(),
            "-hide_banner",
            "-y",
            "-ss",
            f"{start}",
            "-i",
            audio_path,
            "-t",
            f"{duration}",
            "-af",
            af,
            "-ac",
            "2",
            "-ar",
            "44100",
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
            self._cleanup_temp()
            tail = (proc.stderr or proc.stdout or "").strip()[-500:]
            raise RuntimeError(tail or "Esikuuntelun valmistelu epäonnistui")

        winsound.PlaySound(str(tmp), winsound.SND_ASYNC | winsound.SND_FILENAME)
        self.playing = True
        return duration
