"""Testet die Hotkey-Logik ohne echte Tastatur – die Zeit wird einfach vorgegeben."""

from pynput.keyboard import Key

from dictum.hotkey import HotkeyListener, HotkeyStateMachine, State, hotkey_label


def make(mode="both"):
    events = []
    sm = HotkeyStateMachine(
        on_start=lambda: events.append("start"),
        on_stop=lambda: events.append("stop"),
        on_cancel=lambda: events.append("cancel"),
        mode=mode,
        hold_threshold=0.4,
    )
    return sm, events


def test_halten_startet_und_stoppt():
    sm, ev = make()
    sm.combo_down(0.0)
    sm.combo_up(2.0)  # 2 s gehalten
    assert ev == ["start", "stop"]
    assert sm.state == State.IDLE


def test_antippen_laesst_aufnahme_weiterlaufen_bis_zum_zweiten_antippen():
    sm, ev = make()
    sm.combo_down(0.0)
    sm.combo_up(0.1)  # kurz angetippt
    assert ev == ["start"]
    assert sm.state == State.TOGGLED

    sm.combo_down(10.0)  # zweites Antippen
    assert ev == ["start", "stop"]
    sm.combo_up(10.1)
    assert sm.state == State.IDLE


def test_andere_taste_waehrend_halten_verwirft_aufnahme():
    sm, ev = make()
    sm.combo_down(0.0)
    sm.other_key()  # z. B. C – man wollte eigentlich Strg+C drücken
    sm.combo_up(0.5)
    assert ev == ["start", "cancel"]
    assert sm.state == State.IDLE


def test_andere_taste_im_toggle_modus_stoert_nicht():
    sm, ev = make()
    sm.combo_down(0.0)
    sm.combo_up(0.1)
    sm.other_key()  # man tippt nebenbei etwas – Aufnahme läuft weiter
    assert sm.state == State.TOGGLED
    assert ev == ["start"]


def test_modus_hold_stoppt_auch_bei_kurzem_druck():
    sm, ev = make(mode="hold")
    sm.combo_down(0.0)
    sm.combo_up(0.1)
    assert ev == ["start", "stop"]


def test_modus_toggle_wartet_auch_bei_langem_druck():
    sm, ev = make(mode="toggle")
    sm.combo_down(0.0)
    sm.combo_up(3.0)
    assert sm.state == State.TOGGLED


# --- Tastenzuordnung (echte pynput-Tasten → Namen aus settings.toml) ---------------


def test_strg_rechts_loest_aus_strg_links_nicht():
    listener = HotkeyListener(["ctrl_r"], make()[0])
    assert listener.name_for(Key.ctrl_r) == "ctrl_r"
    assert listener.name_for(Key.ctrl_l) is None  # z. B. Strg+C bleibt unberührt


def test_gruppe_ctrl_meint_beide_seiten():
    listener = HotkeyListener(["ctrl", "win"], make()[0])
    assert listener.name_for(Key.ctrl_l) == "ctrl"
    assert listener.name_for(Key.ctrl_r) == "ctrl"
    assert listener.name_for(Key.cmd) == "win"


def test_strg_rechts_halten_ueber_den_listener():
    sm, ev = make()
    listener = HotkeyListener(["ctrl_r"], sm)
    listener._on_press(Key.ctrl_r)
    listener._on_press(Key.ctrl_r)  # automatische Tastenwiederholung beim Halten
    assert ev == ["start"]
    listener._on_release(Key.ctrl_r)
    assert sm.state in (State.IDLE, State.TOGGLED)


def test_lesbarer_name_fuer_das_tray():
    assert hotkey_label(["ctrl_r"]) == "Strg rechts"
    assert hotkey_label(["win", "alt"]) == "Win+Alt"
