"""Beenden von DictumApp: Jeder Schritt läuft, auch wenn ein früherer scheitert; die Notbremse greift."""

import queue

import pytest

import dictum.app as app_module
from dictum.app import DictumApp


class Step:
    def __init__(self, order, name, fails=False):
        self.order, self.name, self.fails = order, name, fails

    def __call__(self, *args):
        self.order.append(self.name)
        if self.fails:
            raise RuntimeError(f"{self.name} kaputt")


class Obj:
    def __init__(self, **methods):
        for name, fn in methods.items():
            setattr(self, name, fn)


def make_app(order, failing=()):
    app = DictumApp.__new__(DictumApp)
    app.meetings = Obj(stop=Step(order, "meeting", "meeting" in failing))
    app.ducker = Obj(shutdown=Step(order, "ton", "ton" in failing))
    app.listener = Obj(stop=Step(order, "tasten", "tasten" in failing))
    app.tray = Obj(stop=Step(order, "tray", "tray" in failing))
    app.qt = Obj(quit=Step(order, "qt", "qt" in failing))
    app._jobs = queue.Queue()
    app.QUIT_TIMEOUT = 60  # Notbremse soll im Test nicht auslösen
    return app


def test_alle_schritte_laufen_in_reihenfolge():
    order = []
    app = make_app(order)
    app._do_quit()
    assert order == ["meeting", "ton", "tasten", "tray", "qt"]
    assert app._jobs.get_nowait() is None            # Worker bekommt das Stoppsignal


@pytest.mark.parametrize("broken", ["meeting", "ton", "tasten", "tray"])
def test_ein_fehler_stoppt_das_beenden_nicht(broken):
    order = []
    app = make_app(order, failing=(broken,))
    app._do_quit()
    assert "qt" in order                              # die Qt-Schleife wird in jedem Fall beendet
    assert app._jobs.get_nowait() is None             # und der Worker auch
    assert len(order) == 5


def test_notbremse_beendet_hart_und_schreibt_stapel(tmp_path, monkeypatch):
    log = tmp_path / "dictum.log"
    exits = []
    monkeypatch.setattr(app_module, "LOG_PATH", log)
    monkeypatch.setattr(app_module.os, "_exit", lambda code: exits.append(code))
    app = make_app([])
    app._force_exit()
    assert exits == [0]
    assert "Thread" in log.read_text(encoding="utf-8")   # faulthandler schreibt "Thread 0x… (most recent call first)"
