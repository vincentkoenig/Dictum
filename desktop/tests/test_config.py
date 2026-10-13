import pytest

from dictum.config import DEFAULT_PATH, load_settings


def test_mitgelieferte_settings_sind_gueltig():
    s = load_settings(DEFAULT_PATH)
    assert s.hotkey.keys == ["ctrl_r"]
    assert s.hotkey.mode == "both"


def test_einzeltasten_und_funktionstasten_sind_erlaubt(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text('[hotkey]\nkeys = ["f9"]\n', encoding="utf-8")
    assert load_settings(f).hotkey.keys == ["f9"]


def test_fehlende_datei_ergibt_standardwerte(tmp_path):
    s = load_settings(tmp_path / "gibts-nicht.toml")
    assert s.transcription.model == "small"
    assert s.transcription.fallback_language == "de"


def test_ungueltiger_modus_wird_abgelehnt(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text('[hotkey]\nmode = "dauernd"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Modus"):
        load_settings(f)


def test_unbekannte_taste_wird_abgelehnt(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text('[hotkey]\nkeys = ["ctrl", "fn"]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Taste"):
        load_settings(f)
