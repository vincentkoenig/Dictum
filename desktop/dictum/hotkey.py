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

Wird während PRESSED eine andere Taste gedrückt (z. B. C, weil man mit der rechten
Strg-Taste Strg+C drücken wollte), war das kein Diktat → Aufnahme wird verworfen (cancel).
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

# Welche echten Tasten hinter einem Namen aus settings.toml stehen.
# - Gruppen ("ctrl") meinen die linke ODER rechte Taste.
# - Einzeltasten ("ctrl_r") meinen genau eine Seite. Praktisch, weil z. B. die rechte
#   Strg-Taste im Alltag kaum benutzt wird und sich gut als Ein-Tasten-Hotkey eignet.
K = keyboard.Key
KEY_MAP: dict[str, set] = {
    "ctrl": {K.ctrl, K.ctrl_l, K.ctrl_r},
    "win": {K.cmd, K.cmd_l, K.cmd_r},
    "alt": {K.alt, K.alt_l, K.alt_r, K.alt_gr},
    "shift": {K.shift, K.shift_l, K.shift_r},
    "ctrl_l": {K.ctrl_l},
    "ctrl_r": {K.ctrl_r},
    "alt_l": {K.alt_l},
    "shift_l": {K.shift_l},
    "shift_r": {K.shift_r},
    **{f"f{n}": {getattr(K, f"f{n}")} for n in range(1, 13)},
}

# Für Tray-Tooltip und Menü
KEY_LABELS: dict[str, str] = {
    "ctrl": "Strg", "win": "Win", "alt": "Alt", "shift": "Umschalt",
    "ctrl_l": "Strg links", "ctrl_r": "Strg rechts", "alt_l": "Alt links",
    "shift_l": "Umschalt links", "shift_r": "Umschalt rechts",
    **{f"f{n}": f"F{n}" for n in range(1, 13)},
}


def hotkey_label(keys: list[str]) -> str:
    return "+".join(KEY_LABELS[k] for k in keys)

# Eine Taste, die es auf keiner Tastatur gibt. Wir "drücken" sie, während die
# Win-Taste gehalten wird. Sonst denkt Windows beim Loslassen, Win wurde allein
# gedrückt, und öffnet das Startmenü. (Gleicher Trick wie bei AutoHotkey.)
_MASK_KEY = keyboard.KeyCode.from_vk(0xE8)


class HotkeyListener:
    def __init__(self, keys: list[str], machine: HotkeyStateMachine) -> None:
        self.keys = set(keys)
        self.machine = machine
        self._down: set[str] = set()  # welche Hotkey-Tasten gerade gedrückt sind
        self._combo_active = False
        self._controller = keyboard.Controller()
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)

    def start(self) -> None:
        self._listener.start()  # läuft in einem eigenen Hintergrund-Thread

    def stop(self) -> None:
        self._listener.stop()

    def name_for(self, key) -> str | None:
        """Zu welcher Hotkey-Taste gehört diese echte Taste? None = gehört nicht dazu."""
        for name in self.keys:
            if key in KEY_MAP[name]:
                return name
        return None

    def _on_press(self, key) -> None:
        if key == _MASK_KEY:
            return  # unser eigener Trick-Tastendruck
        name = self.name_for(key)
        if name is None:
            # Eine "fremde" Taste: Teil einer anderen Tastenkombination
            self.machine.other_key()
            return
        self._down.add(name)
        # _combo_active verhindert, dass die automatische Tastenwiederholung beim
        # Gedrückthalten immer wieder neue Aufnahmen startet
        if not self._combo_active and self._down == self.keys:
            self._combo_active = True
            if "win" in self.keys:
                self._controller.tap(_MASK_KEY)
            self.machine.combo_down(time.monotonic())

    def _on_release(self, key) -> None:
        name = self.name_for(key)
        if name is None:
            return
        self._down.discard(name)
        if self._combo_active:
            self._combo_active = False
            self.machine.combo_up(time.monotonic())
