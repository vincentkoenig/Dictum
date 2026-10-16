import logging
import sys
import threading

import pytest

from dictum import logsetup


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    hooks = (sys.excepthook, threading.excepthook, sys.stdout, sys.stderr)
    yield
    for h in list(root.handlers):
        h.close()
        root.removeHandler(h)
    for h in handlers:
        root.addHandler(h)
    root.setLevel(level)
    sys.excepthook, threading.excepthook, sys.stdout, sys.stderr = hooks


def flush():
    for h in logging.getLogger().handlers:
        h.flush()


def test_meldungen_landen_in_der_datei(tmp_path, restore_logging):
    path = tmp_path / "logs" / "dictum.log"  # Ordner existiert noch nicht
    logsetup.setup_logging(path)
    logging.getLogger("dictum.test").info("Hallo Logdatei äöü")
    flush()
    text = path.read_text(encoding="utf-8")
    assert "INFO" in text and "dictum.test" in text and "Hallo Logdatei äöü" in text


def test_zweimal_einrichten_verdoppelt_die_zeilen_nicht(tmp_path, restore_logging):
    path = tmp_path / "dictum.log"
    logsetup.setup_logging(path)
    logsetup.setup_logging(path)
    logging.getLogger("x").info("einmal")
    flush()
    assert path.read_text(encoding="utf-8").count("einmal") == 1


def test_fehler_in_hintergrund_threads_werden_protokolliert(tmp_path, restore_logging):
    path = tmp_path / "dictum.log"
    logsetup.setup_logging(path)

    def kaputt():
        raise ValueError("boom im Thread")

    t = threading.Thread(target=kaputt, name="Testthread")
    t.start()
    t.join()
    flush()
    text = path.read_text(encoding="utf-8")
    assert "CRITICAL" in text and "Testthread" in text and "boom im Thread" in text


def test_ohne_konsole_wird_stderr_ersetzt(tmp_path, restore_logging, monkeypatch):
    # So verhält sich pythonw.exe: es gibt kein stderr
    monkeypatch.setattr(sys, "stderr", None)
    logsetup.setup_logging(tmp_path / "dictum.log")
    assert sys.stderr is not None
    sys.stderr.write("darf nicht abstürzen")  # z. B. ein Fortschrittsbalken
