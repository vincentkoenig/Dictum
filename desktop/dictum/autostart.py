"""Dictum mit Windows starten – ohne Konsolenfenster.

Wie funktioniert Autostart unter Windows? In der Registry gibt es für jeden Benutzer
einen Schlüssel "Run" (HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run).
Jeder Eintrag darin ist ein Befehl, den Windows beim Anmelden ausführt. Dictum trägt dort
einen einzigen Eintrag namens "Dictum" ein – und entfernt ihn wieder, wenn man den Haken
im Tray-Menü wegnimmt. Es werden keine Administratorrechte gebraucht, und andere Benutzer
des PCs sind nicht betroffen.

Der Befehl sieht so aus:

    "…\\.venv\\Scripts\\pythonw.exe" -X utf8 "…\\desktop\\dictum_tray.pyw" --background

`pythonw.exe` ist Python OHNE Konsolenfenster (das "w" steht für "windowed"). Dadurch
erscheint beim Anmelden kein schwarzes Fenster, nur das Tray-Symbol.

Zieht man den Projektordner um oder baut die virtuelle Umgebung neu, stimmt der gespeicherte
Pfad nicht mehr. Deshalb prüft `refresh_if_enabled()` bei jedem Start, ob der Eintrag zum
aktuellen Pfad passt, und korrigiert ihn bei Bedarf selbst.
"""

from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

from .config import DESKTOP_DIR, FROZEN

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Dictum"
LAUNCHER = DESKTOP_DIR / "dictum_tray.pyw"


def build_command(python_exe: str | Path, launcher: str | Path | None) -> str:
    """Setzt den Befehl zusammen. Die Anführungszeichen sind wichtig: Liegt das Projekt
    in einem Ordner mit Leerzeichen, würde Windows den Pfad sonst zerschneiden.

    `--background`: Beim Anmelden soll Dictum still im Infobereich starten, ohne dass sich
    das Fenster öffnet. Von Hand gestartet (Doppelklick) öffnet sich dagegen das Fenster."""
    if launcher is None:  # als Programm (Dictum.exe) gibt es kein Startskript
        return f'"{python_exe}" --background'
    return f'"{python_exe}" -X utf8 "{launcher}" --background'


def background_python() -> Path:
    """Das Programm, das Dictum ohne Konsolenfenster startet: Dictum.exe, oder pythonw.exe beim Start aus
    dem Quellcode."""
    python = Path(sys.executable)
    if FROZEN:
        return python
    pythonw = python.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else python


def launch_args() -> list[str]:
    """Die Argumente, mit denen background_python() Dictum startet (ohne --background/--restart)."""
    return [] if FROZEN else ["-X", "utf8", str(LAUNCHER)]


def default_command() -> str:
    return build_command(background_python(), None if FROZEN else LAUNCHER)


def current_value(key_path: str = RUN_KEY) -> str | None:
    """Der aktuell gespeicherte Befehl oder None, wenn Autostart aus ist."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            value, _type = winreg.QueryValueEx(key, VALUE_NAME)
            return str(value)
    except FileNotFoundError:
        return None


def is_enabled(key_path: str = RUN_KEY) -> bool:
    return current_value(key_path) is not None


def enable(command: str | None = None, key_path: str = RUN_KEY) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command or default_command())
    log.info("Autostart eingeschaltet")


def disable(key_path: str = RUN_KEY) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        log.info("Autostart ausgeschaltet")
    except FileNotFoundError:
        pass  # war schon aus


def set_enabled(on: bool) -> None:
    enable() if on else disable()


def refresh_if_enabled(key_path: str = RUN_KEY, command: str | None = None) -> bool:
    """Ist Autostart an, aber der Pfad veraltet (Ordner verschoben, venv neu gebaut)?
    Dann korrigieren. Gibt True zurück, wenn etwas geändert wurde."""
    stored = current_value(key_path)
    wanted = command or default_command()
    if stored is not None and stored != wanted:
        enable(wanted, key_path)
        log.info("Autostart-Eintrag war veraltet und wurde korrigiert")
        return True
    return False
