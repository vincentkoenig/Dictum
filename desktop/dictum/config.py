"""Lädt die Einstellungen aus settings.toml.

Warum TOML? Das Format ist gut lesbar, erlaubt Kommentare und Python bringt seit
Version 3.11 mit `tomllib` einen Leser dafür mit – keine zusätzliche Bibliothek nötig.

Die Einstellungen landen in "dataclasses": einfachen Klassen, die nur Daten halten.
So bekommt der restliche Code `settings.hotkey.mode` statt `data["hotkey"]["mode"]`
und Tippfehler fallen sofort auf.
"""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .keys import check_hotkey

# Zwei Arten, Dictum zu starten:
#
# * **Aus dem Quellcode** (python -m dictum): Alles liegt im Projekt. settings.toml im Ordner desktop/,
#   die Schlüssel in .env im Projektordner.
# * **Als Programm** (Dictum.exe, gebaut mit PyInstaller): Das Programm liegt womöglich in einem
#   Ordner ohne Schreibrechte und wird bei Updates ersetzt. Deshalb liegen alle persönlichen Dateien
#   (Einstellungen, Wörterbuch, Verlauf, Logs, .env) in %APPDATA%\Dictum. Was mit dem Programm
#   ausgeliefert wird (Vorlagen, Symbol), steckt im Programmpaket (`RESOURCE_DIR`).
FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DESKTOP_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "Dictum"
    REPO_ROOT = DESKTOP_DIR
else:
    # settings.toml liegt im Ordner desktop/, also eine Ebene über diesem Paket
    DESKTOP_DIR = RESOURCE_DIR = Path(__file__).resolve().parent.parent
    REPO_ROOT = DESKTOP_DIR.parent
DEFAULT_PATH = DESKTOP_DIR / "settings.toml"


def ensure_user_dir() -> None:
    """Beim ersten Start des Programms den Datenordner anlegen und die Standard-Einstellungen hineinkopieren.
    Aus dem Quellcode gibt es nichts zu tun: Dort liegen die Dateien schon im Projekt."""
    if not FROZEN:
        return
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_PATH.exists():
        shutil.copy(RESOURCE_DIR / "settings.toml", DEFAULT_PATH)

VALID_MODES = {"both", "hold", "toggle"}
VALID_ENGINES = {"local", "openai"}
VALID_PROVIDERS = {"anthropic", "openai"}


@dataclass
class HotkeySettings:
    keys: list[str] = field(default_factory=lambda: ["ctrl_r"])
    mode: str = "both"
    hold_threshold: float = 0.4
    max_minutes: float = 20   # Aufnahmen enden nach so vielen Minuten von selbst (0 = unbegrenzt)
    # Zusatz-Tasten wie bei Wispr Flow (leere Liste = aus): letztes Diktat erneut einfügen / kopieren
    command: list[str] = field(default_factory=lambda: ["f9"])   # Command Mode, [] = aus
    paste_last: list[str] = field(default_factory=lambda: ["shift", "alt", "z"])
    copy_last: list[str] = field(default_factory=lambda: ["shift", "alt", "x"])


@dataclass
class TranscriptionSettings:
    engine: str = "local"
    openai_model: str = "gpt-4o-mini-transcribe"
    model: str = "small"
    language: str = "de"
    fallback_language: str = "de"
    whisper_mode: bool = True   # leise Sprache verstärken, Sprachfilter empfindlicher (siehe levels.py)


@dataclass
class CleanupSettings:
    enabled: bool = True
    provider: str = "anthropic"
    anthropic_model: str = "claude-haiku-5-5"
    openai_model: str = "gpt-5-mini"


@dataclass
class CloudSettings:
    url: str = ""
    publishable_key: str = ""


@dataclass
class MeetingSettings:
    include_system_audio: bool = True
    chunk_minutes: float = 5
    mic_gain: float = 1.0
    system_gain: float = 0.8
    sync_minutes: float = 15
    web_url: str = "https://vincentkoenig.github.io/Dictum/"


@dataclass
class HistorySettings:
    enabled: bool = True
    keep_days: int = 90


@dataclass
class DictionarySettings:
    auto_learn: bool = False    # Korrekturen im Textfeld erkennen und Wörter lernen (siehe learn.py)
    learn_delay: float = 10.0   # Sekunden nach dem Einfügen, bevor das Feld erneut gelesen wird


@dataclass
class StylesSettings:
    """Stil pro Kategorie (Auswahl siehe styles.py). `apps` ordnet einzelnen Programmen einen Stil zu."""

    personal_chat: str = "casual"
    work_chat: str = "neutral"
    email: str = "formal"
    other: str = "neutral"
    apps: dict[str, str] = field(default_factory=dict)


@dataclass
class ContextSettings:
    """Was Dictum der KI zusätzlich über die Umgebung verrät (nur für die Bereinigung per Cloud-KI)."""

    window_title: bool = True   # Fenstertitel, z. B. "Re: Angebot Müller GmbH"
    field_text: bool = False    # Text im Eingabefeld rund um die Schreibstelle


@dataclass
class FeedbackSettings:
    sounds: bool = False        # Töne bei Start und Ende der Aufnahme (Standard: aus)
    sound_volume: int = 20      # Lautstärke in Prozent, wenn Töne an sind


@dataclass
class UiSettings:
    flow_bar: bool = True       # dauerhaft sichtbare Blase unten in der Bildschirmmitte
    theme: str = "system"       # "system" (wie Windows), "light" oder "dark"


@dataclass
class Settings:
    hotkey: HotkeySettings = field(default_factory=HotkeySettings)
    transcription: TranscriptionSettings = field(default_factory=TranscriptionSettings)
    cleanup: CleanupSettings = field(default_factory=CleanupSettings)
    cloud: CloudSettings = field(default_factory=CloudSettings)
    meeting: MeetingSettings = field(default_factory=MeetingSettings)
    history: HistorySettings = field(default_factory=HistorySettings)
    dictionary: DictionarySettings = field(default_factory=DictionarySettings)
    styles: StylesSettings = field(default_factory=StylesSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    feedback: FeedbackSettings = field(default_factory=FeedbackSettings)
    ui: UiSettings = field(default_factory=UiSettings)


def load_settings(path: Path = DEFAULT_PATH) -> Settings:
    """Liest die Datei. Fehlt sie oder ein Eintrag, gelten die Standardwerte oben."""
    data: dict = {}
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)

    settings = Settings(
        hotkey=HotkeySettings(**data.get("hotkey", {})),
        transcription=TranscriptionSettings(**data.get("transcription", {})),
        cleanup=CleanupSettings(**data.get("cleanup", {})),
        cloud=CloudSettings(**data.get("cloud", {})),
        meeting=MeetingSettings(**data.get("meeting", {})),
        history=HistorySettings(**data.get("history", {})),
        dictionary=DictionarySettings(**data.get("dictionary", {})),
        styles=StylesSettings(**data.get("styles", {})),
        context=ContextSettings(**data.get("context", {})),
        feedback=FeedbackSettings(**data.get("feedback", {})),
        ui=UiSettings(**data.get("ui", {})),
    )
    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    """Prüft früh auf ungültige Werte – lieber eine klare Fehlermeldung beim Start
    als ein rätselhafter Fehler mitten im Diktat."""
    hk = settings.hotkey
    for name, keys, optional in (("keys", hk.keys, False), ("command", hk.command, True),
                                 ("paste_last", hk.paste_last, True), ("copy_last", hk.copy_last, True)):
        problem = check_hotkey(keys, allow_empty=optional)
        if problem:
            raise ValueError(f"hotkey.{name}: {problem}")
    chosen = [set(k) for k in (hk.keys, hk.command, hk.paste_last, hk.copy_last) if k]
    for index, first in enumerate(chosen):
        for second in chosen[index + 1:]:
            if first <= second or second <= first:
                # Gleiche oder ineinander enthaltene Kombinationen (z. B. Strg rechts und Strg rechts + F9)
                # lösen sich gegenseitig aus: Beim Drücken von Strg würde schon das Diktat starten
                raise ValueError("Keine Tastenkombination darf in einer anderen enthalten sein.")
    if hk.mode not in VALID_MODES:
        raise ValueError(f"Ungültiger Modus '{hk.mode}'. Erlaubt: {VALID_MODES}")
    from .styles import STYLES  # erst hier: styles.py importiert context.py (Windows-Bibliotheken)

    st = settings.styles
    for name in ("personal_chat", "work_chat", "email", "other"):
        if getattr(st, name) not in STYLES:
            raise ValueError(f"Ungültiger Stil '{getattr(st, name)}' bei styles.{name}. Erlaubt: {set(STYLES)}")
    st.apps = {exe.lower(): style for exe, style in st.apps.items()}
    for exe, style in st.apps.items():
        if style not in STYLES:
            raise ValueError(f"Ungültiger Stil '{style}' für {exe}. Erlaubt: {set(STYLES)}")
    if settings.ui.theme not in ("system", "light", "dark"):
        raise ValueError(f"Ungültiges Design '{settings.ui.theme}'. Erlaubt: system, light, dark")
    if not 0 <= settings.feedback.sound_volume <= 100:
        raise ValueError("feedback.sound_volume muss zwischen 0 und 100 liegen.")
    if settings.dictionary.learn_delay < 1:
        raise ValueError("dictionary.learn_delay muss mindestens 1 Sekunde sein.")
    if hk.max_minutes < 0:
        raise ValueError("hotkey.max_minutes darf nicht negativ sein (0 = unbegrenzt).")
    if hk.hold_threshold <= 0:
        raise ValueError("hold_threshold muss größer als 0 sein.")
    if settings.transcription.engine not in VALID_ENGINES:
        raise ValueError(f"Ungültige engine '{settings.transcription.engine}'. Erlaubt: {VALID_ENGINES}")
    if settings.cleanup.provider not in VALID_PROVIDERS:
        raise ValueError(f"Ungültiger provider '{settings.cleanup.provider}'. Erlaubt: {VALID_PROVIDERS}")


def load_env(override: bool = False) -> None:
    """Lädt API-Keys aus der .env im Projektordner in die Umgebungsvariablen.

    Die SDKs von Anthropic und OpenAI lesen ANTHROPIC_API_KEY bzw. OPENAI_API_KEY
    automatisch aus der Umgebung – wir müssen die Keys also nie selbst im Code anfassen.
    Bereits gesetzte Umgebungsvariablen haben Vorrang (override=False). Mit override=True
    gewinnt die Datei – so übernimmt Dictum einen frisch eingetragenen Key ohne Neustart.
    """
    load_dotenv(REPO_ROOT / ".env", override=override)
