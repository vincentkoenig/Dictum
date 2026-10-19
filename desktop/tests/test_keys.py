"""Testet Tastennamen, Prüfung und Tasten-Aufnahme – ohne echte Tastatur."""

from pynput import mouse
from pynput.keyboard import Key, KeyCode

from dictum.keys import CaptureState, canonical, check_hotkey, expand, hotkey_label, is_valid_name


def test_canonical_benennt_tasten_einheitlich():
    assert canonical(Key.ctrl_r) == "ctrl_r"
    assert canonical(Key.ctrl) == "ctrl_l"          # pynput-Alias
    assert canonical(Key.cmd) == "win_l" and canonical(Key.cmd_r) == "win_r"
    assert canonical(Key.alt_gr) == "alt_r"
    assert canonical(Key.f8) == "f8"
    assert canonical(KeyCode.from_vk(0x5A)) == "z"
    assert canonical(KeyCode(vk=0x44, char="\x04")) == "d"  # Steuerzeichen unter Strg
    assert canonical(KeyCode.from_vk(173)) == "vk_173"
    assert canonical(mouse.Button.x2) == "mouse_x2"
    assert canonical(mouse.Button.left) is None


def test_gruppen_meinen_beide_seiten():
    assert expand("ctrl") == {"ctrl_l", "ctrl_r"}
    assert expand("f8") == {"f8"}


def test_gueltige_namen():
    for name in ("ctrl", "ctrl_r", "win_l", "f20", "a", "7", "caps_lock", "vk_173", "mouse_middle"):
        assert is_valid_name(name), name
    for name in ("fn", "strg", "mouse_left", "vk_", "ä"):
        assert not is_valid_name(name), name


def test_pruefung_erlaubt_sondertasten_und_kombinationen():
    assert check_hotkey(["ctrl_r"]) is None
    assert check_hotkey(["f8"]) is None
    assert check_hotkey(["caps_lock"]) is None
    assert check_hotkey(["mouse_x1"]) is None
    assert check_hotkey(["ctrl", "alt", "d"]) is None
    assert check_hotkey(["vk_173"]) is None          # Medientaste


def test_pruefung_lehnt_tipptasten_allein_ab():
    assert "Tippen" in check_hotkey(["a"])
    assert "Tippen" in check_hotkey(["space"])
    assert check_hotkey(["esc"]) and "Abbrechen" in check_hotkey(["esc"])
    assert check_hotkey([]) is not None
    assert check_hotkey([], allow_empty=True) is None
    assert check_hotkey(["quatsch"]) is not None


def test_lesbare_namen():
    assert hotkey_label(["ctrl_r"]) == "Strg rechts"
    assert hotkey_label(["shift", "alt", "z"]) == "Umschalt+Alt+Z"
    assert hotkey_label(["mouse_x1"]).startswith("Maustaste 4")
    assert hotkey_label(["vk_173"]) == "Taste 173"
    assert hotkey_label([]) == "Aus"


def test_aufnahme_meldet_erst_wenn_alles_losgelassen_ist():
    cap = CaptureState()
    cap.press("z")
    cap.press("ctrl_l")
    assert cap.current == ["ctrl_l", "z"]            # Sondertasten zuerst
    assert cap.release("ctrl_l") is None
    assert cap.release("z") == ["ctrl_l", "z"]
    assert cap.release("z") is None                  # nichts doppelt melden


def test_aufnahme_einzelne_taste():
    cap = CaptureState()
    cap.press("ctrl_r")
    assert cap.release("ctrl_r") == ["ctrl_r"]
