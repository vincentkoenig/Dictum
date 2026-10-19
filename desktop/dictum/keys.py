"""Tastennamen: von der echten Taste zum Namen in settings.toml und zurück.

Dictum erlaubt jede Taste oder Kombination als Hotkey (wie Wispr Flow), auch Maustasten.
Damit das sauber bleibt, gibt es zwei Ebenen von Namen:

* **Konkrete Namen** beschreiben genau eine echte Taste: "ctrl_r", "f8", "a", "vk_173",
  "mouse_x1". So nennt `canonical()` jedes Ereignis von pynput.
* **Gruppen** ("ctrl", "win", "alt", "shift") meinen links ODER rechts. Sie stehen nur in
  settings.toml und werden mit `expand()` zu konkreten Namen aufgelöst.

Vergleichen heißt dann einfach: `canonical(ereignis) in expand(name)`. Das ist reine
Textlogik ohne Tastatur und lässt sich testen (tests/test_keys.py).

Außerdem hier: `check_hotkey()` (taugt die Kombination?) und `CaptureState`, die Logik
hinter dem Dialog "Drücke jetzt die gewünschte Taste".
"""

from __future__ import annotations

from pynput import keyboard, mouse

GROUPS: dict[str, frozenset[str]] = {
    "ctrl": frozenset({"ctrl_l", "ctrl_r"}),
    "win": frozenset({"win_l", "win_r"}),
    "alt": frozenset({"alt_l", "alt_r"}),
    "shift": frozenset({"shift_l", "shift_r"}),
}
MODIFIERS: frozenset[str] = frozenset(GROUPS) | frozenset().union(*GROUPS.values())

# pynput nennt manche Tasten doppelt (Key.cmd = Key.cmd_l …); hier die eine Schreibweise
_ALIASES = {
    "ctrl": "ctrl_l", "alt": "alt_l", "shift": "shift_l",
    "cmd": "win_l", "cmd_l": "win_l", "cmd_r": "win_r", "alt_gr": "alt_r",
}

MOUSE_NAMES = {
    mouse.Button.middle: "mouse_middle",
    mouse.Button.x1: "mouse_x1",
    mouse.Button.x2: "mouse_x2",
}  # linke und rechte Maustaste sind bewusst nicht dabei: sie braucht man zum Klicken

_SPECIAL = {k.name for k in keyboard.Key} - set(_ALIASES)
_FKEYS = {f"f{n}" for n in range(1, 25)}

# Diese Tasten darf man allein als Hotkey wählen, weil man mit ihnen sonst nicht tippt
_STANDALONE = (
    MODIFIERS | _FKEYS | set(MOUSE_NAMES.values())
    | {"caps_lock", "scroll_lock", "pause", "insert", "print_screen", "menu", "num_lock"}
)

LABELS = {
    "ctrl": "Strg", "win": "Win", "alt": "Alt", "shift": "Umschalt",
    "ctrl_l": "Strg links", "ctrl_r": "Strg rechts",
    "win_l": "Win links", "win_r": "Win rechts",
    "alt_l": "Alt links", "alt_r": "Alt rechts (AltGr)",
    "shift_l": "Umschalt links", "shift_r": "Umschalt rechts",
    "caps_lock": "Feststelltaste", "scroll_lock": "Rollen", "pause": "Pause",
    "insert": "Einfg", "print_screen": "Druck", "menu": "Menütaste", "num_lock": "Num",
    "space": "Leertaste", "enter": "Enter", "tab": "Tab", "esc": "Esc",
    "backspace": "Rücktaste", "delete": "Entf", "home": "Pos1", "end": "Ende",
    "page_up": "Bild ↑", "page_down": "Bild ↓",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "media_play_pause": "Wiedergabe", "media_stop": "Stopp", "media_next": "Nächster Titel",
    "media_previous": "Vorheriger Titel", "media_volume_up": "Lauter",
    "media_volume_down": "Leiser", "media_volume_mute": "Stumm",
    "mouse_middle": "Mausrad-Klick", "mouse_x1": "Maustaste 4 (zurück)",
    "mouse_x2": "Maustaste 5 (vor)",
}


def canonical(key) -> str | None:
    """Der konkrete Name zu einer Taste oder Maustaste von pynput (None = unbekannt)."""
    if isinstance(key, mouse.Button):
        return MOUSE_NAMES.get(key)
    if isinstance(key, keyboard.Key):
        return _ALIASES.get(key.name, key.name)
    vk = getattr(key, "vk", None)
    if vk is not None:
        # Buchstaben und Ziffern über den Tastencode benennen: Mit gedrückter Strg-Taste
        # meldet pynput sonst Steuerzeichen statt "a"
        if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
            return chr(vk).lower()
        return f"vk_{vk}"
    char = getattr(key, "char", None)
    return char.lower() if char else None


def expand(name: str) -> frozenset[str]:
    """Alle konkreten Namen, die zu einem Namen aus settings.toml gehören."""
    return GROUPS.get(name, frozenset({name}))


def is_valid_name(name: str) -> bool:
    if name in GROUPS or name in _SPECIAL or name in _FKEYS or name in MODIFIERS:
        return True
    if name in MOUSE_NAMES.values():
        return True
    if len(name) == 1 and name.isascii() and name.isalnum():
        return True
    return name.startswith("vk_") and name[3:].isdigit()


def label(name: str) -> str:
    if name in LABELS:
        return LABELS[name]
    if name.startswith("vk_"):
        return f"Taste {name[3:]}"
    return name.upper()


def hotkey_label(keys: list[str]) -> str:
    return "+".join(label(k) for k in keys) if keys else "Aus"


def check_hotkey(keys: list[str], *, allow_empty: bool = False) -> str | None:
    """None, wenn die Kombination als Hotkey taugt, sonst der Grund auf Deutsch."""
    if not keys:
        return None if allow_empty else "Bitte mindestens eine Taste wählen."
    for name in keys:
        if not is_valid_name(name):
            return f"Unbekannte Taste: {name}"
    if "esc" in keys:
        return "Esc ist zum Abbrechen einer Aufnahme reserviert."
    if not set(keys) & MODIFIERS and not set(keys) <= _STANDALONE and not all(
        k.startswith("vk_") and 166 <= int(k[3:]) <= 183 for k in keys  # Browser-/Medientasten
    ):
        return ("Diese Taste kommt beim normalen Tippen vor. Nimm eine Sondertaste "
                "(Strg rechts, F8 …) oder füge Strg, Alt, Umschalt oder Win hinzu.")
    return None


class CaptureState:
    """Die Logik hinter "Drücke jetzt die gewünschte Taste".

    Man drückt eine oder mehrere Tasten und lässt sie wieder los. Fertig ist die Eingabe,
    sobald ALLE losgelassen sind. Gemerkt wird der Höchststand, damit "Strg und R" auch
    dann als Kombination zählt, wenn man die Finger nacheinander hebt.
    """

    def __init__(self) -> None:
        self._down: set[str] = set()
        self._peak: list[str] = []  # in der Reihenfolge des Drückens

    def press(self, name: str) -> None:
        self._down.add(name)
        if name not in self._peak:
            self._peak.append(name)

    def release(self, name: str) -> list[str] | None:
        """Meldet die fertige Kombination (Sondertasten zuerst), wenn alles losgelassen ist."""
        self._down.discard(name)
        if self._down or not self._peak:
            return None
        done = sorted(self._peak, key=lambda k: k not in MODIFIERS)  # stabil: Reihenfolge bleibt
        self._peak = []
        return done

    @property
    def current(self) -> list[str]:
        return sorted(self._peak, key=lambda k: k not in MODIFIERS)
