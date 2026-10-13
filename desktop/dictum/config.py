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

# settings.toml liegt im Ordner desktop/, also eine Ebene über diesem Paket
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "settings.toml"

VALID_KEYS = {"ctrl", "win", "alt", "shift"}
VALID_MODES = {"both", "hold", "toggle"}


@dataclass
class HotkeySettings:
    keys: list[str] = field(default_factory=lambda: ["ctrl", "win"])
    mode: str = "both"
    hold_threshold: float = 0.4


@dataclass
class TranscriptionSettings:
    model: str = "small"
    language: str = "de"
    fallback_language: str = "de"


@dataclass
class FeedbackSettings:
    sounds: bool = True


@dataclass
class Settings:
    hotkey: HotkeySettings = field(default_factory=HotkeySettings)
    transcription: TranscriptionSettings = field(default_factory=TranscriptionSettings)
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
