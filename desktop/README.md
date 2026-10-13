# desktop/

Python-App für Windows: **rechte Strg-Taste halten, sprechen, loslassen** – der Text erscheint
im gerade aktiven Textfeld. Wie das intern funktioniert: [docs/desktop.md](../docs/desktop.md).

## Einrichten (einmalig)

```powershell
cd desktop
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

### API-Keys für die KI-Bereinigung

Im Projektordner (eine Ebene über `desktop/`) die Datei `.env.example` nach `.env` kopieren
und den Anthropic-Key eintragen (optional auch den OpenAI-Key). Die `.env` wird nie committet.
Ohne Key funktioniert Dictum trotzdem, dann aber ohne KI-Bereinigung.

## Starten

Doppelklick auf `start.bat` – oder:

```powershell
.venv\Scripts\python -X utf8 -m dictum
```

Beim allerersten Start wird das Whisper-Modell heruntergeladen (~460 MB).

## Bedienen

| Aktion | Wirkung |
|---|---|
| **Strg rechts halten** und sprechen, dann loslassen | Text wird eingefügt (Push-to-talk) |
| **Strg rechts kurz antippen** | Aufnahme läuft weiter – nochmal antippen zum Beenden |
| Tray-Symbol → Rechtsklick | KI-Bereinigung an/aus, KI-Anbieter, Spracherkennung, Sprache, Modus, Wörterbuch, Snippets |

Einstellungen: [settings.toml](settings.toml) · Wörterbuch: `dictionary.txt` · Textbausteine: `snippets.toml`

## Tests

```powershell
.venv\Scripts\python -m pytest
```
