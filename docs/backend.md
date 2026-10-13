# Das Backend erklärt (Supabase)

Das Backend ist das „Gehirn in der Cloud“: Es nimmt Audio entgegen, macht daraus Text und
Zusammenfassungen und speichert alles. So funktioniert Dictum auch auf dem Handy, ohne dass
dein PC läuft.

**Projekt:** `dictum` · Region Frankfurt (`eu-central-1`) · kostenloser Tarif
**Code:** [`supabase/`](../supabase/)

## 1. Die Bausteine von Supabase

| Baustein | Was es ist | Wofür Dictum es nutzt |
|---|---|---|
| **Postgres** | Eine echte SQL-Datenbank | Aufnahmen, Transkripte, Zusammenfassungen, Wörterbuch, Snippets |
| **Auth** | Login-System | E-Mail und Passwort. Die Registrierung ist gesperrt, es gibt nur dein Konto. |
| **Storage** | Datei-Speicher | Audio-Stücke im privaten Bucket `recordings` |
| **Edge Functions** | Kleine TypeScript-Programme auf Supabase-Servern | Alles, was einen geheimen API-Key braucht: OpenAI und Claude |

## 2. Der Weg einer Gesprächsaufnahme

```
 App (Handy/PC)                       Supabase                               KI-Dienste
 ──────────────                       ────────                               ──────────
 1. Aufnahme anlegen ───────────────► recordings (status: uploading)
 2. je ~5-Min-Stück:
    Audio hochladen ────────────────► Storage: {user}/{aufnahme}/{nr}.webm
    Stück eintragen ────────────────► recording_chunks (pending)
    transcribe aufrufen ────────────► Edge Function transcribe ────────────► OpenAI
                                        Teil-Transkript speichern ◄──────────  (Audio→Text)
 3. Fertig melden ──────────────────► recordings: chunk_count, transcribing
    summarize aufrufen ─────────────► try_start_summary()  ── alle Stücke fertig?
                                        │ ja (genau EIN Aufrufer gewinnt)
                                        ▼
                                      im Hintergrund: runSummary() ────────► Claude Opus 5.5
                                        JSON speichern, status: done ◄───────  (Text→JSON)
 4. Status abfragen ────────────────► recordings (done + summary)
```

**Gemessen** (Testskript, synthetisches Meeting in 2 Teilen): **21 s** vom Anlegen bis zur
fertigen Zusammenfassung.

### Warum Stücke?

| Grenze | Wert | Folge |
|---|---|---|
| OpenAI-Transkription | max. 25 MB pro Datei | Eine Stunde Audio wäre zu groß |
| Edge Function (Free-Tier) | max. 150 s Laufzeit | Eine Stunde am Stück wäre zu langsam |

Mit **~5-Minuten-Stücken** bleibt jedes Teil klein und schnell. Die Stücke werden schon
**während der Aufnahme** einzeln transkribiert, und wenn eins fehlschlägt, wiederholt man nur dieses.

### Das „Wer startet die Zusammenfassung?“-Problem

Stück 3 und Stück 4 werden gleichzeitig fertig. Beide prüfen: „Sind alle Stücke fertig?“ Beide
sehen „ja“, und beide würden die (kostenpflichtige) Zusammenfassung starten.

Die Lösung steckt in der Datenbank-Funktion `try_start_summary()`:

```sql
update recordings set status = 'summarizing' ...
 where id = ... and status = 'transcribing';
```

Postgres sperrt die Zeile beim Update. Der Erste ändert den Status und bekommt `true`. Der
Zweite findet danach keine Zeile mit `status = 'transcribing'` mehr und bekommt `false`. So
läuft die Zusammenfassung garantiert **genau einmal**. Diese Eigenschaft nennt man *atomar*.

## 3. Datenmodell

```
auth.users (von Supabase)
   │ 1
   │
   ├──< recordings          eine Aufnahme: Art, Vorlage, Status, Transkript, summary (JSON)
   │        │ 1
   │        └──< recording_chunks   die Audio-Stücke mit Teil-Transkript
   │
   ├──< dictionary_terms    Wörterbuch (Namen, Fachbegriffe)
   └──< snippets            Textbausteine
```

- **`recordings.status`** durchläuft `uploading → transcribing → summarizing → done`
  (oder `error`, dann steht der Grund in `error`).
- **`recordings.summary`** ist JSON, weil sich der Inhalt je nach Art unterscheidet. Bei
  Diktaten steht dort nur `{ "text": … }`.
- **`recordings.search`** wird von Postgres automatisch berechnet, die deutsche Volltextsuche
  findet dann z. B. „Besprechung“ auch bei „Besprechungen“.

Alles steht als SQL in [`supabase/migrations/`](../supabase/migrations/). Eine **Migration**
ist ein Bauplan-Schritt für die Datenbank, der wie Code versioniert wird.

## 4. Sicherheit

### Row Level Security (RLS)

Der öffentliche Projekt-Schlüssel steckt später in der Handy-App, jeder könnte ihn auslesen.
Trotzdem ist das sicher, weil **die Datenbank selbst** bei jeder Abfrage prüft:

```sql
create policy "Eigene Aufnahmen" on recordings
  using ((select auth.uid()) = user_id);   -- nur Zeilen, die mir gehören
```

`auth.uid()` ist die ID aus dem Login-Token. Ohne Login sieht man nichts, mit Login nur die
eigenen Daten. Das gilt für alle vier Tabellen und für den Storage-Bucket: Dort muss der erste
Ordner im Dateipfad die eigene Nutzer-ID sein.

### Edge Functions arbeiten im Namen des Nutzers

Die Funktionen benutzen **nicht** den mächtigen „service role“-Schlüssel, der RLS umgehen würde.
Sie reichen das Login-Token des Aufrufers an die Datenbank weiter
([`_shared/supabase.ts`](../supabase/functions/_shared/supabase.ts)). Auch ein Fehler im Code
kann deshalb keine fremden Daten berühren.

### Geheimnisse

| Was | Wo | Öffentlich? |
|---|---|---|
| Projekt-URL, publishable key | `desktop/settings.toml`, später in der PWA | ja, schützt nichts ohne Login |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Supabase → Edge Functions → Secrets | **nein**, nur der Server kennt sie |
| Dein Passwort | nur bei dir (`.env`, nie im Repo) | **nein** |

### Registrierung gesperrt

Das Repo ist öffentlich. Wäre die Registrierung offen, könnte sich jeder ein Konto anlegen und
auf deine Kosten KI-Aufrufe auslösen. Deshalb ist sie abgeschaltet. Das einzige Konto wurde im
Dashboard angelegt.

## 5. Die Edge Functions

| Funktion | Aufruf | Macht |
|---|---|---|
| [`transcribe`](../supabase/functions/transcribe/index.ts) | `{recording_id, idx}` | Ein Stück transkribieren. Ist es das letzte, startet sie die Zusammenfassung. |
| [`summarize`](../supabase/functions/summarize/index.ts) | `{recording_id, template?, force?}` | Zusammenfassung starten, auch neu mit anderer Vorlage |
| [`dictate`](../supabase/functions/dictate/index.ts) | Formular mit `audio` | Handy-Diktat → Snippet oder bereinigter Text. Das Audio wird nicht gespeichert. |

Gemeinsamer Code in [`_shared/`](../supabase/functions/_shared/):

| Datei | Inhalt |
|---|---|
| `llm.ts` | Claude und OpenAI hinter einer Schnittstelle, wie `desktop/dictum/llm/` |
| `stt.ts` | Speech-to-Text über OpenAI (`gpt-4o-mini-transcribe`) |
| `cleanup.ts` | Diktat-Bereinigung, derselbe Prompt wie am PC |
| `summary.ts` | Vorlagen, JSON-Schema und `runSummary()` |
| `http.ts`, `supabase.ts` | CORS, Fehlerbehandlung, Hintergrundaufgaben, Login-Prüfung |

### Strukturierte Zusammenfassung

Claude antwortet nicht mit Fließtext, sondern mit **JSON nach festem Schema** (*structured
output*). Die API garantiert, dass die Antwort dem Schema entspricht:

```json
{
  "title": "Start der Diktum-App: Backend und Kosten",
  "summary": "Im Meeting ging es um …",
  "key_points": ["…"],
  "action_items": [{ "task": "Monatliche Kosten prüfen", "owner": "Tom", "due": "Mittwoch" }],
  "decisions": ["Supabase wird als Backend verwendet."],
  "open_questions": ["Wer ist für das Backend verantwortlich?"],
  "glossary": [],
  "topics": [{ "title": "Kosten", "points": ["…"] }]
}
```

So kann die App To-dos als Checkliste anzeigen und `topics` später als Mindmap zeichnen.

### Vorlagen

| Vorlage | Schwerpunkt |
|---|---|
| **Meeting** | Entscheidungen, To-dos mit Verantwortlichen und Fristen |
| **Interview** | Kernaussagen und Positionen, Nachfragen |
| **Vorlesung** | Gliederung, Fachbegriffe mit Definitionen, Lernfragen |
| **Notiz** | Gedanken ordnen, Ideen, eigene Vorhaben |

Alle nutzen dasselbe Schema. Die Vorlage sagt der KI nur, worauf sie achten soll.

### Modelle und Kosten

| Aufgabe | Modell | Warum |
|---|---|---|
| Diktat bereinigen | Claude Haiku 5.5 | Schnell, kostet Bruchteile eines Cents |
| Zusammenfassen | Claude Opus 5.5 | Erkennt Entscheidungen und Zuständigkeiten am zuverlässigsten |
| Sprache → Text | OpenAI gpt-4o-mini-transcribe | ~0,3 Cent pro Minute |

Ändern ohne Code: als Secret `SUMMARY_MODEL`, `CLEANUP_MODEL`, `STT_MODEL` oder
`LLM_PROVIDER=openai` setzen.

Bei Opus 5.5 ist der **Refusal-Fallback** eingeschaltet: Lehnt das Modell eine Anfrage aus
Sicherheitsgründen ab, rechnet die API automatisch mit einem anderen Modell weiter, statt nur
eine Ablehnung zurückzugeben.

## 6. Testen

```powershell
# Logik der Edge Functions (ohne Netzwerk)
deno test supabase/functions

# Ganzer Durchlauf gegen die echte Cloud (braucht DICTUM_EMAIL/PASSWORD in .env)
cd desktop
.venv\Scripts\python -X utf8 scripts\cloud_e2e.py --cleanup
```

**Gemessene Zeiten:**

| Vorgang | Dauer |
|---|---|
| Diktat (warm) | ~3 s, ohne KI-Bereinigung 1,6 s |
| Diktat (Kaltstart) | ~13 s, beim ersten Aufruf nach längerer Pause lädt die Funktion erst ihre Pakete |
| Meeting, 2 Stücke | 21 s inklusive Zusammenfassung |

## 7. Bekannte Grenzen

- **Kaltstart:** Nach einer Pause dauert der erste Aufruf deutlich länger.
- **150 s pro Funktion (Free-Tier):** Sehr lange Aufnahmen (mehrere Stunden) könnten bei der
  Zusammenfassung an die Grenze stoßen. Dann bleibt der Status `error` und man kann mit
  `force` neu starten.
- **Free-Tier pausiert** nach 7 Tagen ohne Nutzung. Im Dashboard lässt es sich mit einem Klick
  fortsetzen.
- **Prompt doppelt gepflegt:** Die Diktat-Bereinigung existiert in Python (PC, offline-fähig)
  und in TypeScript (Server). Änderungen müssen an beiden Stellen passieren.
- **Deployment:** Die Funktionen wurden über die Supabase-Anbindung von Claude Code deployt.
  Selbst geht es mit `npx supabase functions deploy` (braucht `npx supabase login`).
