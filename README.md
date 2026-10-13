# Dictum

**Sprechen statt tippen – am PC und auf dem Handy.**

Dictum ist ein selbst gebautes Sprach-Werkzeug, inspiriert von
[Wispr Flow](https://wisprflow.ai), [Pocket](https://heypocket.com) und [Plaud](https://plaud.ai):

| Funktion | Inspiriert von | Wo |
|---|---|---|
| 🎙 **Diktieren in jedes Textfeld** – Hotkey halten, sprechen, loslassen, Text erscheint | Wispr Flow | PC |
| ✨ **Smarter Text** – Füllwörter raus, Selbstkorrekturen, Satzzeichen, Listen | Wispr Flow | PC + Handy |
| 📖 **Wörterbuch & Snippets** – eigene Namen/Fachbegriffe, Textbausteine per Sprache | Wispr Flow | PC + Handy |
| 🗣 **Gespräche aufnehmen** – Meetings, Interviews, Vorlesungen | Pocket / Plaud | PC + Handy |
| 📝 **Zusammenfassungen** – Kernpunkte, To-dos, Entscheidungen, per Vorlage | Pocket / Plaud | überall |
| 📱 **Handy-App (PWA)** – auch offline aufnehmen, später synchronisieren | Pocket / Plaud | Handy |

> **Status:** 🚧 Im Aufbau – siehe [Projektplan](docs/PLAN.md).

## Wie es funktioniert (Kurzfassung)

```
 PC-App (Python)  ──┐                     ┌── Handy-App (PWA)
  Hotkey → Mikro    │                     │   Aufnehmen, Liste,
  → Whisper → Text  │                     │   Zusammenfassungen
  ins aktive Feld   ▼                     ▼
              ┌────────── Supabase ──────────┐
              │ Login · Datenbank · Audio    │
              │ Edge Functions → OpenAI      │
              │   Whisper + Claude           │
              └──────────────────────────────┘
```

Ausführlich erklärt in [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).
Fachbegriffe stehen im [Glossar](docs/GLOSSAR.md).

## Projektstruktur

```
Dictum/
├── desktop/    Python-App für Windows: Hotkey-Diktat & Meeting-Aufnahme
├── pwa/        Web-App fürs Handy (Vite + React + TypeScript)
├── supabase/   Datenbank-Schema & Edge Functions (Backend in der Cloud)
└── docs/       Architektur, Plan, Glossar und Erklärungen pro Baustein
```

## Datenschutz & Recht

- API-Keys liegen **nur** lokal in `.env` bzw. als Supabase-Secrets – nie im Repo, nie im Browser.
- Gespräche dürfen in Deutschland nur mit Zustimmung **aller** Beteiligten aufgenommen
  werden (§ 201 StGB). Dictum erinnert beim Start einer Aufnahme daran.

## Lizenz

[MIT](LICENSE)
