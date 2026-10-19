"""In welchem Programm wird gerade diktiert?

Wispr Flow passt Stil und Statistik an das Programm an (Mail, Chat, Editor …). Dafür muss Dictum
wissen, welches Fenster beim Start der Aufnahme im Vordergrund war. Windows liefert das Fenster
(`GetForegroundWindow`), daraus die Prozess-Nummer, daraus den Programmnamen (`psutil`).

Alles bleibt lokal: Der Name landet nur im Verlauf auf diesem PC (siehe history.py), nie in der Cloud.
Programme mit Administratorrechten verweigern den Zugriff auf ihren Namen. Dann bleibt er leer, und das
Diktat funktioniert trotzdem.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import psutil
import win32gui
import win32process

log = logging.getLogger(__name__)

# Schönere Namen für häufige Programme (Dateiname ohne .exe, kleingeschrieben)
FRIENDLY = {
    "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "brave": "Brave", "opera": "Opera",
    "code": "VS Code", "cursor": "Cursor", "devenv": "Visual Studio", "pycharm64": "PyCharm",
    "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "outlook": "Outlook",
    "olk": "Outlook", "onenote": "OneNote", "teams": "Teams", "ms-teams": "Teams",
    "slack": "Slack", "discord": "Discord", "whatsapp": "WhatsApp", "telegram": "Telegram",
    "notepad": "Editor", "notepad++": "Notepad++", "obsidian": "Obsidian", "notion": "Notion",
    "windowsterminal": "Terminal", "powershell": "PowerShell", "cmd": "Eingabeaufforderung",
    "explorer": "Explorer", "claude": "Claude", "zoom": "Zoom", "thunderbird": "Thunderbird",
}


@dataclass(frozen=True)
class ActiveWindow:
    exe: str      # z. B. "chrome" (ohne .exe, klein)
    title: str    # Fenstertitel

    @property
    def app(self) -> str:
        """Anzeigename fürs Programm, z. B. "Chrome". Leer, wenn unbekannt."""
        if not self.exe:
            return ""
        return FRIENDLY.get(self.exe, self.exe[:1].upper() + self.exe[1:])


def active_window() -> ActiveWindow | None:
    """Das Fenster im Vordergrund oder None (z. B. beim Wechsel zwischen Fenstern)."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        title = win32gui.GetWindowText(hwnd)
        _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        log.debug("Vordergrundfenster nicht lesbar", exc_info=True)
        return None
    exe = ""
    try:
        name = psutil.Process(pid).name()
        exe = name[:-4].lower() if name.lower().endswith(".exe") else name.lower()
    except (psutil.Error, OSError):
        pass  # z. B. Zugriff verweigert bei Programmen mit Administratorrechten
    return ActiveWindow(exe=exe, title=title)


FIELD_TEXT_TIMEOUT = 1.5  # Sekunden: Manche Programme beantworten UI-Automation sehr langsam


def field_text(max_chars: int = 600) -> str:
    """Text im Eingabefeld mit dem Fokus (die letzten `max_chars` Zeichen) – oder "".

    Das nutzt "UI Automation", die Schnittstelle, über die auch Vorlese-Programme Fenster lesen.
    Passwortfelder werden nie gelesen. Die Abfrage läuft in einem Hilfs-Thread mit Zeitlimit, damit ein
    träges Programm das Diktat nicht aufhält.
    """
    import threading

    result: list[str] = []

    def read() -> None:
        try:
            import uiautomation as auto

            with auto.UIAutomationInitializerInThread():
                control = auto.GetFocusedControl()
                if control is None or getattr(control, "IsPassword", False):
                    return
                text = ""
                try:
                    pattern = control.GetValuePattern()
                    text = pattern.Value if pattern else ""
                except Exception:
                    pass
                if not text:
                    try:
                        pattern = control.GetTextPattern()
                        text = pattern.DocumentRange.GetText(max_chars * 4) if pattern else ""
                    except Exception:
                        pass
                result.append((text or "")[-max_chars:])
        except Exception:
            log.debug("Feldtext nicht lesbar", exc_info=True)

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    worker.join(FIELD_TEXT_TIMEOUT)
    return result[0] if result else ""
