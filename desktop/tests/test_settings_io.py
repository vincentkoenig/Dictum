import shutil

import pytest

from dictum.config import DEFAULT_PATH, load_settings
from dictum.settings_io import save_settings


@pytest.fixture
def copy(tmp_path):
    target = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, target)
    return target


def test_werte_werden_geschrieben_und_wieder_gelesen(copy):
    new = save_settings({"transcription": {"language": "en"}, "history": {"keep_days": 30}}, copy)
    assert new.transcription.language == "en"
    again = load_settings(copy)
    assert again.transcription.language == "en" and again.history.keep_days == 30


def test_kommentare_bleiben_erhalten(copy):
    before = copy.read_text(encoding="utf-8")
    save_settings({"hotkey": {"keys": ["f10"]}}, copy)
    after = copy.read_text(encoding="utf-8")
    assert "# Taste(n), die gedrückt werden." in after
    assert after.count("#") == before.count("#")  # kein Kommentar verloren
    assert load_settings(copy).hotkey.keys == ["f10"]


def test_ungueltiger_wert_wird_abgelehnt_und_datei_bleibt_unberuehrt(copy):
    before = copy.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="Modus"):
        save_settings({"hotkey": {"mode": "dauernd"}}, copy)
    assert copy.read_text(encoding="utf-8") == before


def test_fehlender_abschnitt_wird_angelegt(copy):
    text = copy.read_text(encoding="utf-8")
    start = text.index("[history]")
    end = text.index("[feedback]")
    copy.write_text(text[:start] + text[end:], encoding="utf-8")  # [history] entfernen
    save_settings({"history": {"enabled": False}}, copy)
    assert load_settings(copy).history.enabled is False
