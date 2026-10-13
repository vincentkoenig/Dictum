# Die Desktop-App erklärt

Die Desktop-App macht genau eine Sache sehr gut: **Sprache in jedes Textfeld bringen** –
egal ob Word, Browser, Outlook oder Slack. Dieses Dokument erklärt, wie das funktioniert.

## 1. Der Ablauf eines Diktats

```
 Du drückst Strg+Win
        │
        ▼
 hotkey.py      erkennt die Kombination ──► Startmenü-Trick (Masken-Taste)
        │
        ▼
 audio.py       öffnet das Mikrofon, sammelt Audio (16 kHz mono)
 overlay.py     zeigt "● Hört zu …"
        │
 Du lässt los
        ▼
 audio.py       liefert das Audio als Zahlenreihe (numpy-Array)
 overlay.py     zeigt "◐ Transkribiert …"
        │
        ▼  (Warteschlange → Worker-Thread)
 transcriber.py faster-whisper wandelt Audio in Text (lokal, ~2 s)
        │
        ▼
 inserter.py    Text → Zwischenablage → Strg+V → alte Zwischenablage zurück
        │
        ▼
 Text steht im Feld, Overlay verschwindet
```

## 2. Die Dateien

| Datei | Aufgabe | Kernidee |
|---|---|---|
| `config.py` | Liest `settings.toml` | Dataclasses + Prüfung beim Start |
| `audio.py` | Mikrofon aufnehmen | Callback sammelt Audio-Blöcke |
| `transcriber.py` | Audio → Text | faster-whisper, CPU, int8, VAD-Filter |
| `hotkey.py` | Halten/Antippen erkennen | Zustandsmaschine, getrennt von der Tastatur |
| `inserter.py` | Text einfügen | Zwischenablage + simuliertes Strg+V |
| `overlay.py` | Statusanzeige | Fenster, das nie den Fokus nimmt |
| `tray.py` | Symbol in der Taskleiste | Menü für Modus, Sprache, Beenden |
| `app.py` | Verbindet alles | Threads + Warteschlange |
| `__main__.py` | Einstiegspunkt | `python -m dictum` |

## 3. Die wichtigsten Konzepte

### Zustandsmaschine (hotkey.py)

Halten und Antippen benutzen **dieselbe Taste**. Die App muss sich also merken, in welchem
Zustand sie gerade ist:

| Zustand | Bedeutung | Nächster Schritt |
|---|---|---|
| `IDLE` | Nichts passiert | Kombi gedrückt → Aufnahme startet → `PRESSED` |
| `PRESSED` | Kombi wird gehalten | Loslassen nach ≥ 0,4 s → **Stopp**. Vorher → `TOGGLED` |
| `TOGGLED` | Nach kurzem Antippen, Aufnahme läuft weiter | Erneut drücken → **Stopp** |
| `WAIT_RELEASE` | Fertig, warten bis Tasten los sind | Loslassen → `IDLE` |

Wird während `PRESSED` eine **andere** Taste gedrückt (z. B. Strg+Win+→ für den nächsten
Desktop), war das kein Diktat – die Aufnahme wird verworfen.

Die Logik kennt die echte Tastatur nicht, sondern bekommt nur Ereignisse gemeldet. Dadurch
lässt sie sich mit Tests prüfen, ohne eine Taste zu drücken (`tests/test_hotkey.py`).

### Der Startmenü-Trick

Windows öffnet das Startmenü, wenn die Win-Taste losgelassen wird und *keine andere Taste*
dazwischen kam – Zusatztasten wie Strg reichen nicht zuverlässig, um das zu verhindern. Deshalb „drückt“ Dictum unsichtbar eine Taste,
die es auf keiner Tastatur gibt (`0xE8`). Windows sieht „Win + andere Taste“ und lässt das
Startmenü zu. AutoHotkey verwendet denselben Trick.

### Threads – warum die App nicht hängt

Mehrere Dinge passieren gleichzeitig, deshalb laufen sie in eigenen **Threads**:

| Thread | Macht |
|---|---|
| Hauptthread | Overlay (tkinter verlangt den Hauptthread) |
| pynput | Hört auf die Tastatur |
| pystray | Tray-Symbol |
| Lade-Thread | Lädt einmalig das Whisper-Modell |
| Worker | Transkribiert und fügt ein |

Die Threads reden über **Warteschlangen** (`queue.Queue`) miteinander: Der Tastatur-Thread
legt das Audio hinein und ist sofort wieder frei; der Worker holt es ab und arbeitet es ab.

### Das Overlay darf den Fokus nicht stehlen

Würde das Overlay beim Erscheinen zum aktiven Fenster, landete das Strg+V im Overlay statt
in deinem Dokument. Deshalb bekommt es über die Windows-API das Attribut `WS_EX_NOACTIVATE`.

### Schnell genug ohne Grafikkarte

| Maßnahme | Effekt |
|---|---|
| `faster-whisper` statt `openai-whisper` | ca. 4× schneller, weniger Speicher |
| `compute_type="int8"` | Modell-Gewichte als ganze Zahlen → kleiner und schneller |
| Modell `small` | Guter Kompromiss aus Tempo und Genauigkeit |
| Sprache fest auf `de` | Spart ~2 s pro Diktat (siehe unten) |
| `vad_filter=True` | Schneidet Stille ab → weniger Arbeit, keine erfundenen Sätze |

**Gemessen** (6,8 s Sprache, dieser PC, 16 Kerne):

| Einstellung | Dauer |
|---|---|
| Deutsch fest | ~2,1 s |
| Automatische Spracherkennung | ~4,0 s |

Whisper betrachtet für die Spracherkennung immer ein volles 30-Sekunden-Fenster, auch bei
einem kurzen Satz. Daher ist „Deutsch“ Standard und „Automatisch“ im Tray-Menü wählbar.

## 4. Bekannte Grenzen (Stand Phase 1)

- Der Text wird **roh** eingefügt (mit „ähm“ usw.). Die KI-Bereinigung kommt in Phase 2.
- Die Zwischenablage wird nur wiederhergestellt, wenn sie vorher **Text** enthielt.
- In Programmen, die mit Administratorrechten laufen, kann Windows das simulierte Strg+V
  blockieren.
- Einstellungen aus dem Tray-Menü gelten nur bis zum Beenden. Dauerhaft ändert man sie in `settings.toml`.
