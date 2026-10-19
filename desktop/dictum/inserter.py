"""Fügt Text in das gerade aktive Textfeld ein – egal in welchem Programm.

Der Trick: Text in die Zwischenablage legen und Strg+V "drücken" lassen.
Danach wird der vorherige Inhalt der Zwischenablage wiederhergestellt, damit man
nicht verliert, was man vorher kopiert hatte.

Warum nicht Buchstabe für Buchstabe tippen? Das wäre langsam, manche Programme
verschlucken Zeichen, und Umlaute/Emojis machen je nach Tastaturlayout Probleme.
Einfügen ist sofort da und funktioniert praktisch überall.

Die vorherige Zwischenablage wird mit **allen Formaten** gesichert (Bilder, formatierter Text, kopierte
Dateien) und zurückgelegt, siehe clipboard.py.
"""

from __future__ import annotations

import logging
import time
import uuid

from pynput import keyboard

from . import clipboard

log = logging.getLogger(__name__)

# Kurze Pausen geben dem Zielprogramm Zeit, die Zwischenablage zu lesen
_BEFORE_PASTE = 0.05
_AFTER_PASTE = 0.3

_controller = keyboard.Controller()


def copy_selection(timeout: float = 0.6) -> str:
    """Den markierten Text des aktiven Programms holen ("" = nichts markiert).

    Dafür wird Strg+C "gedrückt". Damit man erkennt, ob wirklich etwas kopiert wurde, steht vorher ein
    Platzhalter in der Zwischenablage: Ist er danach noch da, gab es keine Markierung. Die vorherige
    Zwischenablage kommt anschließend vollständig zurück.
    """
    previous = clipboard.snapshot()
    sentinel = f"__dictum_{uuid.uuid4().hex}__"
    try:
        clipboard.set_text(sentinel)
    except clipboard.ClipboardBusy:
        return ""
    time.sleep(_BEFORE_PASTE)
    with _controller.pressed(keyboard.Key.ctrl):
        _controller.tap("c")

    selection = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.03)
        current = clipboard.get_text()
        if current is not None and current != sentinel:
            selection = current
            break

    clipboard.restore(previous)
    return selection


def insert_text(text: str) -> None:
    if not text:
        return
    previous = clipboard.snapshot()
    try:
        clipboard.set_text(text)
    except clipboard.ClipboardBusy:
        log.warning("Zwischenablage belegt – Text nicht eingefügt")
        return
    time.sleep(_BEFORE_PASTE)
    with _controller.pressed(keyboard.Key.ctrl):
        _controller.tap("v")
    time.sleep(_AFTER_PASTE)

    clipboard.restore(previous)
    log.debug("Eingefügt: %d Zeichen", len(text))
