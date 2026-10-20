"""Verknüpfungen in einem Wegwerf-Ordner anlegen, zurücklesen und löschen (nie auf dem echten Desktop)."""

from dictum import shortcuts
from dictum.autostart import LAUNCHER, background_python


def test_verknuepfung_anlegen_lesen_entfernen(tmp_path):
    assert not shortcuts.is_present("desktop", tmp_path)
    path = shortcuts.create("desktop", tmp_path)
    assert path.exists() and shortcuts.is_present("desktop", tmp_path)

    info = shortcuts.read(path)
    assert info["target"].lower() == str(background_python()).lower()
    assert str(LAUNCHER) in info["arguments"] and "-X utf8" in info["arguments"]
    assert "--background" not in info["arguments"]  # Doppelklick soll das Fenster öffnen
    assert info["icon"].endswith("dictum.ico")

    shortcuts.remove("desktop", tmp_path)
    assert not shortcuts.is_present("desktop", tmp_path)


def test_erneut_anlegen_ersetzt(tmp_path):
    shortcuts.create("start_menu", tmp_path)
    shortcuts.create("start_menu", tmp_path)
    assert len(list(tmp_path.iterdir())) == 1


def test_echte_ordner_gibt_es():
    assert shortcuts.folder_for("desktop").is_dir()
    assert shortcuts.folder_for("start_menu").is_dir()


def test_icon_ist_im_repo():
    assert shortcuts.ICON_PATH.exists()


def test_autostart_ordner_ist_bekannt():
    assert shortcuts.folder_for("startup").is_dir()
