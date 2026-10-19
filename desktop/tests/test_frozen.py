"""Pfade für das gebaute Programm (Dictum.exe): Persönliche Dateien in %APPDATA%, Vorlagen im Paket."""

import importlib
import sys

import pytest

from dictum import config


@pytest.fixture
def frozen(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "settings.toml").write_text('[hotkey]\nkeys = ["f8"]\n', encoding="utf-8")
    appdata = tmp_path / "appdata"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("APPDATA", str(appdata))
    importlib.reload(config)
    yield config, bundle, appdata
    monkeypatch.undo()
    importlib.reload(config)  # zurück in den Normalzustand für die anderen Tests


def test_persoenliche_dateien_liegen_in_appdata(frozen):
    cfg, bundle, appdata = frozen
    assert cfg.FROZEN and cfg.DESKTOP_DIR == appdata / "Dictum" and cfg.REPO_ROOT == cfg.DESKTOP_DIR
    assert cfg.RESOURCE_DIR == bundle and cfg.DEFAULT_PATH == appdata / "Dictum" / "settings.toml"


def test_erster_start_legt_ordner_und_einstellungen_an(frozen):
    cfg, _bundle, _appdata = frozen
    cfg.ensure_user_dir()
    assert cfg.load_settings().hotkey.keys == ["f8"]
    cfg.DEFAULT_PATH.write_text('[hotkey]\nkeys = ["f10"]\n', encoding="utf-8")
    cfg.ensure_user_dir()                              # zweiter Start überschreibt nichts
    assert cfg.load_settings().hotkey.keys == ["f10"]


def test_aus_dem_quellcode_aendert_sich_nichts():
    assert not config.FROZEN
    assert config.DESKTOP_DIR == config.RESOURCE_DIR and config.REPO_ROOT == config.DESKTOP_DIR.parent
    config.ensure_user_dir()                           # tut nichts und legt nichts an
