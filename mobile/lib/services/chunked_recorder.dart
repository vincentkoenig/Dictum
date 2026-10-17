// Aufnahme in Stücken – das Gegenstück zu pwa/src/lib/audio.ts (ChunkedRecorder) und
// desktop/dictum/meeting.py.
//
// Warum Stücke? Jedes Stück wird einzeln hochgeladen und transkribiert: Das hält die Dateien
// unter dem 25-MB-Limit von OpenAI und die Edge Function unter ihrem Zeitlimit. Außerdem geht bei
// einem Absturz höchstens das laufende Stück verloren, nicht die ganze Aufnahme.
//
// Hier ist jedes Stück eine eigene, vollständige Opus-Datei (OGG). Der Wechsel zwischen zwei
// Stücken heißt "Rollover": aufhören, Datei weitergeben, sofort eine neue beginnen. Die Lücke
// dazwischen liegt im Bereich von Millisekunden. Wann gewechselt wird, entscheidet rollover.dart
// (in einer Sprechpause, nicht mitten im Satz).
//
// Die eigentliche Aufnahme steckt hinter `AudioSource`. Dadurch lässt sich die Logik in
// Tests mit einer Attrappe prüfen, ohne Mikrofon und ohne Android.

import 'dart:async';
import 'dart:io';

import 'package:record/record.dart';

import '../config.dart' as config;
import 'rollover.dart';

abstract interface class AudioSource {
  /// Fragt die Mikrofon-Berechtigung ab (zeigt beim ersten Mal den Android-Dialog).
  Future<bool> ensurePermission();
  Future<void> start(String path);

  /// Beendet das aktuelle Stück und gibt den Dateipfad zurück (oder null).
  Future<String?> stop();
  Future<void> pause();
  Future<void> resume();

  /// Aktuelle Lautstärke in dB (0 = laut, -160 = Stille).
  Future<double> amplitudeDb();
  Future<void> dispose();
}

/// Die echte Aufnahme über das Paket `record` (benutzt MediaRecorder von Android).
class RecordPackageSource implements AudioSource {
  final AudioRecorder _recorder = AudioRecorder();

  // Opus ist für Sprache gemacht: 32 kbit/s klingen klar und ergeben ~1,2 MB je 5 Minuten.
  // Verarbeitung (Rauschfilter, Echo, Automatik) bleibt AUS: Whisper kommt mit dem
  // Originalsignal besser zurecht als mit einem bereits "verbesserten".
  static const _config = RecordConfig(
    encoder: AudioEncoder.opus,
    bitRate: 32000,
    sampleRate: 48000,
    numChannels: 1,
  );

  @override
  Future<bool> ensurePermission() => _recorder.hasPermission();

  @override
  Future<void> start(String path) => _recorder.start(_config, path: path);

  @override
  Future<String?> stop() => _recorder.stop();

  @override
  Future<void> pause() => _recorder.pause();

  @override
  Future<void> resume() => _recorder.resume();

  @override
  Future<double> amplitudeDb() async => (await _recorder.getAmplitude()).current;

  @override
  Future<void> dispose() => _recorder.dispose();
}

typedef ChunkCallback = Future<void> Function(File file, int idx, double durationSeconds);

class ChunkedRecorder {
  ChunkedRecorder({
    required this.source,
    required this.dir,
    required this.onChunk,
    this.chunkSeconds = config.chunkSeconds,
    this.searchSeconds = 3.0,
    this.poll = const Duration(milliseconds: 200),
    this.minLastChunkSeconds = 1.0,
  });

  final AudioSource source;
  final Directory dir;
  final ChunkCallback onChunk;
  final double chunkSeconds;

  /// So viele Sekunden vor dem Ende wird auf eine Sprechpause zum Schneiden gewartet.
  final double searchSeconds;
  final Duration poll;

  /// Ein letztes Stück, das kürzer ist, stammt meist vom Antippen des Stopp-Knopfs. Es wird verworfen.
  final double minLastChunkSeconds;

  final Stopwatch _chunkTime = Stopwatch();
  final Stopwatch _total = Stopwatch();
  Timer? _timer;
  int _idx = 0;
  bool _busy = false;
  bool _running = false;
  bool _paused = false;
  int _emitted = 0;

  /// Sekunden aufgenommen, ohne Pausen.
  double get elapsedSeconds => _total.elapsedMilliseconds / 1000;

  /// Anzahl bisher fertiger Stücke.
  int get chunksDone => _emitted;
  bool get isRunning => _running;
  bool get isPaused => _paused;

  String _pathFor(int idx) => '${dir.path}/chunk_$idx.ogg';

  Future<void> start() async {
    dir.createSync(recursive: true);
    _running = true;
    _paused = false;
    await source.start(_pathFor(_idx));
    _chunkTime
      ..reset()
      ..start();
    _total
      ..reset()
      ..start();
    _timer = Timer.periodic(poll, (_) => _tick());
  }

  Future<void> pause() async {
    if (!_running || _paused) return;
    _paused = true;
    _chunkTime.stop();
    _total.stop();
    await source.pause();
  }

  Future<void> resume() async {
    if (!_running || !_paused) return;
    await source.resume();
    _paused = false;
    _chunkTime.start();
    _total.start();
  }

  Future<void> _tick() async {
    if (!_running || _paused || _busy) return;
    final elapsed = _chunkTime.elapsedMilliseconds / 1000;
    // Die Lautstärke nur im Suchfenster abfragen – davor wäre der Aufruf verschwendet
    var db = 0.0;
    if (elapsed >= chunkSeconds - searchSeconds && elapsed < chunkSeconds) {
      db = await source.amplitudeDb();
    }
    if (shouldRollOver(elapsed: elapsed, chunkSeconds: chunkSeconds, amplitudeDb: db, searchSeconds: searchSeconds)) {
      await _rollOver();
    }
  }

  Future<void> _rollOver() async {
    _busy = true;
    try {
      await _finishCurrent(emitShort: true);
      _idx++;
      await source.start(_pathFor(_idx));
      _chunkTime
        ..reset()
        ..start();
    } finally {
      _busy = false;
    }
  }

  Future<void> _finishCurrent({required bool emitShort}) async {
    final seconds = _chunkTime.elapsedMilliseconds / 1000;
    _chunkTime.stop();
    final path = await source.stop();
    if (path == null) return;
    final file = File(path);
    if (!file.existsSync() || file.lengthSync() == 0) return;
    if (!emitShort && seconds < minLastChunkSeconds) {
      file.deleteSync();
      return;
    }
    await onChunk(file, _emitted, seconds);
    _emitted++;
  }

  /// Beendet die Aufnahme. Das letzte Stück geht noch an [onChunk]. Gibt die Zahl der Stücke zurück.
  Future<int> stop() async {
    if (!_running) return _emitted;
    _timer?.cancel();
    // Läuft gerade ein Stückwechsel, kurz warten, damit er sauber zu Ende geht
    while (_busy) {
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    _running = false;
    _total.stop();
    if (_paused) {
      await source.resume(); // sonst lässt sich das Stück nicht sauber beenden
      _paused = false;
    }
    await _finishCurrent(emitShort: false);
    return _emitted;
  }
}
