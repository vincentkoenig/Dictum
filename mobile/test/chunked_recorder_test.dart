import 'dart:io';

import 'package:dictum_mobile/services/chunked_recorder.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
  late Directory tmp;
  late FakeSource source;
  late List<(int, double)> chunks;

  setUp(() {
    tmp = Directory.systemTemp.createTempSync('dictum_rec_');
    source = FakeSource();
    chunks = [];
  });
  tearDown(() => tmp.deleteSync(recursive: true));

  ChunkedRecorder make({double chunkSeconds = 5, double searchSeconds = 3, double minLast = 0.0}) => ChunkedRecorder(
        source: source,
        dir: Directory('${tmp.path}/rec'),
        chunkSeconds: chunkSeconds,
        searchSeconds: searchSeconds,
        poll: const Duration(milliseconds: 30),
        minLastChunkSeconds: minLast,
        onChunk: (file, idx, seconds) async => chunks.add((idx, seconds)),
      );

  Future<void> wait(double seconds) => Future<void>.delayed(Duration(milliseconds: (seconds * 1000).round()));

  test('schneidet zur vollen Zeit, auch wenn gerade laut gesprochen wird', () async {
    final rec = make(chunkSeconds: 0.4, searchSeconds: 0.1);
    source.db = -5;
    await rec.start();
    await wait(1.0);
    final count = await rec.stop();
    expect(count, greaterThanOrEqualTo(2));
    expect(chunks.map((c) => c.$1), List.generate(count, (i) => i)); // Nummern lückenlos 0, 1, 2 …
    expect(chunks.first.$2, greaterThanOrEqualTo(0.4)); // nicht früher als geplant
    expect(source.starts.length, count); // pro Stück eine eigene Datei
    expect(source.starts.toSet().length, count); // mit eigenem Namen
  });

  test('schneidet im Suchfenster bei einer leisen Stelle, also früher', () async {
    final rec = make(chunkSeconds: 1.0, searchSeconds: 0.5);
    source.db = -80; // Stille
    await rec.start();
    await wait(0.9);
    await rec.stop();
    expect(chunks.first.$2, inInclusiveRange(0.45, 0.85)); // im Fenster 0,5–1,0 s, nicht erst bei 1,0
  });

  test('im Suchfenster wird bei Sprache bis zur vollen Zeit gewartet', () async {
    final rec = make(chunkSeconds: 0.8, searchSeconds: 0.4);
    source.db = -10;
    await rec.start();
    await wait(0.6); // mitten im Suchfenster, aber laut
    expect(chunks, isEmpty);
    await rec.stop();
  });

  test('die Pause zählt nicht zur Aufnahmezeit', () async {
    final rec = make();
    await rec.start();
    await wait(0.3);
    await rec.pause();
    expect(source.paused, isTrue);
    await wait(0.6);
    await rec.resume();
    await wait(0.3);
    await rec.stop();
    expect(rec.elapsedSeconds, inInclusiveRange(0.5, 0.85)); // ~0,6 s, nicht ~1,2 s
    expect(chunks.length, 1);
  });

  test('ein zu kurzes letztes Stück (Antippen des Stopp-Knopfs) wird verworfen', () async {
    final rec = make(minLast: 1.0);
    await rec.start();
    await wait(0.15);
    final count = await rec.stop();
    expect(count, 0);
    expect(chunks, isEmpty);
    expect(File(source.starts.first).existsSync(), isFalse); // Datei aufgeräumt
  });

  test('stoppen aus der Pause beendet das Stück sauber', () async {
    final rec = make();
    await rec.start();
    await wait(0.2);
    await rec.pause();
    final count = await rec.stop();
    expect(count, 1);
    expect(source.paused, isFalse);
  });
}
