"""Zwischenablage mit allen Formaten sichern und wiederherstellen.

Dictum fügt Text ein, indem es ihn kurz in die Zwischenablage legt und Strg+V drückt. Damit dabei
nichts verloren geht, was du vorher kopiert hast, wird die Zwischenablage vorher **komplett** gesichert
und danach zurückgelegt: nicht nur Text, sondern auch Bilder, formatierten Text (HTML, RTF) und kopierte Dateien.

Hinter einer Zwischenablage stecken meist mehrere Formate gleichzeitig. Kopiert man in Word einen Absatz,
liegt er als einfacher Text, als RTF und als HTML bereit, damit jedes Zielprogramm das passende nimmt.
`snapshot()` merkt sich jedes Format, `restore()` legt alle wieder hin.

Nicht gesichert werden Formate, die nur als Windows-Handle existieren (z. B. `CF_BITMAP`, `CF_ENHMETAFILE`).
Das ist unkritisch: Zu einem Bild liegt immer auch `CF_DIB` bereit, aus dem Windows das Handle selbst baut.

Der kurzzeitig eingefügte Text wird außerdem für Zwischenablage-Verlauf (Win+V) und Cloud-Zwischenablage
gesperrt, damit dein Diktat dort nicht auftaucht.
"""

from __future__ import annotations

import logging
import struct
import time

import win32clipboard
import win32con

log = logging.getLogger(__name__)

# Nur als Handle vorhanden, nicht als Speicherblock: lassen sich nicht kopieren
_HANDLE_FORMATS = {
    win32con.CF_BITMAP, win32con.CF_METAFILEPICT, win32con.CF_ENHMETAFILE,
    win32con.CF_PALETTE, win32con.CF_DSPBITMAP, win32con.CF_DSPENHMETAFILE, win32con.CF_DSPMETAFILEPICT,
    win32con.CF_OWNERDISPLAY,
}

Snapshot = list[tuple[int, object]]


class ClipboardBusy(Exception):
    """Ein anderes Programm hält die Zwischenablage gerade fest."""


def _open(retries: int = 15, pause: float = 0.02) -> None:
    for _ in range(retries):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception:
            time.sleep(pause)
    raise ClipboardBusy


def _drop_files(files: tuple[str, ...]) -> bytes:
    """Baut den Speicherblock für kopierte Dateien (DROPFILES: Kopf + Pfade als UTF-16, doppelt abgeschlossen)."""
    head = struct.pack("<IiiII", 20, 0, 0, 0, 1)  # Offset der Liste, Mauspunkt, nicht-Client, Unicode
    return head + "".join(f + "\0" for f in files).encode("utf-16-le") + b"\0\0"


def snapshot() -> Snapshot:
    """Alle Formate der Zwischenablage. Eine leere Liste heißt: leer oder nicht lesbar."""
    items: Snapshot = []
    try:
        _open()
    except ClipboardBusy:
        log.debug("Zwischenablage belegt – keine Sicherung")
        return items
    try:
        fmt = 0
        while True:
            fmt = win32clipboard.EnumClipboardFormats(fmt)
            if not fmt:
                break
            if fmt in _HANDLE_FORMATS:
                continue
            try:
                items.append((fmt, win32clipboard.GetClipboardData(fmt)))
            except Exception:
                log.debug("Format %s nicht lesbar", fmt)
    finally:
        win32clipboard.CloseClipboard()
    return items


def restore(items: Snapshot) -> None:
    """Legt die gesicherten Formate zurück (ersetzt den aktuellen Inhalt)."""
    try:
        _open()
    except ClipboardBusy:
        log.warning("Zwischenablage belegt – konnte den alten Inhalt nicht zurücklegen")
        return
    try:
        win32clipboard.EmptyClipboard()
        for fmt, data in items:
            try:
                if fmt == win32con.CF_HDROP and isinstance(data, tuple):
                    data = _drop_files(data)
                win32clipboard.SetClipboardData(fmt, data)
            except Exception:
                log.debug("Format %s nicht zurückgelegt", fmt)
    finally:
        win32clipboard.CloseClipboard()


def set_text(text: str, private: bool = True) -> None:
    """Legt Text in die Zwischenablage. `private`: nicht in Verlauf und Cloud-Zwischenablage aufnehmen."""
    _open()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        if private:
            for name, value in (
                ("ExcludeClipboardContentFromMonitorProcessing", b"\x01\x00\x00\x00"),
                ("CanIncludeInClipboardHistory", b"\x00\x00\x00\x00"),
                ("CanUploadToCloudClipboard", b"\x00\x00\x00\x00"),
            ):
                win32clipboard.SetClipboardData(win32clipboard.RegisterClipboardFormat(name), value)
    finally:
        win32clipboard.CloseClipboard()


def get_text() -> str | None:
    """Der Text in der Zwischenablage oder None (leer, kein Text, belegt)."""
    try:
        _open()
    except ClipboardBusy:
        return None
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        return None
    except Exception:
        return None
    finally:
        win32clipboard.CloseClipboard()
