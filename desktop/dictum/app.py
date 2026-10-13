"""Verbindet alle Bausteine zur fertigen App.

Wer läuft in welchem Thread?

    Hauptthread ......... Overlay (tkinter muss im Hauptthread laufen)
    pynput-Thread ....... hört auf die Tastatur → ruft _start/_stop/_cancel auf
    pystray-Thread ...... Tray-Symbol und Menü
    Lade-Thread ......... lädt einmalig das Whisper-Modell
    Worker-Thread ....... transkribiert und fügt ein – eins nach dem anderen

Warum ein eigener Worker? Transkribieren dauert 1–3 Sekunden. Würde das im
Tastatur-Thread passieren, wäre die Tastatur in dieser Zeit blockiert. Stattdessen
legen wir das Audio in eine Warteschlange und der Worker arbeitet sie ab.
"""

from __future__ import annotations

import logging
import queue
import threading
import winsound

import numpy as np

from .audio import Recorder
from .config import Settings
from .hotkey import HotkeyListener, HotkeyStateMachine
from .inserter import insert_text
from .overlay import Overlay
from .transcriber import Transcriber
from .tray import Tray

log = logging.getLogger(__name__)

KEY_LABELS = {"ctrl": "Strg", "win": "Win", "alt": "Alt", "shift": "Umschalt"}


class DictumApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.recorder = Recorder()
        self.transcriber = Transcriber(
            settings.transcription.model,
            settings.transcription.language,
            settings.transcription.fallback_language,
        )
        self.overlay = Overlay()
        self.machine = HotkeyStateMachine(
            on_start=self._start,
            on_stop=self._stop,
            on_cancel=self._cancel,
            mode=settings.hotkey.mode,
            hold_threshold=settings.hotkey.hold_threshold,
        )
        self.listener = HotkeyListener(settings.hotkey.keys, self.machine)
        hotkey_label = "+".join(KEY_LABELS[k] for k in settings.hotkey.keys)
        self.tray = Tray(
            hotkey_label,
            get_mode=lambda: self.machine.mode,
            set_mode=self._set_mode,
            get_language=lambda: self.transcriber.language,
            set_language=self._set_language,
            on_quit=self.quit,
        )
        self._jobs: queue.Queue[np.ndarray | None] = queue.Queue()

    def run(self) -> None:
        threading.Thread(target=self._load_model, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        self.listener.start()
        self.tray.start()
        log.info("Dictum läuft. Hotkey halten oder antippen zum Diktieren.")
        self.overlay.run()  # blockiert bis zum Beenden

    def quit(self) -> None:
        log.info("Beende Dictum …")
        self.listener.stop()
        self._jobs.put(None)  # Signal an den Worker: aufhören
        self.tray.stop()
        self.overlay.quit()

    # --- Hotkey-Ereignisse (laufen im pynput-Thread, müssen schnell sein) ------------

    def _start(self) -> None:
        try:
            self.recorder.start()
        except Exception:
            log.exception("Mikrofon konnte nicht geöffnet werden")
            self.overlay.flash("Kein Mikrofon gefunden")
            return
        self._beep(880)
        self.overlay.show("listening")

    def _stop(self) -> None:
        audio = self.recorder.stop()
        self._beep(660)
        self.overlay.show("transcribing" if self.transcriber.is_ready else "loading")
        self._jobs.put(audio)

    def _cancel(self) -> None:
        self.recorder.stop()
        self.overlay.hide()
        log.debug("Aufnahme verworfen (andere Tastenkombination)")

    def _set_mode(self, mode: str) -> None:
        self.machine.mode = mode
        log.info("Modus: %s", mode)

    def _set_language(self, language: str) -> None:
        self.transcriber.language = language
        log.info("Sprache: %s", language)

    # --- Hintergrund-Threads ---------------------------------------------------------

    def _load_model(self) -> None:
        try:
            self.transcriber.load()
        except Exception:
            log.exception("Whisper-Modell konnte nicht geladen werden")
            self.overlay.flash("Modell-Fehler – siehe Konsole", seconds=5)

    def _worker(self) -> None:
        while True:
            audio = self._jobs.get()
            if audio is None:
                return
            try:
                text = self.transcriber.transcribe(audio)
                if text:
                    self.overlay.hide()
                    insert_text(text)
                else:
                    self.overlay.flash("Nichts erkannt")
            except Exception:
                log.exception("Fehler beim Transkribieren")
                self.overlay.flash("Fehler – siehe Konsole")

    def _beep(self, frequency: int) -> None:
        if self.settings.feedback.sounds:
            # Beep blockiert für die Tondauer → in eigenem Thread
            threading.Thread(target=winsound.Beep, args=(frequency, 60), daemon=True).start()
