# desktop/

Python-App für Windows: **Strg+Win halten, sprechen, loslassen** – der Text erscheint
im gerade aktiven Textfeld. Wie das intern funktioniert: [docs/desktop.md](../docs/desktop.md).

## Einrichten (einmalig)

```powershell
cd desktop
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Starten

Doppelklick auf `start.bat` – oder:

```powershell
.venv\Scripts\python -X utf8 -m dictum
```

Beim allerersten Start wird das Whisper-Modell heruntergeladen (~460 MB).

## Bedienen

| Aktion | Wirkung |
|---|---|
| **Strg+Win halten** und sprechen, dann loslassen | Text wird eingefügt (Push-to-talk) |
| **Strg+Win kurz antippen** | Aufnahme läuft weiter – nochmal antippen zum Beenden |
| Tray-Symbol → Rechtsklick | Modus, Sprache, Beenden |

Einstellungen: [settings.toml](settings.toml)

## Tests

```powershell
.venv\Scripts\python -m pytest
```
