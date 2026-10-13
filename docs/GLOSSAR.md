# Glossar

Begriffe, die in Dictum vorkommen – kurz und verständlich erklärt.

| Begriff | Erklärung |
|---|---|
| **Whisper** | Spracherkennungs-Modell von OpenAI. Wandelt Audio in Text um und erkennt die Sprache selbst. |
| **faster-whisper** | Nachbau von Whisper, der deutlich schneller und sparsamer läuft – ideal auf einem PC ohne Grafikkarte. |
| **sounddevice** | Python-Bibliothek, mit der wir das Mikrofon auslesen. |
| **Hotkey** | Tastenkombination, die überall funktioniert, auch wenn Dictum nicht im Vordergrund ist. |
| **Push-to-talk** | Taste halten = sprechen, loslassen = fertig. |
| **Tray-Icon** | Kleines Symbol unten rechts in der Windows-Taskleiste, über das die App läuft. |
| **LLM** | „Large Language Model“ – KI wie Claude oder GPT, die Text versteht und schreibt. Bei uns: Text bereinigen und zusammenfassen. |
| **API / API-Key** | Schnittstelle zu einem Online-Dienst. Der Key ist das Passwort dafür – er darf nie öffentlich werden. |
| **PWA** | „Progressive Web App“ – eine Webseite, die man wie eine App auf den Homescreen legt und die offline funktioniert. |
| **Supabase** | Backend-Dienst: Datenbank (Postgres), Login, Datei-Speicher und Server-Funktionen in einem. |
| **Edge Function** | Kleines Programm, das auf Supabase-Servern läuft. Dort liegen die API-Keys sicher, und von dort rufen wir Whisper und Claude auf. |
| **RLS (Row Level Security)** | Regel in der Datenbank: Jeder Nutzer sieht nur seine eigenen Zeilen. |
| **WASAPI-Loopback** | Windows-Funktion, um aufzunehmen, was gerade aus den Lautsprechern kommt (z. B. Teams-Ton). |
| **`.env`-Datei** | Lokale Datei mit geheimen Einstellungen (Keys). Wird nicht committet. |
| **Commit** | Ein gespeicherter Zwischenstand im Git-Verlauf mit Beschreibung, was geändert wurde. |
