# Die Desktop-App erklärt

Die Desktop-App macht genau eine Sache sehr gut: **Sprache in jedes Textfeld bringen** –
egal ob Word, Browser, Outlook oder Slack. Dieses Dokument erklärt, wie das funktioniert.

## 1. Der Ablauf eines Diktats

```
 Du drückst die rechte Strg-Taste (einstellbar in settings.toml)
        │
        ▼
 hotkey.py      erkennt den Hotkey
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
   oder cloud_transcriber.py (OpenAI) – Wörterbuch geht als Hinweis mit
        │
        ▼
 vocabulary.py  Ist das ganze Diktat ein Snippet-Auslöser? → Snippet-Text, fertig
        │ nein
        ▼
 cleanup.py     KI bereinigt: Füllwörter, Korrekturen, Satzzeichen, Listen
 overlay.py     zeigt "✦ Formuliert …"
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
| `transcriber.py` | Audio → Text (lokal) | faster-whisper, CPU, int8, VAD-Filter |
| `cloud_transcriber.py` | Audio → Text (OpenAI) | WAV im Speicher, gleiche Methoden wie lokal |
| `llm/` | KI-Anbieter | Eine Schnittstelle, zwei Umsetzungen (Claude, OpenAI) |
| `cleanup.py` | Text bereinigen | Prompt „Werkzeug, kein Assistent“ + Plausibilitätsprüfung |
| `vocabulary.py` | Wörterbuch & Snippets | Persönliche Dateien, Vorlagen im Repo |
| `hotkey.py` | Halten/Antippen erkennen | Zustandsmaschine, getrennt von der Tastatur |
| `inserter.py` | Text einfügen | Zwischenablage + simuliertes Strg+V |
| `overlay.py` | Statusanzeige | Fenster, das nie den Fokus nimmt |
| `tray.py` | Symbol in der Taskleiste | Alle Schalter zur Laufzeit |
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

Wird während `PRESSED` eine **andere** Taste gedrückt (z. B. C, weil man mit der rechten
Strg-Taste eigentlich Strg+C drücken wollte), war das kein Diktat – die Aufnahme wird verworfen.

### Welche Taste? (Gruppen vs. Einzeltasten)

Ursprünglich war Strg+Win geplant (wie bei Wispr Flow). Weil Wispr Flow diese Kombination
selbst belegt, ist der Standard jetzt **Strg rechts**: eine einzelne Taste, die im Alltag
kaum benutzt wird. Damit das geht, unterscheidet `hotkey.py` zwischen

- **Gruppen** wie `"ctrl"`: die linke *oder* rechte Taste, und
- **Einzeltasten** wie `"ctrl_r"` oder `"f9"`: genau diese eine Taste.

Die linke Strg-Taste (Strg+C, Strg+V …) löst deshalb nichts aus.

Nicht geeignet auf deutschen Tastaturen: Strg+Alt und Alt rechts (beides ist AltGr, also
`@`, `€`, `{`) sowie Strg+Umschalt (wechselt oft das Tastaturlayout).

Die Logik kennt die echte Tastatur nicht, sondern bekommt nur Ereignisse gemeldet. Dadurch
lässt sie sich mit Tests prüfen, ohne eine Taste zu drücken (`tests/test_hotkey.py`).

### Der Startmenü-Trick (nur wenn die Win-Taste Teil des Hotkeys ist)

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

## 4. Smarter Text (Phase 2)

### Die KI-Bereinigung

| Gesagt | Eingefügt |
|---|---|
| „Ähm, wir treffen uns um drei, nein, um vier Uhr“ | „Wir treffen uns um vier Uhr.“ |
| „Bring bitte erstens den Laptop zweitens das Kabel mit“ | „Bring bitte mit:<br>1. den Laptop<br>2. das Kabel“ |
| „Schreib eine Mail an Tom“ | „Schreib eine Mail an Tom.“ (wird **nicht** ausgeführt) |

Das Wichtigste ist der **System-Prompt** in `cleanup.py`. Er legt fest, dass die KI ein
*Werkzeug* ist und kein Assistent. Das Diktat steht in `<transkript>`-Tags, damit die KI
klar trennen kann, was Anweisung ist (der Prompt) und was nur Text ist (das Diktat).

Weil KI nie 100 % verlässlich ist, gibt es **Sicherheitsnetze im Code**:

| Situation | Reaktion |
|---|---|
| Kein Key, offline, Limit, Server-Fehler | Rohtext wird eingefügt |
| Antwort leer | Rohtext |
| Antwort deutlich länger als das Diktat (KI hat geantwortet/erfunden) | Rohtext |
| Antwort viel kürzer (KI hat Inhalt gestrichen) | Rohtext |

Diktieren funktioniert also **immer**. Im schlimmsten Fall kommt nur der unbereinigte Text.

**Modellwahl:** Claude Haiku 5.5, ohne Denkphase und mit `effort: low`. Fürs Bereinigen
braucht es kein großes Modell, aber jede Zehntelsekunde zählt. Kosten: Bruchteile eines Cents
pro Diktat.

### Austauschbare KI-Anbieter (`llm/`)

```
cleanup.py ──► LLMProvider.complete(system, user)
                    ├── AnthropicProvider  (Claude)
                    └── OpenAIProvider     (OpenAI)
```

`cleanup.py` weiß nicht, welcher Anbieter antwortet. Ein neuer Anbieter (z. B. ein lokales
Modell über Ollama) braucht nur eine neue Klasse mit der Methode `complete`. Alle Anbieter
übersetzen ihre eigenen Fehler in einen gemeinsamen `LLMError`. So muss der restliche Code nur
einen Fehlertyp kennen.

### Wörterbuch & Snippets

- **`dictionary.txt`**: ein Begriff pro Zeile. Wird Whisper als `initial_prompt` mitgegeben
  (Whisper tut so, als wären diese Wörter gerade gesagt worden, und schreibt ähnlich klingende
  Wörter dann eher so) und der KI als Liste korrekter Schreibweisen.
- **`snippets.toml`**: Ist das *ganze* Diktat ein Auslöser („meine Adresse“), wird der
  hinterlegte Text eingefügt, sofort und ohne KI.
- Beide Dateien sind **persönlich** und stehen in `.gitignore`. Im Repo liegen nur
  `*.example.*`-Vorlagen, die beim ersten Start kopiert werden. Änderungen wirken beim
  nächsten Diktat, ohne Neustart.

### Lokal oder Cloud?

| | Lokal (faster-whisper) | OpenAI-Cloud |
|---|---|---|
| Privatsphäre | Audio bleibt auf dem PC | Audio geht an OpenAI |
| Kosten | kostenlos | ~0,3 Cent/Minute |
| Tempo | ~2 s | meist schneller |
| Offline | ✅ | ❌ (dann automatisch lokal) |

Umschaltbar im Tray-Menü → „Spracherkennung“.

## 5. Bekannte Grenzen

- Die Zwischenablage wird nur wiederhergestellt, wenn sie vorher **Text** enthielt.
- In Programmen, die mit Administratorrechten laufen, kann Windows das simulierte Strg+V
  blockieren.
- Einstellungen aus dem Tray-Menü gelten nur bis zum Beenden. Dauerhaft ändert man sie in `settings.toml`.
