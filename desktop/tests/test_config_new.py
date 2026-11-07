"""Neue Optionen: Tastaturlayout, Leerlauf, Ton beim Aufnehmen, Abstand."""

import pytest

from dictum.config import DEFAULT_PATH, load_settings


def test_neue_optionen_haben_sichere_standardwerte():
    s = load_settings(DEFAULT_PATH)
    assert s.transcription.follow_keyboard is False
    assert s.transcription.unload_after_minutes == 0
    assert s.recording.while_dictating == "off"
    assert s.insert.smart_spacing is False


def test_neue_optionen_werden_gelesen(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text('[transcription]\nfollow_keyboard = true\nunload_after_minutes = 15\n'
                 '[recording]\nwhile_dictating = "duck"\nduck_percent = 10\n[insert]\nsmart_spacing = true\n',
                 encoding="utf-8")
    s = load_settings(f)
    assert s.transcription.follow_keyboard and s.transcription.unload_after_minutes == 15
    assert (s.recording.while_dictating, s.recording.duck_percent) == ("duck", 10)
    assert s.insert.smart_spacing


@pytest.mark.parametrize("text, message", [
    ('[recording]\nwhile_dictating = "leise"\n', "while_dictating"),
    ('[recording]\nduck_percent = 150\n', "duck_percent"),
    ('[transcription]\nunload_after_minutes = -1\n', "unload_after_minutes"),
])
def test_ungueltige_neue_optionen_werden_abgelehnt(tmp_path, text, message):
    f = tmp_path / "s.toml"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_settings(f)
