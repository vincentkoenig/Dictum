"""Testet die Zwischenablage mit der echten Windows-Zwischenablage. Dein vorheriger Inhalt wird
vor dem Test gesichert und danach zurückgelegt."""

import pytest
import win32clipboard
import win32con

from dictum import clipboard

HTML = win32clipboard.RegisterClipboardFormat("HTML Format")


@pytest.fixture
def real_clipboard():
    original = clipboard.snapshot()
    yield
    clipboard.restore(original)


def put_formats():
    clipboard._open()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, "Hallo Welt")
        win32clipboard.SetClipboardData(HTML, b"<b>Hallo</b> Welt")
    finally:
        win32clipboard.CloseClipboard()


def test_alle_formate_ueberleben_einfuegen(real_clipboard):
    put_formats()
    saved = clipboard.snapshot()
    assert {fmt for fmt, _ in saved} >= {win32con.CF_UNICODETEXT, HTML}

    clipboard.set_text("Diktierter Text")          # überschreibt alles
    assert clipboard.get_text() == "Diktierter Text"

    clipboard.restore(saved)
    assert clipboard.get_text() == "Hallo Welt"
    clipboard._open()
    try:
        assert win32clipboard.GetClipboardData(HTML) == b"<b>Hallo</b> Welt"   # auch der formatierte Teil
    finally:
        win32clipboard.CloseClipboard()


def test_dateien_werden_wiederhergestellt(real_clipboard, tmp_path):
    f = tmp_path / "datei.txt"
    f.write_text("x")
    clipboard._open()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_HDROP, clipboard._drop_files((str(f),)))
    finally:
        win32clipboard.CloseClipboard()
    saved = clipboard.snapshot()
    assert any(fmt == win32con.CF_HDROP for fmt, _ in saved)

    clipboard.set_text("anderer Text")
    clipboard.restore(saved)
    clipboard._open()
    try:
        assert win32clipboard.GetClipboardData(win32con.CF_HDROP) == (str(f),)
    finally:
        win32clipboard.CloseClipboard()


def test_diktat_taucht_nicht_im_verlauf_auf(real_clipboard):
    clipboard.set_text("geheim")
    clipboard._open()
    try:
        fmt = win32clipboard.RegisterClipboardFormat("CanIncludeInClipboardHistory")
        assert win32clipboard.IsClipboardFormatAvailable(fmt)
        assert win32clipboard.GetClipboardData(fmt) == b"\x00\x00\x00\x00"
    finally:
        win32clipboard.CloseClipboard()


def test_leere_zwischenablage(real_clipboard):
    clipboard._open()
    try:
        win32clipboard.EmptyClipboard()
    finally:
        win32clipboard.CloseClipboard()
    assert clipboard.snapshot() == [] and clipboard.get_text() is None
    clipboard.restore([])                              # darf nicht abstürzen
