"""Einfügen: Fernwartung (längere Pausen) und intelligenter Abstand."""

import contextlib

from dictum import inserter
from dictum.context import ActiveWindow


def win(exe="", cls=""):
    return ActiveWindow(exe=exe, title="", hwnd=1, window_class=cls)


def test_fernwartung_wartet_laenger_beim_einfuegen():
    normal = inserter.paste_delays(win(exe="chrome"))
    remote = inserter.paste_delays(win(exe="mstsc"))
    assert remote[0] > normal[0] and remote[1] > normal[1]
    assert remote[1] >= 3.0   # die alte Zwischenablage kommt erst, wenn der andere Rechner den Text geholt hat


def test_fernwartung_wird_am_programm_oder_an_der_fensterklasse_erkannt():
    assert inserter.is_remote_desktop(win(exe="msrdc"))
    assert inserter.is_remote_desktop(win(exe="", cls="TscShellContainerClass"))
    assert not inserter.is_remote_desktop(win(exe="notepad"))
    assert not inserter.is_remote_desktop(None)


def test_abstand_nach_wort_und_satzzeichen():
    assert inserter.needs_space_before("a", "Hallo")
    assert inserter.needs_space_before(".", "Noch ein Satz")
    assert inserter.needs_space_before(",", "und weiter")
    assert inserter.needs_space_before("5", "Euro")


def test_kein_abstand_wenn_er_falsch_waere():
    assert not inserter.needs_space_before("", "Hallo")        # Feldanfang oder unlesbar
    assert not inserter.needs_space_before(" ", "Hallo")       # schon ein Leerzeichen da
    assert not inserter.needs_space_before("\n", "Hallo")      # Zeilenanfang
    assert not inserter.needs_space_before("(", "Hallo")       # hinter einer öffnenden Klammer
    assert not inserter.needs_space_before("/", "pfad")
    assert not inserter.needs_space_before("a", ", sagte er")  # Diktat beginnt mit Satzzeichen
    assert not inserter.needs_space_before("a", "!")
    assert not inserter.needs_space_before("a", " schon mit Abstand")
    assert not inserter.needs_space_before("a", "")


class _FakeController:
    def pressed(self, key):
        return contextlib.nullcontext()

    def tap(self, key):
        pass


def _stub_system(monkeypatch, pasted):
    monkeypatch.setattr(inserter.context, "char_before_caret", lambda: "a")
    monkeypatch.setattr(inserter.context, "active_window", lambda: None)
    monkeypatch.setattr(inserter, "_restore_focus", lambda target: None)
    monkeypatch.setattr(inserter.clipboard, "snapshot", lambda: None)
    monkeypatch.setattr(inserter.clipboard, "set_text", lambda text: pasted.append(text))
    monkeypatch.setattr(inserter.clipboard, "restore", lambda previous: None)
    monkeypatch.setattr(inserter, "_controller", _FakeController())
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: None)


def test_insert_text_setzt_abstand_nur_auf_wunsch(monkeypatch):
    pasted = []
    _stub_system(monkeypatch, pasted)
    inserter.insert_text("Hallo", None)
    inserter.insert_text("Hallo", None, smart_spacing=True)
    assert pasted == ["Hallo", " Hallo"]


def test_insert_text_wartet_bei_fernwartung_laenger(monkeypatch):
    pasted, pauses = [], []
    _stub_system(monkeypatch, pasted)
    monkeypatch.setattr(inserter.time, "sleep", lambda seconds: pauses.append(seconds))
    inserter.insert_text("Hallo", win(exe="mstsc"))
    assert max(pauses) >= 3.0
