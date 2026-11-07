"""Sprache nach Tastaturlayout wählen.

Wer zwischen Deutsch und Englisch schreibt, schaltet in Windows ohnehin das Tastaturlayout um (Win+Leertaste).
Dictum liest dieses Layout vom Fenster, in das diktiert wird, und nimmt dessen Sprache für die Erkennung.
So braucht es weder eine feste Sprache noch die automatische Erkennung, die pro Diktat 1,5–2 s extra kostet.

Windows liefert pro Fenster-Thread ein "Tastaturlayout-Handle" (`GetKeyboardLayout`). Dessen unteres Wort ist die
Sprachkennung (LANGID), und die unteren 10 Bit davon sind die Hauptsprache: 0x07 = Deutsch, 0x09 = Englisch.

Ein Layout ohne Eintrag in der Tabelle (oder ein nicht lesbares Fenster) ergibt None, dann gilt die eingestellte Sprache.
"""

from __future__ import annotations

import ctypes
import logging

log = logging.getLogger(__name__)

# Hauptsprach-Kennung (LANGID & 0x3FF) → Whisper-Sprachcode
PRIMARY_LANGUAGES = {
    0x07: "de", 0x09: "en", 0x0C: "fr", 0x0A: "es", 0x10: "it", 0x13: "nl", 0x16: "pt",
    0x15: "pl", 0x19: "ru", 0x1D: "sv", 0x06: "da", 0x14: "no", 0x0B: "fi", 0x05: "cs",
    0x1F: "tr", 0x22: "uk", 0x08: "el", 0x0E: "hu", 0x18: "ro",
}


def language_from_layout(layout_handle: int) -> str | None:
    """Sprachcode zu einem Tastaturlayout-Handle (HKL), None bei unbekannter Sprache."""
    langid = layout_handle & 0xFFFF
    return PRIMARY_LANGUAGES.get(langid & 0x3FF)


def language_for_window(hwnd: int) -> str | None:
    """Sprache des Tastaturlayouts, das im Fenster `hwnd` gerade aktiv ist (None = nicht ermittelbar)."""
    if not hwnd:
        return None
    try:
        user32 = ctypes.windll.user32
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        thread_id = user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), None)
        if not thread_id:
            return None
        user32.GetKeyboardLayout.restype = ctypes.c_void_p
        handle = user32.GetKeyboardLayout(ctypes.c_ulong(thread_id))
        return language_from_layout(int(handle or 0))
    except Exception:
        log.debug("Tastaturlayout nicht lesbar", exc_info=True)
        return None
