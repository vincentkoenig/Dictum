"""Einstiegspunkt: `python -m dictum` (aus dem Ordner desktop/) oder dictum_tray.pyw."""

import argparse
import ctypes
import logging

from . import autostart
from .config import load_env, load_settings
from .logsetup import setup_logging
from .single_instance import SingleInstance

log = logging.getLogger("dictum")


def main() -> None:
    parser = argparse.ArgumentParser(prog="dictum")
    parser.add_argument("--quiet", action="store_true",
                        help="bei einem zweiten Start keine Meldung anzeigen (für Tests/Skripte)")
    args = parser.parse_args()

    setup_logging()

    instance = SingleInstance()
    if instance.already_running:
        log.warning("Dictum läuft bereits – dieser Start wird beendet.")
        if not args.quiet:
            # 0x40 = Info-Symbol. Ohne Konsole (pythonw) wäre das sonst die einzige Rückmeldung.
            ctypes.windll.user32.MessageBoxW(
                0,
                "Dictum läuft bereits.\n\nDas Mikrofon-Symbol findest du unten rechts in der "
                "Taskleiste (evtl. hinter dem ^-Pfeil).",
                "Dictum",
                0x40,
            )
        return

    # Scharfe Schrift auf hochauflösenden Bildschirmen (sonst skaliert Windows unscharf)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass

    load_env()  # API-Keys aus .env laden, bevor die KI-Clients erzeugt werden
    settings = load_settings()
    autostart.refresh_if_enabled()  # veralteten Autostart-Pfad selbst korrigieren

    # Import erst hier: lädt die schweren Bibliotheken (Whisper, Qt …) nicht, wenn Dictum
    # ohnehin gleich wieder endet, weil schon eine Instanz läuft
    from .app import DictumApp

    log.info("Dictum startet")
    DictumApp(settings).run()
    log.info("Dictum beendet")


if __name__ == "__main__":
    main()
