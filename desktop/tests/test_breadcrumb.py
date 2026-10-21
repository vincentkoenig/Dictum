"""Die Start-Diagnose (start.log) darf bei gleichzeitigen Starts keine Zeile verlieren."""

import threading

from dictum import __main__ as entry


def test_zeilen_werden_angehaengt(tmp_path, monkeypatch):
    monkeypatch.setattr(entry, "DESKTOP_DIR", tmp_path)
    entry._breadcrumb("Start: --background")
    entry._breadcrumb("läuft bereits, beende diese Instanz")
    lines = (tmp_path / "start.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and "Start: --background" in lines[0] and "läuft bereits" in lines[1]


def test_gleichzeitige_starts_verlieren_keine_zeile(tmp_path, monkeypatch):
    """Früher: Datei lesen, Zeile anfügen, alles neu schreiben. Zwei Starts in derselben Sekunde (Run-Eintrag
    und Startordner) überschrieben sich dabei."""
    monkeypatch.setattr(entry, "DESKTOP_DIR", tmp_path)
    threads = [threading.Thread(target=entry._breadcrumb, args=(f"Start {i}",)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    text = (tmp_path / "start.log").read_text(encoding="utf-8")
    assert all(f"Start {i}\n" in text for i in range(12))


def test_grosse_datei_wird_gekuerzt(tmp_path, monkeypatch):
    monkeypatch.setattr(entry, "DESKTOP_DIR", tmp_path)
    (tmp_path / "start.log").write_text("alt\n" * 20_000, encoding="utf-8")
    entry._breadcrumb("neu")
    lines = (tmp_path / "start.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 201 and "neu" in lines[-1]
