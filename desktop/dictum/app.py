"""Verbindet alle Bausteine zur fertigen App.

Wer läuft in welchem Thread?

    Hauptthread ......... Qt: Overlay, Tray-Symbol, Fenster (Qt verlangt den Hauptthread)
    pynput-Thread ....... hört auf die Tastatur → ruft _start/_stop/_cancel auf
    Lade-Thread ......... lädt einmalig das lokale Whisper-Modell
    Worker-Thread ....... transkribiert, bereinigt und fügt ein – eins nach dem anderen
    Meeting-Thread ...... Upload der Meeting-Aufnahmen (siehe meeting_controller.py)

Warum ein eigener Worker? Transkribieren + Bereinigen dauert 1–4 Sekunden. Würde das
im Tastatur-Thread passieren, wäre die Tastatur in dieser Zeit blockiert. Stattdessen
legen wir das Audio in eine Warteschlange und der Worker arbeitet sie ab.

Die Threads reden nie direkt mit Qt-Objekten, sondern über deren thread-sichere Methoden
(Overlay.show, Tray.notify …), die intern Signale senden (siehe gui/__init__.py).

Der Weg eines Diktats im Worker (`_process`):

    Audio ─► Spracherkennung (lokal oder OpenAI) ─► Rohtext
          ─► Snippet? ── ja ─► Snippet-Text einfügen
                     └─ nein ─► KI-Bereinigung (wenn an) ─► Text einfügen ─► Verlauf
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import time
import winsound

import numpy as np
import pyperclip
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from . import autostart, commands, context, costs, learn, levels, shortcuts, styles
from .audio import Recorder, duration_seconds
from .cleanup import clean_text
from .cloud_transcriber import OpenAITranscriber
from .config import REPO_ROOT, Settings, load_env
from .gui.icons import mic_icon
from .gui.overlay import Overlay
from .gui.tray import Tray
from .gui.window import MainWindow
from .history import History
from .hotkey import HotkeyListener, HotkeyStateMachine, hotkey_label
from .inserter import copy_selection, insert_text
from .llm import LLMError, create_provider
from .logsetup import LOG_PATH
from .meeting_controller import MeetingController
from .transcriber import LocalTranscriber
from .vocabulary import (
    DICTIONARY_PATH,
    SNIPPETS_PATH,
    add_terms,
    ensure_user_files,
    load_dictionary,
    load_snippets,
    match_snippet,
)

log = logging.getLogger(__name__)


class _Bus(QObject):
    """Signale, die aus jedem Thread gesendet werden dürfen, aber im Hauptthread ankommen."""

    quit_requested = Signal()
    show_window = Signal()


class DictumApp:
    def __init__(self, settings: Settings, show_window: bool = True) -> None:
        self.settings = settings
        self._show_window_on_start = show_window

        # QApplication muss existieren, bevor irgendein Fenster oder Tray-Symbol entsteht.
        # "QuitOnLastWindowClosed = False": Das Fenster zu schließen beendet Dictum NICHT,
        # es läuft im Infobereich weiter.
        self.qt = QApplication.instance() or QApplication(sys.argv[:1])
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setApplicationName("Dictum")
        self.qt.setWindowIcon(mic_icon())

        tr = settings.transcription
        self.recorder = Recorder()

        # Beide Spracherkennungen bereithalten: das lokale Modell dient auch als
        # Ersatz, falls die Cloud nicht erreichbar ist
        self.local = LocalTranscriber(tr.model, tr.language, tr.fallback_language)
        self.cloud = OpenAITranscriber(tr.openai_model, tr.language)
        self.engine = tr.engine
        self.whisper_mode = tr.whisper_mode
        self.local.sensitive = tr.whisper_mode
        self._limit_timer: threading.Timer | None = None  # beendet vergessene Aufnahmen

        self.cleanup_enabled = settings.cleanup.enabled
        self.provider = create_provider(settings.cleanup.provider, settings.cleanup)
        self.history = History()
        self.hotkey_text = hotkey_label(settings.hotkey.keys)

        self.overlay = Overlay()
        self.machine = HotkeyStateMachine(
            on_start=self._start,
            on_stop=self._stop,
            on_cancel=self._cancel,
            mode=settings.hotkey.mode,
            hold_threshold=settings.hotkey.hold_threshold,
        )
        self.listener = HotkeyListener(settings.hotkey.keys, self.machine)
        # Command Mode: eigene Zustandsmaschine mit denselben Regeln (Halten/Antippen, Esc)
        self.command_machine = HotkeyStateMachine(
            on_start=self._command_start,
            on_stop=self._command_stop,
            on_cancel=self._cancel,
            mode=settings.hotkey.mode,
            hold_threshold=settings.hotkey.hold_threshold,
        )
        self._command_mode = False  # läuft gerade eine Befehls-Aufnahme?
        self.listener.add_machine("command", settings.hotkey.command, self.command_machine)
        self._last_text = ""  # zuletzt eingefügter Text (für "erneut einfügen" / "kopieren")
        self._set_extra_hotkeys(settings.hotkey)
        # Meetings: braucht notify/refresh vom Tray – das Tray braucht die Meetings fürs
        # Menü. Deshalb über kleine Lambdas verbunden, die erst später aufgerufen werden.
        self.meetings = MeetingController(
            settings,
            notify=lambda title, text, click=None: self.tray.notify(title, text, click),
            on_change=self._refresh_tray,
        )
        self._bus = _Bus()
        self.tray = Tray(self, self.hotkey_text, open_window=self.show_window)
        self.window = MainWindow(self)
        self._bus.quit_requested.connect(self._do_quit)
        self._bus.show_window.connect(self.window.show_and_raise)
        self._jobs: queue.Queue[tuple[np.ndarray, context.ActiveWindow | None] | None] = queue.Queue()
        self._target: context.ActiveWindow | None = None  # Fenster, in das gerade diktiert wird
        self._stt_model: str | None = None                # Cloud-Modell des letzten Diktats (None = lokal)
        self._ticker: QTimer | None = None
        ensure_user_files()

    def run(self) -> int:
        threading.Thread(target=self._load_model, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        self.listener.start()
        self.tray.start()
        self.meetings.start_worker()
        removed = self.history.purge(self.settings.history.keep_days)
        if removed:
            log.info("Verlauf: %d alte Einträge gelöscht", removed)

        # Während eines Meetings jede Sekunde die Laufzeit im Tray aktualisieren
        self._ticker = QTimer()
        self._ticker.timeout.connect(self._tick)
        self._ticker.start(1000)

        if self._show_window_on_start:
            self.window.show_and_raise()
        log.info(
            "Dictum läuft. Spracherkennung: %s · KI-Bereinigung: %s (%s)",
            self.engine, "an" if self.cleanup_enabled else "aus", self.provider.name,
        )
        return self.qt.exec()  # blockiert bis qt.quit()

    def quit(self) -> None:
        """Aus jedem Thread aufrufbar: Das eigentliche Beenden läuft im Hauptthread."""
        self._bus.quit_requested.emit()

    def _do_quit(self) -> None:
        log.info("Beende Dictum …")
        # Laufendes Meeting sauber abschließen – der Upload passiert beim nächsten Start
        self.meetings.stop()
        self.listener.stop()
        self._jobs.put(None)  # Signal an den Worker: aufhören
        self.tray.stop()
        self.qt.quit()

    def show_window(self) -> None:
        self._bus.show_window.emit()

    def restart(self) -> None:
        """Startet Dictum neu (z. B. nach einer geänderten Taste). Die neue Instanz bekommt
        `--restart` und wartet, bis diese hier beendet ist und den Mutex freigibt."""
        command = [str(autostart.background_python()), *autostart.launch_args(), "--restart"]
        subprocess.Popen(
            command,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        log.info("Neustart angefordert")
        self.quit()

    # --- Einstellungen zur Laufzeit (Tray-Menü und Fenster) ---------------------------

    def get(self, setting: str):
        return {
            "mode": lambda: self.machine.mode,
            "language": lambda: self.local.language,
            "engine": lambda: self.engine,
            "cleanup": lambda: self.cleanup_enabled,
            "provider": lambda: self.provider.name,
            "autostart": autostart.is_enabled,
            "desktop_shortcut": lambda: shortcuts.is_present("desktop"),
            "start_menu_shortcut": lambda: shortcuts.is_present("start_menu"),
        }[setting]()

    def set(self, setting: str, value) -> None:
        if setting == "mode":
            self.machine.mode = self.command_machine.mode = value
        elif setting == "language":
            self.local.language = self.cloud.language = value
        elif setting == "engine":
            self.engine = value
        elif setting == "cleanup":
            self.cleanup_enabled = value
        elif setting == "provider":
            self.provider = create_provider(value, self.settings.cleanup)
        elif setting == "autostart":
            if bool(value) != autostart.is_enabled():
                autostart.set_enabled(bool(value))
        elif setting in ("desktop_shortcut", "start_menu_shortcut"):
            kind = "desktop" if setting == "desktop_shortcut" else "start_menu"
            if bool(value) != shortcuts.is_present(kind):
                (shortcuts.create if value else shortcuts.remove)(kind)
        log.info("Einstellung geändert: %s = %s", setting, value)

    def apply_settings(self, new: Settings) -> list[str]:
        """Übernimmt neu gespeicherte Einstellungen. Das meiste wirkt sofort. Was einen Neustart
        braucht (lokales Modell), wird als Liste zurückgegeben, damit das Fenster es sagen kann."""
        old = self.settings
        needs_restart = []
        if new.transcription.model != old.transcription.model:
            needs_restart.append("das lokale Modell")

        # Laufende Bausteine auf die neuen Werte stellen … Tasten wirken sofort, ohne Neustart
        self.listener.set_keys(new.hotkey.keys)
        self._set_extra_hotkeys(new.hotkey)
        self.hotkey_text = hotkey_label(new.hotkey.keys)
        self.tray.set_hotkey_label(self.hotkey_text)
        self.machine.mode = self.command_machine.mode = new.hotkey.mode
        self.machine.hold_threshold = self.command_machine.hold_threshold = new.hotkey.hold_threshold
        self.listener.add_machine("command", new.hotkey.command, self.command_machine)
        self.local.language = self.cloud.language = new.transcription.language
        self.local.fallback_language = new.transcription.fallback_language
        self.engine = new.transcription.engine
        self.whisper_mode = self.local.sensitive = new.transcription.whisper_mode
        self.cloud.model = new.transcription.openai_model
        self.cleanup_enabled = new.cleanup.enabled
        self.provider = create_provider(new.cleanup.provider, new.cleanup)
        # … und das gemeinsame Einstellungs-Objekt aktualisieren, aus dem u. a. der
        # MeetingController bei jedem Meeting liest. Es ist dasselbe Objekt wie bisher,
        # deshalb sehen alle Beteiligten die neuen Werte sofort.
        for section in ("hotkey", "transcription", "cleanup", "meeting", "history", "dictionary", "styles",
                        "context", "feedback"):
            setattr(old, section, getattr(new, section))
        log.info("Einstellungen übernommen (Neustart nötig für: %s)", ", ".join(needs_restart) or "nichts")
        return needs_restart

    def set_hotkeys_enabled(self, enabled: bool) -> None:
        self.listener.set_enabled(enabled)

    def _set_extra_hotkeys(self, hk) -> None:
        self.listener.set_trigger("paste_last", hk.paste_last, self.paste_last)
        self.listener.set_trigger("copy_last", hk.copy_last, self.copy_last)

    def last_text(self) -> str:
        """Das letzte Diktat: aus dem Speicher, sonst aus dem Verlauf (nach einem Neustart)."""
        if self._last_text:
            return self._last_text
        try:
            entries = self.history.recent(1)
        except Exception:
            return ""
        return entries[0].text if entries else ""

    def paste_last(self) -> None:
        """Hotkey: das letzte Diktat noch einmal einfügen (z. B. wenn das Feld es verschluckt hat)."""
        text = self.last_text()
        if not text:
            self.overlay.flash("Noch kein Diktat vorhanden")
            return
        # In einem eigenen Thread: Einfügen wartet kurz, und der Tastatur-Thread soll frei bleiben
        threading.Thread(target=insert_text, args=(text,), daemon=True).start()

    def copy_last(self) -> None:
        """Hotkey: das letzte Diktat nur in die Zwischenablage legen."""
        text = self.last_text()
        if not text:
            self.overlay.flash("Noch kein Diktat vorhanden")
            return
        pyperclip.copy(text)
        self.overlay.flash("Letztes Diktat kopiert")

    def open_env(self) -> None:
        """Die Schlüsseldatei im Editor öffnen. Die Keys trägt man selbst ein, Dictum fasst sie nie an."""
        path = REPO_ROOT / ".env"
        if not path.exists():
            path.write_text("ANTHROPIC_API_KEY=\nOPENAI_API_KEY=\n", encoding="utf-8")
        subprocess.Popen(["notepad.exe", str(path)])

    def reload_keys(self) -> dict[str, bool]:
        """Liest die .env neu ein und verwirft Verbindungen, die mit dem alten Key aufgebaut wurden."""
        load_env(override=True)
        self.cloud._client = None
        self.provider = create_provider(self.provider.name, self.settings.cleanup)
        log.info("Schlüssel neu geladen")
        return self.key_status()

    @staticmethod
    def key_status() -> dict[str, bool]:
        return {name: bool(os.environ.get(name)) for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}

    def open_dictionary(self) -> None:
        os.startfile(DICTIONARY_PATH)  # öffnet die Datei im Standard-Editor

    def open_log(self) -> None:
        os.startfile(LOG_PATH)

    def open_snippets(self) -> None:
        os.startfile(SNIPPETS_PATH)

    def _refresh_tray(self) -> None:
        self.tray.refresh(self.meetings.is_recording, self.meetings.elapsed)

    def _tick(self) -> None:
        if self.meetings.is_recording:
            self._refresh_tray()

    # --- Hotkey-Ereignisse (laufen im pynput-Thread, müssen schnell sein) ------------

    def _start(self) -> None:
        self._target = context.active_window()  # merken, bevor das Overlay oder ein Piepton stört
        try:
            self.recorder.start()
        except Exception:
            log.exception("Mikrofon konnte nicht geöffnet werden")
            self.overlay.flash("Kein Mikrofon gefunden")
            return
        self._beep(880)
        self.overlay.show("listening")
        self._arm_limit()

    def _arm_limit(self) -> None:
        """Eine vergessene Aufnahme (z. B. angetippt und dann weggegangen) soll nicht ewig laufen."""
        self._disarm_limit()
        minutes = self.settings.hotkey.max_minutes
        if minutes > 0:
            self._limit_timer = threading.Timer(minutes * 60, self._limit_reached)
            self._limit_timer.daemon = True
            self._limit_timer.start()

    def _disarm_limit(self) -> None:
        if self._limit_timer is not None:
            self._limit_timer.cancel()
            self._limit_timer = None

    def _limit_reached(self) -> None:
        log.info("Zeitlimit der Aufnahme erreicht – beende sie")
        self.overlay.flash("Zeitlimit erreicht – Aufnahme beendet", seconds=3)
        self.machine.finish()
        self.command_machine.finish()

    def _stop(self) -> None:
        self._disarm_limit()
        audio = self.recorder.stop()
        self._beep(660)
        ready = self.engine == "openai" or self.local.is_ready
        self.overlay.show("transcribing" if ready else "loading")
        self._jobs.put((audio, self._target, self._command_mode))
        self._command_mode = False

    def _command_start(self) -> None:
        """Command-Taste gedrückt: Es wird die Anweisung aufgenommen, nicht ein Diktat."""
        self._command_mode = True
        self._start()
        if self.recorder.is_recording:
            self.overlay.show("command")
        else:
            self._command_mode = False

    def _command_stop(self) -> None:
        self._stop()

    def _cancel(self) -> None:
        self._disarm_limit()
        self._command_mode = False
        self.recorder.stop()
        self.overlay.hide()
        log.debug("Aufnahme verworfen (andere Taste oder Esc)")

    # --- Hintergrund-Threads ---------------------------------------------------------

    def _load_model(self) -> None:
        try:
            self.local.load()
        except Exception:
            log.exception("Whisper-Modell konnte nicht geladen werden")
            self.overlay.flash("Modell-Fehler – siehe Logdatei", seconds=5)

    def _worker(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                self._process(*job)
            except Exception:
                log.exception("Fehler bei der Verarbeitung")
                self.overlay.flash("Fehler – siehe Logdatei")

    def _process(self, audio: np.ndarray, target: context.ActiveWindow | None = None,
                 command: bool = False) -> None:
        if command:
            self._process_command(audio, target)
            return
        # Wörterbuch und Snippets bei jedem Diktat frisch lesen – so wirken Änderungen
        # an den Dateien sofort, ohne Neustart (die Dateien sind winzig)
        dictionary = load_dictionary()
        snippets = load_snippets()

        t0 = time.perf_counter()
        raw = self._transcribe(audio, dictionary)
        t1 = time.perf_counter()
        if not raw:
            self.overlay.flash("Nichts erkannt")
            return

        snippet = match_snippet(raw, snippets)
        cleaned = False
        if snippet is not None:
            log.info("Snippet erkannt: %r", raw)
            text = snippet
        elif self.cleanup_enabled:
            self.overlay.show("polishing")
            style = styles.style_for(target, self.settings.styles)
            text = clean_text(raw, self.provider, dictionary, style, self._context_for(target))
            cleaned = True
        else:
            text = raw
        t2 = time.perf_counter()

        log.info("Fertig: Erkennung %.1f s · Bereinigung %.1f s → %r", t1 - t0, t2 - t1, text)
        self.overlay.hide()
        self._last_text = text
        insert_text(text)
        self._remember(raw, text, audio, cleaned, snippet is not None, target)
        self._learn_async(text, target)

    def _process_command(self, audio: np.ndarray, target: context.ActiveWindow | None) -> None:
        """Command Mode: Anweisung erkennen, markierten Text holen, KI anwenden, Ergebnis einfügen."""
        dictionary = load_dictionary()
        instruction = self._transcribe(audio, dictionary)
        if not instruction:
            self.overlay.flash("Keine Anweisung erkannt")
            return
        selection = copy_selection()
        self.overlay.show("command_working")
        try:
            result = commands.run_command(instruction, selection, self.provider, dictionary)
        except commands.CommandError as error:
            self.overlay.flash(str(error), seconds=3)
            return
        log.info("Command Mode: %r auf %d Zeichen → %d Zeichen", instruction, len(selection), len(result))
        self.overlay.hide()
        self._last_text = result
        insert_text(result)  # ersetzt die Markierung (oder landet an der Schreibstelle)
        self._remember(instruction, result, audio, True, False, target)

    def _learn_async(self, text: str, target: context.ActiveWindow | None) -> None:
        """Lern-Wörterbuch: ein paar Sekunden später prüfen, ob du ein Wort korrigiert hast."""
        if self.settings.dictionary.auto_learn and target is not None:
            threading.Thread(target=self._learn, args=(text, target), daemon=True).start()

    def _learn(self, text: str, target: context.ActiveWindow) -> None:
        try:
            def same_window() -> bool:
                now = context.active_window()
                return now is not None and now.exe == target.exe

            found = learn.learn_from_field(
                text, lambda: context.field_text(5000), same_window,
                load_dictionary(), self.settings.dictionary.learn_delay,
            )
            added = add_terms([new for _old, new in found])
            if added:
                log.info("Wörterbuch gelernt: %s", added)
                self.tray.notify("Dictum hat dazugelernt", "Neu im Wörterbuch: " + ", ".join(added))
        except Exception:
            log.exception("Lern-Wörterbuch fehlgeschlagen")

    def _context_for(self, target: context.ActiveWindow | None) -> str:
        """Was die KI über die Umgebung erfahren darf (siehe [context] in settings.toml)."""
        parts = []
        if self.settings.context.window_title and target and target.title:
            parts.append(f"Fenstertitel: {target.title}")
        if self.settings.context.field_text:
            text = context.field_text()
            if text.strip():
                parts.append(f"Text im Eingabefeld (Ausschnitt):\n{text}")
        return "\n".join(parts)

    def _remember(self, raw: str, text: str, audio: np.ndarray, cleaned: bool, snippet: bool,
                  target: context.ActiveWindow | None = None) -> None:
        """Eintrag im lokalen Verlauf – ein Fehler hier darf ein Diktat nie stören."""
        if not self.settings.history.enabled:
            return
        try:
            duration = duration_seconds(audio)
            cost = costs.estimate(
                stt_model=self._stt_model, duration=duration,
                cleanup_model=getattr(self.provider, "model", None) if cleaned else None,
                raw=raw, text=text,
            )
            self.history.add(raw, text, duration, self.engine, cleaned, snippet,
                             app=target.app if target else "", cost=cost)
        except Exception:
            log.exception("Verlauf konnte nicht gespeichert werden")

    def _transcribe(self, audio: np.ndarray, dictionary: list[str]) -> str:
        self.local.vocabulary = self.cloud.vocabulary = dictionary
        audio, gain = levels.boost_quiet(audio, self.whisper_mode)
        if gain > 1.5:
            log.info("Leise Sprache um den Faktor %.1f verstärkt (Flüstermodus)", gain)
        self._stt_model = None
        if self.engine == "openai":
            try:
                text = self.cloud.transcribe(audio)
                self._stt_model = self.cloud.model
                return text
            except LLMError as e:
                # Cloud nicht verfügbar → lokal weitermachen statt das Diktat zu verlieren
                log.warning("%s – nutze lokales Whisper", e)
                self.overlay.show("transcribing")
        return self.local.transcribe(audio)

    def _beep(self, frequency: int) -> None:
        if self.settings.feedback.sounds:
            # Beep blockiert für die Tondauer → in eigenem Thread
            threading.Thread(target=winsound.Beep, args=(frequency, 60), daemon=True).start()
