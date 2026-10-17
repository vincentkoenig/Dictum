import 'package:dictum_mobile/services/rollover.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const chunk = 300.0;

  test('mitten im Stück wird nie geschnitten, auch nicht bei Stille', () {
    expect(shouldRollOver(elapsed: 120, chunkSeconds: chunk, amplitudeDb: -90), isFalse);
  });

  test('im Suchfenster (letzte 3 s) wird in einer leisen Stelle geschnitten', () {
    expect(shouldRollOver(elapsed: 298, chunkSeconds: chunk, amplitudeDb: -55), isTrue);
  });

  test('im Suchfenster wird bei Sprache weiter gewartet', () {
    expect(shouldRollOver(elapsed: 298, chunkSeconds: chunk, amplitudeDb: -15), isFalse);
  });

  test('zur vollen Zeit wird spätestens geschnitten, auch mitten im Satz', () {
    expect(shouldRollOver(elapsed: 300, chunkSeconds: chunk, amplitudeDb: -5), isTrue);
    expect(shouldRollOver(elapsed: 305, chunkSeconds: chunk, amplitudeDb: -5), isTrue);
  });

  test('das Suchfenster beginnt genau 3 Sekunden vor dem Ende', () {
    expect(shouldRollOver(elapsed: 296.9, chunkSeconds: chunk, amplitudeDb: -90), isFalse);
    expect(shouldRollOver(elapsed: 297.0, chunkSeconds: chunk, amplitudeDb: -90), isTrue);
  });
}
