"""Meeting-Aufnahme am PC: dein Mikrofon UND der PC-Ton (Teams, Zoom, Meet …).

Wie kommt man an den PC-Ton? Windows bietet mit **WASAPI-Loopback** eine Art
"virtuelles Mikrofon", das genau das aufnimmt, was gerade aus den Lautsprechern bzw.
dem Headset kommt. Die Bibliothek `soundcard` macht das zugänglich.

Aufbau:

    Mikrofon-Thread  ──► Puffer ┐
                                ├─► Misch-Thread ──► ChunkAccumulator ──► on_chunk()
    Loopback-Thread  ──► Puffer ┘     (Summe)          (alle 5 Minuten)

- Beide Quellen laufen in eigenen Threads, weil `record()` blockiert, bis Daten da sind.
- Der Misch-Thread nimmt von beiden gleich viel, addiert sie (mit Lautstärke-Faktoren)
  und gibt das Ergebnis an den ChunkAccumulator, der alle 5 Minuten ein Stück abgibt.
- Aufgenommen wird mit 48 kHz – das ist die native Rate von Windows-Audio und von Opus,
  dem Format, in dem die Stücke gespeichert werden (siehe encoder.py).

`mix()` und `ChunkAccumulator` sind reine Logik ohne Geräte – deshalb testbar.
"""

from __future__ import annotations

import logging
import threading
import time
import warnings
from collections import deque
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
BLOCK = SAMPLE_RATE // 10  # 100 ms pro Lese-Vorgang
MIN_LAST_CHUNK_SECONDS = 1.0  # kürzere Reste am Ende sind meist nur das Stopp-Klicken


def mix(mic: np.ndarray, system: np.ndarray, mic_gain: float = 1.0, system_gain: float = 0.8) -> np.ndarray:
    """Addiert zwei gleich lange Spuren. np.clip verhindert Übersteuern (Werte > 1)."""
    return np.clip(mic * mic_gain + system * system_gain, -1.0, 1.0).astype(np.float32)


class ChunkAccumulator:
    """Sammelt Audio und gibt immer dann ein fertiges Stück zurück, wenn
    `chunk_seconds` voll sind. Am Ende liefert `flush()` den Rest."""

    def __init__(self, chunk_seconds: float, sample_rate: int = SAMPLE_RATE) -> None:
        self.chunk_samples = int(chunk_seconds * sample_rate)
        self.sample_rate = sample_rate
        self._parts: list[np.ndarray] = []
        self._size = 0

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        self._parts.append(samples)
        self._size += len(samples)
        done = []
        while self._size >= self.chunk_samples:
            data = np.concatenate(self._parts)
            done.append(data[: self.chunk_samples])
            rest = data[self.chunk_samples:]
            self._parts, self._size = ([rest] if len(rest) else []), len(rest)
        return done

    def flush(self) -> np.ndarray | None:
        if self._size < MIN_LAST_CHUNK_SECONDS * self.sample_rate:
            return None
        data = np.concatenate(self._parts)
        self._parts, self._size = [], 0
        return data


class _Source:
    """Liest in einem eigenen Thread von einem Gerät in einen Puffer."""

    def __init__(self, name: str, device) -> None:
        self.name = name
        self.device = device
        self.buffer: deque[np.ndarray] = deque()
        self.lock = threading.Lock()
        self.error: Exception | None = None

    def run(self, stop: threading.Event) -> None:
        try:
            with warnings.catch_warnings():
                # soundcard warnt bei Lücken im Loopback (wenn gerade nichts abgespielt
                # wird) – das ist normal und wird beim Mischen mit Stille aufgefüllt
                warnings.simplefilter("ignore")
                with self.device.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK) as rec:
                    while not stop.is_set():
                        data = rec.record(numframes=BLOCK)[:, 0].astype(np.float32)
                        with self.lock:
                            self.buffer.append(data)
        except Exception as e:  # z. B. Headset abgezogen
            log.exception("Aufnahme von %s abgebrochen", self.name)
            self.error = e

    def take(self, n: int) -> np.ndarray:
        """Nimmt genau n Samples aus dem Puffer (oder weniger, wenn nicht genug da ist)."""
        out, got = [], 0
        with self.lock:
            while self.buffer and got < n:
                block = self.buffer.popleft()
                need = n - got
                if len(block) > need:
                    self.buffer.appendleft(block[need:])
                    block = block[:need]
                out.append(block)
                got += len(block)
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)

    def available(self) -> int:
        with self.lock:
            return sum(len(b) for b in self.buffer)


class MeetingRecorder:
    def __init__(
        self,
        on_chunk: Callable[[int, np.ndarray, float], None],
        chunk_seconds: float = 300,
        include_system_audio: bool = True,
        mic_gain: float = 1.0,
        system_gain: float = 0.8,
    ) -> None:
        self.on_chunk = on_chunk
        self.include_system_audio = include_system_audio
        self.mic_gain, self.system_gain = mic_gain, system_gain
        self._acc = ChunkAccumulator(chunk_seconds)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._sources: list[_Source] = []
        self._idx = 0
        self.started_at = 0.0

    def start(self) -> None:
        import soundcard as sc  # erst hier importieren: wird nur für Meetings gebraucht

        self._sources = [_Source("Mikrofon", sc.default_microphone())]
        if self.include_system_audio:
            speaker = sc.default_speaker()
            loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            self._sources.append(_Source("PC-Ton", loopback))
            log.info("Meeting: Mikrofon + PC-Ton von '%s'", speaker.name)

        self._stop.clear()
        self.started_at = time.monotonic()
        for src in self._sources:
            t = threading.Thread(target=src.run, args=(self._stop,), daemon=True)
            t.start()
            self._threads.append(t)
        mixer = threading.Thread(target=self._mix_loop, daemon=True)
        mixer.start()
        self._threads.append(mixer)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at if self.started_at else 0.0

    def stop(self) -> int:
        """Beendet die Aufnahme, liefert das letzte Stück und gibt die Anzahl Stücke zurück."""
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3)
        self._threads.clear()
        self._mix_available(final=True)
        rest = self._acc.flush()
        if rest is not None:
            self._emit(rest)
        return self._idx

    def _mix_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.5)
            self._mix_available(final=False)

    def _mix_available(self, final: bool) -> None:
        mic = self._sources[0]
        if len(self._sources) == 1:
            samples = mic.take(mic.available())
        else:
            system = self._sources[1]
            n = min(mic.available(), system.available())
            # Liefert der Loopback nichts (Stille, keine Wiedergabe), läuft das Mikrofon
            # trotzdem weiter: nach >1 s Rückstand wird der PC-Ton mit Stille aufgefüllt
            if final or mic.available() - system.available() > SAMPLE_RATE:
                n = mic.available()
            m = mic.take(n)
            s = system.take(n)
            if len(s) < len(m):
                s = np.concatenate([s, np.zeros(len(m) - len(s), dtype=np.float32)])
            samples = mix(m, s, self.mic_gain, self.system_gain)
        if len(samples):
            for chunk in self._acc.push(samples):
                self._emit(chunk)

    def _emit(self, chunk: np.ndarray) -> None:
        duration = len(chunk) / SAMPLE_RATE
        log.info("Meeting: Stück %d fertig (%.0f s)", self._idx, duration)
        try:
            self.on_chunk(self._idx, chunk, duration)
        finally:
            self._idx += 1
