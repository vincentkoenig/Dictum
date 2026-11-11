"""Dictum von außen steuern: `dictum --toggle`, `--cancel` und mehr.

Idee von Handy (`--toggle-transcription`, `--cancel`). Gedacht für Skripte, AutoHotkey, ein Stream Deck oder
eine Maus-Zusatztaste, die ein Programm startet. Der Aufruf startet **kein** zweites Dictum, sondern schickt
dem laufenden einen Befehl und beendet sich wieder:

    dictum --toggle              Diktat starten bzw. beenden (wie zweimal die Taste antippen)
    dictum --toggle-command      dasselbe für den Command Mode
    dictum --toggle-translate    dasselbe für das Übersetzen
    dictum --toggle-assistant    dasselbe für den Assistenten
    dictum --cancel              laufende Aufnahme verwerfen (wie Esc)
    dictum --paste-last          letztes Diktat noch einmal einfügen
    dictum --copy-last           letztes Diktat kopieren
    dictum --toggle-meeting      Meeting-Aufnahme starten bzw. beenden
    dictum --show                das Dictum-Fenster öffnen

Wie kommt der Befehl an? Über eine **benannte Pipe** (ein Kanal, den Windows zwischen zwei Programmen
bereitstellt, ähnlich wie der Mutex in single_instance.py). Sie hört nur auf diesem PC, nie im Netzwerk.
Damit nicht jedes Programm Befehle schicken kann, braucht man einen **Schlüssel**: eine zufällige Datei
(`control.key`) im Datenordner von Dictum. Wer sie lesen kann, darf Dictum steuern; das gilt ohnehin für
jedes Programm, das unter deinem Windows-Konto läuft und dessen Dateien lesen darf.
"""

from __future__ import annotations

import getpass
import logging
import os
import secrets
import threading
from multiprocessing.connection import AuthenticationError, Client, Connection, Listener
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

COMMANDS = ("toggle", "toggle-command", "toggle-translate", "toggle-assistant", "cancel",
            "paste-last", "copy-last", "toggle-meeting", "show")
REPLY_TIMEOUT = 5.0


def default_address() -> str:
    """Name der Pipe, pro Windows-Benutzer eigen (zwei angemeldete Benutzer stören sich nicht)."""
    user = "".join(c for c in getpass.getuser() if c.isalnum()) or "user"
    return rf"\\.\pipe\DictumControl-{user}"


def default_key_path() -> Path:
    from .config import DESKTOP_DIR

    return DESKTOP_DIR / "control.key"


def load_key(path: Path, create: bool = False) -> bytes | None:
    """Liest den Schlüssel. Mit `create=True` wird er beim ersten Mal angelegt (nur das laufende Dictum)."""
    try:
        key = path.read_bytes()
        if key:
            return key
    except OSError:
        pass
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32).encode()
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


class ControlServer:
    """Wartet im Hintergrund auf Befehle und ruft `handler(befehl)` auf. Die Antwort (Text) geht zurück."""

    def __init__(self, handler: Callable[[str], str], address: str | None = None,
                 key_path: Path | None = None) -> None:
        self.handler = handler
        self.address = address or default_address()
        self.key_path = key_path or default_key_path()
        self._listener: Listener | None = None
        self._stopping = False

    def start(self) -> bool:
        """Startet den Hörer. False, wenn das nicht klappt (die Fernsteuerung fehlt dann, Dictum läuft normal)."""
        try:
            key = load_key(self.key_path, create=True)
            self._listener = Listener(self.address, family="AF_PIPE", authkey=key)
        except Exception:
            log.exception("Fernsteuerung konnte nicht gestartet werden")
            return False
        threading.Thread(target=self._serve, daemon=True, name="dictum-control").start()
        log.info("Fernsteuerung bereit (%s)", self.address)
        return True

    def stop(self) -> None:
        self._stopping = True
        listener, self._listener = self._listener, None
        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass

    def _serve(self) -> None:
        while not self._stopping:
            listener = self._listener
            if listener is None:
                return
            try:
                conn = listener.accept()
            except AuthenticationError:
                log.warning("Fernsteuerung: Verbindung mit falschem Schlüssel abgewiesen")
                continue
            except Exception:
                if not self._stopping:
                    log.exception("Fernsteuerung: Annehmen fehlgeschlagen – beende die Fernsteuerung")
                return
            # Jede Verbindung in einem eigenen Thread: Ein hängender Client blockiert so die nächsten nicht
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: Connection) -> None:
        try:
            with conn:
                if not conn.poll(REPLY_TIMEOUT):
                    return
                command = conn.recv()
                if command not in COMMANDS:
                    conn.send(f"unbekannter Befehl: {command!r}")
                    return
                try:
                    reply = self.handler(command) or "ok"
                except Exception as e:
                    log.exception("Fernsteuerung: Befehl %r fehlgeschlagen", command)
                    reply = f"Fehler: {e}"
                conn.send(reply)
        except Exception:
            log.debug("Fernsteuerung: Verbindung abgebrochen", exc_info=True)


def send_command(command: str, address: str | None = None, key_path: Path | None = None) -> tuple[bool, str]:
    """Schickt einen Befehl an das laufende Dictum. Gibt (geklappt, Meldung) zurück."""
    if command not in COMMANDS:
        return False, f"Unbekannter Befehl: {command}"
    key = load_key(key_path or default_key_path())
    if key is None:
        return False, "Dictum läuft nicht (kein Schlüssel gefunden)."
    try:
        with Client(address or default_address(), family="AF_PIPE", authkey=key) as conn:
            conn.send(command)
            if not conn.poll(REPLY_TIMEOUT):
                return False, "Dictum antwortet nicht."
            reply = conn.recv()
    except FileNotFoundError:
        return False, "Dictum läuft nicht."
    except AuthenticationError:
        return False, "Falscher Schlüssel (control.key gehört zu einem anderen Dictum)."
    except OSError as e:
        return False, f"Keine Verbindung zu Dictum: {e}"
    return reply == "ok", reply
