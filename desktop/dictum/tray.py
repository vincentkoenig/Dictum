"""Symbol unten rechts in der Taskleiste – darüber wird Dictum bedient und beendet.

`pystray` zeichnet das Symbol und das Rechtsklick-Menü. Das Bild erzeugen wir mit
Pillow direkt im Code (ein stilisiertes Mikrofon), so braucht es keine Bilddatei.

Das Menü liest und ändert Einstellungen direkt an der App (`app.get(...)`,
`app.set(...)`). pystray fragt `checked` bei jedem Öffnen des Menüs neu ab – so zeigen
die Häkchen immer den aktuellen Stand.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw

if TYPE_CHECKING:  # nur für die Typprüfung, verhindert einen Import-Kreis
    from .app import DictumApp

# Jede Option: interner Wert → Beschriftung im Menü
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
ENGINE_LABELS = {
    "local": "Lokal (privat, kostenlos)",
    "openai": "OpenAI-Cloud (schneller)",
}
PROVIDER_LABELS = {
    "anthropic": "Claude",
    "openai": "OpenAI",
}


TEMPLATE_LABELS = {
    "meeting": "Meeting",
    "interview": "Interview",
    "lecture": "Vorlesung",
    "note": "Notiz",
}


def _draw_icon(recording: bool = False) -> Image.Image:
    """Mikrofon auf dunklem Kreis – während einer Meeting-Aufnahme auf rotem Kreis."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size - 1, size - 1), fill=(229, 72, 77, 255) if recording else (31, 31, 35, 255))
    white = (242, 242, 242, 255)
    d.rounded_rectangle((24, 12, 40, 38), radius=8, fill=white)   # Mikrofon-Kopf
    d.arc((17, 22, 47, 46), start=0, end=180, fill=white, width=3)  # Halterung
    d.line((32, 46, 32, 52), fill=white, width=3)                 # Stiel
    d.line((24, 52, 40, 52), fill=white, width=3)                 # Fuß
    return img


class Tray:
    def __init__(self, app: DictumApp, hotkey_label: str) -> None:
        def radio_menu(setting: str, labels: dict[str, str]) -> pystray.Menu:
            """Untermenü mit Auswahlpunkten für eine Einstellung."""
            def item(value: str, label: str) -> pystray.MenuItem:
                # Eigene Funktion pro Eintrag, damit sich jeder Eintrag "seinen" Wert merkt.
                # Lambdas direkt in einer Schleife würden alle auf den letzten Wert zeigen.
                return pystray.MenuItem(
                    label,
                    lambda: app.set(setting, value),
                    checked=lambda _item: app.get(setting) == value,
                    radio=True,
                )
            return pystray.Menu(*(item(v, l) for v, l in labels.items()))

        meetings = app.meetings

        def start_item(template: str, label: str) -> pystray.MenuItem:
            return pystray.MenuItem(label, lambda: meetings.start(template))

        def stop_text(_item) -> str:
            m, s = divmod(int(meetings.elapsed), 60)
            return f"⏹ Meeting beenden ({m:02d}:{s:02d})"

        menu = pystray.Menu(
            pystray.MenuItem(f"Dictum – {hotkey_label}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            # Während der Aufnahme sieht man nur "beenden", sonst nur "aufnehmen"
            pystray.MenuItem(stop_text, lambda: meetings.stop(), visible=lambda _i: meetings.is_recording),
            pystray.MenuItem(
                "🔴 Meeting aufnehmen",
                pystray.Menu(*(start_item(t, l) for t, l in TEMPLATE_LABELS.items())),
                visible=lambda _i: not meetings.is_recording,
            ),
            pystray.MenuItem(
                "Letztes Meeting öffnen",
                lambda: meetings.open_last(),
                enabled=lambda _i: meetings.last_recording_id is not None,
            ),
            pystray.MenuItem("Dictum im Web öffnen", lambda: meetings.open_web()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "KI-Bereinigung",
                lambda: app.set("cleanup", not app.get("cleanup")),
                checked=lambda _item: app.get("cleanup"),
            ),
            pystray.MenuItem("KI-Anbieter", radio_menu("provider", PROVIDER_LABELS)),
            pystray.MenuItem("Spracherkennung", radio_menu("engine", ENGINE_LABELS)),
            pystray.MenuItem("Sprache", radio_menu("language", LANGUAGE_LABELS)),
            pystray.MenuItem("Modus", radio_menu("mode", MODE_LABELS)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Wörterbuch bearbeiten", lambda: app.open_dictionary()),
            pystray.MenuItem("Snippets bearbeiten", lambda: app.open_snippets()),
            pystray.MenuItem("Mit Cloud abgleichen", lambda: meetings.sync_now()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", lambda: app.quit()),
        )
        self.hotkey_label = hotkey_label
        self.icon = pystray.Icon("dictum", _draw_icon(), f"Dictum ({hotkey_label})", menu)
        self._recording_shown = False

    def refresh(self, recording: bool, elapsed: float) -> None:
        """Symbol, Tooltip und Menü an den aktuellen Zustand anpassen."""
        if recording != self._recording_shown:
            self.icon.icon = _draw_icon(recording)
            self._recording_shown = recording
        if recording:
            m, s = divmod(int(elapsed), 60)
            self.icon.title = f"Dictum – Meeting läuft {m:02d}:{s:02d}"
        else:
            self.icon.title = f"Dictum ({self.hotkey_label})"
        self.icon.update_menu()

    def notify(self, title: str, message: str) -> None:
        """Windows-Benachrichtigung unten rechts."""
        try:
            self.icon.notify(message, title)
        except Exception:
            pass  # Benachrichtigungen sind nett, aber nicht wichtig

    def start(self) -> None:
        # run_detached: das Symbol läuft im Hintergrund, der Hauptthread bleibt für tkinter frei
        self.icon.run_detached()

    def stop(self) -> None:
        self.icon.stop()
