// Upload-Warteschlange auf dem Handy – das Gegenstück zu desktop/dictum/upload_queue.py und
// pwa/src/lib/queue.ts. Dieselbe Idee in allen dreien:
//
// Jeder Schritt einer Aufnahme wird ZUERST als Datei gespeichert und ERST DANN hochgeladen:
//
//   <app-ordner>/queue/
//     00001760000000000-001.json     {"type": "create", ...}
//     00001760000000123-002.json     {"type": "chunk", "idx": 0, "audio": "…ogg"}
//     00001760000000123-002.ogg      das Audio dazu
//     00001760000300456-003.json     {"type": "finish", ...}
//
// - Kein Netz? Die Dateien warten, bis es wieder geht.
// - App beendet oder Handy neu gestartet? Beim nächsten Start geht es dort weiter.
//
// Abgearbeitet wird in Dateinamen-Reihenfolge und beim ersten Fehler gestoppt: "finish" darf
// nie vor dem letzten Stück laufen. Alle Schritte sind wiederholbar, ohne Schaden anzurichten.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

/// Was die Warteschlange zum Hochladen braucht (in der App: DictumCloud, im Test eine Attrappe).
abstract interface class QueueBackend {
  Future<void> createRecording({required String id, required String template, required String language});
  Future<void> uploadChunk({
    required String recordingId,
    required int idx,
    required Uint8List bytes,
    required double durationSeconds,
  });
  Future<void> transcribeChunk(String recordingId, int idx);
  Future<void> finish(String recordingId, int chunkCount, double durationSeconds);
}

class QueueResult {
  QueueResult(this.done, this.remaining, [this.error]);

  final int done;
  final int remaining;
  final Object? error;
}

class UploadQueue {
  UploadQueue(this.dir) {
    dir.createSync(recursive: true);
  }

  final Directory dir;
  int _counter = 0;
  bool _running = false;

  String _newName() {
    _counter = (_counter + 1) % 1000;
    return '${DateTime.now().microsecondsSinceEpoch.toString().padLeft(17, '0')}-${_counter.toString().padLeft(3, '0')}';
  }

  // --- Einreihen -----------------------------------------------------------------------

  Future<void> addCreate(String recordingId, String template, String language) =>
      _write({'type': 'create', 'recording_id': recordingId, 'template': template, 'language': language});

  /// Das Audio wird in den Warteschlangen-Ordner VERSCHOBEN. Erst danach entsteht der JSON-
  /// Eintrag: So gibt es nie einen Eintrag ohne Audio, auch wenn genau dazwischen der Akku leer ist.
  Future<void> addChunk(String recordingId, int idx, File audio, double durationSeconds) async {
    final name = _newName();
    final audioName = '$name.ogg';
    try {
      await audio.rename('${dir.path}/$audioName');
    } on FileSystemException {
      await audio.copy('${dir.path}/$audioName'); // anderes Laufwerk: kopieren statt verschieben
      await audio.delete();
    }
    await _write({
      'type': 'chunk',
      'recording_id': recordingId,
      'idx': idx,
      'audio': audioName,
      'duration_seconds': durationSeconds,
    }, name);
  }

  Future<void> addFinish(String recordingId, int chunkCount, double durationSeconds) =>
      _write({'type': 'finish', 'recording_id': recordingId, 'chunk_count': chunkCount, 'duration_seconds': durationSeconds});

  Future<void> _write(Map<String, Object?> item, [String? name]) async {
    name ??= _newName();
    // Erst in eine Probedatei, dann umbenennen: Die Datei ist ganz da oder gar nicht
    final tmp = File('${dir.path}/$name.json.tmp');
    await tmp.writeAsString(jsonEncode(item), flush: true);
    await tmp.rename('${dir.path}/$name.json');
  }

  List<File> pending() {
    final files = dir.listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    return files;
  }

  bool hasPendingFor(String recordingId) =>
      pending().any((f) => f.readAsStringSync().contains('"$recordingId"'));

  // --- Abarbeiten ----------------------------------------------------------------------

  /// Lädt alles hoch, was geht. Läuft schon ein Durchgang, passiert nichts (kein Doppeln).
  Future<QueueResult> process(QueueBackend backend) async {
    if (_running) return QueueResult(0, pending().length);
    _running = true;
    var done = 0;
    try {
      for (final file in pending()) {
        final item = jsonDecode(await file.readAsString()) as Map<String, dynamic>;
        await _run(item, backend);
        await file.delete();
        if (item['type'] == 'chunk') {
          final audio = File('${dir.path}/${item['audio']}');
          if (audio.existsSync()) await audio.delete();
        }
        done++;
      }
      return QueueResult(done, 0);
    } catch (e) {
      return QueueResult(done, pending().length, e);
    } finally {
      _running = false;
    }
  }

  Future<void> _run(Map<String, dynamic> item, QueueBackend backend) async {
    final id = item['recording_id'] as String;
    switch (item['type']) {
      case 'create':
        await backend.createRecording(id: id, template: item['template'] as String, language: item['language'] as String);
      case 'chunk':
        final bytes = await File('${dir.path}/${item['audio']}').readAsBytes();
        final idx = item['idx'] as int;
        await backend.uploadChunk(
          recordingId: id,
          idx: idx,
          bytes: bytes,
          durationSeconds: (item['duration_seconds'] as num).toDouble(),
        );
        await backend.transcribeChunk(id, idx);
      case 'finish':
        await backend.finish(id, item['chunk_count'] as int, (item['duration_seconds'] as num).toDouble());
    }
  }
}
