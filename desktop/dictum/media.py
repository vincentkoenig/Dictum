"""Ton anderer Programme beim Diktieren leiser stellen oder stummschalten.

Läuft nebenbei Musik oder ein Video, nimmt das Mikrofon sie mit auf, und die Erkennung wird schlechter.
Dictum stellt deshalb für die Dauer der Aufnahme die Lautstärke der anderen Programme herunter und danach genau
auf den alten Wert zurück.

Technik: Windows führt für jedes Programm, das Ton ausgibt, eine eigene "Audio-Sitzung" mit eigener Lautstärke
(das ist der Lautstärkemixer). Die Bibliothek `pycaw` gibt Zugriff darauf. Dictums eigener Ton (Start- und
Stopp-Piepton) bleibt unberührt.

Alle Windows-Aufrufe laufen in einem einzigen Hilfs-Thread, der Befehle nacheinander abarbeitet. So bremst das
Dämpfen den Tastatur-Thread nie, und "stumm" und "zurück" können sich nicht überholen.

Fällt etwas aus (pycaw fehlt, ein Programm verweigert den Zugriff), läuft das Diktat unverändert weiter.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Protocol

log = logging.getLogger(__name__)


class Session(Protocol):
    """Eine Audio-Sitzung eines Programms (so wie `pycaw` sie liefert, oder ein Testersatz)."""

    process_id: int

    def get_volume(self) -> float: ...
    def set_volume(self, value: float) -> None: ...
    def get_mute(self) -> bool: ...
    def set_mute(self, value: bool) -> None: ...


class PycawBackend:
    """Liest die Audio-Sitzungen über pycaw. Muss im selben Thread benutzt werden, der es erzeugt hat."""

    def __init__(self) -> None:
        import comtypes

        comtypes.CoInitialize()
        self._comtypes = comtypes

    def close(self) -> None:
        self._comtypes.CoUninitialize()

    def sessions(self) -> list[Session]:
        from pycaw.pycaw import AudioUtilities

        return [_PycawSession(s) for s in AudioUtilities.GetAllSessions()]


class _PycawSession:
    def __init__(self, session) -> None:
        self._volume = session.SimpleAudioVolume
        self.process_id = int(session.ProcessId or 0)

    def get_volume(self) -> float:
        return float(self._volume.GetMasterVolume())

    def set_volume(self, value: float) -> None:
        self._volume.SetMasterVolume(max(0.0, min(1.0, value)), None)

    def get_mute(self) -> bool:
        return bool(self._volume.GetMute())

    def set_mute(self, value: bool) -> None:
        self._volume.SetMute(1 if value else 0, None)


def lowered_volume(original: float, percent: int) -> float:
    """Die Lautstärke, auf die ein Programm gedämpft wird: `percent` Prozent des bisherigen Werts."""
    return max(0.0, min(1.0, original * percent / 100))


class AudioDucker:
    """Dämpft bzw. stummt andere Programme (`duck`) und stellt sie wieder her (`restore`).

    mode: "off" (nichts tun), "duck" (auf `percent` Prozent), "mute" (stumm).
    `backend_factory` ist für Tests austauschbar.
    """

    def __init__(self, mode: str = "off", percent: int = 20, backend_factory=PycawBackend,
                 own_pid: int | None = None) -> None:
        self.mode = mode
        self.percent = percent
        self._backend_factory = backend_factory
        self._own_pid = os.getpid() if own_pid is None else own_pid
        self._commands: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._changed: list[tuple[Session, float, bool]] = []  # Sitzung, alte Lautstärke, alt stumm?
        self._failed = False

    # --- von überall aufrufbar -------------------------------------------------------

    def duck(self) -> None:
        if self.mode != "off" and not self._failed:
            self._send("duck")

    def restore(self) -> None:
        # Auch bei "off" zurückstellen: Der Modus kann mitten in einer Aufnahme geändert worden sein
        if self._thread is not None and not self._failed:
            self._send("restore")

    def shutdown(self, timeout: float = 3.0) -> None:
        """Beim Beenden: alles zurückstellen und den Hilfs-Thread abwarten."""
        thread = self._thread
        if thread is None:
            return
        self._commands.put("restore")
        self._commands.put(None)
        thread.join(timeout)

    # --- Hilfs-Thread ----------------------------------------------------------------

    def _send(self, command: str) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="dictum-ducker", daemon=True)
            self._thread.start()
        self._commands.put(command)

    def _run(self) -> None:
        try:
            backend = self._backend_factory()
        except Exception:
            # Meist fehlt pycaw. Einmal melden, dann nicht mehr versuchen.
            log.warning("Ton anderer Programme lässt sich nicht steuern", exc_info=True)
            self._failed = True
            return
        try:
            while True:
                command = self._commands.get()
                if command is None:
                    return
                try:
                    if command == "duck":
                        self._duck(backend)
                    else:
                        self._restore()
                except Exception:
                    log.warning("Ton anderer Programme: Fehler bei '%s'", command, exc_info=True)
        finally:
            self._restore()
            close = getattr(backend, "close", None)
            if close:
                close()

    def _duck(self, backend) -> None:
        self._restore()  # nie zwei Dämpfungen übereinander: sonst ginge der Originalwert verloren
        for session in backend.sessions():
            if session.process_id in (0, self._own_pid):
                continue  # Systemtöne und Dictum selbst nicht anfassen
            try:
                volume, muted = session.get_volume(), session.get_mute()
                if self.mode == "mute":
                    session.set_mute(True)
                else:
                    session.set_volume(lowered_volume(volume, self.percent))
                self._changed.append((session, volume, muted))
            except Exception:
                log.debug("Sitzung nicht steuerbar", exc_info=True)
        if self._changed:
            log.info("Ton von %d Programm(en) für die Aufnahme %s", len(self._changed),
                     "stummgeschaltet" if self.mode == "mute" else f"auf {self.percent} % gesenkt")

    def _restore(self) -> None:
        changed, self._changed = self._changed, []
        for session, volume, muted in changed:
            try:
                session.set_volume(volume)
                session.set_mute(muted)
            except Exception:
                log.debug("Sitzung nicht zurückstellbar (Programm beendet?)", exc_info=True)
        if changed:
            log.info("Ton der anderen Programme wiederhergestellt")
