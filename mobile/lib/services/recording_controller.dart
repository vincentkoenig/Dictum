// Steuert eine Aufnahme von Anfang bis Ende und verbindet alle Bausteine:
//
//   start()  → Mikrofon-Dienst starten, Aufnahme beginnen, "Aufnahme anlegen" einreihen
//   alle ~5 Minuten fertig: ein Stück → in die Warteschlange → Uploader anstoßen
//   stop()   → letztes Stück, "abschließen" einreihen, Dienst beenden
//
// Der Uploader lädt hoch, sobald Netz da ist. Auch nach "Stopp" läuft das weiter.
//
// Zu jedem Zeitpunkt erzählt der Controller der Web-App über [events], was los ist
// (siehe bridge/native_bridge.dart): Zustand, Sekunden, Stücke, offene Uploads.
//
// **Absturzsicherheit:** Beim Start wird die Datei `active.json` geschrieben und bei jedem
// Stück aktualisiert. Wird die App mitten in einer Aufnahme beendet (Wischen im App-Wechsler, Akku
// leer), bleibt die Datei liegen. Beim nächsten Start schließt [recoverInterrupted] die Aufnahme
// mit den Stücken ab, die schon gesichert waren. Sonst blieben sie ohne Zusammenfassung liegen.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:uuid/uuid.dart';

import 'background_service.dart';
import 'chunked_recorder.dart';
import 'upload_queue.dart';
import 'uploader.dart';

enum RecState { idle, recording, paused }

class RecordingController {
  RecordingController({
    required this.queue,
    required this.uploader,
    required this.service,
    required this.sourceFactory,
    required this.workDir,
    required this.hasSession,
    this.chunkSeconds = 300,
  }) {
    workDir.createSync(recursive: true);
  }

  final UploadQueue queue;
  final Uploader uploader;
  final BackgroundService service;
  final AudioSource Function() sourceFactory;
  final Directory workDir;
  final bool Function() hasSession;
  final double chunkSeconds;

  final _events = StreamController<Map<String, Object?>>.broadcast();
  static const _uuid = Uuid();

  RecState _state = RecState.idle;
  ChunkedRecorder? _recorder;
  AudioSource? _source;
  Timer? _ticker;
  String? _recordingId;
  double _chunkedSeconds = 0;
  String? lastRecordingId;

  Stream<Map<String, Object?>> get events => _events.stream;
  RecState get state => _state;

  File get _marker => File('${workDir.path}/active.json');

  Map<String, Object?> status({String? error}) => {
        'type': 'recording',
        'state': switch (_state) {
          RecState.idle => 'idle',
          RecState.recording => 'recording',
          RecState.paused => 'paused',
        },
        'recordingId': _recordingId ?? lastRecordingId,
        'seconds': _recorder?.elapsedSeconds.floor() ?? 0,
        'chunks': _recorder?.chunksDone ?? 0,
        'pending': uploader.pending,
        if (error != null) 'error': error,
      };

  void _emit({String? error}) => _events.add(status(error: error));

  // --- Aufnahme -------------------------------------------------------------------------

  Future<void> start({required String template, required String language}) async {
    if (_state != RecState.idle) {
      _emit();
      return;
    }
    if (!hasSession()) {
      _emit(error: 'auth_required'); // die Web-App soll zum Neuanmelden auffordern
      return;
    }
    final source = sourceFactory();
    if (!await source.ensurePermission()) {
      await source.dispose();
      _emit(error: 'mic_permission');
      return;
    }

    final id = _uuid.v4();
    // Den Dienst starten, solange die App sichtbar ist (Android verlangt das)
    await service.start(title: 'Dictum nimmt auf', text: 'Tippen zum Öffnen', stopLabel: 'Stopp');

    final recorder = ChunkedRecorder(
      source: source,
      dir: Directory('${workDir.path}/$id'),
      chunkSeconds: chunkSeconds,
      onChunk: (file, idx, seconds) async {
        await queue.addChunk(id, idx, file, seconds);
        _chunkedSeconds += seconds;
        await _writeMarker(id, idx + 1, _chunkedSeconds);
        unawaited(uploader.kick());
        _emit();
      },
    );
    try {
      // Erst die Aufnahme starten, DANN "anlegen" einreihen: Scheitert der Start, bleibt
      // kein verwaister Eintrag in der Warteschlange zurück
      await recorder.start();
    } catch (_) {
      await service.stop();
      await source.dispose();
      _emit(error: 'recorder_failed');
      return;
    }
    await queue.addCreate(id, template, language);
    await _writeMarker(id, 0, 0);

    _source = source;
    _recorder = recorder;
    _recordingId = id;
    _chunkedSeconds = 0;
    _state = RecState.recording;
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) => _emit());
    unawaited(uploader.kick());
    _emit();
  }

  Future<void> pause() async {
    if (_state != RecState.recording) return;
    await _recorder!.pause();
    _state = RecState.paused;
    _emit();
  }

  Future<void> resume() async {
    if (_state != RecState.paused) return;
    await _recorder!.resume();
    _state = RecState.recording;
    _emit();
  }

  Future<void> stop() async {
    final recorder = _recorder;
    final id = _recordingId;
    if (recorder == null || id == null) return;
    _ticker?.cancel();

    final seconds = recorder.elapsedSeconds;
    final count = await recorder.stop(); // gibt das letzte Stück noch über onChunk ab
    await _source?.dispose();
    await service.stop();

    _recorder = null;
    _source = null;
    _state = RecState.idle;
    lastRecordingId = id;
    _recordingId = null;

    if (count == 0) {
      await queue.addDiscard(id); // nichts Brauchbares aufgenommen
      await _clearMarker();
      unawaited(uploader.kick());
      _events.add({...status(error: 'too_short'), 'recordingId': null});
      return;
    }
    await queue.addFinish(id, count, seconds);
    await _clearMarker();
    unawaited(uploader.kick());
    _emit();
  }

  // --- Absturzsicherheit ------------------------------------------------------------------

  Future<void> _writeMarker(String id, int chunks, double seconds) =>
      _marker.writeAsString(jsonEncode({'id': id, 'chunks': chunks, 'seconds': seconds}), flush: true);

  Future<void> _clearMarker() async {
    if (_marker.existsSync()) await _marker.delete();
  }

  /// Beim App-Start: Eine unterbrochene Aufnahme mit den gesicherten Stücken abschließen.
  /// Gibt die ID zurück, wenn etwas gerettet wurde.
  Future<String?> recoverInterrupted() async {
    if (!_marker.existsSync() || _state != RecState.idle) return null;
    try {
      final data = jsonDecode(await _marker.readAsString()) as Map<String, dynamic>;
      final id = data['id'] as String;
      final chunks = data['chunks'] as int;
      if (chunks > 0) {
        await queue.addFinish(id, chunks, (data['seconds'] as num).toDouble());
      } else {
        await queue.addDiscard(id);
      }
      // Das angebrochene Stück ist unvollständig (nicht abgeschlossene Datei): wegwerfen
      final leftover = Directory('${workDir.path}/$id');
      if (leftover.existsSync()) leftover.deleteSync(recursive: true);
      await _clearMarker();
      unawaited(uploader.kick());
      if (chunks > 0) {
        lastRecordingId = id;
        return id;
      }
    } catch (_) {
      await _clearMarker(); // kaputte Markierung nicht für immer behalten
    }
    return null;
  }

  Future<void> dispose() async {
    _ticker?.cancel();
    await _events.close();
  }
}
