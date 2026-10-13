"""Symbol unten rechts in der Taskleiste – darüber wird Dictum bedient und beendet.

`pystray` zeichnet das Symbol und das Rechtsklick-Menü. Das Bild erzeugen wir mit
Pillow direkt im Code (ein stilisiertes Mikrofon), so braucht es keine Bilddatei.
"""

from __future__ import annotations

from typing import Callable

import pystray
from PIL import Image, ImageDraw

MODE_LABELS = {
    "both": "Halten oder Antippen",
    "hold": "Nur Halten",
    "toggle": "Nur Antippen",
}

LANGUAGE_LABELS = {
    "de": "Deutsch",
    "en": "Englisch",
    "auto": "Automatisch (langsamer)",
}


def _draw_icon() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size - 1, size - 1), fill=(31, 31, 35, 255))
    white = (242, 242, 242, 255)
    d.rounded_rectangle((24, 12, 40, 38), radius=8, fill=white)   # Mikrofon-Kopf
    d.arc((17, 22, 47, 46), start=0, end=180, fill=white, width=3)  # Halterung
    d.line((32, 46, 32, 52), fill=white, width=3)                 # Stiel
    d.line((24, 52, 40, 52), fill=white, width=3)                 # Fuß
    return img


class Tray:
    def __init__(
        self,
        hotkey_label: str,
        get_mode: Callable[[], str],
        set_mode: Callable[[str], None],
        get_language: Callable[[], str],
        set_language: Callable[[str], None],
        on_quit: Callable[[], None],
    ) -> None:
        def radio_item(label: str, value: str, get, set_) -> pystray.MenuItem:
            # Eine eigene Funktion pro Eintrag "merkt" sich ihren Wert. Lambdas direkt in
            # der Schleife würden am Ende alle auf den letzten Wert zeigen.
            return pystray.MenuItem(
                label,
                lambda: set_(value),
                checked=lambda _item: get() == value,
                radio=True,
            )

        modes = [radio_item(l, v, get_mode, set_mode) for v, l in MODE_LABELS.items()]
        langs = [radio_item(l, v, get_language, set_language) for v, l in LANGUAGE_LABELS.items()]

        menu = pystray.Menu(
            pystray.MenuItem(f"Dictum – {hotkey_label}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Modus", pystray.Menu(*modes)),
            pystray.MenuItem("Sprache", pystray.Menu(*langs)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", lambda: on_quit()),
        )
        self.icon = pystray.Icon("dictum", _draw_icon(), f"Dictum ({hotkey_label})", menu)

    def start(self) -> None:
        # run_detached: das Symbol läuft im Hintergrund, der Hauptthread bleibt für tkinter frei
        self.icon.run_detached()

    def stop(self) -> None:
        self.icon.stop()
