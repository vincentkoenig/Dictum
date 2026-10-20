"""Einstiegspunkt: `python -m dictum` (aus dem Ordner desktop/) oder dictum_tray.pyw."""

import argparse
import ctypes
import logging
import sys

from . import autostart
from .config import DESKTOP_DIR, ensure_user_dir, load_env, load_settings
from .logsetup import setup_logging
from .single_instance import SingleInstance

log = logging.getLogger("dictum")


def _breadcrumb(text: str) -> None:
    """Eine Zeile in start.log, ganz am Anfang, noch bevor irgendetwas anderes passiert. So lässt sich später
    sehen, ob Windows Dictum beim Anmelden überhaupt gestartet hat und wie weit es kam. Die Datei behält
    die letzten 200 Zeilen."""
    try:
        from datetime import datetime

        path = DESKTOP_DIR / "start.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        lines.append(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}")
        path.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
    except Exception:
        pass  # Diagnose darf den Start nie verhindern


def main() -> None:
    _breadcrumb(f"Start: {' '.join(sys.argv[1:]) or '(ohne Argumente)'}")
    try:
        _main()
    except SystemExit:
        raise
    except BaseException:
        import traceback

        _breadcrumb("ABSTURZ beim Start:\n" + traceback.format_exc())
        raise


def _main() -> None:
    parser = argparse.ArgumentParser(prog="dictum")
    parser.add_argument("--quiet", action="store_true",
                        help="bei einem zweiten Start keine Meldung anzeigen (für Tests/Skripte)")
    parser.add_argument("--background", action="store_true",
                        help="still im Infobereich starten, ohne das Fenster zu öffnen (Autostart)")
    parser.add_argument("--install-shortcuts", action="store_true",
                        help="Verknüpfungen auf dem Desktop und im Startmenü anlegen und beenden")
    parser.add_argument("--install", action="store_true",
                        help="Verknüpfungen anlegen und Autostart einschalten (für die installierte .exe)")
    parser.add_argument("--restart", action="store_true",
                        help="Neustart: wartet, bis die alte Instanz beendet ist")
    args = parser.parse_args()

    ensure_user_dir()  # nur als Programm (.exe): Datenordner und Standard-Einstellungen anlegen
    setup_logging()

    if args.install:
        from . import shortcuts

        for kind in ("desktop", "start_menu"):
            print("angelegt:", shortcuts.create(kind))
        autostart.enable()
        print("Autostart eingeschaltet")
        return

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
        _breadcrumb("läuft bereits, beende diese Instanz")
        if not (args.quiet or args.background):  # beim Autostart (zwei Wege!) keine Meldung
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
