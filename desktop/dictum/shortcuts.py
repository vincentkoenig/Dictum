"""Verknüpfungen (.lnk) auf dem Desktop und im Startmenü – damit Dictum wie ein richtiges Programm wirkt.

Eine Verknüpfung ist eine kleine Datei mit Ziel, Argumenten, Arbeitsordner und Symbol. Sie zeigt auf
`pythonw.exe` (Python ohne Konsolenfenster) mit dem Startskript `dictum_tray.pyw`, genauso wie der
Autostart (siehe autostart.py), nur ohne `--background`: Ein Doppelklick öffnet das Fenster.

Zwei Feinheiten:

* **Ordner nicht raten:** Der Desktop liegt bei vielen PCs in OneDrive. Windows weiß, wo er wirklich ist
  (`SHGetFolderPath`).
* **AppUserModelID:** Das ist der "Ausweis" eines Programms für die Taskleiste. Steht dieselbe ID in der
  Verknüpfung und im laufenden Prozess (`set_app_id`), zeigt die Taskleiste das Dictum-Symbol statt des
  Python-Symbols, und ein Anheften bleibt dem richtigen Programm zugeordnet.
"""

from __future__ import annotations

import ctypes
import logging
from pathlib import Path

import pythoncom
from win32com.propsys import propsys, pscon
from win32com.shell import shell, shellcon

from .autostart import background_python, launch_args
from .config import DESKTOP_DIR, FROZEN, RESOURCE_DIR

log = logging.getLogger(__name__)

APP_ID = "VincentKoenig.Dictum"
ICON_PATH = RESOURCE_DIR / "assets" / "dictum.ico"
NAME = "Dictum.lnk"

_FOLDERS = {
    "desktop": shellcon.CSIDL_DESKTOPDIRECTORY,
    "start_menu": shellcon.CSIDL_PROGRAMS,  # Startmenü → Alle Apps
}


def set_app_id() -> None:
    """Dem laufenden Prozess die AppUserModelID geben (vor dem ersten Fenster aufrufen)."""
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def folder_for(kind: str) -> Path:
    return Path(shell.SHGetFolderPath(0, _FOLDERS[kind], 0, 0))


def path_for(kind: str, folder: Path | None = None) -> Path:
    return (folder or folder_for(kind)) / NAME


def is_present(kind: str, folder: Path | None = None) -> bool:
    return path_for(kind, folder).exists()


def create(kind: str, folder: Path | None = None) -> Path:
    """Legt die Verknüpfung an (oder ersetzt sie). `folder` gibt es für Tests."""
    path = path_for(kind, folder)
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
    )
    link.SetPath(str(background_python()))
    link.SetArguments(" ".join(f'"{a}"' if " " in a else a for a in launch_args()))
    link.SetWorkingDirectory(str(background_python().parent if FROZEN else DESKTOP_DIR))
    link.SetDescription("Dictum – Diktieren und Gespräche aufnehmen")
    if ICON_PATH.exists():
        link.SetIconLocation(str(ICON_PATH), 0)

    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID))
    store.Commit()

    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), 0)
    log.info("Verknüpfung angelegt: %s", path)
    return path


def remove(kind: str, folder: Path | None = None) -> None:
    path = path_for(kind, folder)
    if path.exists():
        path.unlink()
        log.info("Verknüpfung entfernt: %s", path)


def read(path: Path) -> dict[str, str]:
    """Liest eine Verknüpfung zurück (für Tests und Fehlersuche)."""
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
    )
    link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(path))
    return {
        "target": link.GetPath(shell.SLGP_RAWPATH)[0],
        "arguments": link.GetArguments(),
        "working_dir": link.GetWorkingDirectory(),
        "icon": link.GetIconLocation()[0],
    }
