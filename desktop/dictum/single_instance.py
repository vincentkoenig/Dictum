"""Dictum darf nur einmal laufen.

Würden zwei Dictum-Prozesse gleichzeitig laufen, hörte jeder auf die rechte Strg-Taste: ein
Diktat würde doppelt eingefügt, und beide würden das Mikrofon blockieren. Das passiert schnell,
z. B. wenn der Autostart schon läuft und man zusätzlich start.bat doppelklickt.

Die Lösung ist ein **Mutex** ("mutual exclusion", gegenseitiger Ausschluss): ein benanntes
Objekt, das Windows verwaltet. Der erste Prozess legt es an. Versucht ein zweiter, ein Objekt
mit demselben Namen anzulegen, meldet Windows ERROR_ALREADY_EXISTS – dann weiß er, dass schon
jemand da ist, und beendet sich. Stirbt der erste Prozess (auch bei einem Absturz), räumt
Windows das Objekt automatisch weg. Es bleibt also nie ein "Geister-Sperrzeichen" zurück,
anders als bei einer Sperrdatei auf der Festplatte.

"Local\\" im Namen heißt: gilt nur innerhalb der Windows-Anmeldung. Meldet sich ein zweiter
Benutzer an, darf er sein eigenes Dictum starten.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

ERROR_ALREADY_EXISTS = 183
DEFAULT_NAME = "Local\\DictumDesktop"

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
# Typen angeben: Handles sind auf 64-Bit-Windows 64 Bit groß (siehe overlay.py)
kernel32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL


class SingleInstance:
    def __init__(self, name: str = DEFAULT_NAME) -> None:
        ctypes.set_last_error(0)
        self._handle = kernel32.CreateMutexW(None, False, name)
        # Wichtig: GetLastError direkt nach dem Aufruf lesen, bevor etwas anderes es überschreibt
        self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS

    def release(self) -> None:
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None
