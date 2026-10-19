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

from .keys import check_hotkey

# settings.toml liegt im Ordner desktop/, also eine Ebene über diesem Paket
DESKTOP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = DESKTOP_DIR.parent
DEFAULT_PATH = DESKTOP_DIR / "settings.toml"

VALID_MODES = {"both", "hold", "toggle"}
VALID_ENGINES = {"local", "openai"}
VALID_PROVIDERS = {"anthropic", "openai"}


@dataclass
class HotkeySettings:
    keys: list[str] = field(default_factory=lambda: ["ctrl_r"])
    mode: str = "both"
    hold_threshold: float = 0.4
    # Zusatz-Tasten wie bei Wispr Flow (leere Liste = aus): letztes Diktat erneut einfügen / kopieren
    paste_last: list[str] = field(default_factory=lambda: ["shift", "alt", "z"])
    copy_last: list[str] = field(default_factory=lambda: ["shift", "alt", "x"])


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
    for name, keys, optional in (("keys", hk.keys, False), ("paste_last", hk.paste_last, True),
                                 ("copy_last", hk.copy_last, True)):
        problem = check_hotkey(keys, allow_empty=optional)
        if problem:
            raise ValueError(f"hotkey.{name}: {problem}")
    chosen = [tuple(sorted(k)) for k in (hk.keys, hk.paste_last, hk.copy_last) if k]
    if len(chosen) != len(set(chosen)):
        raise ValueError("Jede Tastenkombination darf nur einmal vergeben werden.")
    if hk.mode not in VALID_MODES:
        raise ValueError(f"Ungültiger Modus '{hk.mode}'. Erlaubt: {VALID_MODES}")
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
