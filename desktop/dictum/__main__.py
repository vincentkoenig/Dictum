"""Einstiegspunkt: `python -m dictum` (aus dem Ordner desktop/) oder dictum_tray.pyw."""

import argparse
import ctypes
import logging
import sys

from . import autostart
from .config import load_env, load_settings
from .logsetup import setup_logging
from .single_instance import SingleInstance

log = logging.getLogger("dictum")


def main() -> None:
    parser = argparse.ArgumentParser(prog="dictum")
    parser.add_argument("--quiet", action="store_true",
                        help="bei einem zweiten Start keine Meldung anzeigen (für Tests/Skripte)")
    parser.add_argument("--background", action="store_true",
                        help="still im Infobereich starten, ohne das Fenster zu öffnen (Autostart)")
    parser.add_argument("--install-shortcuts", action="store_true",
                        help="Verknüpfungen auf dem Desktop und im Startmenü anlegen und beenden")
    parser.add_argument("--restart", action="store_true",
                        help="Neustart: wartet, bis die alte Instanz beendet ist")
    args = parser.parse_args()

    setup_logging()

    if args.install_shortcuts:
        from . import shortcuts

        for kind in ("desktop", "start_menu"):
            print("angelegt:", shortcuts.create(kind))
        return

    # Vor dem ersten Fenster: Die Taskleiste zeigt dann das Dictum-Symbol statt "Python"
    from . import shortcuts

    shortcuts.set_app_id()

    # Nach einem Neustart läuft die alte Instanz noch kurz: bis zu 20 s auf sie warten
    instance = SingleInstance(wait_seconds=20 if args.restart else 0)
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

    # Hinweis: Eine DPI-Einstellung wie früher ist nicht mehr nötig. Qt skaliert auf
    # hochauflösenden Bildschirmen selbst.

    load_env()  # API-Keys aus .env laden, bevor die KI-Clients erzeugt werden
    settings = load_settings()
    autostart.refresh_if_enabled()  # veralteten Autostart-Pfad selbst korrigieren

    # Import erst hier: lädt die schweren Bibliotheken (Whisper, Qt …) nicht, wenn Dictum
    # ohnehin gleich wieder endet, weil schon eine Instanz läuft
    from .app import DictumApp

    log.info("Dictum startet%s", " (im Hintergrund)" if args.background else "")
    code = DictumApp(settings, show_window=not args.background).run()
    log.info("Dictum beendet")
    instance.release()
    sys.exit(code)


if __name__ == "__main__":
    main()
