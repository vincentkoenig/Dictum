import pytest

from dictum.config import DEFAULT_PATH, load_settings


def test_mitgelieferte_settings_sind_gueltig():
    s = load_settings(DEFAULT_PATH)
    assert s.hotkey.keys == ["ctrl_r"]
    assert s.hotkey.mode == "both"


def test_einzeltasten_und_funktionstasten_sind_erlaubt(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text('[hotkey]\nkeys = ["f10"]\n', encoding="utf-8")
    assert load_settings(f).hotkey.keys == ["f10"]


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


def test_ki_bereinigung_ist_standardmaessig_an_mit_claude():
    s = load_settings(DEFAULT_PATH)
    assert s.cleanup.enabled is True
    assert s.cleanup.provider == "anthropic"
    assert s.transcription.engine == "local"


def test_unbekannter_ki_anbieter_wird_abgelehnt(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text('[cleanup]\nprovider = "gemini"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="provider"):
        load_settings(f)


def test_zeitlimit_und_fluestermodus(tmp_path):
    import pytest

    f = tmp_path / "s.toml"
    assert load_settings(f).hotkey.max_minutes == 20 and load_settings(f).transcription.whisper_mode is True
    f.write_text("[hotkey]\nmax_minutes = -1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="max_minutes"):
        load_settings(f)
    f.write_text("[hotkey]\nmax_minutes = 0\n[transcription]\nwhisper_mode = false\n", encoding="utf-8")
    s = load_settings(f)
    assert s.hotkey.max_minutes == 0 and s.transcription.whisper_mode is False
