"""Merkt, wann ein Meeting beginnt, und fragt, ob Dictum aufnehmen soll.

Technik: Jedes Programm, das ein Mikrofon benutzt, bekommt von Windows eine "Audio-Sitzung" auf dem Aufnahmegerät
(dasselbe System wie der Lautstärkemixer, nur für Aufnahme). Eine Sitzung ist *aktiv*, solange das Programm wirklich
Ton aufnimmt, und *inaktiv*, wenn es nur geöffnet ist (Teams und Zoom haben auch im Leerlauf eine). Dictum fragt
über `pycaw` alle Aufnahmegeräte nach aktiven Sitzungen und liest die Programmnamen dazu. Das öffnet das Mikrofon
nicht und stört kein Meeting.

Warum nicht die Registry ("ConsentStore\\microphone", die Quelle der Mikrofon-Anzeige in den Datenschutz-Einstellungen)?
Das war der erste Versuch. Auf diesem PC hat Windows die Einträge seit Wochen nicht mehr aktualisiert, auch für
Dictum selbst nicht: Die Erkennung hätte nie angeschlagen. Die Audio-Sitzungen laufen live (geprüft mit Teams, Zoom
und einem offenen Mikrofon).

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
import threading
import time
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

END_GRACE = 30.0  # Sekunden ohne Mikrofon, bevor "Meeting vorbei?" kommt
E_CAPTURE = 1            # Aufnahmegeräte (0 wäre Wiedergabe)
DEVICE_ACTIVE = 1        # nur eingesteckte, eingeschaltete Geräte
SESSION_ACTIVE = 1       # Sitzungszustand: 0 inaktiv, 1 aktiv, 2 abgelaufen
QUERY_TIMEOUT = 3.0      # so lange darf die Abfrage höchstens dauern

# Anzeigenamen für die Nachfrage (Suchbegriff → Name)
LABELS = {"teams": "Teams", "zoom": "Zoom", "webex": "Webex", "slack": "Slack", "discord": "Discord",
          "skype": "Skype", "whatsapp": "WhatsApp", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox"}


def _active_capture_names() -> list[str]:
    """Programmnamen (klein geschrieben) mit aktiver Sitzung auf irgendeinem Aufnahmegerät. Eigener Thread nötig."""
    import gc

    import comtypes

    comtypes.CoInitialize()
    try:
        return _read_active_sessions()
    finally:
        # Alle COM-Objekte müssen freigegeben sein, BEVOR CoUninitialize läuft: Sonst gibt Python sie danach frei
        # und der Prozess stürzt ab (beobachtet: Segmentation fault).
        gc.collect()
        comtypes.CoUninitialize()


def _read_active_sessions() -> list[str]:
    import comtypes
    import psutil
    from comtypes import CLSCTX_ALL
    from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
    from pycaw.constants import CLSID_MMDeviceEnumerator
    from pycaw.pycaw import IAudioSessionControl2, IAudioSessionManager2

    enumerator = comtypes.CoCreateInstance(
        CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)
    devices = enumerator.EnumAudioEndpoints(E_CAPTURE, DEVICE_ACTIVE)
    found: list[str] = []
    for d in range(devices.GetCount()):
        manager = devices.Item(d).Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None)
        sessions = manager.QueryInterface(IAudioSessionManager2).GetSessionEnumerator()
        for i in range(sessions.GetCount()):
            control = sessions.GetSession(i)
            if control.GetState() != SESSION_ACTIVE:
                continue
            pid = control.QueryInterface(IAudioSessionControl2).GetProcessId()
            try:
                found.append(psutil.Process(pid).name().lower())
            except Exception:       # Prozess schon weg oder kein Zugriff
                continue
    return found


def apps_using_microphone(timeout: float = QUERY_TIMEOUT) -> list[str]:
    """Namen aller Programme, die gerade Ton vom Mikrofon aufnehmen (z. B. "zoom.exe", "ms-teams.exe").

    Die Abfrage läuft in einem kurzen eigenen Thread: COM verträgt sich nicht mit dem Qt-Thread, und ein
    hängender Aufruf soll die Oberfläche nie festhalten."""
    names: list[str] = []
    errors: list[BaseException] = []

    def work() -> None:
        try:
            names.extend(_active_capture_names())
        except BaseException as e:  # noqa: BLE001 – wird unten weitergereicht
            errors.append(e)

    thread = threading.Thread(target=work, name="dictum-mic-query", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("Abfrage der Audio-Sitzungen hängt")
    if errors:
        raise errors[0]
    return names


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
