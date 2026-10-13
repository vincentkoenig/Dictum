"""Testet die Hotkey-Logik ohne echte Tastatur – die Zeit wird einfach vorgegeben."""

from dictum.hotkey import HotkeyStateMachine, State


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
    sm.other_key()  # z. B. Strg+Win+D
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
