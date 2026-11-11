"""Prüft, warum Dictum ein Meeting nicht erkannt hat (oder ob die Erkennung bei dir funktioniert).

Aufruf in einem normalen PowerShell-Fenster (nicht in dem der Claude-App), aus dem Ordner desktop:

  cd C:\\dev\\Dictum\\desktop
  .venv\\Scripts\\python -X utf8 scripts\\check_meeting_detect.py              # Momentaufnahme
  .venv\\Scripts\\python -X utf8 scripts\\check_meeting_detect.py --watch 60   # 60 s beobachten

Mit --watch: Skript starten, dann Meeting beitreten bzw. mit Dictum diktieren. Jede Änderung wird mit Uhrzeit
aufgeschrieben. Es zeigt außerdem die echten Einstellungen und die letzten Log-Zeilen und ändert nichts.

Statt "aktiv" steht bei Programmen, die nur geöffnet sind (Teams und Zoom haben auch im Leerlauf eine Audio-Sitzung),
"bereit": Nur "aktiv" zählt für die Erkennung.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictum.meeting_detect import apps_using_microphone  # noqa: E402


def sessions() -> list[tuple[str, bool]]:
    """(Programmname, aktiv?) aller Aufnahme-Sitzungen. Läuft in einem eigenen COM-Thread wie in Dictum."""
    import threading

    out: list[tuple[str, bool]] = []
    errors: list[BaseException] = []

    def work() -> None:
        try:
            import comtypes
            import psutil
            from comtypes import CLSCTX_ALL
            from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
            from pycaw.constants import CLSID_MMDeviceEnumerator
            from pycaw.pycaw import IAudioSessionControl2, IAudioSessionManager2

            def read() -> None:
                enumerator = comtypes.CoCreateInstance(
                    CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)
                devices = enumerator.EnumAudioEndpoints(1, 1)
                for d in range(devices.GetCount()):
                    manager = devices.Item(d).Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None)
                    found = manager.QueryInterface(IAudioSessionManager2).GetSessionEnumerator()
                    for i in range(found.GetCount()):
                        control = found.GetSession(i)
                        pid = control.QueryInterface(IAudioSessionControl2).GetProcessId()
                        try:
                            name = psutil.Process(pid).name() if pid else "(System)"
                        except Exception:
                            name = f"pid {pid}"
                        out.append((name, control.GetState() == 1))

            comtypes.CoInitialize()
            try:
                read()
            finally:
                import gc

                gc.collect()  # COM-Objekte vor CoUninitialize freigeben, sonst Absturz
                comtypes.CoUninitialize()
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(5)
    if errors:
        raise errors[0]
    return out


def show(items: list[tuple[str, bool]]) -> str:
    if not items:
        return "  keine Sitzungen"
    return "\n".join(f"  {name:<28}{'AKTIV (nimmt auf)' if active else 'bereit'}" for name, active in sorted(items))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", type=int, default=0, help="so viele Sekunden beobachten")
    args = parser.parse_args()

    data = Path(os.environ.get("APPDATA", "")) / "Dictum"
    print(f"== 1. Einstellungen ({data / 'settings.toml'}) ==")
    settings = data / "settings.toml"
    if settings.exists():
        lines = [l.strip() for l in settings.read_text(encoding="utf-8").splitlines()
                 if l.strip().startswith(("auto_detect", "detect_seconds", "detect_apps"))]
        print("\n".join(lines) or "auto_detect steht nicht in der Datei, es gilt der Standard: aus")
    else:
        print("keine settings.toml gefunden")

    print("\n== 2. Audio-Sitzungen auf den Aufnahmegeräten ==")
    print(show(sessions()))
    print("Was Dictum als Meeting-Mikrofon sieht:", apps_using_microphone() or "nichts")

    if args.watch > 0:
        end = time.monotonic() + args.watch
        began = datetime.now()
        print(f"\nBeobachtung {began:%H:%M:%S} bis {datetime.fromtimestamp(time.time() + args.watch):%H:%M:%S}."
              " Jetzt Meeting beitreten bzw. diktieren ...")
        last = None
        while time.monotonic() < end:
            time.sleep(1)
            current = sorted(sessions())
            if current != last:
                last = current
                print(f"\n  {datetime.now():%H:%M:%S}")
                print(show(current))
        print(f"\nBeobachtung beendet um {datetime.now():%H:%M:%S}.")

    print("\n== 3. Log (letzte Aufnahme-/Meeting-Zeilen) ==")
    log = data / "logs" / "dictum.log"
    if log.exists():
        rows = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
                if any(w in l for w in ("Aufnahme", "Meeting", "Mikrofon", "Einstellungen übernommen"))]
        print("\n".join(rows[-8:]) or "nichts Passendes")
    else:
        print("keine Logdatei gefunden")


if __name__ == "__main__":
    main()
