import winreg

import pytest

from dictum import autostart

# Eigener Test-Schlüssel – der echte "Run"-Eintrag des Benutzers wird nie angefasst
TEST_KEY = r"Software\DictumTest\Run"


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    for key in (TEST_KEY, r"Software\DictumTest"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except FileNotFoundError:
            pass


def test_befehl_hat_anfuehrungszeichen_fuer_pfade_mit_leerzeichen():
    cmd = autostart.build_command(r"C:\Mein Ordner\pythonw.exe", r"C:\Mein Ordner\dictum_tray.pyw")
    assert cmd == r'"C:\Mein Ordner\pythonw.exe" -X utf8 "C:\Mein Ordner\dictum_tray.pyw" --background'


def test_standardbefehl_nutzt_pythonw_ohne_konsole():
    cmd = autostart.default_command()
    assert "pythonw.exe" in cmd.lower()
    assert str(autostart.LAUNCHER) in cmd


def test_ein_und_ausschalten():
    assert autostart.is_enabled(TEST_KEY) is False
    autostart.enable("befehl-1", TEST_KEY)
    assert autostart.is_enabled(TEST_KEY) is True
    assert autostart.current_value(TEST_KEY) == "befehl-1"
    autostart.disable(TEST_KEY)
    assert autostart.is_enabled(TEST_KEY) is False


def test_ausschalten_ohne_eintrag_ist_kein_fehler():
    autostart.disable(TEST_KEY)  # Schlüssel existiert gar nicht


def test_veralteter_pfad_wird_korrigiert():
    autostart.enable("alter-pfad", TEST_KEY)
    assert autostart.refresh_if_enabled(TEST_KEY, command="neuer-pfad") is True
    assert autostart.current_value(TEST_KEY) == "neuer-pfad"
    # und wenn alles stimmt, wird nichts angefasst
    assert autostart.refresh_if_enabled(TEST_KEY, command="neuer-pfad") is False


def test_ausgeschaltet_bleibt_ausgeschaltet_beim_auffrischen():
    # Wer Autostart nicht will, bekommt ihn auch nicht heimlich eingeschaltet
    assert autostart.refresh_if_enabled(TEST_KEY, command="egal") is False
    assert autostart.is_enabled(TEST_KEY) is False


def test_befehl_fuer_die_exe_hat_kein_startskript():
    assert autostart.build_command(r"C:\Programme\Dictum\Dictum.exe", None) == r'"C:\Programme\Dictum\Dictum.exe" --background'
