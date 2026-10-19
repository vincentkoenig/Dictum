"""Globaler Hotkey: halten zum Sprechen ODER antippen für Start/Stopp.

Aufgeteilt in zwei Teile:

1. `HotkeyStateMachine` – die reine Logik, OHNE Tastatur. Sie bekommt nur gemeldet
   "Kombination gedrückt / losgelassen / andere Taste" und entscheidet, ob eine
   Aufnahme startet, endet oder verworfen wird. Weil sie nichts von der echten
   Tastatur weiß, kann man sie leicht testen (siehe tests/test_hotkey.py).

2. `HotkeyListener` – hört mit `pynput` systemweit auf Tastatur (und bei Bedarf Maus),
   merkt sich, welche Tasten gerade gedrückt sind, und meldet das an die Zustandsmaschine.
   Welche Taste wie heißt, steht in `keys.py`.

Die Zustände:

    IDLE ──Kombi gedrückt──► PRESSED ──losgelassen nach ≥ Schwelle──► (stop) IDLE
                               │
                               └──losgelassen vor Schwelle──► TOGGLED
                                                                │
    IDLE ◄──losgelassen── WAIT_RELEASE ◄──Kombi erneut gedrückt (stop)┘

Wird während PRESSED eine andere Taste gedrückt (z. B. C, weil man mit der rechten
Strg-Taste Strg+C drücken wollte), war das kein Diktat → Aufnahme wird verworfen (cancel).
Esc bricht jede laufende Aufnahme ab (`escape`), auch eine angetippte.
"""

from __future__ import annotations

import enum
import logging
import time
from typing import Callable

from pynput import keyboard, mouse

from .keys import GROUPS, CaptureState, canonical, expand, hotkey_label  # noqa: F401

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

    def escape(self) -> None:
        """Esc: laufende Aufnahme verwerfen. Ohne Aufnahme tut es nichts (Esc bleibt normal)."""
        if self.state == State.PRESSED:
            self.state = State.WAIT_RELEASE  # Tasten sind noch unten: erst loslassen lassen
            self.on_cancel()
        elif self.state == State.TOGGLED:
            self.state = State.IDLE
            self.on_cancel()

    def _is_tap(self, held: float) -> bool:
        if self.mode == "hold":
            return False  # jedes Loslassen beendet die Aufnahme
        if self.mode == "toggle":
            return True   # jedes Loslassen gilt als Antippen
        return held < self.hold_threshold


# --- Verbindung zur echten Tastatur und Maus ------------------------------------------

# Eine Taste, die es auf keiner Tastatur gibt. Wir "drücken" sie, während die
# Win-Taste gehalten wird. Sonst denkt Windows beim Loslassen, Win wurde allein
# gedrückt, und öffnet das Startmenü. (Gleicher Trick wie bei AutoHotkey.)
_MASK_KEY = keyboard.KeyCode.from_vk(0xE8)
_MASK_NAME = "vk_232"
_WIN_NAMES = GROUPS["win"]


class _Combo:
    """Eine Tastenkombination und der Stand, wie viel davon gerade gedrückt ist."""

    def __init__(self, keys: list[str], on_down: Callable[[], None],
                 on_up: Callable[[], None] | None = None) -> None:
        self.keys = list(keys)
        self.on_down = on_down
        self.on_up = on_up
        self.down: set[str] = set()   # welche Namen aus `keys` gerade gedrückt sind
        self.active = False

    def match(self, name: str) -> str | None:
        """Zu welchem Namen aus settings.toml gehört die konkrete Taste? None = zu keinem."""
        for configured in self.keys:
            if name in expand(configured):
                return configured
        return None

    @property
    def uses_win(self) -> bool:
        return any(expand(k) & _WIN_NAMES for k in self.keys)

    @property
    def uses_mouse(self) -> bool:
        return any(k.startswith("mouse_") for k in self.keys)


class HotkeyListener:
    """Hört systemweit auf Tastatur und (bei Bedarf) Maustasten.

    Das Diktat-Hotkey läuft über die Zustandsmaschine. Weitere Kombinationen (z. B. "letztes
    Diktat einfügen") sind einfache Auslöser: Sobald die Kombination komplett gedrückt ist,
    wird ihre Funktion einmal aufgerufen. Tasten lassen sich zur Laufzeit austauschen
    (`set_keys`, `set_trigger`) – ein Neustart ist dafür nicht nötig.
    """

    def __init__(self, keys: list[str], machine: HotkeyStateMachine) -> None:
        self.machine = machine
        self._main = _Combo(keys, lambda: machine.combo_down(time.monotonic()),
                            lambda: machine.combo_up(time.monotonic()))
        self._triggers: dict[str, _Combo] = {}
        self._controller = keyboard.Controller()
        self._keyboard = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._mouse: mouse.Listener | None = None
        self.enabled = True

    def set_enabled(self, enabled: bool) -> None:
        """Pausieren (z. B. während der Dialog "Taste wählen" offen ist). Beim Wechsel wird
        gemerkt Gedrücktes vergessen, damit nach der Pause nichts hängen bleibt."""
        self.enabled = enabled
        for combo in [self._main, *self._triggers.values()]:
            combo.down.clear()
            combo.active = False

    @property
    def keys(self) -> set[str]:
        return set(self._main.keys)

    def start(self) -> None:
        self._keyboard.start()  # läuft in einem eigenen Hintergrund-Thread
        self._sync_mouse()

    def stop(self) -> None:
        self._keyboard.stop()
        if self._mouse:
            self._mouse.stop()

    def set_keys(self, keys: list[str]) -> None:
        """Neue Diktat-Taste ab sofort."""
        self._main = _Combo(keys, self._main.on_down, self._main.on_up)
        self._sync_mouse()

    def set_trigger(self, trigger_id: str, keys: list[str], callback: Callable[[], None]) -> None:
        """Eine Zusatz-Kombination anlegen oder ändern. Leere Liste = ausschalten."""
        if keys:
            self._triggers[trigger_id] = _Combo(keys, callback)
        else:
            self._triggers.pop(trigger_id, None)
        self._sync_mouse()

    def name_for(self, key) -> str | None:
        """Zu welcher Hotkey-Taste gehört diese echte Taste? None = gehört nicht dazu."""
        name = canonical(key)
        return self._main.match(name) if name else None

    # --- Ereignisse -------------------------------------------------------------------

    def _on_press(self, key) -> None:
        self._press(canonical(key))

    def _on_release(self, key) -> None:
        self._release(canonical(key))

    def _on_click(self, _x, _y, button, pressed) -> None:
        (self._press if pressed else self._release)(canonical(button))

    def _press(self, name: str | None) -> None:
        if name == _MASK_NAME or not self.enabled:
            return  # unser eigener Trick-Tastendruck bzw. pausiert
        if name == "esc":
            self.machine.escape()
        for combo in list(self._triggers.values()):
            self._combo_press(combo, name)
        if not self._combo_press(self._main, name):
            # Eine "fremde" Taste: Teil einer anderen Tastenkombination
            self.machine.other_key()

    def _combo_press(self, combo: _Combo, name: str | None) -> bool:
        configured = combo.match(name) if name else None
        if configured is None:
            return False
        combo.down.add(configured)
        # `active` verhindert, dass die automatische Tastenwiederholung beim
        # Gedrückthalten immer wieder neu auslöst
        if not combo.active and combo.down == set(combo.keys):
            combo.active = True
            if combo.uses_win:
                self._controller.tap(_MASK_KEY)
            combo.on_down()
        return True

    def _release(self, name: str | None) -> None:
        if not name or not self.enabled:
            return
        for combo in [self._main, *self._triggers.values()]:
            configured = combo.match(name)
            if configured is None:
                continue
            combo.down.discard(configured)
            if combo.active:
                combo.active = False
                if combo.on_up:
                    combo.on_up()

    # --- Maus -------------------------------------------------------------------------

    def _sync_mouse(self) -> None:
        """Den Maus-Hook nur laufen lassen, wenn eine Maustaste belegt ist: Ein globaler
        Maus-Hook bremst sonst ohne Grund jede Mausbewegung ein wenig."""
        needed = self._main.uses_mouse or any(c.uses_mouse for c in self._triggers.values())
        running = self._mouse is not None
        if needed and not running and self._keyboard.running:
            self._mouse = mouse.Listener(on_click=self._on_click)
            self._mouse.start()
        elif not needed and running:
            self._mouse.stop()
            self._mouse = None


class KeyCapture:
    """Hört auf die nächste Tastenkombination (für den Dialog "Taste ändern").

    `on_update(keys)` meldet laufend, was gerade gedrückt ist, `on_done(keys)` die fertige
    Kombination, sobald alles losgelassen ist. Beide Rückrufe kommen aus einem
    Hintergrund-Thread.
    """

    def __init__(self, on_update: Callable[[list[str]], None], on_done: Callable[[list[str]], None]) -> None:
        self._state = CaptureState()
        self._on_update = on_update
        self._on_done = on_done
        self._finished = False
        self._keyboard = keyboard.Listener(on_press=lambda k: self._press(canonical(k)),
                                           on_release=lambda k: self._release(canonical(k)))
        self._mouse = mouse.Listener(
            on_click=lambda _x, _y, b, pressed: (self._press if pressed else self._release)(canonical(b)))

    def start(self) -> None:
        self._keyboard.start()
        self._mouse.start()

    def stop(self) -> None:
        self._keyboard.stop()
        self._mouse.stop()

    def _press(self, name: str | None) -> None:
        if not name or self._finished:
            return
        self._state.press(name)
        self._on_update(self._state.current)

    def _release(self, name: str | None) -> None:
        if not name or self._finished:
            return
        done = self._state.release(name)
        if done is not None:
            self._finished = True
            self._on_done(done)
