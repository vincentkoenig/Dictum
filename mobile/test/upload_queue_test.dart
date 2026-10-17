import 'dart:io';
import 'dart:typed_data';

import 'package:dictum_mobile/services/upload_queue.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeBackend implements QueueBackend {
  FakeBackend({this.failOn});

  final String? failOn;
  final log = <String>[];

  void _do(String what) {
    if (what == failOn) throw const SocketException('kein Netz');
    log.add(what);
  }

  @override
  Future<void> createRecording({required String id, required String template, required String language}) async =>
      _do('create:$template');

  @override
  Future<void> uploadChunk({
    required String recordingId,
    required int idx,
    required Uint8List bytes,
    required double durationSeconds,
  }) async {
    expect(bytes, [1, 2, 3]);
    _do('upload$idx');
  }

  @override
  Future<void> transcribeChunk(String recordingId, int idx) async => _do('transcribe$idx');

  @override
  Future<void> finish(String recordingId, int chunkCount, double durationSeconds) async => _do('finish:$chunkCount');

  @override
  Future<void> discardRecording(String recordingId) async => _do('discard');
}

void main() {
  late Directory tmp;
  late UploadQueue queue;

  setUp(() {
    tmp = Directory.systemTemp.createTempSync('dictum_queue_');
    queue = UploadQueue(Directory('${tmp.path}/queue'));
  });
  tearDown(() => tmp.deleteSync(recursive: true));

  File audio(String name) => File('${tmp.path}/$name')..writeAsBytesSync([1, 2, 3]);

  Future<void> fill() async {
    await queue.addCreate('r1', 'meeting', 'de');
    await queue.addChunk('r1', 0, audio('a.ogg'), 300);
    await queue.addChunk('r1', 1, audio('b.ogg'), 42);
    await queue.addFinish('r1', 2, 342);
  }

  test('arbeitet alles in der richtigen Reihenfolge ab und räumt auf', () async {
    await fill();
    final backend = FakeBackend();
    final result = await queue.process(backend);
    expect(backend.log, ['create:meeting', 'upload0', 'transcribe0', 'upload1', 'transcribe1', 'finish:2']);
    expect(result.done, 4);
    expect(result.error, isNull);
    expect(Directory('${tmp.path}/queue').listSync(), isEmpty); // auch die Audio-Dateien sind weg
  });

  test('das Audio wird verschoben, nicht kopiert (kein doppelter Speicher)', () async {
    final source = audio('a.ogg');
    await queue.addChunk('r1', 0, source, 10);
    expect(source.existsSync(), isFalse);
  });

  test('ohne Netz bleibt alles liegen und geht später dort weiter', () async {
    await fill();
    final offline = FakeBackend(failOn: 'upload1');
    final first = await queue.process(offline);
    expect(first.done, 2); // create + chunk 0
    expect(first.error, isA<SocketException>());
    expect(first.remaining, 2);

    // "Neustart": neues Warteschlangen-Objekt auf demselben Ordner
    final again = UploadQueue(Directory('${tmp.path}/queue'));
    final online = FakeBackend();
    await again.process(online);
    expect(online.log, ['upload1', 'transcribe1', 'finish:2']);
  });

  test('zwei gleichzeitige Durchgänge laden nichts doppelt hoch', () async {
    await fill();
    final backend = FakeBackend();
    await Future.wait([queue.process(backend), queue.process(backend)]);
    expect(backend.log.where((e) => e.startsWith('upload')).length, 2);
  });

  test('eine verworfene Aufnahme wird beim Server gelöscht', () async {
    await queue.addCreate('r1', 'meeting', 'de');
    await queue.addDiscard('r1');
    final backend = FakeBackend();
    await queue.process(backend);
    expect(backend.log, ['create:meeting', 'discard']);
  });

  test('hasPendingFor erkennt offene Schritte einer Aufnahme', () async {
    await queue.addCreate('r1', 'meeting', 'de');
    expect(queue.hasPendingFor('r1'), isTrue);
    expect(queue.hasPendingFor('r2'), isFalse);
    await queue.process(FakeBackend());
    expect(queue.hasPendingFor('r1'), isFalse);
  });
}
