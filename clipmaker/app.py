"""ClipMaker — nopea musiikkivideo TikTok / YouTube / Snapchat -käyttöön."""

from __future__ import annotations

import threading
import traceback
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

from clipmaker import tiktok_publish, youtube_publish
from clipmaker.audio_analyze import find_best_clip_start
from clipmaker.audio_preview import AudioPreview
from clipmaker.config_store import load_settings, update_settings
from clipmaker.ffmpeg_worker import (
    AUDIO_EXTS,
    IMAGE_EXTS,
    PRESETS,
    VIDEO_EXTS,
    default_output_name,
    export_clip,
    format_timestamp,
    parse_timestamp,
    probe_duration,
)

AUDIO_TYPES = [
    ("Ääni", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma *.opus"),
    ("Kaikki", "*.*"),
]
VISUAL_TYPES = [
    ("Kuva / video", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.mp4 *.mov *.mkv *.webm *.avi *.m4v"),
    ("Kaikki", "*.*"),
]
VISUAL_EXTS = IMAGE_EXTS | VIDEO_EXTS


class ClipMakerApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self) -> None:
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.title("ClipMaker")
        self.geometry("760x900")
        self.minsize(680, 720)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        settings = load_settings()

        self.audio_path = ctk.StringVar(value="")
        self.visual_path = ctk.StringVar(value="")
        self.output_path = ctk.StringVar(value="")
        self.start_text = ctk.StringVar(value="0:00")
        self.duration = ctk.DoubleVar(value=30.0)
        self.preset_key = ctk.StringVar(value="tiktok")
        self.fade_enabled = ctk.BooleanVar(value=True)
        self.auto_best = ctk.BooleanVar(value=True)
        self.status = ctk.StringVar(value="Valitse tai pudota musiikki ja kuva/video.")
        self.audio_info = ctk.StringVar(value="")
        self.publish_title = ctk.StringVar(value="")
        self.publish_desc = ctk.StringVar(value="")
        self.yt_privacy = ctk.StringVar(value="public")
        self.tiktok_mode = ctk.StringVar(value="inbox")
        self.yt_client_secrets = ctk.StringVar(value=settings.get("youtube_client_secrets", ""))
        self.yt_client_id = ctk.StringVar(value=settings.get("youtube_client_id", ""))
        self.yt_client_secret = ctk.StringVar(value=settings.get("youtube_client_secret", ""))
        self.tiktok_key = ctk.StringVar(value=settings.get("tiktok_client_key", ""))
        self.tiktok_secret = ctk.StringVar(value=settings.get("tiktok_client_secret", ""))
        self.yt_status = ctk.StringVar(value="")
        self.tt_status = ctk.StringVar(value="")
        self._connect_busy = False

        self._busy = False
        self._analyze_busy = False
        self._preview_busy = False
        self._preview = AudioPreview()
        self._preview_cleanup_job: str | None = None
        self._audio_duration = 0.0
        self._last_export = ""

        self._build()
        self._refresh_connection_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=0, pady=0)
        root = self.scroll
        pad = {"padx": 20, "pady": (8, 0)}

        header = ctk.CTkLabel(
            root,
            text="ClipMaker",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        header.pack(padx=20, pady=(20, 4), anchor="w")

        sub = ctk.CTkLabel(
            root,
            text="Leikkaa musiikista 20–60 s pätkä, yhdistä kuvaan/videoon ja julkaise Shortsina tai TikTokiin.",
            text_color=("gray40", "gray70"),
            wraplength=680,
            justify="left",
        )
        sub.pack(padx=20, pady=(0, 12), anchor="w")

        # Audio
        self._section(root, "1. Musiikki")
        self.audio_drop = self._make_drop_zone(
            root,
            hint="Valitse… tai pudota musiikkitiedosto tähän",
            path_var=self.audio_path,
            on_click=self._pick_audio,
            on_drop=self._on_audio_drop,
        )
        self.audio_drop.pack(fill="x", **pad)
        ctk.CTkLabel(root, textvariable=self.audio_info, text_color=("gray40", "gray65")).pack(
            padx=20, anchor="w"
        )
        ctk.CTkCheckBox(
            root,
            text="Etsi paras kohta automaattisesti (kertosae / voimakkain osa)",
            variable=self.auto_best,
            command=self._on_auto_best_toggle,
        ).pack(padx=20, pady=(6, 0), anchor="w")

        # Start + duration
        self._section(root, "2. Aloitus ja kesto")
        grid = ctk.CTkFrame(root, fg_color="transparent")
        grid.pack(fill="x", **pad)

        ctk.CTkLabel(grid, text="Aloitus (m:ss)").grid(row=0, column=0, sticky="w")
        start_entry = ctk.CTkEntry(grid, textvariable=self.start_text, width=100)
        start_entry.grid(row=1, column=0, sticky="w", padx=(0, 16))
        start_entry.bind("<FocusOut>", lambda _e: self._sync_start_slider())
        start_entry.bind("<Return>", lambda _e: self._sync_start_slider())

        ctk.CTkLabel(grid, text="Tai liu'uta aloituskohtaa").grid(row=0, column=1, sticky="w")
        self.start_slider = ctk.CTkSlider(
            grid, from_=0, to=1, number_of_steps=1000, command=self._on_start_slide
        )
        self.start_slider.set(0)
        self.start_slider.grid(row=1, column=1, sticky="ew")
        grid.columnconfigure(1, weight=1)

        find_row = ctk.CTkFrame(root, fg_color="transparent")
        find_row.pack(fill="x", padx=20, pady=(6, 0))
        self.find_btn = ctk.CTkButton(
            find_row, text="Etsi paras kohta", width=160, command=self._find_best_start
        )
        self.find_btn.pack(side="left")
        self.preview_btn = ctk.CTkButton(
            find_row, text="Esikuuntele", width=140, command=self._toggle_preview
        )
        self.preview_btn.pack(side="left", padx=(8, 0))

        dur_row = ctk.CTkFrame(root, fg_color="transparent")
        dur_row.pack(fill="x", **pad)
        self.duration_label = ctk.CTkLabel(dur_row, text="Kesto: 30 s")
        self.duration_label.pack(anchor="w")
        self.duration_slider = ctk.CTkSlider(
            dur_row, from_=20, to=60, number_of_steps=40, command=self._on_duration
        )
        self.duration_slider.set(30)
        self.duration_slider.pack(fill="x", pady=(4, 0))
        self.duration_slider.bind("<ButtonRelease-1>", lambda _e: self._maybe_auto_find())

        # Visual
        self._section(root, "3. Kuva tai video")
        self.visual_drop = self._make_drop_zone(
            root,
            hint="Valitse… tai pudota kuva/video tähän",
            path_var=self.visual_path,
            on_click=self._pick_visual,
            on_drop=self._on_visual_drop,
        )
        self.visual_drop.pack(fill="x", **pad)

        # Preset
        self._section(root, "4. Formaatti")
        presets = ctk.CTkFrame(root, fg_color="transparent")
        presets.pack(fill="x", **pad)
        for key, preset in PRESETS.items():
            ctk.CTkRadioButton(
                presets, text=preset.label, variable=self.preset_key, value=key
            ).pack(anchor="w", pady=2)

        ctk.CTkCheckBox(
            root,
            text="Pehmeä fade alkuun ja loppuun (0,5 s)",
            variable=self.fade_enabled,
        ).pack(padx=20, pady=(10, 0), anchor="w")

        # Output
        self._section(root, "5. Tallennus")
        row3 = ctk.CTkFrame(root, fg_color="transparent")
        row3.pack(fill="x", **pad)
        ctk.CTkEntry(row3, textvariable=self.output_path).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ctk.CTkButton(row3, text="Sijainti…", width=110, command=self._pick_output).pack(side="right")

        self.progress = ctk.CTkProgressBar(root)
        self.progress.pack(fill="x", padx=20, pady=(16, 4))
        self.progress.set(0)

        ctk.CTkLabel(root, textvariable=self.status, wraplength=680).pack(padx=20, anchor="w")

        self.export_btn = ctk.CTkButton(
            root,
            text="Luo video",
            height=44,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._export,
        )
        self.export_btn.pack(padx=20, pady=16, fill="x")

        # Connections
        self._section(root, "6. YouTube Shorts & TikTok -yhteydet")

        # --- YouTube ---
        ctk.CTkLabel(root, text="YouTube Shorts", font=ctk.CTkFont(weight="bold")).pack(
            padx=20, pady=(8, 0), anchor="w"
        )
        ctk.CTkLabel(
            root,
            text=(
                "1) Ota YouTube Data API v3 käyttöön  →  2) OAuth consent screen (lisää itsesi test user)  →\n"
                "3) Credentials → Create OAuth client ID → Desktop app  →  4) Kopioi Client ID + Secret alle\n"
                "JSON-tiedostoa EI tarvita, jos liität ID:n ja Secretin tähän."
            ),
            text_color=("gray40", "gray65"),
            justify="left",
            wraplength=680,
        ).pack(padx=20, pady=(2, 0), anchor="w")

        yt_help = ctk.CTkFrame(root, fg_color="transparent")
        yt_help.pack(fill="x", padx=20, pady=(6, 0))
        ctk.CTkButton(
            yt_help, text="1. Avaa API", width=110, command=lambda: webbrowser.open(youtube_publish.API_ENABLE_URL)
        ).pack(side="left")
        ctk.CTkButton(
            yt_help, text="2. Consent", width=110, command=lambda: webbrowser.open(youtube_publish.CONSENT_URL)
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            yt_help, text="3. Credentials", width=120, command=lambda: webbrowser.open(youtube_publish.HELP_URL)
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(yt_help, text="Ohjeikkuna", width=110, command=self._show_youtube_help).pack(
            side="left", padx=(8, 0)
        )

        ctk.CTkEntry(
            root, textvariable=self.yt_client_id, placeholder_text="Client ID (...apps.googleusercontent.com)"
        ).pack(fill="x", padx=20, pady=(8, 0))
        ctk.CTkEntry(
            root, textvariable=self.yt_client_secret, placeholder_text="Client Secret", show="*"
        ).pack(fill="x", padx=20, pady=(6, 0))

        yt_row = ctk.CTkFrame(root, fg_color="transparent")
        yt_row.pack(fill="x", **pad)
        ctk.CTkButton(yt_row, text="Tallenna YouTube-avaimet", width=180, command=self._save_youtube_creds).pack(
            side="left"
        )
        self.yt_connect_btn = ctk.CTkButton(
            yt_row, text="Yhdistä YouTube", width=150, command=self._connect_youtube
        )
        self.yt_connect_btn.pack(side="left", padx=(8, 0))
        ctk.CTkButton(yt_row, text="Tai JSON…", width=100, command=self._pick_yt_secrets).pack(
            side="left", padx=(8, 0)
        )

        ctk.CTkLabel(root, textvariable=self.yt_status, text_color=("gray40", "gray65")).pack(
            padx=20, anchor="w"
        )

        # --- TikTok ---
        ctk.CTkLabel(root, text="TikTok", font=ctk.CTkFont(weight="bold")).pack(
            padx=20, pady=(14, 0), anchor="w"
        )
        ctk.CTkLabel(
            root,
            text=(
                "developers.tiktok.com → Login Kit (Desktop) + Content Posting API.\n"
                "Redirect URI TARKALLEEN: http://127.0.0.1:8765/callback\n"
                "Scopes: user.info.basic, video.upload"
            ),
            text_color=("gray40", "gray65"),
            justify="left",
            wraplength=680,
        ).pack(padx=20, pady=(2, 0), anchor="w")

        tt_help = ctk.CTkFrame(root, fg_color="transparent")
        tt_help.pack(fill="x", padx=20, pady=(6, 0))
        ctk.CTkButton(
            tt_help,
            text="Avaa TikTok Developers",
            width=180,
            command=lambda: webbrowser.open("https://developers.tiktok.com/apps"),
        ).pack(side="left")
        ctk.CTkButton(tt_help, text="Ohjeikkuna", width=110, command=self._show_tiktok_help).pack(
            side="left", padx=(8, 0)
        )

        tt_row = ctk.CTkFrame(root, fg_color="transparent")
        tt_row.pack(fill="x", **pad)
        ctk.CTkEntry(tt_row, textvariable=self.tiktok_key, placeholder_text="TikTok Client Key").pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ctk.CTkEntry(
            tt_row, textvariable=self.tiktok_secret, placeholder_text="TikTok Client Secret", show="*"
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(tt_row, text="Tallenna", width=90, command=self._save_tiktok_creds).pack(side="left")
        self.tt_connect_btn = ctk.CTkButton(
            tt_row, text="Yhdistä TikTok", width=130, command=self._connect_tiktok
        )
        self.tt_connect_btn.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(root, textvariable=self.tt_status, text_color=("gray40", "gray65")).pack(
            padx=20, anchor="w"
        )

        self.tt_callback_url = ctk.StringVar(value="")
        cb_row = ctk.CTkFrame(root, fg_color="transparent")
        cb_row.pack(fill="x", padx=20, pady=(6, 0))
        ctk.CTkEntry(
            cb_row,
            textvariable=self.tt_callback_url,
            placeholder_text="Jos kirjautuminen jumissa: liita callback-URL tahan...",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(cb_row, text="Liitä callback-URL", width=150, command=self._finish_tiktok_callback).pack(
            side="left"
        )

        disc = ctk.CTkFrame(root, fg_color="transparent")
        disc.pack(fill="x", padx=20, pady=(6, 0))
        ctk.CTkButton(disc, text="Katkaise YouTube", width=140, command=self._disconnect_youtube).pack(
            side="left"
        )
        ctk.CTkButton(disc, text="Katkaise TikTok", width=140, command=self._disconnect_tiktok).pack(
            side="left", padx=(8, 0)
        )

        # Publish
        self._section(root, "7. Julkaise clip")
        ctk.CTkLabel(root, text="Otsikko").pack(padx=20, pady=(4, 0), anchor="w")
        ctk.CTkEntry(root, textvariable=self.publish_title, placeholder_text="Clipin otsikko").pack(
            fill="x", padx=20, pady=(2, 0)
        )
        ctk.CTkLabel(root, text="Kuvaus (valinnainen)").pack(padx=20, pady=(8, 0), anchor="w")
        ctk.CTkEntry(root, textvariable=self.publish_desc, placeholder_text="#Shorts #fyp …").pack(
            fill="x", padx=20, pady=(2, 0)
        )

        pub_opts = ctk.CTkFrame(root, fg_color="transparent")
        pub_opts.pack(fill="x", padx=20, pady=(10, 0))
        ctk.CTkLabel(pub_opts, text="YouTube:").pack(side="left")
        for label, value in (("Julkinen", "public"), ("Listaamaton", "unlisted"), ("Yksityinen", "private")):
            ctk.CTkRadioButton(pub_opts, text=label, variable=self.yt_privacy, value=value).pack(
                side="left", padx=(8, 0)
            )

        tt_opts = ctk.CTkFrame(root, fg_color="transparent")
        tt_opts.pack(fill="x", padx=20, pady=(8, 0))
        ctk.CTkLabel(tt_opts, text="TikTok:").pack(side="left")
        ctk.CTkRadioButton(
            tt_opts, text="Inbox-luonnos (suositus)", variable=self.tiktok_mode, value="inbox"
        ).pack(side="left", padx=(8, 0))
        ctk.CTkRadioButton(
            tt_opts, text="Suora julkaisu", variable=self.tiktok_mode, value="direct"
        ).pack(side="left", padx=(8, 0))

        pub_btns = ctk.CTkFrame(root, fg_color="transparent")
        pub_btns.pack(fill="x", padx=20, pady=(12, 24))
        self.yt_publish_btn = ctk.CTkButton(
            pub_btns, text="Julkaise YouTube Shorts", height=40, command=self._publish_youtube
        )
        self.yt_publish_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.tt_publish_btn = ctk.CTkButton(
            pub_btns, text="Julkaise TikTok", height=40, command=self._publish_tiktok
        )
        self.tt_publish_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # Window-level drop
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self._on_window_drop)

    def _make_drop_zone(
        self,
        parent,
        *,
        hint: str,
        path_var: ctk.StringVar,
        on_click: Callable[[], None],
        on_drop: Callable[[object], None],
    ) -> ctk.CTkFrame:
        zone = ctk.CTkFrame(parent, corner_radius=10, border_width=2, height=72)
        zone.pack_propagate(False)

        hint_label = ctk.CTkLabel(zone, text=hint, text_color=("gray40", "gray65"))
        hint_label.pack(padx=12, pady=(10, 2), anchor="w")

        path_label = ctk.CTkLabel(zone, textvariable=path_var, anchor="w", wraplength=640)
        path_label.pack(padx=12, pady=(0, 10), fill="x")

        for widget in (zone, hint_label, path_label):
            widget.bind("<Button-1>", lambda _e, cb=on_click: cb())
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", on_drop)
            widget.dnd_bind("<<DragEnter>>", lambda _e, z=zone: z.configure(border_color="#3B8ED0"))
            widget.dnd_bind(
                "<<DragLeave>>",
                lambda _e, z=zone: z.configure(border_color=("gray70", "gray35")),
            )

        zone.configure(border_color=("gray70", "gray35"))
        return zone

    def _section(self, parent, title: str) -> None:
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=14, weight="bold")).pack(
            padx=20, pady=(14, 0), anchor="w"
        )

    def _show_youtube_help(self) -> None:
        messagebox.showinfo("YouTube-ohje", youtube_publish.missing_config_message())

    def _show_tiktok_help(self) -> None:
        messagebox.showinfo("TikTok-ohje", tiktok_publish.setup_help())

    def _refresh_connection_status(self) -> None:
        if youtube_publish.is_connected():
            self.yt_status.set("YouTube: yhdistetty ✓")
        elif youtube_publish.is_configured():
            self.yt_status.set("YouTube: avaimet OK — paina Yhdistä YouTube (selain aukeaa)")
        else:
            self.yt_status.set("YouTube: ei asetettu — lisää Client ID + Secret")

        if tiktok_publish.is_connected():
            self.tt_status.set("TikTok: yhdistetty ✓")
        elif tiktok_publish.is_configured():
            self.tt_status.set("TikTok: avaimet OK — paina Yhdistä TikTok (selain aukeaa)")
        else:
            self.tt_status.set("TikTok: ei asetettu — lisää Client Key + Secret")

    def _save_youtube_creds(self) -> None:
        cid = self.yt_client_id.get().strip()
        csec = self.yt_client_secret.get().strip()
        if not cid or not csec:
            messagebox.showwarning(
                "Puuttuu",
                "Liitä Client ID ja Client Secret.\n\n"
                "Ne löytyvät Google Cloud → Credentials → OAuth 2.0 Client IDs\n"
                "kun olet luonut Desktop-sovelluksen.",
            )
            return
        try:
            path = youtube_publish.save_client_secrets_from_fields(cid, csec)
        except ValueError as exc:
            messagebox.showerror("YouTube", str(exc))
            return
        self.yt_client_secrets.set(str(path))
        self._refresh_connection_status()
        self.status.set("YouTube-avaimet tallennettu.")
        messagebox.showinfo(
            "Tallennettu",
            "YouTube-avaimet OK.\n\nSeuraavaksi paina: Yhdistä YouTube\n"
            "(selain aukeaa Google-kirjautumiseen).",
        )

    def _pick_yt_secrets(self) -> None:
        path = filedialog.askopenfilename(
            title="Valitse Google client_secrets.json / lataamasi JSON",
            filetypes=[("JSON", "*.json"), ("Kaikki", "*.*")],
        )
        if not path:
            return
        self.yt_client_secrets.set(path)
        update_settings(youtube_client_secrets=path)
        self._refresh_connection_status()
        self.status.set("YouTube JSON tallennettu.")
        messagebox.showinfo("Tallennettu", "JSON OK. Paina seuraavaksi: Yhdistä YouTube")

    def _save_tiktok_creds(self) -> None:
        key = self.tiktok_key.get().strip()
        secret = self.tiktok_secret.get().strip()
        if not key or not secret:
            messagebox.showwarning(
                "Puuttuu",
                "Liitä TikTok Client Key ja Client Secret.\n\n"
                "developers.tiktok.com → Apps → oma app.",
            )
            return
        update_settings(
            tiktok_client_key=key,
            tiktok_client_secret=secret,
            tiktok_redirect_uri="http://127.0.0.1:8765/callback",
        )
        self._refresh_connection_status()
        self.status.set("TikTok-credentials tallennettu.")
        messagebox.showinfo(
            "Tallennettu",
            "TikTok-avaimet OK.\n\nSeuraavaksi paina: Yhdistä TikTok",
        )

    def _connect_youtube(self) -> None:
        if self._connect_busy:
            messagebox.showinfo("Odota", "Yhdistäminen on jo käynnissä…")
            return

        # Prefer typed fields if present
        if self.yt_client_id.get().strip() and self.yt_client_secret.get().strip():
            try:
                path = youtube_publish.save_client_secrets_from_fields(
                    self.yt_client_id.get(), self.yt_client_secret.get()
                )
                self.yt_client_secrets.set(str(path))
            except ValueError as exc:
                messagebox.showerror("YouTube", str(exc))
                return
        elif self.yt_client_secrets.get().strip():
            update_settings(youtube_client_secrets=self.yt_client_secrets.get().strip())

        if not youtube_publish.is_configured():
            self._show_youtube_help()
            if messagebox.askyesno("YouTube", "Avaa Google Credentials -sivu selaimeen?"):
                webbrowser.open(youtube_publish.HELP_URL)
            return

        self._connect_busy = True
        self.yt_connect_btn.configure(state="disabled", text="Yhdistetään…")
        self.status.set("Selain aukeaa — kirjaudu Google/YouTube-tilille…")
        messagebox.showinfo(
            "YouTube",
            "Selain aukeaa seuraavaksi.\n\n"
            "1) Kirjaudu Google-tilille\n"
            "2) Hyväksy ClipMaker / YouTube-oikeudet\n"
            "3) Palaa tähän kun valmis",
        )

        def work() -> None:
            try:
                msg = youtube_publish.connect()
                self.after(0, lambda: self._connect_done("youtube", True, msg))
            except Exception as exc:  # noqa: BLE001
                err = f"{exc}"
                self.after(0, lambda: self._connect_done("youtube", False, err))

        threading.Thread(target=work, daemon=True).start()

    def _connect_tiktok(self) -> None:
        if self._connect_busy:
            messagebox.showinfo("Odota", "Yhdistäminen on jo käynnissä…")
            return

        key = self.tiktok_key.get().strip()
        secret = self.tiktok_secret.get().strip()
        if not key or not secret:
            self._show_tiktok_help()
            if messagebox.askyesno("TikTok", "Avaa TikTok Developers selaimeen?"):
                webbrowser.open("https://developers.tiktok.com/apps")
            return

        update_settings(
            tiktok_client_key=key,
            tiktok_client_secret=secret,
            tiktok_redirect_uri="http://127.0.0.1:8765/callback",
        )

        self._connect_busy = True
        self.tt_connect_btn.configure(state="disabled", text="Yhdistetään…")
        self.status.set("Selain aukeaa — kirjaudu TikTokiin…")
        messagebox.showinfo(
            "TikTok",
            "Selain aukeaa seuraavaksi.\n\n"
            "1) Kirjaudu TikTokiin\n"
            "2) Hyväksy oikeudet\n"
            "3) Jos sivu ei palaa ClipMakeriin:\n"
            "   kopioi osoitepalkin URL ja paina\n"
            "   'Liitä callback-URL'\n\n"
            "Redirect URI appissa:\n"
            "http://127.0.0.1:8765/callback",
        )

        def work() -> None:
            try:
                msg = tiktok_publish.connect(timeout_sec=120)
                self.after(0, lambda: self._connect_done("tiktok", True, msg))
            except Exception as exc:  # noqa: BLE001
                err = f"{exc}"
                self.after(0, lambda: self._connect_done("tiktok", False, err))

        threading.Thread(target=work, daemon=True).start()

    def _finish_tiktok_callback(self) -> None:
        url = self.tt_callback_url.get().strip()
        if not url:
            messagebox.showwarning(
                "Puuttuu",
                "Liitä ensin callback-URL.\n\n"
                "Se näyttää tältä:\n"
                "http://127.0.0.1:8765/callback?code=...&state=...",
            )
            return
        try:
            msg = tiktok_publish.finish_from_redirect_url(url)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("TikTok", str(exc)[:2500])
            return
        self.tt_callback_url.set("")
        self._refresh_connection_status()
        self.status.set(msg)
        messagebox.showinfo("Yhdistetty", msg)

    def _connect_done(self, which: str, ok: bool, detail: str) -> None:
        self._connect_busy = False
        self.yt_connect_btn.configure(state="normal", text="Yhdistä YouTube")
        self.tt_connect_btn.configure(state="normal", text="Yhdistä TikTok")
        self._refresh_connection_status()
        if ok:
            self.status.set(detail)
            messagebox.showinfo("Yhdistetty", detail)
        else:
            self.status.set(f"{which}-yhteys epäonnistui.")
            messagebox.showerror("Yhteys epäonnistui", detail[:2500])

    def _disconnect_youtube(self) -> None:
        youtube_publish.disconnect()
        self._refresh_connection_status()
        self.status.set("YouTube-yhteys katkaistu.")

    def _disconnect_tiktok(self) -> None:
        tiktok_publish.disconnect()
        self._refresh_connection_status()
        self.status.set("TikTok-yhteys katkaistu.")

    def _publish_video_path(self) -> str | None:
        path = self._last_export or self.output_path.get().strip()
        if not path or not Path(path).is_file():
            messagebox.showwarning("Puuttuu", "Luo ensin video (Luo video) ennen julkaisua.")
            return None
        return path

    def _publish_youtube(self) -> None:
        video = self._publish_video_path()
        if not video or self._busy:
            return
        title = self.publish_title.get().strip() or Path(video).stem
        desc = self.publish_desc.get().strip()
        privacy = self.yt_privacy.get()

        self._busy = True
        self.yt_publish_btn.configure(state="disabled", text="Lähetetään…")
        self.progress.set(0)
        self.status.set("Julkaistaan YouTube Shortsia…")

        def work() -> None:
            try:
                result = youtube_publish.upload_short(
                    video,
                    title=title,
                    description=desc,
                    privacy_status=privacy,
                    on_progress=lambda p: self.after(0, lambda: self.progress.set(p)),
                )
                self.after(0, lambda: self._publish_done("youtube", True, result))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._publish_done("youtube", False, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _publish_tiktok(self) -> None:
        video = self._publish_video_path()
        if not video or self._busy:
            return
        title = self.publish_title.get().strip() or Path(video).stem
        direct = self.tiktok_mode.get() == "direct"

        self._busy = True
        self.tt_publish_btn.configure(state="disabled", text="Lähetetään…")
        self.progress.set(0)
        self.status.set("Julkaistaan TikTokiin…")

        def work() -> None:
            try:
                result = tiktok_publish.upload_video(
                    video,
                    title=title,
                    direct_post=direct,
                    privacy_level="SELF_ONLY",
                    on_progress=lambda p: self.after(0, lambda: self.progress.set(p)),
                )
                self.after(0, lambda: self._publish_done("tiktok", True, result))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._publish_done("tiktok", False, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _publish_done(self, which: str, ok: bool, result) -> None:
        self._busy = False
        self.yt_publish_btn.configure(state="normal", text="Julkaise YouTube Shorts")
        self.tt_publish_btn.configure(state="normal", text="Julkaise TikTok")
        if ok:
            self.progress.set(1)
            if which == "youtube":
                url = result.get("url") or ""
                self.status.set(f"YouTube Shorts valmis: {url}")
                if url and messagebox.askyesno("Valmis", f"Shorts ladattu.\n\n{url}\n\nAvaa selaimessa?"):
                    webbrowser.open(url)
            else:
                msg = result.get("message") or "TikTok-lähetys valmis."
                self.status.set(msg)
                messagebox.showinfo("TikTok", msg)
        else:
            self.progress.set(0)
            self.status.set("Julkaisu epäonnistui.")
            messagebox.showerror("Julkaisu", str(result)[:2000])

    def _parse_drop_paths(self, event_data: str) -> list[Path]:
        raw = self.tk.splitlist(event_data)
        paths: list[Path] = []
        for item in raw:
            text = str(item).strip().strip("{}")
            if text:
                paths.append(Path(text))
        return paths

    def _on_audio_drop(self, event) -> None:
        paths = self._parse_drop_paths(event.data)
        audio = next((p for p in paths if p.suffix.lower() in AUDIO_EXTS), None)
        if audio is None and paths:
            audio = paths[0]
        if audio is None:
            return
        if audio.suffix.lower() not in AUDIO_EXTS:
            messagebox.showwarning("Tiedostotyyppi", f"Tämä ei näytä musiikkitiedostolta:\n{audio.name}")
            return
        self._set_audio(str(audio))

    def _on_visual_drop(self, event) -> None:
        paths = self._parse_drop_paths(event.data)
        visual = next((p for p in paths if p.suffix.lower() in VISUAL_EXTS), None)
        if visual is None and paths:
            visual = paths[0]
        if visual is None:
            return
        if visual.suffix.lower() not in VISUAL_EXTS:
            messagebox.showwarning("Tiedostotyyppi", f"Tämä ei näytä kuvalta tai videolta:\n{visual.name}")
            return
        self._set_visual(str(visual))

    def _on_window_drop(self, event) -> None:
        paths = self._parse_drop_paths(event.data)
        if not paths:
            return
        audio = next((p for p in paths if p.suffix.lower() in AUDIO_EXTS), None)
        visual = next((p for p in paths if p.suffix.lower() in VISUAL_EXTS), None)
        if audio:
            self._set_audio(str(audio))
        if visual:
            self._set_visual(str(visual))
        if not audio and not visual:
            messagebox.showwarning("Tiedostotyyppi", "Pudota musiikkitiedosto ja/tai kuva/video.")

    def _set_audio(self, path: str) -> None:
        self.audio_path.set(path)
        self._audio_duration = probe_duration(path)
        if self._audio_duration > 0:
            self.audio_info.set(f"Pituus: {format_timestamp(self._audio_duration)}")
            self.start_slider.configure(to=max(0.1, self._audio_duration))
            self.start_slider.set(0)
            self.start_text.set("0:00")
        else:
            self.audio_info.set("Pituutta ei saatu luettua — voit silti yrittää.")
        if not self.output_path.get():
            desktop = Path.home() / "Desktop"
            if not desktop.exists():
                desktop = Path.home() / "Työpöytä"
            if not desktop.exists():
                desktop = Path.home()
            name = default_output_name(path, self.preset_key.get())
            self.output_path.set(str(desktop / name))
        if not self.publish_title.get().strip():
            self.publish_title.set(Path(path).stem)
        self.status.set("Musiikki valittu.")
        self._maybe_auto_find()

    def _set_visual(self, path: str) -> None:
        self.visual_path.set(path)
        self.status.set("Visuaali valittu.")

    def _pick_audio(self) -> None:
        path = filedialog.askopenfilename(title="Valitse musiikki", filetypes=AUDIO_TYPES)
        if path:
            self._set_audio(path)

    def _on_auto_best_toggle(self) -> None:
        if self.auto_best.get():
            self._maybe_auto_find()

    def _maybe_auto_find(self) -> None:
        if self.auto_best.get() and self.audio_path.get().strip():
            self._find_best_start()

    def _find_best_start(self) -> None:
        audio = self.audio_path.get().strip()
        if not audio:
            messagebox.showwarning("Puuttuu", "Valitse ensin musiikkitiedosto.")
            return
        if self._analyze_busy:
            return

        duration = float(self.duration.get())
        self._analyze_busy = True
        self.find_btn.configure(state="disabled", text="Analysoidaan…")
        self.status.set("Etsitään parasta kohtaa…")

        def work() -> None:
            try:
                suggestion = find_best_clip_start(
                    audio,
                    duration,
                    total_duration=self._audio_duration or None,
                )
                self.after(0, lambda: self._apply_best_start(suggestion))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._analyze_failed(str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _apply_best_start(self, suggestion) -> None:
        self._analyze_busy = False
        self.find_btn.configure(state="normal", text="Etsi paras kohta")
        self.start_slider.set(suggestion.start_sec)
        self.start_text.set(format_timestamp(suggestion.start_sec))
        self.status.set(
            f"Paras kohta: {format_timestamp(suggestion.start_sec)} "
            f"({int(self.duration.get())} s clip)"
        )

    def _analyze_failed(self, detail: str) -> None:
        self._analyze_busy = False
        self.find_btn.configure(state="normal", text="Etsi paras kohta")
        self.status.set("Automaattinen haku epäonnistui — valitse kohta käsin.")

    def _on_close(self) -> None:
        self._cancel_preview_cleanup()
        self._preview.stop()
        self.destroy()

    def _cancel_preview_cleanup(self) -> None:
        if self._preview_cleanup_job is not None:
            try:
                self.after_cancel(self._preview_cleanup_job)
            except ValueError:
                pass
            self._preview_cleanup_job = None

    def _toggle_preview(self) -> None:
        if self._preview.playing:
            self._stop_preview()
            return
        self._start_preview()

    def _stop_preview(self) -> None:
        self._cancel_preview_cleanup()
        self._preview.stop()
        self._preview_busy = False
        self.preview_btn.configure(state="normal", text="Esikuuntele")
        if not self._busy:
            self.status.set("Esikuuntelu pysäytetty.")

    def _start_preview(self) -> None:
        audio = self.audio_path.get().strip()
        if not audio:
            messagebox.showwarning("Puuttuu", "Valitse ensin musiikkitiedosto.")
            return
        if self._preview_busy:
            return
        try:
            start = parse_timestamp(self.start_text.get())
        except ValueError:
            messagebox.showerror("Virhe", "Aloitusajan muoto on väärä. Käytä esim. 0:45 tai 45.")
            return

        duration = float(self.duration.get())
        fade = 0.5 if self.fade_enabled.get() else 0.0
        self._preview_busy = True
        self.preview_btn.configure(state="disabled", text="Valmistellaan…")
        self.status.set("Valmistellaan esikuuntelua…")

        def work() -> None:
            try:
                played = self._preview.play(audio, start, duration, fade_sec=fade)
                self.after(0, lambda: self._preview_started(played, start))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._preview_failed(str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _preview_started(self, played_sec: float, start_sec: float) -> None:
        self._preview_busy = False
        self.preview_btn.configure(state="normal", text="Pysäytä")
        self.status.set(
            f"Soittaa: {format_timestamp(start_sec)} → {format_timestamp(start_sec + played_sec)}"
        )
        self._cancel_preview_cleanup()
        ms = int(played_sec * 1000) + 400
        self._preview_cleanup_job = self.after(ms, self._preview_finished)

    def _preview_finished(self) -> None:
        self._preview_cleanup_job = None
        if not self._preview.playing:
            return
        self._preview.stop()
        self.preview_btn.configure(text="Esikuuntele")
        if not self._busy:
            self.status.set("Esikuuntelu valmis.")

    def _preview_failed(self, detail: str) -> None:
        self._preview_busy = False
        self.preview_btn.configure(state="normal", text="Esikuuntele")
        self.status.set("Esikuuntelu epäonnistui.")
        messagebox.showerror("Esikuuntelu", detail[:1500])

    def _pick_visual(self) -> None:
        path = filedialog.askopenfilename(title="Valitse kuva tai video", filetypes=VISUAL_TYPES)
        if path:
            self._set_visual(path)

    def _pick_output(self) -> None:
        initial = self.output_path.get() or "clip.mp4"
        path = filedialog.asksaveasfilename(
            title="Tallenna video",
            defaultextension=".mp4",
            initialfile=Path(initial).name,
            filetypes=[("MP4-video", "*.mp4")],
        )
        if path:
            self.output_path.set(path)

    def _on_duration(self, value: float) -> None:
        seconds = round(float(value))
        self.duration.set(seconds)
        self.duration_label.configure(text=f"Kesto: {seconds} s")

    def _on_start_slide(self, value: float) -> None:
        self.start_text.set(format_timestamp(float(value)))

    def _sync_start_slider(self) -> None:
        try:
            sec = parse_timestamp(self.start_text.get())
        except ValueError:
            return
        if self._audio_duration > 0:
            sec = min(sec, max(0.0, self._audio_duration - 1))
        self.start_slider.set(sec)
        self.start_text.set(format_timestamp(sec))

    def _export(self) -> None:
        if self._busy:
            return
        self._stop_preview()
        audio = self.audio_path.get().strip()
        visual = self.visual_path.get().strip()
        output = self.output_path.get().strip()
        if not audio:
            messagebox.showwarning("Puuttuu", "Valitse ensin musiikkitiedosto.")
            return
        if not visual:
            messagebox.showwarning("Puuttuu", "Valitse kuva tai video.")
            return
        if not output:
            messagebox.showwarning("Puuttuu", "Valitse tallennussijainti.")
            return
        try:
            start = parse_timestamp(self.start_text.get())
        except ValueError:
            messagebox.showerror("Virhe", "Aloitusajan muoto on väärä. Käytä esim. 0:45 tai 45.")
            return

        duration = float(self.duration.get())
        preset = PRESETS[self.preset_key.get()]
        fade = 0.5 if self.fade_enabled.get() else 0.0

        out_path = Path(output)
        if out_path.suffix.lower() != ".mp4":
            out_path = out_path.with_suffix(".mp4")
            self.output_path.set(str(out_path))

        self._busy = True
        self.export_btn.configure(state="disabled", text="Luodaan…")
        self.progress.set(0)
        self.status.set("Renderöidään…")

        def work() -> None:
            try:
                export_clip(
                    audio_path=audio,
                    visual_path=visual,
                    output_path=str(out_path),
                    start_sec=start,
                    duration_sec=duration,
                    preset=preset,
                    fade_sec=fade,
                    on_progress=lambda p: self.after(0, lambda: self.progress.set(p)),
                )
                self.after(0, lambda: self._done(True, str(out_path)))
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc()
                self.after(0, lambda: self._done(False, f"{exc}\n\n{tb}"))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, ok: bool, detail: str) -> None:
        self._busy = False
        self.export_btn.configure(state="normal", text="Luo video")
        if ok:
            self.progress.set(1)
            self._last_export = detail
            self.status.set(f"Valmis: {detail}")
            if not self.publish_title.get().strip():
                self.publish_title.set(Path(detail).stem)
            messagebox.showinfo(
                "Valmis",
                f"Video tallennettu:\n{detail}\n\nVoit nyt julkaista sen YouTube Shortsina tai TikTokiin.",
            )
        else:
            self.progress.set(0)
            self.status.set("Virhe renderöinnissä.")
            messagebox.showerror("Virhe", detail[:2000])


def main() -> None:
    app = ClipMakerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
