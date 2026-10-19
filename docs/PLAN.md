# Projektplan

Jede Phase wird vor dem Bauen vorgestellt und erst nach „Go“ umgesetzt.
Jede Phase besteht aus mehreren kleinen Commits und bekommt eine Erklärung in `docs/`.

| Phase | Inhalt | Status |
|---|---|---|
| 0 | **Grundgerüst** – Repo, Struktur, README, Lizenz, Architektur-Doku | ✅ |
| 1 | **Diktieren am PC (MVP)** – Hotkey (halten/antippen) → Mikrofon → faster-whisper → Text ins aktive Feld; Tray-Icon, Overlay, Einstellungen | ✅ |
| 2 | **Smarter Text** – KI-Bereinigung (Claude, austauschbar mit OpenAI), persönliches Wörterbuch, Snippets | ✅ |
| 3 | **Supabase-Backend** – Schema, Login, Audio-Speicher, Edge Functions `transcribe`, `summarize` & `dictate`, Zusammenfassungs-Vorlagen | ✅ |
| 4 | **Handy-PWA** – Login, Diktat + Kopieren, Gespräche aufnehmen, Offline-Warteschlange, Liste/Suche, Detailansicht, Markdown-Export | ✅ |
| 5 | **Meetings am PC** – Mikrofon + PC-Ton aufnehmen, Upload nach Supabase, Wörterbuch/Snippets abgleichen | ✅ |
| 6 | **Dauerbetrieb und Fenster am PC** – Autostart, Einzelinstanz, Logdatei, Qt-Oberfläche (Overlay, Tray, Fenster), lokaler Verlauf, Einstellungen speichern | ✅ (Installer zurückgestellt) |
| 7 | **Android-App mit Hintergrundaufnahme** – Flutter-Hülle mit der Web-App darin, Mikrofon-Dienst mit Stopp-Knopf, Teilen-Ziel für Audio | 🔧 Prototyp gebaut, Test am Handy offen |
| 8 | **Wispr-Funktionen am PC** – freie Tastenwahl, OpenAI-Anbindung, Programm-Symbol und Dictum.exe, Wörterbuch- und Statistik-Reiter, Stile pro App und Kontext, Command Mode, Flüstermodus, Lern-Wörterbuch | ✅ (Entwickler-Modus offen, Test mit echter Stimme steht aus) |
| 9 | **Aufnahmen auf Pocket/Plaud-Niveau** – Live-Transkript, Markieren mit Foto, Sprecher, Vorlagen, Mindmap, Übersetzen, Tags, Import, Export | ⏳ |
| 10 | **Wissen und Automatisierung** – Fragen an alle Aufnahmen, Kalender, Aufgaben, Auto-Flow, Follow-up, MCP | ⏳ |
| 11 | **Android-Extras** – Blase in Textfeldern, Kachel, Widget, Telefonat-Modus | ⏳ |

Die einzelnen Funktionen und was sich aus welchem Vorbild überschneidet, steht in [FEATURES.md](FEATURES.md).

## Was wir uns von den Vorbildern abschauen

**Wispr Flow:** Diktat in jede App per Hotkey · Füllwörter & Selbstkorrekturen entfernen ·
automatische Formatierung (Listen, Absätze) · persönliches Wörterbuch · Snippets ·
Stil pro App · 100+ Sprachen mit Auto-Erkennung.

**Pocket / Plaud:** Ein-Knopf-Aufnahme, auch offline mit späterem Sync · Transkript +
Zusammenfassung + To-dos · Vorlagen für verschiedene Gesprächsarten · Sprechererkennung ·
Mindmaps · „Frag deine Aufnahmen“ · Export (Markdown/PDF) · Suche über alle Aufnahmen.
