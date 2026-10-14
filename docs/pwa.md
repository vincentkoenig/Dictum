# Die Handy-App erklärt (PWA)

**Adresse:** https://vincentkoenig.github.io/Dictum/
**Code:** [`pwa/`](../pwa/)

## 1. Was ist eine PWA?

Eine **Progressive Web App** ist eine Webseite, die sich wie eine App verhält:

| Eigenschaft | Wie |
|---|---|
| Eigenes Icon auf dem Startbildschirm | **Manifest** (`manifest.webmanifest`): Name, Icon, Farben |
| Startet ohne Browser-Leiste | `display: "standalone"` im Manifest |
| Startet auch offline | **Service Worker**: ein Hintergrund-Skript, das die App-Dateien zwischenspeichert |
| Ein Code für iPhone und Android | Es ist eine Webseite, kein App-Store nötig |

Beides erzeugt `vite-plugin-pwa` beim Bauen automatisch ([`vite.config.ts`](../pwa/vite.config.ts)).

**Installieren:**
- **iPhone (Safari):** Teilen-Symbol → „Zum Home-Bildschirm“
- **Android (Chrome):** Menü ⋮ → „App installieren“ bzw. „Zum Startbildschirm hinzufügen“

## 2. Aufbau des Codes

```
pwa/src/
├── main.tsx          Einstieg: hängt die App in die Seite
├── App.tsx           Rahmen: Login-Prüfung, Bildschirmwahl, Navigation, Warteschlange
├── styles.css        Gestaltung (Farben als Variablen, hell/dunkel automatisch)
├── lib/              LOGIK – ohne Oberfläche, deshalb testbar
│   ├── supabase.ts   Verbindung zum Backend
│   ├── api.ts        alle Backend-Zugriffe an einer Stelle
│   ├── audio.ts      Aufnahme: Format, 5-Minuten-Stücke, Pegel, Bildschirm anlassen
│   ├── queue.ts      Offline-Warteschlange (IndexedDB)
│   ├── clipboard.ts  Kopieren – auch wenn der Text erst später kommt
│   ├── markdown.ts   Export
│   ├── route.ts      Welcher Bildschirm? (#/…)
│   └── types.ts      Datenstrukturen
├── components/       wiederverwendbare Bausteine (Icons, Liste, Pegelanzeige)
└── screens/          die Bildschirme: Login, Home, Dictate, Record, Detail, Search, Settings
```

Die Regel dahinter: **Logik (`lib/`) und Oberfläche (`screens/`) sind getrennt.** Die Bildschirme
rufen nur Funktionen wie `dictate()` oder `listRecordings()` auf und wissen nichts von Tabellen
oder Dateipfaden.

### React in einem Absatz

React baut die Oberfläche aus **Komponenten**, also Funktionen, die beschreiben, was zu sehen
ist. Ändert sich ein **State** (`useState`), etwa „Aufnahme läuft“, ruft React die Funktion neu
auf und aktualisiert nur das, was sich geändert hat. `useEffect` ist für Nebenwirkungen da:
Daten laden, Timer starten und beim Verlassen wieder aufräumen.

## 3. Die drei kniffligen Stellen

### a) Audio in Stücken (`audio.ts`)

Der Browser nimmt mit dem **MediaRecorder** auf. Zwei Probleme:

1. **Formate:** Chrome/Android liefert `webm`, Safari/iPhone `mp4`. `pickMimeType()` fragt den
   Browser, was er kann. Das Backend akzeptiert beides.
2. **Eigenständige Stücke:** Der MediaRecorder kann zwar alle X Sekunden Daten liefern, aber nur
   das erste Teil enthält den Datei-Kopf. Die anderen Teile allein sind keine gültigen Dateien.
   Deshalb stoppt `ChunkedRecorder` den Recorder **alle 5 Minuten und startet sofort neu**. Jedes
   Stück ist so eine vollständige Datei. Die Lücke dazwischen liegt im Millisekundenbereich.

### b) Offline-Warteschlange (`queue.ts`)

```
Aufnahme ──► IndexedDB (im Browser) ──► Supabase
              create, chunk 0, chunk 1, …, finish
```

- **Alles geht zuerst in die Warteschlange.** Die Aufnahme hängt nie vom Netz ab.
- Abgearbeitet wird **der Reihe nach** und beim ersten Fehler gestoppt. So kann „finish“ nie vor
  dem letzten Stück laufen.
- Jeder Schritt ist **idempotent**: Zweimal ausgeführt ergibt dasselbe wie einmal (`upsert`,
  feste IDs). Ein abgebrochener Upload kann deshalb gefahrlos wiederholt werden.
- Die ID der Aufnahme erzeugt der Browser selbst (`crypto.randomUUID()`), so funktioniert auch der
  Start ohne Netz.
- `App.tsx` arbeitet die Schlange ab: beim Start, wenn das Handy wieder online ist, und alle 30 s.

### c) Automatisch kopieren (`clipboard.ts`)

Browser erlauben das Kopieren nur **direkt nach einem Fingertipp**. Der Diktat-Text kommt aber
erst 2–3 s später vom Server. Der Trick: Beim Tipp auf Stopp wird ein `ClipboardItem` mit einem
**Promise** als Inhalt geschrieben. Das ist ein Platzhalter, der sagt „der Text kommt gleich“.
Der Browser merkt sich die Erlaubnis und füllt die Zwischenablage, sobald der Text da ist. Klappt
das nicht, erscheint ein Kopieren-Knopf.

## 4. Weitere Entscheidungen

| Entscheidung | Warum |
|---|---|
| **Hash-Routing** (`#/search`) statt `/search` | GitHub Pages kennt nur echte Dateien. `/Dictum/search` wäre ein 404. Was hinter `#` steht, sieht der Server nie. |
| **Abfragen alle 3–4 s** statt Live-Verbindung | Solange etwas verarbeitet wird, lädt die Seite neu. Einfacher als Realtime und genauso gut für diesen Zweck. |
| **Wake Lock** | Hält den Bildschirm während der Aufnahme an, sonst stoppt das iPhone die Aufnahme. |
| **Pegelanzeige ohne React-State** | 60 Aktualisierungen pro Sekunde direkt am DOM, statt die ganze Seite 60-mal neu zu zeichnen |
| **Keine UI-Bibliothek** | Etwa 300 Zeilen CSS reichen. Jede Zeile ist nachvollziehbar. |

## 5. Veröffentlichung

[`.github/workflows/pwa.yml`](../.github/workflows/pwa.yml) läuft bei jedem Push mit Änderungen
in `pwa/`:

```
npm ci → npm test → npm run build → GitHub Pages
```

Schlägt ein Test fehl, wird **nicht** veröffentlicht. Den Verlauf siehst du im Repo unter
„Actions“. Neue Versionen lädt die App beim nächsten Start automatisch (`registerType: "autoUpdate"`).

## 6. Lokal entwickeln

```powershell
cd pwa
npm install
npm run dev      # http://localhost:5173/Dictum/
npm test         # Vitest: Warteschlange, Formate, Export, Routing
npm run build    # Typprüfung + Build nach dist/
```

Fürs Mikrofon braucht der Browser **HTTPS** oder `localhost`. Zum Testen am Handy deshalb die
veröffentlichte Adresse nehmen.

## 7. Grenzen

| Grenze | Erklärung |
|---|---|
| **Bildschirm muss an bleiben** | Ein Handy-Browser darf im Hintergrund nicht dauerhaft aufnehmen. Hardware wie Plaud oder Pocket hat das Problem nicht. Eine native App könnte das. |
| **Kein Tippen in fremde Apps** | Am Handy gibt es Kopieren und Teilen statt direktem Einfügen. Dafür bräuchte es eine eigene Tastatur-App. |
| **iOS-Eigenheiten** | Kopieren nach einer Wartezeit und Wake Lock funktionieren erst mit neueren iOS-Versionen. Ältere bekommen den Kopieren-Knopf. |
| **Kaltstart** | Das erste Diktat nach längerer Pause dauert ~13 s statt ~3 s (siehe [backend.md](backend.md)). |
