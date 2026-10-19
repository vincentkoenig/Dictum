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
OPENAI_STT_MODELS = {
    "gpt-4o-mini-transcribe": "gpt-4o-mini-transcribe (≈ 0,3 ct/min, schnell)",
    "gpt-4o-transcribe": "gpt-4o-transcribe (≈ 0,6 ct/min, genauer)",
    "whisper-1": "whisper-1 (≈ 0,6 ct/min)",
}
OPENAI_CLEANUP_MODELS = {
    "gpt-5-nano": "gpt-5-nano (am billigsten)",
    "gpt-5-mini": "gpt-5-mini (genauer)",
}
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3-turbo"]
