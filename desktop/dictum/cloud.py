"""Kleiner Client für das Dictum-Backend auf Supabase.

Supabase bietet für alles eine normale HTTP-Schnittstelle (REST). Wir sprechen sie
direkt mit `requests` an – so sieht man genau, was passiert:

    /auth/v1/token          Login mit E-Mail + Passwort → Zugangs-Token (JWT)
    /rest/v1/<tabelle>      Datenbank lesen/schreiben (PostgREST)
    /storage/v1/object/...  Dateien hochladen
    /functions/v1/<name>    Edge Functions aufrufen

Bei JEDER Anfrage schicken wir zwei Dinge mit:
    apikey:        der öffentliche Projekt-Schlüssel ("Welches Projekt?")
    Authorization: das Login-Token ("Wer bin ich?") – damit greift die Row Level Security

Ablauf einer Gesprächsaufnahme:
    create_recording() → upload_chunk() + transcribe_chunk() je Stück
                       → finish()  → wait_until_done()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

TIMEOUT = 60  # Sekunden pro Anfrage


class CloudError(Exception):
    pass


@dataclass
class Session:
    access_token: str
    user_id: str


class DictumCloud:
    def __init__(self, url: str, publishable_key: str) -> None:
        if not url or not publishable_key:
            raise CloudError("Supabase-URL oder Schlüssel fehlt in settings.toml [cloud]")
        self.url = url.rstrip("/")
        self.key = publishable_key
        self.session: Session | None = None

    # --- Login --------------------------------------------------------------------

    def sign_in(self, email: str, password: str) -> Session:
        r = requests.post(
            f"{self.url}/auth/v1/token?grant_type=password",
            headers={"apikey": self.key},
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            raise CloudError(f"Login fehlgeschlagen: {r.json().get('msg') or r.text}")
        data = r.json()
        self.session = Session(data["access_token"], data["user"]["id"])
        return self.session

    def _headers(self, **extra: str) -> dict[str, str]:
        if self.session is None:
            raise CloudError("Nicht eingeloggt – zuerst sign_in() aufrufen")
        return {"apikey": self.key, "Authorization": f"Bearer {self.session.access_token}", **extra}

    def _check(self, r: requests.Response, what: str) -> requests.Response:
        if not r.ok:
            raise CloudError(f"{what} fehlgeschlagen ({r.status_code}): {r.text[:300]}")
        return r

    # --- Gesprächsaufnahmen -------------------------------------------------------

    def create_recording(self, template: str = "meeting", language: str = "de",
                         title: str | None = None) -> str:
        r = requests.post(
            f"{self.url}/rest/v1/recordings",
            # "return=representation": die angelegte Zeile (mit ihrer neuen ID) zurückgeben
            headers=self._headers(Prefer="return=representation"),
            json={"kind": "conversation", "template": template, "language": language,
                  "source": "desktop", "title": title},
            timeout=TIMEOUT,
        )
        return self._check(r, "Aufnahme anlegen").json()[0]["id"]

    def upload_chunk(self, recording_id: str, idx: int, audio: bytes,
                     content_type: str = "audio/wav", duration_seconds: float | None = None) -> None:
        ext = {"audio/wav": "wav", "audio/webm": "webm", "audio/ogg": "ogg"}.get(content_type, "bin")
        # Pfad beginnt mit der eigenen Nutzer-ID – sonst lehnt die Storage-Policy ab
        path = f"{self.session.user_id}/{recording_id}/{idx}.{ext}"
        r = requests.post(
            f"{self.url}/storage/v1/object/recordings/{path}",
            headers=self._headers(**{"Content-Type": content_type, "x-upsert": "true"}),
            data=audio,
            timeout=TIMEOUT * 2,
        )
        self._check(r, f"Upload Stück {idx}")
        r = requests.post(
            f"{self.url}/rest/v1/recording_chunks",
            headers=self._headers(Prefer="resolution=merge-duplicates"),
            json={"recording_id": recording_id, "idx": idx, "storage_path": path,
                  "duration_seconds": duration_seconds},
            timeout=TIMEOUT,
        )
        self._check(r, f"Stück {idx} eintragen")

    def transcribe_chunk(self, recording_id: str, idx: int) -> dict:
        r = requests.post(
            f"{self.url}/functions/v1/transcribe",
            headers=self._headers(),
            json={"recording_id": recording_id, "idx": idx},
            timeout=150,  # Laufzeitlimit der Edge Function
        )
        return self._check(r, f"Transkription Stück {idx}").json()

    def finish(self, recording_id: str, chunk_count: int, duration_seconds: float | None = None) -> dict:
        """Meldet: Alle Stücke sind hochgeladen. Startet die Zusammenfassung, sobald
        alle Stücke transkribiert sind."""
        r = requests.patch(
            f"{self.url}/rest/v1/recordings?id=eq.{recording_id}",
            headers=self._headers(),
            json={"chunk_count": chunk_count, "status": "transcribing", "duration_seconds": duration_seconds},
            timeout=TIMEOUT,
        )
        self._check(r, "Aufnahme abschließen")
        return self.summarize(recording_id)

    def summarize(self, recording_id: str, template: str | None = None, force: bool = False) -> dict:
        body: dict = {"recording_id": recording_id, "force": force}
        if template:
            body["template"] = template
        r = requests.post(f"{self.url}/functions/v1/summarize", headers=self._headers(), json=body,
                          timeout=TIMEOUT)
        return self._check(r, "Zusammenfassung starten").json()

    def get_recording(self, recording_id: str) -> dict:
        r = requests.get(
            f"{self.url}/rest/v1/recordings?id=eq.{recording_id}&select=*",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        rows = self._check(r, "Aufnahme laden").json()
        if not rows:
            raise CloudError("Aufnahme nicht gefunden")
        return rows[0]

    def wait_until_done(self, recording_id: str, timeout: float = 300, poll: float = 3) -> dict:
        """Fragt alle paar Sekunden den Status ab, bis die Aufnahme fertig ist."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rec = self.get_recording(recording_id)
            if rec["status"] in ("done", "error"):
                return rec
            log.info("Status: %s …", rec["status"])
            time.sleep(poll)
        raise CloudError(f"Zeitüberschreitung – Status blieb {rec['status']}")

    def delete_recording(self, recording_id: str) -> None:
        """Löscht Aufnahme, Stücke (per Fremdschlüssel "on delete cascade") und Audio."""
        rec_chunks = requests.get(
            f"{self.url}/rest/v1/recording_chunks?recording_id=eq.{recording_id}&select=storage_path",
            headers=self._headers(), timeout=TIMEOUT,
        )
        paths = [c["storage_path"] for c in self._check(rec_chunks, "Stücke laden").json()]
        if paths:
            r = requests.delete(f"{self.url}/storage/v1/object/recordings", headers=self._headers(),
                                json={"prefixes": paths}, timeout=TIMEOUT)
            self._check(r, "Audio löschen")
        r = requests.delete(f"{self.url}/rest/v1/recordings?id=eq.{recording_id}",
                            headers=self._headers(), timeout=TIMEOUT)
        self._check(r, "Aufnahme löschen")

    # --- Diktat -------------------------------------------------------------------

    def dictate(self, audio: bytes, filename: str = "diktat.wav", language: str = "de",
                cleanup: bool = True) -> dict:
        r = requests.post(
            f"{self.url}/functions/v1/dictate",
            headers=self._headers(),
            files={"audio": (filename, audio)},
            data={"language": language, "cleanup": str(cleanup).lower()},
            timeout=TIMEOUT,
        )
        return self._check(r, "Diktat").json()
