# Funktionen im Vergleich: Wispr Flow, Pocket, Plaud und Dictum

Ziel: Von den drei Vorbildern alles übernehmen, was in Software machbar ist. Wo sich Funktionen
überschneiden, baut Dictum die **bessere Variante genau einmal**. Quellen: Produktseiten und Hilfecenter
der Anbieter (Stand Oktober 2026, siehe unten).

✅ fertig · 🔨 geplant (Phase) · ➖ nicht umsetzbar oder nicht nötig

## Diktieren (Vorbild: Wispr Flow)

| Funktion | Stand | Anmerkung |
|---|---|---|
| Diktat in jede App, Satzzeichen, Füllwörter, Selbstkorrektur, Listen | ✅ | Phase 1–2 |
| Hotkey halten oder antippen | ✅ | Doppeltipp als Freihand-Modus: 🔨 8 |
| Eigenes Wörterbuch, Snippets, Abgleich mit dem Handy | ✅ | Phase 2, 5 |
| Fenster, Verlauf mit Suche, Tagesstatistik | ✅ | Phase 6 |
| **Command Mode**: Text markieren, Befehl sprechen („kürzer“); ohne Markierung Text erzeugen; Esc bricht ab, Strg+Z macht rückgängig | 🔨 8 | eigener Hotkey |
| Stile pro App (formell/locker) und Kontext (Namen aus Fenster und Textfeld) | 🔨 8 | Windows-UI-Automation |
| Flüstermodus | 🔨 8 | automatische Pegelanhebung |
| Wörterbuch lernt aus deinen Korrekturen, Branchenlisten | 🔨 8 | ein gemeinsames Wörterbuch |
| Entwickler-Modus (CamelCase, Dateinamen), Privatmodus | 🔨 8 | |
| Verlauf und Statistik (Tempo, Top-Apps), Kosten pro Aufnahme | 🔨 8 | Verlauf selbst ✅ |
| Android: schwebende **Blase** in Textfeldern (Tipp- und Halte-Modus) | 🔨 11 | Bedienungshilfe-Dienst |
| iPhone-Tastatur | ➖ | Handy ist Android |
| Team: geteilte Wörterbücher, Nutzungs-Dashboards | ➖ | Einzelnutzer |

## Aufnehmen (Vorbild: Pocket, Plaud, Wispr Notetaker)

| Funktion | Stand | Anmerkung |
|---|---|---|
| Ein-Tasten-Aufnahme, offline, späterer Sync | ✅ | Handy-App und PC |
| Meetings am PC: Mikrofon und PC-Ton | ✅ | Phase 5 |
| Aufnahme bei gesperrtem Handy | 🔨 7 | Flutter-Hülle mit Mikrofon-Dienst |
| Audio importieren (Dateien, WhatsApp-Sprachnachrichten) | 🔨 7, 9 | Teilen-Ziel am Handy |
| Live-Transkript während der Aufnahme | 🔨 9 | 30-Sekunden-Stücke |
| **Markieren** mit Notiz und Foto (Folien, Whiteboard, Visitenkarte) | 🔨 9 | ein Knopf für „Highlight“, „Notiz“, „Foto“ |
| Sprecher erkennen und benennen (Stimmprofile) | 🔨 9 | OpenAI-Diarisierung, bis 4 Referenzclips |
| Telefonate mit der Stimme des Gegenübers | ➖ | Android blockiert das für Apps; Lautsprecher-Modus in 11 |
| Gerät: Knopf, Kontaktmikrofon, Akku, 15 m Reichweite | ➖ | Hardware; Ersatz: Kachel, Widget, Benachrichtigungs-Knöpfe |

## Zusammenfassen (Vorbild: Pocket, Plaud)

| Funktion | Stand | Anmerkung |
|---|---|---|
| Strukturierte Zusammenfassung: Kernpunkte, To-dos, Entscheidungen, offene Fragen | ✅ | Phase 3 |
| Vorlagen | ✅ 4 | 🔨 9: ca. 20, eigene Vorlagen („Skills“), mehrere Zusammenfassungen je Aufnahme, bearbeiten |
| Mindmap | 🔨 9 | aus den `topics` |
| Übersetzen | 🔨 9 | |
| Tags, Ordner, Favoriten | 🔨 9 | Suche ✅ |

## Wissen und Verbindungen (Vorbild: Pocket, Plaud)

| Funktion | Stand | Anmerkung |
|---|---|---|
| Fragen an alle Aufnahmen, Gedächtnis (Personen, Themen), Recherche-Bericht | 🔨 10 | Embeddings plus Claude mit Quellenangabe |
| Kalender: Titel, Teilnehmer, Erinnerung | 🔨 10 | geheime iCal-Adresse, kein OAuth |
| Aufgaben: Todoist, Google Tasks, Webhook | 🔨 10 | Webhook deckt Asana, Linear, ClickUp über Zapier, Make, n8n ab |
| Auto-Flow: nach dem Meeting automatisch an Obsidian-Ordner, Notion, Webhook, E-Mail | 🔨 10 | |
| Follow-up-Mail entwerfen („Agent“) | 🔨 10 | |
| Zugriff für Claude oder Cursor per MCP | 🔨 10 | |
| Export: Markdown ✅; TXT, PDF, DOCX, SRT, JSON, Audio, ZIP | 🔨 9 | |
| Teilen-Link mit Ablauf, Audio-Aufbewahrung, Daten löschen | 🔨 10 | |
| Enterprise: SOC 2, HIPAA, SSO, Rollen | ➖ | Einzelnutzer |

## Phasen

| Phase | Inhalt | Stand |
|---|---|---|
| 0–5 | Grundgerüst, Diktat, KI-Text, Backend, Handy-App, Meetings am PC | ✅ |
| 6 | Dauerbetrieb und Fenster am PC: Autostart, Einzelinstanz, Logdatei, Qt-Oberfläche, Verlauf, Einstellungen | ✅ (Installer zurückgestellt) |
| 7 | Android-App mit Hintergrundaufnahme (Flutter-Hülle mit der Web-App darin) | 🔨 |
| 8 | Wispr-Funktionen am PC | 🔨 |
| 9 | Aufnahmen auf Pocket/Plaud-Niveau | 🔨 |
| 10 | Wissen und Automatisierung | 🔨 |
| 11 | Android-Extras: Blase, Kachel, Widget, Telefonat-Modus | 🔨 |

## Quellen

[Wispr Flow](https://wisprflow.ai/features) · [Command Mode](https://docs.wisprflow.ai/articles/4816967992-how-to-use-command-mode) ·
[Wispr auf Android](https://techcrunch.com/2026/02/23/wispr-flow-launches-an-android-app-for-ai-powered-dictation) ·
[Pocket](https://heypocket.com/pages/pocket) · [Plaud](https://www.plaud.ai/) ·
[Plaud Intelligence](https://au.plaud.ai/pages/plaud-intelligence) ·
[OpenAI Speech to text](https://developers.openai.com/api/docs/guides/speech-to-text.md) ·
[Google Play: Anrufaufnahme](https://www.engadget.com/google-is-banning-third-party-call-recording-apps-from-the-play-store-093201443.html)
