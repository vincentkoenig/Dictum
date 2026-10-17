// Lädt die Warteschlange hoch, sobald etwas Neues da ist – und versucht es bei einem Fehler
// (kein Netz, Server-Problem) automatisch nach einer Weile wieder.
//
// `kick()` heißt "es gibt etwas zu tun". Es darf beliebig oft und aus jedem Teil der App aufgerufen
// werden: Läuft schon ein Durchgang, wird nur vermerkt, dass nach seinem Ende noch einer folgt.
// So wird nie parallel hochgeladen (das würde die Reihenfolge durcheinanderbringen), und kein
// Auslöser geht verloren.

import 'dart:async';

import 'upload_queue.dart';

class Uploader {
  Uploader({
    required this.queue,
    required this.backend,
    this.retryAfter = const Duration(seconds: 30),
    this.onProgress,
  });

  final UploadQueue queue;
  final QueueBackend backend;
  final Duration retryAfter;

  /// Wird nach jedem Durchgang mit der Zahl der noch offenen Schritte aufgerufen.
  final void Function(int pending)? onProgress;

  bool _busy = false;
  bool _again = false;
  Timer? _retry;

  int get pending => queue.pending().length;

  Future<void> kick() async {
    if (_busy) {
      _again = true;
      return;
    }
    _busy = true;
    try {
      do {
        _again = false;
        _retry?.cancel();
        final result = await queue.process(backend);
        onProgress?.call(result.remaining);
        if (result.error != null && result.remaining > 0) {
          _retry = Timer(retryAfter, kick);
        }
      } while (_again);
    } finally {
      _busy = false;
    }
  }

  void dispose() => _retry?.cancel();
}
