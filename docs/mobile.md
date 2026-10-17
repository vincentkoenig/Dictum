# Die Android-App erklärt

**Code:** [`mobile/`](../mobile/) · **Stand:** Prototyp gebaut und getestet, **Test auf dem Handy steht noch aus**

## 1. Die Idee in einem Bild

```
┌──────────────────────── Android-App "Dictum" (Flutter) ────────────────────────┐
│                                                                                 │
│  ┌───────── WebView ─────────┐   Brücke (JSON)   ┌──────── nativer Teil ──────┐ │
│  │ die Web-App (pwa/):       │ ◄───────────────► │ Mikrofon-Dienst im Vorder- │ │
│  │ Liste, Details, Suche,    │  "Aufnahme       │ grund, Aufnahme in 5-Min-  │ │
│  │ Einstellungen, Login      │   starten" …     │ Stücken, Upload-Warte-     │ │
│  └───────────────────────────┘                   │ schlange, eigene Sitzung   │ │
│                                                  └────────────┬───────────────┘ │
└───────────────────────────────────────────────────────────────┼─────────────────┘
                                                                ▼
                                     Supabase (Storage → transcribe → summarize)
```

Die Web-App ist die **Oberfläche**. Der native Teil macht nur das, was ein Browser nicht kann:
**im Hintergrund aufnehmen**, auch bei gesperrtem Bildschirm.

### Warum nicht einfach die PWA?

Android erlaubt den Mikrofonzugriff im Hintergrund nur einem **Dienst im Vordergrund vom Typ
„microphone“**, der gestartet wurde, während die App sichtbar war. Ein solcher Dienst zeigt eine
dauerhafte Benachrichtigung und gibt dem Prozess höhere Priorität. Eine Web-App kann so einen Dienst
nicht anlegen. Dasselbe Muster nutzt Khutba-Translation (`flutter_foreground_task`).

### Warum eine WebView und keine komplett neue Oberfläche?

| | Oberfläche komplett in Flutter | **Flutter-Hülle mit der Web-App** (gewählt) |
|---|---|---|
| Neue Funktion (z. B. Mindmap) | zweimal bauen: React **und** Dart | **einmal** (React), steht überall |
| Aussehen | rein nativ | wie die PWA im Vollbild |
| Aufwand für alle geplanten Funktionen | doppelt | einfach |

Das Risiko der Lösung liegt an der Naht zwischen WebView und nativem Teil: Anmeldung und Zustand müssen
sauber geteilt werden. Genau deshalb gibt es zuerst diesen Prototyp.

## 2. Die Dateien

```
mobile/lib/
├── main.dart                     Einstieg
├── shell.dart                    WebView, Zurück-Taste, Berechtigungen, Navigation gesperrt
├── app_services.dart             "Zusammenstecken" aller Bausteine
├── config.dart                   Web-Adresse, Supabase-URL (öffentlich), Stücklänge
├── bridge/native_bridge.dart     Protokoll Web ↔ nativ, Prüfung eingehender Nachrichten
└── services/
    ├── cloud_client.dart         Supabase per HTTP (Port von desktop/dictum/cloud.py)
    ├── upload_queue.dart         Warteschlange in Dateien (Port von upload_queue.py)
    ├── uploader.dart             lädt hoch, wiederholt bei Fehlern
    ├── chunked_recorder.dart     Aufnahme in Opus-Stücken
    ├── rollover.dart             Schnitt in der Sprechpause
    ├── recording_controller.dart steuert alles, Wiederherstellung nach Absturz
    ├── background_service.dart   Mikrofon-Dienst mit Stopp-Knopf
    └── secure_session_store.dart Refresh-Token im Android Keystore
```

Dieselbe Aufteilung wie am PC: Gleiche Idee, gleiche Namen. Wer `desktop/` versteht, versteht `mobile/`.

## 3. Der Weg einer Aufnahme

```
Web-App  "Aufnahme starten"
  → Brücke: record_start
  → Controller: Mikrofon-Erlaubnis, Dienst starten, Aufnahme beginnen,
                "Aufnahme anlegen" in die Warteschlange
  ─ alle ~5 Minuten ─────────────────────────────────────────────────────────┐
  │ ChunkedRecorder: Stück fertig (in einer Sprechpause geschnitten)          │
  │ → Warteschlange → Uploader → Storage + "transcribe"                       │
  └────────────────────────────────────────────────────────────────────────────┘
Web-App  "Stopp"  (oder Stopp-Knopf in der Benachrichtigung)
  → letztes Stück, "abschließen" in die Warteschlange, Dienst beenden
  → Uploader: abschließen → Zusammenfassung → Web-App zeigt sie (Detailseite)
```

- **Erst speichern, dann hochladen:** Wie am PC und in der PWA steht jeder Schritt zuerst als Datei in
  der Warteschlange. Ohne Netz warten die Dateien und werden alle 30 s erneut versucht.
- **Stücke in Pausen schneiden:** Ab 3 s vor dem Ende wartet der Rekorder auf eine leise Stelle
  (`getAmplitude`) und schneidet dort. Sonst zerreißen Sätze, und Whisper erfindet an der Schnittstelle Wörter.
- **Opus** (32 kbit/s, Mono) statt WAV: ~1,2 MB je 5 Minuten. Das braucht Android 10 (API 29).

## 4. Die Brücke

Zwei Wege, beide mit JSON:

| Richtung | Weg | Beispiel |
|---|---|---|
| Web → nativ | `DictumNative.postMessage(…)` (von webview_flutter bereitgestellt) | `{"type":"record_start","template":"meeting"}` |
| nativ → Web | `window`-Ereignis `dictum-native` | `{"type":"recording","state":"recording","seconds":42,…}` |

Nachrichten Web → nativ: `credentials`, `logout`, `record_start`, `record_pause`, `record_resume`,
`record_stop`, `status`. Eingehendes gilt als **nicht vertrauenswürdig** und wird geprüft: Unbekannte
Typen, falsche Datentypen oder unzulässige Werte werden ignoriert (`parseBridgeMessage`).

**Sicherheit der Brücke:**
- Die WebView lädt **nur** die eigene Web-Adresse. Jede Navigation zu einem anderen Host wird blockiert,
  sonst könnte eine fremde Seite die Aufnahme starten.
- Ereignisse an die Seite gehen über `jsonEncode`. Text in den Daten kann so nie als Code ausbrechen
  (ein Test prüft das mit einem Angriffsstring).
- Das Passwort taucht in keiner Antwort an die Seite auf (ebenfalls getestet).

## 5. Anmeldung: Warum zwei Sitzungen?

Supabase erneuert Tokens mit einem **Refresh-Token, das sich bei jeder Erneuerung ändert** („Rotation“).
Würden Web-App und nativer Teil dasselbe Token benutzen, entzöge die Erneuerung des einen dem anderen das
Token. Wird ein altes Token nach dem Ablauf einer kurzen Frist wiederverwendet, kann Supabase sogar die ganze
Sitzung sperren.

Die Lösung: **Beide melden sich getrennt an.** Beim Login in der Web-App schickt diese die eingegebenen
Daten über die Brücke an den nativen Teil, der sich damit selbst anmeldet. Gespeichert wird dort nur das
**eigene Refresh-Token** im Android Keystore, **nie das Passwort**. Ein Nutzer darf in Supabase mehrere
Sitzungen haben, sie stören sich nicht.

Fehlt dem nativen Teil die Anmeldung (z. B. nach Neuinstallation), zeigt die Web-App „Einmal neu anmelden“.

## 6. Absturzsicherheit

| Situation | Was passiert |
|---|---|
| Kein Netz | alles bleibt in der Warteschlange, Wiederholung alle 30 s |
| App beendet oder Handy neu gestartet | die Warteschlange liegt als Dateien vor und macht beim Start weiter |
| App wird **mitten in der Aufnahme** beendet | Eine Markierung `active.json` bleibt liegen. Beim nächsten Start werden die gesicherten Stücke abgeschlossen und bekommen ihre Zusammenfassung. Das angebrochene Stück geht verloren. |
| Aufnahme kürzer als 1 s | wird verworfen, auch auf dem Server |
| Token abgelaufen | wird vor dem Ablauf erneuert; bei 401 einmal erneuert und wiederholt |

**Zurück-Taste:** Läuft eine Aufnahme, schiebt sie die App nur in den Hintergrund. Beenden würde die Aufnahme
beenden. **Aus dem App-Wechsler wegwischen** beendet Aufnahme und Dienst (`stopWithTask`).

## 7. Was geprüft ist, und was nicht

| Geprüft | Wie |
|---|---|
| Cloud-Client (Anmeldung, Token-Erneuerung, 401, Upload-Pfade) | 12 Tests mit `MockClient` |
| Warteschlange (Reihenfolge, Neustart, Abbruch, kein Doppeln) | 6 Tests |
| Stückwechsel (Zeit, Sprechpause, Pause, zu kurz) | 6 Tests mit einem Attrappen-Mikrofon, dazu 5 für die Schnittregel |
| Aufnahme-Ablauf, Wiederherstellung, Offline | 10 Tests, dazu 3 für den Uploader |
| Brücke (Prüfung, Passwort-Leck, Code-Einschleusung) | 11 Tests |
| Web-Seite der Brücke | 6 Tests (`pwa/src/lib/native.test.ts`) |
| Android-Build | Debug-APK gebaut; Manifest im fertigen Paket geprüft: Dienst vom Typ „microphone“, `stopWithTask`, Berechtigungen |

**Noch nicht geprüft** (braucht das Handy): Aufnahme bei ausgeschaltetem Bildschirm, Opus-Qualität, die
Benachrichtigung samt Stopp-Knopf, der Login-Weg in der WebView und das Verhalten der Zurück-Taste.

## 8. Entwickeln

```powershell
cd mobile
flutter test                 # 53 Tests, ohne Handy
flutter analyze
flutter build apk --debug    # → build/app/outputs/flutter-apk/app-debug.apk
flutter run                  # auf das per USB verbundene Handy (USB-Debugging nötig)
```

Mit dem Entwicklungsserver der Web-App (Änderungen sofort sichtbar, ohne zu veröffentlichen):

```powershell
cd pwa; npm run dev -- --port 5180
adb reverse tcp:5180 tcp:5180        # "localhost" am Handy ist dann der PC
cd ..\mobile; flutter run --dart-define=WEB_URL=http://localhost:5180/Dictum/
```

Klartext-HTTP ist nur im **Debug-Build** erlaubt (`src/debug/AndroidManifest.xml`), im Release-Build nicht.

## 9. Bekannte Grenzen

- **Wegwischen beendet die Aufnahme** (siehe oben). Ein Dienst, der das überlebt, bräuchte die Aufnahme
  selbst im Dienst statt in der App. Das wäre ein größerer Umbau.
- **Upload nach dem Beenden der App:** Offene Schritte warten, bis die App wieder geöffnet wird. Ein
  Hintergrund-Upload über WorkManager wäre eine spätere Verbesserung.
- **Kein Pegel in der Oberfläche:** Der native Teil meldet bisher keine Lautstärke.
- **Zwei Anmeldungen:** Wer sich in der Web-App abmeldet, meldet auch den nativen Teil ab.
- **Telefonate:** Android blockiert die Aufnahme der Gegenstelle (siehe [FEATURES.md](FEATURES.md)).
