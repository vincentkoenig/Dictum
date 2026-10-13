"""Kleine Statusanzeige unten in der Bildschirmmitte ("● Hört zu…").

Zwei Besonderheiten:

1. **Sie darf niemals den Fokus stehlen.** Sonst würde der Text in unser Overlay
   eingefügt statt in das Programm, in dem man gerade schreibt. Deshalb setzen wir
   über die Windows-API (ctypes) das Fenster-Attribut WS_EX_NOACTIVATE und zeigen das
   Fenster mit SW_SHOWNOACTIVATE an.

2. **tkinter ist nicht thread-sicher.** Hotkey und Transkription laufen in anderen
   Threads. Die schicken deshalb nur Nachrichten in eine Warteschlange (`queue`), und
   der tkinter-Hauptthread holt sie alle 50 ms ab (`root.after`).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import queue
import tkinter as tk

user32 = ctypes.windll.user32

# ctypes kennt die Parametertypen der Windows-Funktionen nicht von selbst und würde
# Zahlen als 32 Bit übergeben. Fenster-Handles sind auf 64-Bit-Windows aber 64 Bit groß
# – z. B. HWND_TOPMOST (-1) käme sonst falsch an und das Fenster wäre nicht "oben".
user32.GetParent.argtypes = [wt.HWND]
user32.GetParent.restype = wt.HWND
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]

# Windows-Konstanten (aus der Win32-Dokumentation)
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080   # kein Eintrag in Taskleiste / Alt+Tab
WS_EX_NOACTIVATE = 0x08000000   # Fenster bekommt beim Klicken/Anzeigen keinen Fokus
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10

# Größen in "logischen" Pixeln bei 100 % Windows-Skalierung. Auf hochauflösenden
# Bildschirmen (z. B. 4K mit 150 %) werden sie unten mit dem Skalierungsfaktor
# multipliziert – sonst wäre das Overlay winzig.
WIDTH, HEIGHT = 230, 44
BOTTOM_MARGIN = 110  # Abstand zum unteren Bildschirmrand (über der Taskleiste)

BG = "#1f1f23"
FG = "#f2f2f2"

# Status → (Symbol, Symbolfarbe, Text)
STATES = {
    "loading": ("◌", "#9aa0a6", "Lade Modell …"),
    "listening": ("●", "#ff4d4f", "Hört zu …"),
    "transcribing": ("◐", "#4c9ffe", "Transkribiert …"),
    "polishing": ("✦", "#b48cff", "Formuliert …"),
}


class Overlay:
    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._hide_job: str | None = None

        self.root = tk.Tk()
        self.root.overrideredirect(True)  # kein Rahmen, keine Titelleiste
        self.root.configure(bg=BG)
        self.root.attributes("-alpha", 0.92)
        self.root.attributes("-topmost", True)

        # 96 Pixel pro Zoll = 100 % Skalierung
        scale = self.root.winfo_fpixels("1i") / 96
        w, h, margin = int(WIDTH * scale), int(HEIGHT * scale), int(BOTTOM_MARGIN * scale)
        x = (self.root.winfo_screenwidth() - w) // 2
        y = self.root.winfo_screenheight() - h - margin
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        frame = tk.Frame(self.root, bg=BG)
        frame.pack(expand=True)
        self._icon = tk.Label(frame, bg=BG, font=("Segoe UI Symbol", 14))
        self._icon.pack(side="left", padx=(0, 8))
        self._text = tk.Label(frame, bg=BG, fg=FG, font=("Segoe UI", 11))
        self._text.pack(side="left")

        self.root.update_idletasks()
        self._hwnd = user32.GetParent(self.root.winfo_id())
        style = user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            self._hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
        )
        self._round_corners()
        user32.ShowWindow(self._hwnd, SW_HIDE)

    # --- Diese Methoden dürfen aus JEDEM Thread aufgerufen werden ---------------------

    def show(self, state: str) -> None:
        self._queue.put(("show", state))

    def flash(self, message: str, seconds: float = 1.8) -> None:
        """Zeigt kurz eine Meldung (z. B. "Nichts erkannt") und blendet sie aus."""
        self._queue.put(("flash", (message, seconds)))

    def hide(self) -> None:
        self._queue.put(("hide", None))

    def quit(self) -> None:
        self._queue.put(("quit", None))

    # --- Ab hier nur im tkinter-Hauptthread -------------------------------------------

    def run(self) -> None:
        self.root.after(50, self._poll)
        self.root.mainloop()

    def _poll(self) -> None:
        try:
            while True:
                cmd, arg = self._queue.get_nowait()
                if cmd == "show":
                    symbol, color, text = STATES[arg]
                    self._display(symbol, color, text)
                elif cmd == "flash":
                    message, seconds = arg
                    self._display("ⓘ", "#f5a623", message)
                    self._hide_job = self.root.after(int(seconds * 1000), self._hide_now)
                elif cmd == "hide":
                    self._hide_now()
                elif cmd == "quit":
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _display(self, symbol: str, color: str, text: str) -> None:
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        self._icon.configure(text=symbol, fg=color)
        self._text.configure(text=text)
        user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(
            self._hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        )

    def _hide_now(self) -> None:
        self._hide_job = None
        user32.ShowWindow(self._hwnd, SW_HIDE)

    def _round_corners(self) -> None:
        """Windows 11: abgerundete Ecken. Auf älteren Systemen passiert einfach nichts."""
        try:
            DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
            pref = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                self._hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref), ctypes.sizeof(pref)
            )
        except (AttributeError, OSError):
            pass
