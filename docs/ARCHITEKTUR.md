# Architektur von Dictum

Dieses Dokument erklärt, **aus welchen Teilen Dictum besteht, wie sie zusammenspielen und
warum** sie so gebaut sind. Es wächst mit jeder Phase mit.

## 1. Das große Bild

```
┌──────────────── PC (Windows) ────────────────┐      ┌────────── Handy (PWA) ──────────┐
│ Desktop-App (Python, im Tray)                │      │ Web-App auf dem Homescreen       │
│  • Hotkey (halten oder antippen)             │      │  • Aufnehmen (auch offline)      │
│  • Mikrofon → faster-whisper (lokal)         │      │  • Diktat → Text kopieren/teilen │
│  • Claude bereinigt den Text                 │      │  • Gespräche + Zusammenfassungen │
│  • Text wird ins aktive Feld eingefügt       │      └───────────────┬──────────────────┘
│  • Meetings aufnehmen (Mikro + PC-Ton)       │                      │
└───────────────────────┬──────────────────────┘                      │
                        └───────────────┐      ┌──────────────────────┘
                                        ▼      ▼
                    ┌──────────────── Supabase (Cloud) ────────────────┐
                    │ Auth (Login) · Postgres (Transkripte, Wörterbuch, │
                    │ Snippets) · Storage (Audio) · Edge Functions:     │
                    │   transcribe → OpenAI Whisper                     │
                    │   summarize  → Claude (OpenAI austauschbar)       │
                    └───────────────────────────────────────────────────┘
```

Es gibt **drei Bausteine**:

| Baustein | Ordner | Sprache | Aufgabe |
|---|---|---|---|
| Desktop-App | `desktop/` | Python | Diktieren per Hotkey in jedes Programm, Meetings am PC aufnehmen |
| Handy-App | `pwa/` | TypeScript (React) | Aufnehmen unterwegs, Transkripte & Zusammenfassungen ansehen |
| Backend | `supabase/` | SQL + TypeScript | Login, Speicher, Datenbank, KI-Verarbeitung in der Cloud |

## 2. Die zwei Hauptabläufe

### A) Diktieren am PC (wie Wispr Flow)

```
Hotkey gedrückt ─► Mikrofon nimmt auf (sounddevice)
Hotkey losgelassen ─► Audio an faster-whisper (lokal) ─► Rohtext
   ─► Claude bereinigt (Füllwörter, Korrekturen, Satzzeichen) ─► sauberer Text
   ─► Text in Zwischenablage ─► Strg+V wird simuliert ─► Text steht im aktiven Feld
```

Warum **lokal**? Kurze Diktate sind auch ohne Grafikkarte in 1–3 Sekunden fertig,
kostenlos und verlassen den PC nicht. Optional kann auf die OpenAI-Cloud umgeschaltet werden.

Warum **Zwischenablage + Strg+V** statt Buchstabe für Buchstabe tippen? Es ist sofort da,
funktioniert mit Umlauten/Emojis zuverlässig und in praktisch jedem Programm.

### B) Gespräch aufnehmen (wie Pocket/Plaud)

```
Aufnahme starten (Handy oder PC) ─► Audio in ~10-Minuten-Stücken
   ─► Upload in Supabase Storage
   ─► Edge Function "transcribe" ─► OpenAI Whisper ─► Transkript in Datenbank
   ─► Edge Function "summarize"  ─► Claude + Vorlage ─► Kernpunkte, To-dos, Entscheidungen
   ─► sichtbar auf Handy und PC
```

Warum **Stücke**? OpenAI nimmt max. 25 MB pro Datei an und Edge Functions haben ein
Zeitlimit. Viele kleine Stücke umgehen beides – und wenn eins fehlschlägt, wird nur dieses
wiederholt.

## 3. Wichtige Entscheidungen

| Entscheidung | Begründung |
|---|---|
| **API-Keys nur in Supabase-Secrets bzw. lokaler `.env`** | Das Repo ist öffentlich und eine Web-App kann nichts geheim halten, was im Browser liegt. Deshalb ruft nur der Server (Edge Function) die KI auf. |
| **Supabase als Backend** | Login, Datenbank, Datei-Speicher und Server-Funktionen aus einer Hand; läuft unabhängig vom PC; kostenloses Kontingent. |
| **PWA statt nativer App** | Eine Codebasis für iPhone und Android, kein App-Store nötig. Grenze: kann auf dem Handy nicht in fremde Apps tippen → dort „Kopieren/Teilen“. |
| **KI-Anbieter austauschbar** | Eine gemeinsame Schnittstelle, dahinter Claude (Standard) oder OpenAI – per Einstellung wählbar. |
| **Deutsch + Auto-Erkennung** | Deutsch als Standard, andere Sprachen erkennt Whisper selbst. |

## 4. Bausteine im Detail

Pro Baustein entsteht eine eigene Erklärung, sobald er gebaut ist:

- `docs/desktop.md` – Desktop-App (Phase 1, 2, 5)
- `docs/backend.md` – Supabase (Phase 3)
- `docs/pwa.md` – Handy-App (Phase 4)
