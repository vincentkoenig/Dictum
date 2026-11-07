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

from . import clipboard, context

log = logging.getLogger(__name__)

# Kurze Pausen geben dem Zielprogramm Zeit, die Zwischenablage zu lesen
_BEFORE_PASTE = 0.05
_AFTER_PASTE = 0.3

# Fernwartung (Remote-Desktop-Client): Die Zwischenablage wandert asynchron zum anderen Rechner, und der holt den
# Text erst, wenn er selbst einfügt. Strg+V sofort zu schicken oder die alte Zwischenablage nach 0,3 s
# zurückzulegen, ginge schief. Daher längere Pausen (Idee von Hex, einer Open-Source-Diktier-App).
_REMOTE_DESKTOP_EXES = {"mstsc", "msrdc", "msrdcw"}
_REMOTE_DESKTOP_CLASSES = {"tscshellcontainerclass"}
_REMOTE_BEFORE_PASTE = 0.4
_AFTER_PASTE_REMOTE = 3.0

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


def _restore_focus(target: context.ActiveWindow | None) -> None:
    """Das Fenster, in dem diktiert wurde, wieder nach vorn holen, falls ein anderes den Fokus hat.

    Während der Erkennung kann etwas dazwischenfunken (Benachrichtigung, anderes Programm). Ohne diesen
    Schritt landet der Text im falschen Fenster.
    """
    if target is None or not target.hwnd:
        return
    try:
        import win32gui

        if win32gui.GetForegroundWindow() == target.hwnd or not win32gui.IsWindow(target.hwnd):
            return
        win32gui.SetForegroundWindow(target.hwnd)
        time.sleep(0.1)
    except Exception:
        log.debug("Fokus konnte nicht zurückgeholt werden", exc_info=True)


def is_remote_desktop(window: context.ActiveWindow | None) -> bool:
    if window is None:
        return False
    return window.exe in _REMOTE_DESKTOP_EXES or window.window_class.lower() in _REMOTE_DESKTOP_CLASSES


def paste_delays(window: context.ActiveWindow | None) -> tuple[float, float]:
    """Pause vor dem Einfügen und Pause, bevor die alte Zwischenablage zurückkommt."""
    if is_remote_desktop(window):
        return _REMOTE_BEFORE_PASTE, _AFTER_PASTE_REMOTE
    return _BEFORE_PASTE, _AFTER_PASTE


# Vor diesen Zeichen steht kein Leerzeichen (Satzzeichen, schließende Klammern)
_NO_SPACE_BEFORE = set(".,;:!?)]}…%»”’")
# Hinter diesen Zeichen beginnt etwas Neues, ein Leerzeichen wäre falsch (öffnende Klammern, Anführungszeichen, Pfade)
_NO_SPACE_AFTER = set("([{„«“‘'\"/@#-_") | {chr(92)}


def needs_space_before(previous: str, text: str) -> bool:
    """Soll vor `text` ein Leerzeichen stehen, wenn der Cursor direkt hinter `previous` steht?

    Nur dann, wenn das Zeichen davor zu einem Wort oder Satz gehört (Buchstabe, Ziffer, Satzzeichen) und das
    Diktat selbst nicht mit einem Satzzeichen beginnt. Am Zeilen- oder Feldanfang ("" oder Leerraum) oder hinter
    einer öffnenden Klammer bleibt alles wie diktiert."""
    if not previous or not text:
        return False
    if previous.isspace() or previous in _NO_SPACE_AFTER:
        return False
    first = text[0]
    return not (first.isspace() or first in _NO_SPACE_BEFORE)


def insert_text(text: str, target: context.ActiveWindow | None = None, smart_spacing: bool = False) -> None:
    """Fügt `text` ins aktive Feld ein. Mit `smart_spacing` kommt ein Leerzeichen davor, wenn der Cursor direkt
    hinter einem Wort steht (sonst klebt das Diktat am vorigen Wort)."""
    if not text:
        return
    _restore_focus(target)
    window = target if target is not None else context.active_window()
    if smart_spacing and needs_space_before(context.char_before_caret(), text):
        text = " " + text
    before_paste, after_paste = paste_delays(window)
    previous = clipboard.snapshot()
    try:
        clipboard.set_text(text)
    except clipboard.ClipboardBusy:
        log.warning("Zwischenablage belegt – Text nicht eingefügt")
        return
    time.sleep(before_paste)
    # Klassische Terminals fügen erst mit Strg+Shift+V ein
    shift = context.is_terminal(window)
    with _controller.pressed(keyboard.Key.ctrl):
        if shift:
            with _controller.pressed(keyboard.Key.shift):
                _controller.tap("v")
        else:
            _controller.tap("v")
    time.sleep(after_paste)

    clipboard.restore(previous)
    log.debug("Eingefügt: %d Zeichen", len(text))
