"""Globaler Hotkey: halten zum Sprechen ODER antippen für Start/Stopp.

Aufgeteilt in zwei Teile:

1. `HotkeyStateMachine` – die reine Logik, OHNE Tastatur. Sie bekommt nur gemeldet
   "Kombination gedrückt / losgelassen / andere Taste" und entscheidet, ob eine
   Aufnahme startet, endet oder verworfen wird. Weil sie nichts von der echten
   Tastatur weiß, kann man sie leicht testen (siehe tests/test_hotkey.py).

2. `HotkeyListener` – hört mit `pynput` systemweit auf die Tastatur, merkt sich,
   welche Tasten gerade gedrückt sind, und meldet das an die Zustandsmaschine.

Die Zustände:

    IDLE ──Kombi gedrückt──► PRESSED ──losgelassen nach ≥ Schwelle──► (stop) IDLE
                               │
                               └──losgelassen vor Schwelle──► TOGGLED
                                                                │
    IDLE ◄──losgelassen── WAIT_RELEASE ◄──Kombi erneut gedrückt (stop)┘

Wird während PRESSED eine andere Taste gedrückt (z. B. Strg+Win+D für einen neuen
Desktop), war das kein Diktat → Aufnahme wird verworfen (cancel).
"""

from __future__ import annotations

import enum
import logging
import time
from typing import Callable

from pynput import keyboard

log = logging.getLogger(__name__)


class State(enum.Enum):
    IDLE = "idle"
    PRESSED = "pressed"            # Kombi wird gerade gehalten, Aufnahme läuft
    TOGGLED = "toggled"            # nach kurzem Antippen: Aufnahme läuft weiter
    WAIT_RELEASE = "wait_release"  # Aufnahme beendet, warten bis Tasten losgelassen


class HotkeyStateMachine:
    def __init__(
        self,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_cancel: Callable[[], None],
        mode: str = "both",
        hold_threshold: float = 0.4,
    ) -> None:
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_cancel = on_cancel
        self.mode = mode
        self.hold_threshold = hold_threshold
        self.state = State.IDLE
        self._pressed_at = 0.0

    def combo_down(self, now: float) -> None:
        if self.state == State.IDLE:
            self.state = State.PRESSED
            self._pressed_at = now
            self.on_start()
        elif self.state == State.TOGGLED:
            # Zweites Antippen beendet das Diktat
            self.state = State.WAIT_RELEASE
            self.on_stop()

    def combo_up(self, now: float) -> None:
        if self.state == State.PRESSED:
            held = now - self._pressed_at
            if self._is_tap(held):
                self.state = State.TOGGLED
                log.debug("Antippen erkannt (%.2f s) → Aufnahme läuft weiter", held)
            else:
                self.state = State.IDLE
                self.on_stop()
        elif self.state == State.WAIT_RELEASE:
            self.state = State.IDLE

    def other_key(self) -> None:
        if self.state == State.PRESSED:
            self.state = State.WAIT_RELEASE
            self.on_cancel()

    def _is_tap(self, held: float) -> bool:
        if self.mode == "hold":
            return False  # jedes Loslassen beendet die Aufnahme
        if self.mode == "toggle":
            return True   # jedes Loslassen gilt als Antippen
        return held < self.hold_threshold


# --- Verbindung zur echten Tastatur -------------------------------------------------

# pynput unterscheidet linke/rechte Tasten. Wir fassen sie zu einem Namen zusammen.
_KEY_GROUPS: dict[str, set] = {
    "ctrl": {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r},
    "win": {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r},
    "alt": {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr},
    "shift": {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r},
}

# Eine Taste, die es auf keiner Tastatur gibt. Wir "drücken" sie, während die
# Win-Taste gehalten wird. Sonst denkt Windows beim Loslassen, Win wurde allein
# gedrückt, und öffnet das Startmenü. (Gleicher Trick wie bei AutoHotkey.)
_MASK_KEY = keyboard.KeyCode.from_vk(0xE8)


def _group_of(key) -> str | None:
    for name, members in _KEY_GROUPS.items():
        if key in members:
            return name
    return None


class HotkeyListener:
    def __init__(self, keys: list[str], machine: HotkeyStateMachine) -> None:
        self.keys = set(keys)
        self.machine = machine
        self._down: set[str] = set()  # welche Gruppen gerade gedrückt sind
        self._combo_active = False
        self._controller = keyboard.Controller()
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)

    def start(self) -> None:
        self._listener.start()  # läuft in einem eigenen Hintergrund-Thread

    def stop(self) -> None:
        self._listener.stop()

    def _on_press(self, key) -> None:
        if key == _MASK_KEY:
            return  # unser eigener Trick-Tastendruck
        group = _group_of(key)
        if group is None or group not in self.keys:
            # Eine "fremde" Taste: Teil einer anderen Tastenkombination
            self.machine.other_key()
            return
        self._down.add(group)
        if not self._combo_active and self._down == self.keys:
            self._combo_active = True
            if "win" in self.keys:
                self._controller.tap(_MASK_KEY)
            self.machine.combo_down(time.monotonic())

    def _on_release(self, key) -> None:
        group = _group_of(key)
        if group is None:
            return
        self._down.discard(group)
        if self._combo_active and group in self.keys:
            self._combo_active = False
            self.machine.combo_up(time.monotonic())
