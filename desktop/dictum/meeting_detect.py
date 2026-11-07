"""Merkt, wann ein Meeting beginnt, und fragt, ob Dictum aufnehmen soll.

Technik: Windows führt für jedes Programm Buch, wann es zuletzt das Mikrofon benutzt hat (das ist die Anzeige
"Mikrofon wird verwendet" in den Datenschutz-Einstellungen). Die Einträge liegen in der Registry unter
`HKCU\\Software\\Microsoft\\Windows\\CapabilityAccessManager\\ConsentStore\\microphone`: pro Programm ein Schlüssel mit
`LastUsedTimeStart` und `LastUsedTimeStop`. Ist Start größer als Stopp (oder Stopp 0), hört das Programm gerade zu.
Das braucht keine Rechte und kein Mikrofon-Öffnen, Dictum greift also nicht in den Ton ein.

Regeln, damit es nicht nervt:
- Es zählen nur Programme aus einer Liste (Teams, Zoom, Browser für Meet …, einstellbar in settings.toml).
- Erst wenn ein Programm das Mikrofon `seconds` Sekunden am Stück benutzt, kommt die Nachfrage (kurze Anrufe
  und Tests lösen nichts aus). Pro Nutzungsphase fragt Dictum nur einmal.
- Dictum nimmt **nie von selbst** auf: Die Nachfrage ist eine Benachrichtigung, erst der Klick startet.
  Aufnahmen brauchen die Einwilligung aller Beteiligten (§ 201 StGB).
- Läuft eine erkannte Aufnahme und das Programm gibt das Mikrofon `END_GRACE` Sekunden lang frei, fragt Dictum, ob es
  die Aufnahme beenden soll. So bleibt keine Aufnahme versehentlich stundenlang offen.
"""

from __future__ import annotations

import logging
import time
import winreg
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

CONSENT_KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
END_GRACE = 30.0  # Sekunden ohne Mikrofon, bevor "Meeting vorbei?" kommt

# Anzeigenamen für die Nachfrage (Suchbegriff → Name)
LABELS = {"teams": "Teams", "zoom": "Zoom", "webex": "Webex", "slack": "Slack", "discord": "Discord",
          "skype": "Skype", "whatsapp": "WhatsApp", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox"}


def apps_using_microphone() -> list[str]:
    """Namen (klein geschrieben) aller Programme, die das Mikrofon gerade benutzen.

    Store-Apps stehen mit ihrem Paketnamen direkt unter dem Schlüssel ("msteams_8wekyb3d8bbwe"), klassische
    Programme unter "NonPackaged" mit dem Pfad, in dem "\\" durch "#" ersetzt ist: Wir nehmen den Dateinamen.
    """
    found: list[str] = []

    def scan(path: str, packaged: bool) -> None:
        try:
            parent = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            return
        with parent:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(parent, index)
                except OSError:
                    break
                index += 1
                if name == "NonPackaged":
                    continue
                try:
                    with winreg.OpenKey(parent, name) as key:
                        start = winreg.QueryValueEx(key, "LastUsedTimeStart")[0]
                        stop = winreg.QueryValueEx(key, "LastUsedTimeStop")[0]
                except OSError:
                    continue
                if start > stop:
                    found.append(name.lower() if packaged else name.rsplit("#", 1)[-1].lower())

    scan(CONSENT_KEY, packaged=True)
    scan(CONSENT_KEY + r"\NonPackaged", packaged=False)
    return found


def label_for(name: str, apps: list[str]) -> str:
    for needle, label in LABELS.items():
        if needle in name:
            return label
    return name.removesuffix(".exe").capitalize()


@dataclass
class Detection:
    kind: str   # "start": Meeting scheint zu beginnen · "end": scheint vorbei
    app: str    # Anzeigename, z. B. "Zoom"


class MeetingDetector:
    def __init__(self, apps: list[str], seconds: float,
                 reader: Callable[[], list[str]] = apps_using_microphone,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.apps = apps
        self.seconds = seconds
        self._reader = reader
        self._clock = clock
        self._since: dict[str, float] = {}      # Programm → seit wann es das Mikrofon belegt
        self._asked: set[str] = set()           # Programme, bei denen in dieser Phase schon gefragt wurde
        self._watching: str | None = None       # Programm, dessen Meeting wir ggf. aufnehmen
        self._silent_since: float | None = None
        self._failed = False

    def _matching(self) -> set[str]:
        try:
            names = self._reader()
        except Exception:
            if not self._failed:
                log.exception("Mikrofon-Nutzung konnte nicht gelesen werden – Meeting-Erkennung pausiert")
            self._failed = True
            return set()
        wanted = [a.lower() for a in self.apps]
        return {n for n in names if any(a in n for a in wanted)}

    def poll(self, recording: bool) -> Detection | None:
        """Alle paar Sekunden aufrufen. `recording`: läuft gerade eine Meeting-Aufnahme?"""
        now = self._clock()
        using = self._matching()
        for name in list(self._since):
            if name not in using:                # freigegeben → die nächste Nutzung darf wieder fragen
                del self._since[name]
                self._asked.discard(name)
        for name in using:
            self._since.setdefault(name, now)

        if self._watching is not None:
            if self._watching in using:
                self._silent_since = None
            elif recording:
                if self._silent_since is None:
                    self._silent_since = now
                elif now - self._silent_since >= END_GRACE:
                    app, self._watching, self._silent_since = self._watching, None, None
                    return Detection("end", label_for(app, self.apps))
            else:
                self._watching = self._silent_since = None   # nicht aufgenommen und vorbei: nichts zu tun

        if not recording:
            for name in sorted(using):
                if name not in self._asked and now - self._since[name] >= self.seconds:
                    self._asked.add(name)
                    self._watching, self._silent_since = name, None
                    return Detection("start", label_for(name, self.apps))
        return None
