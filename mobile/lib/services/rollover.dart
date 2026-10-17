// Wann beginnt ein neues Aufnahme-Stück?
//
// Eine Aufnahme wird alle ~5 Minuten in ein neues Stück geteilt (siehe config.dart). Schneidet
// man stur nach der Uhr, zerreißt es Sätze: Whisper erkennt die Bruchstücke schlecht und erfindet
// an der Schnittstelle gern Wörter (am PC kam so ein erfundenes "Hm" vor, siehe docs/desktop.md).
//
// Deshalb gilt dieselbe Idee wie am PC: Ab 3 Sekunden vor dem Ende wird auf eine leise Stelle
// gewartet und genau dort geschnitten. Kommt keine, wird spätestens zur vollen Zeit geschnitten.
//
// Reine Funktion ohne Android-Bezug – deshalb testbar (test/rollover_test.dart).

/// [elapsed]: Sekunden im aktuellen Stück (ohne Pausen). [amplitudeDb]: aktuelle Lautstärke
/// in Dezibel (0 = laut, -160 = Stille; Sprache liegt meist über -30).
bool shouldRollOver({
  required double elapsed,
  required double chunkSeconds,
  required double amplitudeDb,
  double searchSeconds = 3.0,
  double quietDb = -40.0,
}) {
  if (elapsed >= chunkSeconds) return true;
  return elapsed >= chunkSeconds - searchSeconds && amplitudeDb < quietDb;
}
