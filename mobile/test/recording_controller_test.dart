import 'dart:convert';
import 'dart:io';

import 'package:dictum_mobile/services/recording_controller.dart';
import 'package:dictum_mobile/services/upload_queue.dart';
import 'package:dictum_mobile/services/uploader.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
  late Directory tmp;
  late UploadQueue queue;
  late FakeBackend backend;
  late Uploader uploader;
  late FakeService service;
  late FakeSource source;
  late bool signedIn;
  late List<Map<String, Object?>> events;
  late RecordingController controller;

  setUp(() {
    tmp = Directory.systemTemp.createTempSync('dictum_ctrl_');
    queue = UploadQueue(Directory('${tmp.path}/queue'));
    backend = FakeBackend();
    uploader = Uploader(queue: queue, backend: backend, retryAfter: const Duration(milliseconds: 80));
    service = FakeService();
    source = FakeSource();
    signedIn = true;
    events = [];
    controller = RecordingController(
      queue: queue,
      uploader: uploader,
      service: service,
      sourceFactory: () => source,
      workDir: Directory('${tmp.path}/work'),
      hasSession: () => signedIn,
      chunkSeconds: 0.4,
    );
    controller.events.listen(events.add);
  });

  tearDown(() async {
    await controller.stop(); // läuft nach einem fehlgeschlagenen Test noch eine Aufnahme, beenden
    uploader.dispose();
    await controller.dispose();
    await removeDir(tmp);
  });

  test('ohne Anmeldung wird nicht aufgenommen, die Web-App bekommt Bescheid', () async {
    signedIn = false;
    await controller.start(template: 'meeting', language: 'de');
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(events.last['error'], 'auth_required');
    expect(controller.state, RecState.idle);
    expect(service.log, isEmpty);
    expect(queue.pending(), isEmpty);
  });

  test('fehlt die Mikrofon-Berechtigung, startet nichts', () async {
    source.permission = false;
    await controller.start(template: 'meeting', language: 'de');
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(events.last['error'], 'mic_permission');
    expect(service.log, isEmpty);
    expect(source.disposed, isTrue);
  });

  test('komplette Aufnahme: anlegen, Stücke hochladen, abschließen – in dieser Reihenfolge', () async {
    await controller.start(template: 'interview', language: 'de');
    expect(controller.state, RecState.recording);
    expect(service.log, ['start']);
    await Future<void>.delayed(const Duration(milliseconds: 1500));
    await controller.stop();
    expect(service.log, ['start', 'stop']);
    expect(controller.state, RecState.idle);

    await waitUntil(() => queue.pending().isEmpty);
    expect(backend.log.first, 'create:interview');
    expect(backend.log.last.startsWith('finish:'), isTrue);
    final uploads = backend.log.where((e) => e.startsWith('upload')).toList();
    expect(uploads, isNotEmpty);
    expect(backend.log.last, 'finish:${uploads.length}'); // Stückzahl stimmt mit den Uploads überein
    expect(backend.log.indexOf('create:interview'), lessThan(backend.log.indexOf('upload0')));
    expect(controller.lastRecordingId, isNotNull);
    expect(events.last['state'], 'idle');
  });

  test('Aufnahme ohne Netz: alles bleibt in der Warteschlange und geht später hoch', () async {
    backend.failOn = 'create:meeting';
    await controller.start(template: 'meeting', language: 'de');
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    await controller.stop();
    expect(queue.pending(), isNotEmpty); // nichts hochgeladen, nichts verloren

    backend.failOn = null; // Netz ist zurück – der Uploader versucht es von selbst wieder
    await waitUntil(() => queue.pending().isEmpty);
    expect(backend.log.first, 'create:meeting');
    expect(backend.log.last.startsWith('finish:'), isTrue);
  });

  test('zu kurze Aufnahme wird verworfen statt eine leere Aufnahme anzulegen', () async {
    await controller.start(template: 'meeting', language: 'de');
    await Future<void>.delayed(const Duration(milliseconds: 100));
    await controller.stop();
    await Future<void>.delayed(Duration.zero); // Stream-Ereignisse kommen einen Mikrotask später an
    expect(events.last['error'], 'too_short');
    await waitUntil(() => queue.pending().isEmpty);
    expect(backend.log, ['create:meeting', 'discard']);
  });

  test('Pause und Weiter ändern den Zustand', () async {
    await controller.start(template: 'meeting', language: 'de');
    await controller.pause();
    expect(controller.state, RecState.paused);
    await Future<void>.delayed(Duration.zero); // Stream-Ereignisse kommen einen Mikrotask später an
    expect(events.last['state'], 'paused');
    await controller.resume();
    expect(controller.state, RecState.recording);
    await controller.stop();
  });

  group('Wiederherstellung nach einem Absturz', () {
    File marker() => File('${tmp.path}/work/active.json');

    test('gesicherte Stücke werden abgeschlossen, damit sie eine Zusammenfassung bekommen', () async {
      marker().writeAsStringSync(jsonEncode({'id': 'abc', 'chunks': 2, 'seconds': 611.5}));
      Directory('${tmp.path}/work/abc').createSync(recursive: true);
      File('${tmp.path}/work/abc/chunk_2.ogg').writeAsBytesSync([9]);

      expect(await controller.recoverInterrupted(), 'abc');
      await waitUntil(() => queue.pending().isEmpty);
      expect(backend.log, ['finish:2']);
      expect(marker().existsSync(), isFalse);
      expect(Directory('${tmp.path}/work/abc').existsSync(), isFalse); // angebrochenes Stück weg
    });

    test('ohne gesicherte Stücke wird die leere Aufnahme verworfen', () async {
      marker().writeAsStringSync(jsonEncode({'id': 'abc', 'chunks': 0, 'seconds': 0}));
      expect(await controller.recoverInterrupted(), isNull);
      await waitUntil(() => queue.pending().isEmpty);
      expect(backend.log, ['discard']);
    });

    test('eine kaputte Markierung blockiert nichts', () async {
      marker().writeAsStringSync('das ist kein json');
      expect(await controller.recoverInterrupted(), isNull);
      expect(marker().existsSync(), isFalse);
    });

    test('ohne Markierung passiert nichts', () async {
      expect(await controller.recoverInterrupted(), isNull);
      expect(backend.log, isEmpty);
    });
  });
}
