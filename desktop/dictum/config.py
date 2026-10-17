"""Lädt die Einstellungen aus settings.toml.

Warum TOML? Das Format ist gut lesbar, erlaubt Kommentare und Python bringt seit
Version 3.11 mit `tomllib` einen Leser dafür mit – keine zusätzliche Bibliothek nötig.

Die Einstellungen landen in "dataclasses": einfachen Klassen, die nur Daten halten.
So bekommt der restliche Code `settings.hotkey.mode` statt `data["hotkey"]["mode"]`
und Tippfehler fallen sofort auf.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# settings.toml liegt im Ordner desktop/, also eine Ebene über diesem Paket
DESKTOP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = DESKTOP_DIR.parent
DEFAULT_PATH = DESKTOP_DIR / "settings.toml"

VALID_KEYS = {
    "ctrl", "win", "alt", "shift",                      # linke ODER rechte Taste
    "ctrl_l", "ctrl_r", "alt_l", "shift_l", "shift_r",  # genau eine Seite
    *(f"f{n}" for n in range(1, 13)),                   # F1 … F12
}
VALID_MODES = {"both", "hold", "toggle"}
VALID_ENGINES = {"local", "openai"}
VALID_PROVIDERS = {"anthropic", "openai"}


@dataclass
class HotkeySettings:
    keys: list[str] = field(default_factory=lambda: ["ctrl_r"])
    mode: str = "both"
    hold_threshold: float = 0.4


@dataclass
class TranscriptionSettings:
    engine: str = "local"
    openai_model: str = "gpt-4o-mini-transcribe"
    model: str = "small"
    language: str = "de"
    fallback_language: str = "de"


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
class FeedbackSettings:
    sounds: bool = True


@dataclass
class Settings:
    hotkey: HotkeySettings = field(default_factory=HotkeySettings)
    transcription: TranscriptionSettings = field(default_factory=TranscriptionSettings)
    cleanup: CleanupSettings = field(default_factory=CleanupSettings)
    cloud: CloudSettings = field(default_factory=CloudSettings)
    meeting: MeetingSettings = field(default_factory=MeetingSettings)
    history: HistorySettings = field(default_factory=HistorySettings)
    feedback: FeedbackSettings = field(default_factory=FeedbackSettings)


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
        feedback=FeedbackSettings(**data.get("feedback", {})),
    )
    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    """Prüft früh auf ungültige Werte – lieber eine klare Fehlermeldung beim Start
    als ein rätselhafter Fehler mitten im Diktat."""
    hk = settings.hotkey
    unknown = set(hk.keys) - VALID_KEYS
    if unknown:
        raise ValueError(f"Unbekannte Hotkey-Taste(n): {unknown}. Erlaubt: {VALID_KEYS}")
    if len(hk.keys) < 1:
        raise ValueError("Mindestens eine Hotkey-Taste angeben.")
    if hk.mode not in VALID_MODES:
        raise ValueError(f"Ungültiger Modus '{hk.mode}'. Erlaubt: {VALID_MODES}")
    if hk.hold_threshold <= 0:
        raise ValueError("hold_threshold muss größer als 0 sein.")
    if settings.transcription.engine not in VALID_ENGINES:
        raise ValueError(f"Ungültige engine '{settings.transcription.engine}'. Erlaubt: {VALID_ENGINES}")
    if settings.cleanup.provider not in VALID_PROVIDERS:
        raise ValueError(f"Ungültiger provider '{settings.cleanup.provider}'. Erlaubt: {VALID_PROVIDERS}")


def load_env() -> None:
    """Lädt API-Keys aus der .env im Projektordner in die Umgebungsvariablen.

    Die SDKs von Anthropic und OpenAI lesen ANTHROPIC_API_KEY bzw. OPENAI_API_KEY
    automatisch aus der Umgebung – wir müssen die Keys also nie selbst im Code anfassen.
    Bereits gesetzte Umgebungsvariablen haben Vorrang (override=False).
    """
    load_dotenv(REPO_ROOT / ".env", override=False)
