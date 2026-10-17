// Attrappen für die Tests: ersetzen Mikrofon, Dienst und Server, damit sich die Logik ohne
// Handy prüfen lässt.

import 'dart:io';
import 'dart:typed_data';

import 'package:dictum_mobile/services/background_service.dart';
import 'package:dictum_mobile/services/chunked_recorder.dart';
import 'package:dictum_mobile/services/upload_queue.dart';

/// Ein "Mikrofon", das beim Starten eine kleine Datei anlegt.
class FakeSource implements AudioSource {
  FakeSource({this.permission = true});

  bool permission;
  double db = -10; // laut: es wird nie in einer "Pause" geschnitten
  bool disposed = false;
  bool paused = false;
  final starts = <String>[];
  String? _path;

  @override
  Future<bool> ensurePermission() async => permission;

  @override
  Future<void> start(String path) async {
    starts.add(path);
    File(path).writeAsBytesSync([1, 2, 3]);
    _path = path;
  }

  @override
  Future<String?> stop() async {
    final path = _path;
    _path = null;
    return path;
  }

  @override
  Future<void> pause() async => paused = true;

  @override
  Future<void> resume() async => paused = false;

  @override
  Future<double> amplitudeDb() async => db;

  @override
  Future<void> dispose() async => disposed = true;
}

class FakeService implements BackgroundService {
  final log = <String>[];

  @override
  Future<void> start({required String title, required String text, required String stopLabel}) async =>
      log.add('start');

  @override
  Future<void> stop() async => log.add('stop');
}

/// Ein "Server", der jeden Schritt aufschreibt. [failOn] lässt einen Schritt scheitern.
class FakeBackend implements QueueBackend {
  FakeBackend({this.failOn});

  String? failOn;
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
  }) async =>
      _do('upload$idx');

  @override
  Future<void> transcribeChunk(String recordingId, int idx) async => _do('transcribe$idx');

  @override
  Future<void> finish(String recordingId, int chunkCount, double durationSeconds) async => _do('finish:$chunkCount');

  @override
  Future<void> discardRecording(String recordingId) async => _do('discard');
}

/// Wartet (höchstens [timeout]), bis [condition] stimmt – statt feste Zeiten zu raten.
Future<void> waitUntil(bool Function() condition, {Duration timeout = const Duration(seconds: 3)}) async {
  final end = DateTime.now().add(timeout);
  while (!condition()) {
    if (DateTime.now().isAfter(end)) throw StateError('Bedingung nicht rechtzeitig erfüllt');
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
}

/// Löscht einen Ordner. Läuft im Hintergrund noch ein Upload, hält Windows einzelne Dateien kurz
/// fest ("von einem anderen Prozess verwendet"): Dann einen Moment warten und erneut versuchen.
Future<void> removeDir(Directory dir) async {
  for (var attempt = 0; attempt < 50; attempt++) {
    try {
      if (dir.existsSync()) dir.deleteSync(recursive: true);
      return;
    } on FileSystemException {
      await Future<void>.delayed(const Duration(milliseconds: 40));
    }
  }
}
