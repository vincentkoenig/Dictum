import 'dart:io';

import 'package:dictum_mobile/services/upload_queue.dart';
import 'package:dictum_mobile/services/uploader.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
  late Directory tmp;
  late UploadQueue queue;

  setUp(() {
    tmp = Directory.systemTemp.createTempSync('dictum_uploader_');
    queue = UploadQueue(Directory('${tmp.path}/queue'));
  });
  tearDown(() => tmp.deleteSync(recursive: true));

  test('lädt hoch und meldet den Fortschritt', () async {
    final progress = <int>[];
    final uploader = Uploader(queue: queue, backend: FakeBackend(), onProgress: progress.add);
    await queue.addCreate('r1', 'meeting', 'de');
    await uploader.kick();
    expect(queue.pending(), isEmpty);
    expect(progress.last, 0);
    uploader.dispose();
  });

  test('versucht es nach einem Fehler von selbst wieder', () async {
    final backend = FakeBackend(failOn: 'create:meeting');
    final uploader = Uploader(queue: queue, backend: backend, retryAfter: const Duration(milliseconds: 60));
    await queue.addCreate('r1', 'meeting', 'de');
    await uploader.kick();
    expect(queue.pending(), hasLength(1)); // gescheitert, aber nichts verloren

    backend.failOn = null;
    await waitUntil(() => queue.pending().isEmpty);
    expect(backend.log, ['create:meeting']);
    uploader.dispose();
  });

  test('ein Auslöser während eines Durchgangs geht nicht verloren', () async {
    final backend = FakeBackend();
    final uploader = Uploader(queue: queue, backend: backend);
    await queue.addCreate('r1', 'meeting', 'de');
    final first = uploader.kick();
    await queue.addFinish('r1', 1, 10); // kommt dazu, während der erste Durchgang läuft
    final second = uploader.kick(); // wird nur vermerkt
    await Future.wait([first, second]);
    await waitUntil(() => queue.pending().isEmpty);
    expect(backend.log, ['create:meeting', 'finish:1']);
    uploader.dispose();
  });
}
