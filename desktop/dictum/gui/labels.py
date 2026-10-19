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
