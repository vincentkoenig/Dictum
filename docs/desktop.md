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
 gui/overlay.py zeigt "● Hört zu …"
        │
 Du lässt los
        ▼
 audio.py       liefert das Audio als Zahlenreihe (numpy-Array)
 gui/overlay.py zeigt "◐ Transkribiert …"
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
 gui/overlay.py zeigt "✦ Formuliert …"
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
| `keys.py` | Tastennamen | echte Taste → Name und zurück, Prüfung, Tasten-Aufnahme |
| `hotkey.py` | Halten/Antippen erkennen | Zustandsmaschine, getrennt von der Tastatur |
| `gui/hotkey_field.py` | „Taste wählen“ | Dialog: Taste drücken statt aus einer Liste wählen |
| `inserter.py` | Text einfügen | Zwischenablage + simuliertes Strg+V |
| `clipboard.py` | Zwischenablage | alle Formate sichern/zurücklegen, Diktat nicht im Win+V-Verlauf |
| `gui/overlay.py` | Flow Bar | Blase unten in der Mitte: Ruhe, Hover, Status, Klick = diktieren |
| `sounds.py` | Töne | eigener sanfter Ton in einstellbarer Lautstärke |
| `gui/tray.py` | Symbol im Infobereich | Menü wird vor dem Aufklappen synchronisiert |
| `gui/window.py` | Dictum-Fenster | Seitenleiste, Karte mit der Seite, Einstellungen als Dialog |
| `gui/theme.py` | Aussehen | Farben hell/dunkel, Stylesheet, Serifen-Überschriften |
| `shortcuts.py` | Desktop-Symbol, Startmenü | `.lnk` mit Symbol und AppUserModelID |
| `context.py` | Aktives Programm | Vordergrundfenster → Prozessname (Win32 + psutil) |
| `costs.py` | Kostenschätzung | Preise je Modell, Token grob aus der Textlänge |
| `gui/stats_tab.py` | Reiter Statistik | Kennzahlen, Säulendiagramm, Top-Programme |
| `gui/dictionary_tab.py` | Reiter Wörterbuch | Wörter und Snippets bearbeiten, sofort gespeichert |
| `styles.py` | Stile pro Programm | Programm → Kategorie → Stil, Anweisung an die KI |
| `gui/styles_tab.py` | Reiter Stile | Stil je Kategorie, eigene Zuordnung, Kontext-Haken |
| `commands.py` | Command Mode | Anweisung + markierter Text → KI → Ergebnis |
| `levels.py` | Flüstermodus | leise Aufnahmen auf Sprechpegel anheben |
| `learn.py` | Lern-Wörterbuch | Korrekturen im Textfeld erkennen (difflib) |
| `history.py` | Lokaler Verlauf | SQLite-Datei, nur auf diesem PC |
| `settings_io.py` | Einstellungen speichern | tomlkit erhält die Kommentare |
| `app.py` | Verbindet alles | Threads, Signale, Warteschlange |
| `__main__.py` | Einstiegspunkt | `python -m dictum`, Flags `--background`, `--restart` |

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
**Esc** verwirft jede laufende Aufnahme, auch eine angetippte (`escape()`); ohne Aufnahme bleibt
Esc eine ganz normale Taste.

### Freie Tastenwahl (`keys.py`, `gui/hotkey_field.py`)

Im Reiter *Einstellungen* steht keine Liste mehr, sondern **„Ändern …“**: Ein Dialog sagt „Drücke jetzt
die Taste“, man drückt sie (oder eine Kombination, oder eine Maustaste) und lässt los. Fertig ist die
Eingabe, sobald **alles losgelassen** ist, damit „Strg + R“ auch klappt, wenn die Finger nacheinander
abheben (`CaptureState`).

Damit das sauber bleibt, hat jede Taste einen **konkreten Namen** (`ctrl_r`, `f8`, `z`, `vk_173`,
`mouse_x1`). Der Hörer wandelt jedes Ereignis von pynput mit `canonical()` in so einen Namen um.
Gruppen wie `"ctrl"` werden mit `expand()` zu `{ctrl_l, ctrl_r}`. Verglichen wird dann nur noch Text.
Buchstaben werden über den Tastencode (`vk`) benannt, weil pynput unter gedrückter Strg-Taste sonst
Steuerzeichen statt „a“ meldet.

**Was als Taste taugt** (`check_hotkey`): Sondertasten wie Strg rechts, F1–F24, Feststelltaste, Pause,
Medientasten und Maustasten (Mausrad-Klick, Seitentasten) gehen allein. Buchstaben, Ziffern, Leertaste
und Co. brauchen eine Strg-, Alt-, Umschalt- oder Win-Taste dazu, sonst würde jedes Tippen ein Diktat
auslösen. Esc ist zum Abbrechen reserviert. Linke und rechte Maustaste fehlen mit Absicht.

**Sofort wirksam:** `HotkeyListener.set_keys()` tauscht die Taste im laufenden Betrieb, ein Neustart ist
nicht nötig. Während der Dialog offen ist, sind die Hotkeys pausiert (`set_enabled(False)`), sonst würde
das Drücken der alten Taste gleich ein Diktat starten. Der Maus-Hook läuft nur, solange eine Maustaste
belegt ist.

**Zusatz-Tasten wie bei Wispr Flow:** *Letztes Diktat einfügen* (Standard Umschalt+Alt+Z) und
*Letztes Diktat kopieren* (Umschalt+Alt+X). Praktisch, wenn ein Feld das Einfügen verschluckt hat. Sie
laufen als einfache Auslöser neben dem Diktat-Hotkey (`set_trigger`). Das Diktat selbst bleibt im
Speicher, nach einem Neustart kommt es aus dem Verlauf.

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
| Hauptthread | Qt: Overlay, Tray-Symbol, Fenster (Qt verlangt den Hauptthread) |
| pynput | Hört auf die Tastatur |
| Lade-Thread | Lädt einmalig das Whisper-Modell |
| Worker | Transkribiert, bereinigt, fügt ein |
| Meeting-Thread | Lädt Meeting-Aufnahmen hoch, wartet auf die Zusammenfassung |

Die Threads reden über **Warteschlangen** (`queue.Queue`) miteinander: Der Tastatur-Thread
legt das Audio hinein und ist sofort wieder frei; der Worker holt es ab und arbeitet es ab.

**Mit Qt gilt zusätzlich:** Qt-Objekte dürfen nur im Hauptthread verändert werden. Alle anderen
Threads rufen deshalb nur Methoden wie `overlay.show(…)` oder `tray.notify(…)` auf, die intern ein
**Signal** senden. Qt reiht Signale aus fremden Threads automatisch in die Warteschlange des
Hauptthreads ein, dort werden sie abgearbeitet. So muss man sich um Sperren nicht selbst kümmern.

### Das Overlay darf den Fokus nicht stehlen

Würde das Overlay beim Erscheinen zum aktiven Fenster, landete das Strg+V im Overlay statt
in deinem Dokument. In Qt gibt es dafür die Fenster-Eigenschaft `WindowDoesNotAcceptFocus`
(Windows: `WS_EX_NOACTIVATE`) und das Attribut `WA_ShowWithoutActivating`. Zusätzlich reagiert die
Pille nicht auf Mausklicks (`WA_TransparentForMouseEvents`), ein Klick geht an das Fenster dahinter.
Geprüft habe ich das nicht nur im Code, sondern am echten Fenster: Das Vordergrundfenster bleibt
unverändert, und die Fensterflags sind gesetzt.

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

### Mit einem einzigen OpenAI-Key (Stand Oktober 2026)

OpenAI kann beide Schritte übernehmen, jeweils im Reiter *Einstellungen* wählbar:

| Schritt | Modell | Preis (laut OpenAI-Preisseite) |
|---|---|---|
| Sprache → Text | `gpt-4o-mini-transcribe` (Standard) | ca. 0,003 $/min |
| | `gpt-4o-transcribe`, `whisper-1` | ca. 0,006 $/min |
| Text bereinigen | `gpt-5-nano` | 0,05 / 0,40 $ je 1 Mio. Token (ein/aus) |
| | `gpt-5-mini` | 0,25 / 2,00 $ |
| | Claude Haiku 5.5 (zum Vergleich) | 0,10 / 0,50 $ |

Ehrlich gerechnet ist die **Erkennung** der Teil, bei dem OpenAI sich lohnt (schneller als Whisper auf der
CPU, eine Stunde Diktat ≈ 18 Cent). Bei der **Bereinigung** liegen Haiku und `gpt-5-nano` fast gleichauf.
Ein Diktat hat ein paar hundert Token, das sind Bruchteile eines Cents. Der echte Vorteil eines
OpenAI-Keys ist deshalb, dass man **nur einen Anbieter** braucht.

Die gpt-5-Modelle denken standardmäßig erst nach. Für die Bereinigung ist das reine Wartezeit,
deshalb schickt `OpenAIProvider` `reasoning_effort="minimal"` mit (und versucht es ohne, falls ein Modell
das nicht kennt).

**Schlüssel:** Der Key steht nur in der Datei `.env` (nie im Repo). Im Reiter *Einstellungen* öffnet
„Schlüsseldatei öffnen“ die Datei, nach dem Speichern liest „Schlüssel neu laden“ sie ein, ohne Neustart.
Fehlt der Key, fällt Dictum bei der Erkennung auf das lokale Whisper und bei der Bereinigung auf den
Rohtext zurück.

## 5. Meetings am PC (Phase 5)

Tray-Menü → **🔴 Meeting aufnehmen** → Vorlage wählen (Meeting, Interview, Vorlesung, Notiz).
Während der Aufnahme ist das Tray-Symbol **rot**, und der Tooltip zeigt die Laufzeit. **⏹ Meeting
beenden** schließt ab. Wenig später meldet eine Windows-Benachrichtigung „Zusammenfassung
fertig“, und **Letztes Meeting öffnen** zeigt sie in der Web-App.

### Der Weg eines Meetings

```
 Mikrofon ─────► Thread ─► Puffer ┐
                                  ├─► mischen ─► ChunkAccumulator ─► Opus ─► Warteschlange
 PC-Ton (Loopback) ► Thread ─► Puffer ┘   (Summe)   (~5 Min., Schnitt         (Dateien auf
                                                     in Sprechpause)          der Festplatte)
                                                                                   │
                     Benachrichtigung ◄── Status abfragen ◄── Supabase ◄── Upload ┘
                                                (Phase-3-Backend: transcribe → summarize)
```

| Datei | Aufgabe |
|---|---|
| `meeting.py` | Aufnahme von Mikrofon und PC-Ton, mischen, in Stücke teilen |
| `encoder.py` | Stücke als Opus/OGG speichern |
| `upload_queue.py` | Warteschlange auf der Festplatte (`desktop/recordings/queue/`) |
| `meeting_controller.py` | Start/Stopp, Hintergrund-Upload, auf Ergebnis warten, Benachrichtigung |
| `sync.py` | Wörterbuch und Snippets mit der Cloud abgleichen |
| `cloud.py` | Supabase-Client, inklusive automatischer Login-Erneuerung |

### PC-Ton per WASAPI-Loopback

Windows bietet für jedes Ausgabegerät ein **Loopback**, eine Art virtuelles Mikrofon, das genau
das aufnimmt, was gerade abgespielt wird. Dazu gehört auch die Stimme der anderen in Teams oder
Zoom. Die Bibliothek `soundcard` macht es zugänglich (`include_loopback=True`). Wird nichts
abgespielt, liefert der Loopback Stille, und die Aufnahme läuft trotzdem weiter.

Beide Quellen laufen in **eigenen Threads**, weil das Lesen blockiert. Ein dritter Thread nimmt
alle 0,5 s von beiden gleich viel, **addiert** die Spuren (mit Lautstärke-Faktoren) und begrenzt
das Ergebnis auf −1…1, damit nichts übersteuert.

### Schnitt in der Sprechpause

Der erste Probelauf hat gezeigt: Werden die Stücke stur nach Zeit geschnitten, zerreißt es Sätze.
Whisper erkennt die Bruchstücke schlecht und erfand am Rand ein „Hm“. Deshalb sucht
`quietest_cut()` in den letzten **3 Sekunden** vor der Grenze die **leiseste 200-ms-Stelle** und
schneidet dort, also meist in einer Atempause.

| | Probelauf 1 (starr) | Probelauf 2 (Pause) |
|---|---|---|
| Stücklängen | 12,0 s · 12,0 s · 5,5 s | 10,6 s · 11,9 s · 6,9 s |
| Transkript | „…Offen ist noch. / Ob wir…“, „Hm, die Aufnahmen…“ | ganze Sätze, kein erfundenes „Hm“ |

### Warum Opus?

| Format | 5 Minuten |
|---|---|
| WAV, 48 kHz, 16 Bit | ~28 MB, über dem OpenAI-Limit von 25 MB |
| **Opus** | **~4 MB** (gemessen: 12 s ≈ 155 KB) |

### Nichts geht verloren

Wie in der Handy-App wird **alles zuerst gespeichert, dann hochgeladen**. Die Warteschlange liegt
als Dateien in `desktop/recordings/queue/` (in `.gitignore`):
- Ohne Netz bleiben die Dateien liegen und werden alle 30 s erneut versucht.
- Nach Absturz oder Neustart lädt Dictum beim nächsten Start hoch.
- Jeder Schritt ist **idempotent**. Ein Beispiel: `finish()` ändert eine Aufnahme nur, solange
  sie noch `uploading` ist. Sonst würde ein wiederholter Aufruf eine fertige Aufnahme auf
  „transcribing“ zurücksetzen. Diesen Fehler hat genau diese Überlegung gefunden.

**Login-Erneuerung:** Supabase-Tokens gelten 1 Stunde. Weil ein Meeting länger dauern kann, holt
`cloud.py` kurz vor Ablauf mit dem *refresh token* ein neues.

### Wörterbuch und Snippets abgleichen

Beim Start und alle 15 Minuten (`sync_minutes`) gleicht `sync.py` `dictionary.txt`/`snippets.toml`
mit der Cloud ab. Dort pflegt die Handy-App ihre Einträge. **Es wird nur ergänzt, nie gelöscht.**
Ohne Zeitstempel ist nicht erkennbar, ob ein fehlender Eintrag gelöscht wurde oder auf der
anderen Seite neu ist. Löschen macht man deshalb bewusst an beiden Stellen. PC-Diktate selbst
bleiben lokal und gehen nicht in die Cloud.

### Ausprobieren ohne echtes Meeting

```powershell
cd desktop
.venv\Scripts\python -X utf8 scripts\meeting_e2e.py   # spielt ~25 s Sprachausgabe ab
```

## 6. Dauerbetrieb: Autostart, Einzelinstanz, Logdatei (Phase 6)

**Ausgangspunkt:** Dictum lief nur, solange sein Terminal-Fenster offen war. Nach einem Neustart
reagierte die Hotkey-Taste deshalb nicht mehr, und es gab keinen Hinweis warum. Drei Bausteine
beheben das.

### Autostart (`autostart.py`)

Windows führt beim Anmelden alle Befehle aus, die in der Registry unter
`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` stehen. Dictum trägt dort einen
Eintrag `Dictum` ein:

```
"…\desktop\.venv\Scripts\pythonw.exe" -X utf8 "…\desktop\dictum_tray.pyw" --background
```

- **`pythonw.exe`** ist Python ohne Konsolenfenster. Beim Anmelden erscheint nur das Tray-Symbol.
- **`--background`**: Beim Anmelden öffnet sich kein Fenster, Dictum startet still im Infobereich.
  Startet man es von Hand, öffnet sich das Dictum-Fenster.
- **`dictum_tray.pyw`** ergänzt den Suchpfad selbst, denn Windows startet Run-Einträge nicht im
  Projektordner.
- Ein-/ausschalten: Tray → **Mit Windows starten** (Haken). Es braucht keine Administratorrechte,
  und es ist nur dein Benutzerkonto betroffen.
- **Selbstheilung:** Zieht man den Ordner um oder baut die virtuelle Umgebung neu, stimmt der Pfad
  nicht mehr. `refresh_if_enabled()` prüft das bei jedem Start und korrigiert ihn. Ist Autostart
  aus, wird er nie heimlich eingeschaltet.

### Einzelinstanz (`single_instance.py`)

Zwei laufende Dictums würden beide auf die rechte Strg-Taste hören: Ein Diktat würde doppelt
eingefügt. Der erste Prozess legt einen **Mutex** an, ein benanntes Objekt, das Windows verwaltet.
Ein zweiter Start merkt über ERROR_ALREADY_EXISTS, dass es das Objekt schon gibt, zeigt „Dictum
läuft bereits“ und beendet sich. Stirbt der erste Prozess, räumt Windows den Mutex selbst weg.
Anders als bei einer Sperrdatei bleibt also nie ein Geister-Sperrzeichen zurück.

### Logdatei (`logsetup.py`)

Ohne Konsole wäre jeder Fehler unsichtbar. Dictum schreibt deshalb alles nach
`desktop/logs/dictum.log` (Tray → **Logdatei öffnen**). Bei 1 MB wird die Datei rotiert, es bleiben
höchstens 3 alte Dateien. Auch nicht abgefangene Fehler in Hintergrund-Threads landen dort.
Ohne Konsole gibt es kein `stderr`, Fortschrittsbalken von Bibliotheken würden abstürzen, deshalb
wird `stderr` dann auf einen Papierkorb umgeleitet.

### Wie ich es geprüft habe

| Test | Ergebnis |
|---|---|
| Start über `pythonw.exe` aus einem fremden Arbeitsverzeichnis | läuft, Log vollständig |
| Zweiter Start | beendet sich, Log: „läuft bereits“, weiter genau eine Instanz |
| Gespeicherten Registry-Befehl per `CreateProcess` ausführen (wie Windows beim Anmelden) | Dictum startet |
| Unit-Tests: Registry mit eigenem Test-Schlüssel, Mutex, Log in Datei | 13 neue Tests |

Ein echter Neustart des Laptops ist nicht Teil der Prüfung.

## 7. Das Dictum-Fenster und Qt (Phase 6)

Bisher gab es nur ein Tray-Symbol und das Overlay beim Sprechen. Jetzt gibt es ein Fenster:
**Linksklick auf das Symbol** oder Tray → **Dictum öffnen**. Das **X** schließt nur das Fenster,
Dictum läuft im Infobereich weiter (beim ersten Mal sagt es das per Hinweis). Nur Tray →
**Beenden** beendet das Programm.

| Reiter | Inhalt |
|---|---|
| **Start** | Status („Bereit – Strg rechts halten und sprechen“, „Meeting läuft – 02:05“), Meeting starten und beenden, Einrichtungs-Check (Mikrofon, Schlüssel, Konto, Autostart), „Heute: 12 Diktate, 140 Wörter“ |
| **Verlauf** | Deine letzten Diktate mit Suche. Doppelklick kopiert einen Eintrag. |
| **Einstellungen** | Taste, Bedienung, Sprache, Spracherkennung, Modell, KI, Meetings, Verlauf, Autostart |
| **Info** | Version, Dateipfade, Logdatei, Wörterbuch und Snippets öffnen |

Der Einrichtungs-Check löst ein Problem aus dem Alltag: Wenn „nichts passiert“, sieht man hier sofort,
ob es am Mikrofon, an einem fehlenden Schlüssel oder am Konto liegt.

### Warum von tkinter und pystray auf Qt gewechselt wurde

tkinter und Qt wollen beide den **Hauptthread** für ihre Ereignisschleife, und in einem Prozess
geht nur eines von beiden. Für ein echtes Fenster braucht es Qt. Deshalb sind Overlay und
Tray-Symbol auf Qt umgezogen, wie in Khutba-Translation. Nebenbei wurde manches besser:

| | vorher (tkinter, pystray) | jetzt (Qt) |
|---|---|---|
| Hochauflösende Bildschirme | Skalierung von Hand umrechnen | automatisch |
| Overlay mit zwei Monitoren | immer Hauptbildschirm | dort, wo der Mauszeiger ist |
| Tray-Menü | Häkchen und Untermenüs mit Eigenheiten | normales Menü, vor dem Aufklappen synchronisiert |
| Benachrichtigung | nur Anzeige | anklickbar („Zusammenfassung fertig“ öffnet das Meeting) |
| Abhängigkeiten | tkinter, pystray, Pillow | PySide6-Essentials |

### Einstellungen speichern: sofort oder nach Neustart?

Das Fenster schreibt in `settings.toml`. Weil Python TOML nur lesen kann, benutzt es **tomlkit**,
das die Datei ändert und dabei alle Kommentare erhält. Vor dem Überschreiben wird der neue Inhalt mit
derselben Prüfung wie beim Start getestet. Ein ungültiger Wert lässt die alte Datei unberührt.

Danach übernimmt `DictumApp.apply_settings()` die neuen Werte:

| Wirkt sofort | Braucht einen Neustart |
|---|---|
| **Tasten**, Bedienung, Sprache, Spracherkennung, KI an/aus, KI-Anbieter, Töne, Meeting-Optionen, Verlauf, Autostart | das **lokale Modell** (es ist geladen) |

Für den Neustart gibt es „Speichern und neu starten“. Die neue Instanz startet mit `--restart`
und **wartet bis zu 20 Sekunden**, bis die alte beendet ist und den Mutex freigibt. Ohne das Warten
würde sie sich als „zweite Instanz“ sofort wieder beenden.

### Der lokale Verlauf

Nach jedem Diktat speichert `history.py` Rohtext und eingefügten Text in einer SQLite-Datei
(`desktop/data/history.db`, in `.gitignore`). Es bleibt **nur auf diesem PC**: Es geht nie in die Cloud
und erscheint nicht in der Handy-App. Man kann ihn komplett abschalten (`[history] enabled = false`),
die Aufbewahrung begrenzen (`keep_days`, Standard 90 Tage, ältere Einträge löscht Dictum beim Start)
oder im Fenster alles löschen.

Ein Detail aus der Praxis: Die Suche nutzt SQL `LIKE`, bei dem `%` und `_` Platzhalter sind. Sucht
man nach „50%“, würde sonst alles gefunden. `history.py` entwertet diese Zeichen mit `\`.

### Wie ich es geprüft habe

| Test | Ergebnis |
|---|---|
| 90 Tests, davon 22 für die Oberfläche (Qt-Plugin `offscreen`, ohne sichtbare Fenster) | alle grün |
| Overlay am echten Fenster: Vordergrundfenster, Fensterflags, Aufruf aus fremdem Thread | Fokus bleibt, Flags gesetzt, Signal kommt an |
| `scripts/dictate_e2e.py`: Sprachausgabe → echtes Whisper → echtes Claude → Verlauf | Diktat in 3,9 s verarbeitet, eingefügter Text steht im Verlauf |
| Echter Start über `pythonw`, Fenster per `WM_CLOSE` schließen | Fenster verschwindet, Prozess läuft weiter |
| Alter Autostart-Eintrag ohne `--background` | korrigiert sich beim Start selbst |

Nicht geprüft habe ich das Klicken im Tray-Menü und den Neustart-Knopf an der echten Oberfläche.
Dafür gibt es Tests der Menü-Logik und von `apply_settings`, aber keinen Klick auf dem Bildschirm.

### Ein „richtiges“ Programm: Symbol und Verknüpfungen (`shortcuts.py`)

- **Symbol:** `scripts/make_app_icon.py` malt das Mikrofon aus `gui/icons.py` in sieben Größen
  (16–256 px) in `desktop/assets/dictum.ico`. Windows nimmt je nach Ort die schärfste passende.
- **Verknüpfungen:** Im Reiter *Einstellungen* (Haken *Symbol auf dem Desktop*, *Eintrag im Startmenü*)
  oder per `python -m dictum --install-shortcuts`. Ziel ist `pythonw.exe` mit `dictum_tray.pyw`, also ohne
  Konsolenfenster. Doppelklick öffnet das Fenster; der Autostart startet dagegen still mit `--background`.
- **Taskleiste:** Ohne weiteres Zutun zeigt Windows das Python-Symbol. `set_app_id()` gibt dem Prozess die
  AppUserModelID `VincentKoenig.Dictum`, dieselbe steckt in den Verknüpfungen. So erscheint das Dictum-Symbol,
  und ein Anheften bleibt zugeordnet.
- **Ordner:** Der Desktop liegt oft in OneDrive. Deshalb fragt Dictum Windows (`SHGetFolderPath`), statt
  `~/Desktop` zu raten. Die Tests legen Verknüpfungen nur in Wegwerf-Ordnern an.

### Das Fenster im Stil von Wispr Flow (`gui/window.py`, `gui/theme.py`)

Statt Reitern gibt es jetzt eine **Seitenleiste** und rechts eine weiße **Karte** mit der aktuellen Seite:

| Seite | Inhalt |
|---|---|
| **Diktat** | Status, Banner „Stile einrichten“, Verlauf mit Suche (Zeit als „Heute 11:07“), rechts Kennzahlen |
| **Meetings** | Aufnahme starten/beenden, letztes Meeting, Einrichtungs-Check |
| **Statistik** | Tempo-Anzeige, gesparte Zeit, Wörter, Nutzung nach Programmart, Kalender der Serie, Top-Programme (wie „Insights“ bei Wispr Flow) |
| **Wörterbuch** / **Textbausteine** | die beiden Listen, jetzt getrennt (Lern-Schalter beim Wörterbuch) |
| **Stile** | Stil je Programmart, eigene Zuordnung, Kontext für die KI |
| **Notizblock** | Textfeld zum Ausprobieren des Diktats, bleibt gespeichert (`notizblock.txt`) |
| **Einstellungen** (unten links) | eigener Dialog mit Navigation: Allgemein, Erkennung & KI, Schlüssel, Datenschutz & System, Meetings, Info |

**Aussehen (`theme.py`):** Drei Dinge zusammen sorgen dafür, dass es überall gleich aussieht: der Qt-Stil
„Fusion“ (Qt zeichnet die Bedienelemente selbst), eine `QPalette` mit den Grundfarben und ein Stylesheet für
Rundungen, Karten und Knöpfe. Die Farben stehen in einer Tabelle je Modus, Umschalten heißt „andere Tabelle
einsetzen“. Überschriften sind Serifenschrift (Georgia), der Rest Segoe UI. Die Symbole der Seitenleiste sind
selbst gemalt (`icons.nav_icon`), damit sie nicht von einer Symbolschrift abhängen, die es nicht überall gibt.

**Schriften (`gui/fonts.py`):** Dictum benutzt dieselben Schriften wie Wispr Flow. Nachgesehen wurde im
Programmordner von Wispr Flow (`assets/fonts`) und im Stylesheet seiner App (`html { font-family: Figtree }`):
**Figtree** für Text, Knöpfe und Seitentitel, **EB Garamond** (mit Kursiv) für Banner-Überschriften und die großen
Kennzahlen. Beide sind freie Schriften (SIL Open Font License, Lizenztexte liegen in `desktop/assets/fonts`) und werden
beim Start nur in den Speicher geladen, installiert wird nichts. Fehlt eine Datei, nimmt Qt die nächste Schrift der
Liste in `theme.py` (Georgia, Segoe UI). Die Dateien sind im Programmpaket (`dictum.spec`) mit dabei.

**Keine Windows-Titelleiste:** Das Fenster hat keinen Rahmen mehr (`FramelessWindowHint`), also auch keine
Leiste mit Verkleinern/Vergrößern/Schließen in der Akzentfarbe. Die drei Knöpfe sitzen stattdessen oben rechts im
Fenster. Drei kleine Bausteine ersetzen, was Windows sonst liefert:

- `_DragBar`: Der leere Streifen oben (und beim Namen „Dictum“) verschiebt das Fenster per `startSystemMove()`,
  Windows übernimmt dabei auch das Andocken an Bildschirmränder. Doppelklick vergrößert/verkleinert.
- `_Root`: Die äußeren 8 Pixel erkennen Rand und Ecken, zeigen den passenden Pfeil und lassen Windows per
  `startSystemResize()` die Größe ändern.
- Das **X** versteckt nur das Fenster, Dictum läuft im Infobereich weiter (wie bisher). Der Einstellungsdialog
  hat ebenfalls keine Titelleiste.

**Statistik-Seite:** Tempo als Halbkreis (Skala bis 250 Wörter/Min.) mit „x-mal so schnell wie Tippen“; gesparte
Zeit; Wörter mit Diktaten, KI-Bereinigungen und Kosten; **Nutzung nach Programmart** (KI-Chats, Programmieren,
Dokumente, E-Mails, Arbeits- und private Nachrichten, Sonstiges) als Balken; ein **Kalender der letzten 26 Wochen**
(dunkler = mehr Wörter) mit aktueller und längster Serie. Die Programmart wird beim Diktat gespeichert
(`History.grp`, `styles.usage_group`) und erkennt auch KI-Chats im Browser am Fenstertitel; ältere Einträge ohne
Programm zählen nicht mit. Die Felder des Kalenders passen sich der Fensterbreite an.

**Hell/Dunkel:** Der Mond/Sonne-Knopf oben rechts schaltet um und speichert `[ui] theme`. Mögliche Werte:
`system` (folgt Windows, Standard), `light`, `dark`. Auch unter Einstellungen → Allgemein → Darstellung.

**Technik:** Jede Seite steckt in einem Scrollbereich (kleine Fenster schneiden nichts ab) und hat eine
`refresh()`. Ein Zeitgeber ruft sie nur für die sichtbare Seite auf. Die Auswertung der Statistik auf der Startseite
läuft höchstens alle 5 Sekunden, weil sie den ganzen Verlauf liest.

### Flow Bar und Töne (`gui/overlay.py`, `sounds.py`)

**Flow Bar:** Die kleine Blase unten in der Bildschirmmitte ist jetzt dauerhaft da (wie bei Wispr Flow),
solange sie in den Einstellungen eingeschaltet ist.

| Zustand | Aussehen | Klick |
|---|---|---|
| Ruhe | schmaler dunkler Strich | |
| Maus darüber | zwei Kapseln: links **Mikrofon**, rechts **Aufnahme-Knopf** mit **Pfeil**. Der Knopf unter der Maus wird heller, darüber steht ein Hinweis („Diktieren **Strg rechts**“, „Meeting aufnehmen“) | Mikrofon: Diktat starten/beenden · Aufnahme: Meeting starten/beenden (rot, solange es läuft) · Pfeil: Karte mit den Meeting-Arten |
| Aufnahme | „● Hört zu …“ (bzw. „Befehl – sprich …“) | beendet die Aufnahme |
| Verarbeitung, Meldung | „Transkribiert …“, „Formuliert …“, „Nichts erkannt“ … | nur Anzeige |

**Kein Flimmern, überall treffbar:** Unter Windows lassen durchsichtige Fenster Mausklicks genau dort durch, wo nichts
gemalt ist. Dann „verließ“ die Maus die Blase mitten auf ihr (im Zwischenraum der Kapseln), sie schrumpfte, die Maus
war wieder darauf, und es flimmerte. Deshalb hat das ganze Fenster eine fast unsichtbare Grundfläche (Alpha 12 von 255,
`HIT_ALPHA`), der Ruhestrich eine großzügige Trefffläche (110 × 30 Pixel) und das Hover-Fenster einen treffbaren Rand rund
um die Kapseln. Das Hover-Fenster ist größer als die Fläche des Ruhestrichs und sitzt auf derselben Mitte und Unterkante,
also führt die Maus von jeder Stelle des Strichs ohne Lücke zu beiden Kapseln. Beim Verlassen klappt die Blase erst nach
250 ms zu, und nur wenn die Maus wirklich nicht mehr darauf ist (beim Vergrößern schickt Qt kurz ein „Verlassen“).
Zwei gleichzeitig laufende Blasen an derselben Stelle (z. B. Wispr Flow und Dictum) stören sich gegenseitig.

Die Blase ist der Flow Bar von Wispr Flow nachempfunden (Kapseln, Hinweis über dem Knopf, kleine Karte beim Pfeil; die Karte zeigt
statt „Kalender verbinden“ die Meeting-Arten). Ein Klick auf das Mikrofon verhält sich wie zweimaliges Antippen der Taste: `HotkeyStateMachine.start_toggled()` startet im
Zustand `TOGGLED`, `finish()` beendet. Dadurch kommen Mausklick und Tastatur nicht durcheinander. Die Blase
**stiehlt nie den Fokus**: Das Fenster hat `WindowDoesNotAcceptFocus` (unter Windows `WS_EX_NOACTIVATE`), also
bleibt auch nach einem Klick das Programm aktiv, in das der Text soll. Mit Flow Bar sitzt die Blase auf dem
Hauptbildschirm; ohne sie erscheint sie wie früher nur während einer Aufnahme und dort, wo der Mauszeiger ist.
Aus- und einschalten: Einstellungen → „Flow Bar anzeigen“ (wirkt sofort).

**Töne:** Standardmäßig **aus**. Sind sie an, spielt `sounds.py` einen selbst erzeugten Ton: eine kurze
Sinuswelle (70 ms) mit weichen Flanken, damit nichts knackt, deren Lautstärke einstellbar ist (Standard 20 %).
Der alte Windows-Piepton (`winsound.Beep`) ließ sich nicht leiser stellen, deshalb wurde er ersetzt. Der Ton
liegt als WAV im Arbeitsspeicher und läuft in einem eigenen Thread, damit die Aufnahme nicht wartet.

### Reiter Wörterbuch und Statistik

**Wörterbuch** (`gui/dictionary_tab.py`): Eigene Wörter und Textbausteine werden im Fenster hinzugefügt,
geändert und gelöscht, ohne Textdatei. Gespeichert wird sofort in dieselben Dateien wie bisher
(`dictionary.txt`, `snippets.toml`), und weil `_process` sie bei jedem Diktat neu liest, wirkt es gleich.
Einleitende Kommentare der Dateien bleiben erhalten; geschrieben wird erst in eine Nebendatei und dann
umbenannt, damit eine halb geschriebene Datei nie die alte ersetzt. Doppelte Wörter und doppelte Auslöser
werden abgelehnt (Groß-/Kleinschreibung egal).

**Statistik** (`gui/stats_tab.py`, `History.stats()`): Alles wird aus dem lokalen Verlauf gerechnet.

| Kennzahl | Berechnung |
|---|---|
| Wörter, Diktate | Summen über den Verlauf |
| Wörter pro Minute | Wörter ÷ gesprochene Minuten (Länge der Aufnahmen, mit Pausen) |
| Tage in Folge | aufeinanderfolgende Tage mit Diktat; bricht nicht ab, nur weil heute noch nichts diktiert wurde |
| gespart | Wörter ÷ 40 (Tippen mit 40 Wörtern/Min.) minus gesprochene Zeit |
| Cloud-Kosten | Schätzung je Diktat (`costs.py`): Audio-Minuten bei OpenAI-Erkennung plus Token der Bereinigung |
| Top-Programme | Wörter und Diktate je Programm |

Das **Programm** merkt sich `context.active_window()` beim Start der Aufnahme: Vordergrundfenster →
Prozess → Name. Programme mit Administratorrechten verweigern den Namen, dann bleibt er leer. Der Name
steht nur im lokalen Verlauf. Ältere Datenbanken bekommen die neuen Spalten `app` und `cost` beim Öffnen
nachgerüstet (`MIGRATIONS`), alte Einträge haben dann kein Programm.

### Lern-Wörterbuch (`learn.py`)

Du diktierst „Wir nutzen super Base“, Whisper schreibt es so, du machst im Textfeld „Supabase“ daraus.
Dictum nimmt das Wort selbst ins Wörterbuch auf; beim nächsten Mal stimmt es sofort. So funktioniert es:

1. Nach dem Einfügen merkt sich Dictum Text und Programm.
2. Nach `learn_delay` Sekunden (Standard 10) liest es das Eingabefeld erneut (`context.field_text`) und
   vergleicht **Wort für Wort** mit dem Eingefügten (`difflib.SequenceMatcher`).
3. Gelernt wird nur, was sicher eine **Korrektur** ist:
   - ein bis drei Wörter wurden durch ein bis drei andere ersetzt (auch zusammen-/auseinandergeschrieben),
   - links oder rechts davon steht der Text unverändert (zwei Wörter reichen als Anker; so ist es unsere Stelle),
   - alt und neu sehen sich ähnlich (Ähnlichkeit ≥ 0,5, ohne Leerzeichen gerechnet): „Mueller → Müller“ ja,
     „Mueller → Frau“ nein,
   - das neue Wort steht noch nicht im Wörterbuch, und nur Groß-/Kleinschreibung zählt nicht,
   - höchstens drei neue Wörter pro Diktat.
   Ein umformulierter Satz erzeugt deshalb keine Einträge.
4. Neue Wörter landen in `dictionary.txt`, und eine Meldung sagt, welche. Falsche Einträge löscht man im Reiter
   *Wörterbuch*.

**Datenschutz:** Weil dafür der Text im Eingabefeld gelesen wird, ist das Lernen **aus**, bis man es im Reiter
*Wörterbuch* einschaltet. Es bleibt lokal, nur das gelernte Wort wird gespeichert, Passwortfelder werden nie
gelesen, und wer inzwischen in ein anderes Programm gewechselt ist, wird nicht ausgelesen.

**Grenze:** Das Lesen hängt an UI Automation. Programme, die ihr Textfeld nicht preisgeben (manche Spiele,
einige Electron-Apps), liefern nichts, dann lernt Dictum dort nichts. Das Ergebnis der Tests betrifft die
Vergleichslogik, nicht jede einzelne Anwendung.

### Flüstermodus und Freihand (`levels.py`)

**Freihand** (Hände frei, Aufnahme läuft von allein weiter) gibt es von Anfang an: Die Taste **kurz antippen**
startet die Aufnahme, ein zweites Antippen beendet sie (siehe Zustandsmaschine, `TOGGLED`). Wispr Flow macht
dafür einen Doppeltipp, weil dort Halten und Antippen sonst kollidieren; bei Dictum entscheidet die Haltedauer
(unter 0,4 s = Antippen), das ist eine Bewegung weniger. Neu ist ein **Zeitlimit** (Standard 20 Minuten, wie bei
Wispr): Eine vergessene Aufnahme endet von selbst und wird verarbeitet (`HotkeyStateMachine.finish`, damit der
nächste Tastendruck wieder sauber eine neue Aufnahme startet). Einstellbar, 0 = unbegrenzt.

**Flüstermodus:** Wer leise spricht, wird von Whisper oft nicht verstanden, weil der eingebaute Sprachfilter
(VAD) leise Sprache für Stille hält. Zwei Mittel, beide automatisch:

1. `levels.boost_quiet`: Misst den Pegel der Sprache (90. Perzentil der 20-ms-Blöcke, damit Pausen den Wert
   nicht drücken) und hebt die Aufnahme auf einen normalen Pegel an, höchstens um das 30-Fache (sonst würde
   nur Rauschen laut). Normal laute Aufnahmen und Stille bleiben unverändert.
2. Der Sprachfilter des lokalen Whisper wird empfindlicher gestellt (Schwelle 0,3 statt 0,5).

Das gilt für lokale und OpenAI-Erkennung und lässt sich im Reiter *Einstellungen* ausschalten. Getestet ist die
Verstärkung mit künstlichen Tönen (Pegel, Grenzen, Stille); mit echtem Flüstern solltest du es selbst
ausprobieren und mir sagen, ob die Schwellen passen.

### Command Mode: Text per Sprache umschreiben (`commands.py`)

**Bedienung:** Text markieren, die Befehls-Taste (Standard **F9**, frei wählbar) halten oder antippen, eine
Anweisung sprechen („mach das kürzer“, „übersetze ins Englische“, „formuliere freundlicher“), loslassen. Das
Ergebnis ersetzt die Markierung, **Strg+Z macht es rückgängig**, **Esc** bricht die Aufnahme ab. Ohne
Markierung schreibt die KI einen neuen Text nach der Anweisung („schreib eine kurze Absage für morgen“).

```
F9 gedrückt ─► Aufnahme (Overlay "Befehl – sprich …")  ─► Anweisung erkannt (wie beim Diktat)
   ─► Strg+C: markierten Text holen (copy_selection) ─► KI: Anweisung auf Text anwenden
   ─► Strg+V: Ergebnis ersetzt die Markierung (insert_text) ─► Verlauf
```

Die Teile im Einzelnen:

- **Zweite Zustandsmaschine.** Der Command Mode benutzt dieselbe Logik wie das Diktat (Halten/Antippen/Esc),
  nur mit eigener Taste. `HotkeyListener` verwaltet jetzt mehrere solcher Maschinen (`add_machine`).
- **Markierten Text holen** (`inserter.copy_selection`): Dictum legt einen Platzhalter in die Zwischenablage,
  „drückt“ Strg+C und wartet, bis der Platzhalter verschwindet. Bleibt er stehen, war nichts markiert. Die
  vorherige Zwischenablage kommt danach zurück.
- **Sicherheit:** Markierter Text und Anweisung stehen in eigenen Tags und gelten als Daten. Steht im Text
  „ignoriere alles“, wird das nicht befolgt. Das Schließ-Tag wird herausgefiltert, damit ein Text nicht aus dem
  Block ausbrechen kann.
- **Fehler lassen den Text in Ruhe:** Ist die KI nicht erreichbar oder liefert sie nichts, wird nichts
  eingefügt, die Markierung bleibt unverändert, und das Overlay sagt es.
- **Tasten dürfen sich nicht überlappen:** Eine Kombination darf nicht in einer anderen stecken (sonst würde
  „Strg rechts“ schon das Diktat starten, bevor man „Strg rechts + F9“ fertig gedrückt hat). Das prüft
  `config._validate` beim Speichern.

Braucht die KI-Bereinigung-Einstellungen (Claude oder OpenAI, mit gültigem Key); dasselbe Modell wie die
Bereinigung. Ausschalten: Befehls-Taste auf „Aus“.

### Stile pro Programm und Kontext (`styles.py`, `context.py`)

In einer Chat-Nachricht schreibt man anders als in einer Mail. Dictum merkt sich beim Start der Aufnahme
das Vordergrundfenster und wählt daraus den **Stil**:

1. eigene Zuordnung für ein Programm (`[styles.apps]`, z. B. `chrome = "casual"`), sonst
2. Kategorie aus dem Programmnamen (Outlook → E-Mail, WhatsApp → private Nachrichten, Slack → Arbeits-Chat)
   oder bei Browsern aus dem **Fenstertitel** („Posteingang … Gmail“ → E-Mail), sonst
3. der Stil von „Alles andere“.

| Stil | Wirkung |
|---|---|
| Neutral | wie gesprochen (Standard für Arbeits-Chat und alles andere) |
| Formell | Satzzeichen vollständig, Punkt am Ende (Standard für E-Mail) |
| Locker | normale Schreibweise, aber kein Punkt am Ende eines Satzes (Standard für private Nachrichten) |
| Sehr locker | alles klein, kaum Satzzeichen |
| Begeistert | Ausrufezeichen statt Punkt, wo es passt |

**Ein Stil ändert nur Groß-/Kleinschreibung und Satzzeichen, nie die Wörter.** Das steht ausdrücklich im
Prompt, und so passt es zur Regel der Bereinigung „nichts hinzufügen, nichts weglassen“ (und zur
Plausibilitätsprüfung, die zu stark veränderte Antworten verwirft).

**Kontext (`[context]`):** Damit Namen richtig geschrieben werden, kann die KI zusätzlich den
**Fenstertitel** („Re: Angebot Müller GmbH“) und, wenn man es einschaltet, den **Text im Eingabefeld**
sehen. Letzteres liest `context.field_text()` über UI Automation, die Schnittstelle, über die auch
Vorlese-Programme Fenster lesen. Datenschutz:

- Fenstertitel ist an (Standard), Feldtext ist **aus** (Standard). Beides ist im Reiter *Stile* schaltbar.
- Es geht nur an den KI-Anbieter, nur wenn die Bereinigung an ist, und wird nirgends gespeichert.
- Passwortfelder werden nie gelesen. Die Abfrage läuft in einem Hilfs-Thread mit 1,5 s Zeitlimit.
- Der Kontext steht im Prompt in einem eigenen `<kontext>`-Block mit dem Hinweis „keine Anweisung, nie
  in der Ausgabe“. Das Schließ-Tag wird herausgefiltert, damit der Text nicht aus dem Block ausbrechen kann.

### Als Programm: Dictum.exe (`dictum.spec`, `scripts/build_exe.ps1`)

Bisher lief Dictum nur mit der installierten Python-Umgebung des Projekts. Mit **PyInstaller** wird daraus ein
Programmordner, der ohne Python läuft:

```powershell
cd desktop
powershell -File scripts\build_exe.ps1                 # baut dist\Dictum\Dictum.exe (ca. 350 MB, 2–3 Minuten)
powershell -File scripts\install_exe.ps1 -MigrateData  # kopiert ihn nach %LOCALAPPDATA%\Programs\Dictum
```

**Was PyInstaller tut:** Es sammelt Python, alle Bibliotheken (Qt, Whisper-Rechenkern, Audio …) und den Code in
einen Ordner (`onedir`) und legt einen kleinen Starter `Dictum.exe` davor. Der Bauplan steht in `dictum.spec`.
Zwei Dinge muss man ihm ausdrücklich sagen: die **Sprachfilter-Datei** von faster-whisper (eine `.onnx`, die
PyInstaller nicht von selbst findet) und die **KI-Anbieter**, die Dictum erst zur Laufzeit nach Namen lädt.

**Wohin mit den persönlichen Dateien?** Ein Programm in `Programs\Dictum` soll beim nächsten Update einfach
ersetzt werden können, ohne dass Einstellungen oder Verlauf verloren gehen. Deshalb liegen sie als Programm in
`%APPDATA%\Dictum` (`config.py`: `FROZEN`, `RESOURCE_DIR`, `DESKTOP_DIR`):

| Datei | Aus dem Quellcode | Als Programm |
|---|---|---|
| `settings.toml`, `dictionary.txt`, `snippets.toml`, `data\history.db`, `logs\` | `desktop\` | `%APPDATA%\Dictum` |
| `.env` (Schlüssel) | Projektordner | `%APPDATA%\Dictum\.env` |
| Standard-Einstellungen, Vorlagen, Symbol | `desktop\` | im Programmpaket (`_internal`) |

Beim ersten Start legt das Programm den Datenordner an und kopiert die Standard-Einstellungen hinein.
`install_exe.ps1 -MigrateData` übernimmt zusätzlich Einstellungen, Wörterbuch, Snippets und Verlauf der
bisherigen Version (vorhandene Dateien werden als `.bak` gesichert). Die **Schlüssel** kopiert nur
`-MigrateKeys`, oder du trägst sie im Fenster ein (Einstellungen → Schlüsseldatei öffnen).

`Dictum.exe --install` legt Desktop-Symbol und Startmenü-Eintrag an und schaltet Autostart ein. Autostart
und Neustart kennen den Unterschied: Als Programm starten sie `Dictum.exe`, aus dem Quellcode `pythonw.exe` mit
dem Startskript. Wer die Version wechselt, bekommt den Autostart-Eintrag beim nächsten Start automatisch passend
korrigiert (`refresh_if_enabled`).

**Geprüft:** Gebaut, gestartet, der Datenordner wurde angelegt, Whisper-Modell und Sprachfilter laden, und ein
simulierter Tastendruck durchlief Hotkey, Mikrofon und Erkennung ohne Fehler im Log. Das Installationsskript
ist auf Syntax geprüft, aber noch nicht ausgeführt. **Nicht geprüft:** Windows Defender kann unsignierte
`.exe`-Dateien beim ersten Start verdächtig finden (PyInstaller-Programme sind dafür bekannt). Ein
Code-Signatur-Zertifikat kostet Geld und gibt es für ein Hobby-Projekt meist nicht.

## 8. Bekannte Grenzen

- **Einwilligung:** Dictum erinnert beim Start daran (§ 201 StGB). Fragen musst du selbst.
- **Kopfhörer und Bluetooth:** Aufgenommen wird der PC-Ton des Standard-Ausgabegeräts. Wechselt
  man während des Meetings das Gerät, fehlt danach der PC-Ton.
- **Eine Spur:** Mikrofon und PC-Ton werden gemischt. Wer was gesagt hat, unterscheidet erst eine
  Sprechererkennung (Idee für Phase 6).

### Allgemein

- Die Zwischenablage kommt nach dem Einfügen **mit allen Formaten** zurück (Bild, formatierter Text, kopierte Dateien). Nur reine Windows-Handles ohne Speicherblock (`CF_BITMAP` & Co.) bleiben außen vor; zu Bildern liegt immer auch `CF_DIB` bereit.
- In Programmen, die mit Administratorrechten laufen, kann Windows das simulierte Strg+V
  blockieren.
- Einstellungen aus dem **Tray-Menü** gelten nur bis zum Beenden. Dauerhaft speichert man sie im Reiter
  **Einstellungen** (oder in `settings.toml`).
