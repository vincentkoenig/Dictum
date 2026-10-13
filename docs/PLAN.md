# Projektplan

Jede Phase wird vor dem Bauen vorgestellt und erst nach „Go“ umgesetzt.
Jede Phase besteht aus mehreren kleinen Commits und bekommt eine Erklärung in `docs/`.

| Phase | Inhalt | Status |
|---|---|---|
| 0 | **Grundgerüst** – Repo, Struktur, README, Lizenz, Architektur-Doku | ✅ |
| 1 | **Diktieren am PC (MVP)** – Hotkey (halten/antippen) → Mikrofon → faster-whisper → Text ins aktive Feld; Tray-Icon, Overlay, Einstellungen | ✅ |
| 2 | **Smarter Text** – KI-Bereinigung (Claude, austauschbar mit OpenAI), persönliches Wörterbuch, Snippets | ✅ |
| 3 | **Supabase-Backend** – Schema, Login, Audio-Speicher, Edge Functions `transcribe`, `summarize` & `dictate`, Zusammenfassungs-Vorlagen | ✅ |
| 4 | **Handy-PWA** – Login, Diktat + Kopieren, Gespräche aufnehmen, Offline-Warteschlange, Liste/Suche, Detailansicht, Markdown-Export | ⏳ |
| 5 | **Meetings am PC** – Mikrofon + PC-Ton aufnehmen, Upload nach Supabase, Verlauf synchronisieren | ⏳ |
| 6 | **Extras** (einzeln wählbar) – Sprechererkennung, „Frag deine Aufnahmen“, Mindmap, Stil pro App | 💡 |

## Was wir uns von den Vorbildern abschauen

**Wispr Flow:** Diktat in jede App per Hotkey · Füllwörter & Selbstkorrekturen entfernen ·
automatische Formatierung (Listen, Absätze) · persönliches Wörterbuch · Snippets ·
Stil pro App · 100+ Sprachen mit Auto-Erkennung.

**Pocket / Plaud:** Ein-Knopf-Aufnahme, auch offline mit späterem Sync · Transkript +
Zusammenfassung + To-dos · Vorlagen für verschiedene Gesprächsarten · Sprechererkennung ·
Mindmaps · „Frag deine Aufnahmen“ · Export (Markdown/PDF) · Suche über alle Aufnahmen.
