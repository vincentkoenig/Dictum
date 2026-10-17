"""Beschriftungen und Auswahllisten, die Tray-Menü und Einstellungsfenster gemeinsam nutzen.
Steht an einer Stelle, damit beide immer dieselben Wörter benutzen."""

from __future__ import annotations

MODE_LABELS = {
    "both": "Halten oder Antippen",
    "hold": "Nur Halten",
    "toggle": "Nur Antippen",
}
LANGUAGE_LABELS = {
    "de": "Deutsch",
    "en": "Englisch",
    "auto": "Automatisch (langsamer)",
}
ENGINE_LABELS = {
    "local": "Lokal (privat, kostenlos)",
    "openai": "OpenAI-Cloud (schneller)",
}
PROVIDER_LABELS = {
    "anthropic": "Claude",
    "openai": "OpenAI",
}
TEMPLATE_LABELS = {
    "meeting": "Meeting",
    "interview": "Interview",
    "lecture": "Vorlesung",
    "note": "Notiz",
}
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3-turbo"]

# Hotkey-Voreinstellungen: Beschriftung → Tasten (wie in settings.toml). Ungeeignete
# Kombinationen auf deutschen Tastaturen (Strg+Alt = AltGr, Strg+Umschalt) fehlen mit Absicht.
HOTKEY_PRESETS: list[tuple[str, list[str]]] = [
    ("Strg rechts", ["ctrl_r"]),
    ("Umschalt rechts", ["shift_r"]),
    ("F8", ["f8"]),
    ("F9", ["f9"]),
    ("F10", ["f10"]),
    ("Win + Alt", ["win", "alt"]),
]
