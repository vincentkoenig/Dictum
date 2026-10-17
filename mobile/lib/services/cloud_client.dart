// Kleiner Client für das Dictum-Backend auf Supabase – das Dart-Gegenstück zu
// desktop/dictum/cloud.py. Er spricht die normalen HTTP-Schnittstellen von Supabase direkt an:
//
//   /auth/v1/token          Login (E-Mail + Passwort) und Token erneuern
//   /rest/v1/<tabelle>      Datenbank (PostgREST)
//   /storage/v1/object/...  Dateien hochladen
//   /functions/v1/<name>    Edge Functions
//
// Bei JEDER Anfrage gehen zwei Kennungen mit: `apikey` ("welches Projekt?") und
// `Authorization: Bearer <Token>` ("wer bin ich?"), damit die Row Level Security greift.
//
// Warum hat die App ihre EIGENE Sitzung und nutzt nicht die der Web-App?
// Supabase erneuert Tokens mit einem "refresh token", das sich bei jeder Erneuerung ändert
// ("Rotation"). Würden Web-App und Aufnahme-Dienst dasselbe Token benutzen, entzöge die
// Erneuerung des einen dem anderen das Token – im schlimmsten Fall wird die ganze Sitzung
// gesperrt. Zwei getrennte Anmeldungen desselben Nutzers stören sich dagegen nie.

import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'upload_queue.dart' show QueueBackend;

class CloudException implements Exception {
  CloudException(this.what, {this.status, this.body});

  final String what;
  final int? status;
  final String? body;

  /// 401/403: das Token ist ungültig, es hilft nur eine neue Anmeldung.
  bool get isAuthError => status == 401 || status == 403;

  @override
  String toString() {
    final shortBody = (body ?? '').length > 200 ? '${body!.substring(0, 200)}…' : body;
    return 'CloudException: $what${status != null ? ' ($status)' : ''}${shortBody != null && shortBody.isNotEmpty ? ' – $shortBody' : ''}';
  }
}

class Session {
  Session({required this.accessToken, required this.refreshToken, required this.userId, required this.expiresAt});

  final String accessToken;
  final String refreshToken;
  final String userId;
  final DateTime expiresAt;
}

/// Wo das Refresh-Token dauerhaft liegt (in der App: Android Keystore über flutter_secure_storage).
abstract interface class SessionStore {
  Future<String?> readRefreshToken();
  Future<void> writeRefreshToken(String token);
  Future<void> clear();
}

/// Was die Brücke zur Web-App für die Anmeldung braucht (in der App: DictumCloud).
abstract interface class AuthBackend {
  Future<void> signIn(String email, String password);
  Future<void> signOut();
  bool get hasSession;
}

class DictumCloud implements QueueBackend, AuthBackend {
  DictumCloud({
    required this.url,
    required this.key,
    required this.store,
    http.Client? client,
    DateTime Function()? now,
  })  : _http = client ?? http.Client(),
        _now = now ?? DateTime.now;

  final String url;
  final String key;
  final SessionStore store;
  final http.Client _http;
  final DateTime Function() _now;

  Session? _session;

  /// Hat die App eine Anmeldung, mit der sie hochladen darf?
  @override
  bool get hasSession => _session != null;

  // --- Anmeldung ------------------------------------------------------------------------

  @override
  Future<void> signIn(String email, String password) async {
    final res = await _http.post(
      Uri.parse('$url/auth/v1/token?grant_type=password'),
      headers: {'apikey': key, 'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (res.statusCode != 200) {
      throw CloudException('Anmeldung fehlgeschlagen', status: res.statusCode, body: res.body);
    }
    await _adopt(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// Beim App-Start: mit dem gespeicherten Refresh-Token wieder anmelden. Gibt false zurück,
  /// wenn es keins gibt oder es nicht mehr gilt (dann muss man sich neu anmelden).
  Future<bool> restore() async {
    final token = await store.readRefreshToken();
    if (token == null) return false;
    try {
      await _refresh(token);
      return true;
    } on CloudException catch (e) {
      if (e.isAuthError || e.status == 400) {
        await store.clear();
        return false;
      }
      rethrow; // z. B. kein Netz: Token behalten und später nochmal versuchen
    }
  }

  @override
  Future<void> signOut() async {
    _session = null;
    await store.clear();
  }

  Future<void> _refresh(String refreshToken) async {
    final res = await _http.post(
      Uri.parse('$url/auth/v1/token?grant_type=refresh_token'),
      headers: {'apikey': key, 'Content-Type': 'application/json'},
      body: jsonEncode({'refresh_token': refreshToken}),
    );
    if (res.statusCode != 200) {
      throw CloudException('Token erneuern fehlgeschlagen', status: res.statusCode, body: res.body);
    }
    await _adopt(jsonDecode(res.body) as Map<String, dynamic>);
  }

  Future<void> _adopt(Map<String, dynamic> data) async {
    final refresh = data['refresh_token'] as String;
    _session = Session(
      accessToken: data['access_token'] as String,
      refreshToken: refresh,
      userId: (data['user'] as Map<String, dynamic>)['id'] as String,
      expiresAt: _now().add(Duration(seconds: (data['expires_in'] as num?)?.toInt() ?? 3600)),
    );
    // Das NEUE Refresh-Token sofort sichern: das alte ist nach der Erneuerung wertlos
    await store.writeRefreshToken(refresh);
  }

  /// Gültiges Access-Token; erneuert es kurz vor Ablauf (Tokens gelten 1 Stunde, ein Meeting
  /// kann länger dauern).
  Future<Session> _valid({bool force = false}) async {
    final s = _session;
    if (s == null) throw CloudException('Nicht angemeldet');
    if (force || _now().isAfter(s.expiresAt.subtract(const Duration(minutes: 2)))) {
      await _refresh(s.refreshToken);
    }
    return _session!;
  }

  /// Führt eine Anfrage mit Login aus. Antwortet der Server mit 401, ist das Token
  /// möglicherweise gerade abgelaufen: dann ein einziges Mal erneuern und wiederholen.
  Future<http.Response> _authed(Future<http.Response> Function(Map<String, String> auth, Session session) call) async {
    var session = await _valid();
    Map<String, String> auth(Session s) => {'apikey': key, 'Authorization': 'Bearer ${s.accessToken}'};
    var res = await call(auth(session), session);
    if (res.statusCode == 401) {
      session = await _valid(force: true);
      res = await call(auth(session), session);
    }
    return res;
  }

  http.Response _check(http.Response res, String what) {
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw CloudException('$what fehlgeschlagen', status: res.statusCode, body: res.body);
    }
    return res;
  }

  // --- Gesprächsaufnahmen ------------------------------------------------------------------

  /// Legt die Aufnahme an. Mit fester ID wiederholbar: Gibt es sie schon, passiert nichts
  /// ("ignore-duplicates") – wichtig, weil die Warteschlange Schritte wiederholt.
  @override
  Future<void> createRecording({required String id, required String template, required String language}) async {
    final res = await _authed((auth, _) => _http.post(
          Uri.parse('$url/rest/v1/recordings'),
          headers: {
            ...auth,
            'Content-Type': 'application/json',
            'Prefer': 'resolution=ignore-duplicates,return=minimal',
          },
          // source "pwa": Die Datenbank erlaubt bisher nur pwa/desktop. Die Android-App ist
          // technisch dieselbe Web-Oberfläche, deshalb passt der Wert.
          body: jsonEncode({'id': id, 'kind': 'conversation', 'template': template, 'language': language, 'source': 'pwa'}),
        ));
    _check(res, 'Aufnahme anlegen');
  }

  @override
  Future<void> uploadChunk({
    required String recordingId,
    required int idx,
    required Uint8List bytes,
    required double durationSeconds,
  }) async {
    // Der Pfad MUSS mit der eigenen Nutzer-ID beginnen, sonst lehnt die Storage-Policy ab.
    // Aus dem gleichen Grund wie bei der Aufnahme-ID gilt: wiederholbar dank "x-upsert".
    late final String path;
    final up = await _authed((auth, session) {
      path = '${session.userId}/$recordingId/$idx.ogg';
      return _http.post(
        Uri.parse('$url/storage/v1/object/recordings/$path'),
        headers: {...auth, 'Content-Type': 'audio/ogg', 'x-upsert': 'true'},
        body: bytes,
      );
    });
    _check(up, 'Upload Stück $idx');

    final row = await _authed((auth, _) => _http.post(
          Uri.parse('$url/rest/v1/recording_chunks'),
          headers: {...auth, 'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates,return=minimal'},
          body: jsonEncode({'recording_id': recordingId, 'idx': idx, 'storage_path': path, 'duration_seconds': durationSeconds}),
        ));
    _check(row, 'Stück $idx eintragen');
  }

  @override
  Future<void> transcribeChunk(String recordingId, int idx) async {
    final res = await _authed((auth, _) => _http
        .post(
          Uri.parse('$url/functions/v1/transcribe'),
          headers: {...auth, 'Content-Type': 'application/json'},
          body: jsonEncode({'recording_id': recordingId, 'idx': idx}),
        )
        .timeout(const Duration(seconds: 150))); // Laufzeitlimit der Edge Function
    _check(res, 'Transkription Stück $idx');
  }

  /// "Alle Stücke sind hochgeladen": setzt die Stückzahl und startet die Zusammenfassung.
  @override
  Future<void> finish(String recordingId, int chunkCount, double durationSeconds) async {
    // Nur ändern, solange die Aufnahme noch "uploading" ist. Sonst würde ein wiederholter
    // Aufruf eine schon fertige Aufnahme zurück auf "transcribing" setzen.
    final patch = await _authed((auth, _) => _http.patch(
          Uri.parse('$url/rest/v1/recordings?id=eq.$recordingId&status=eq.uploading'),
          headers: {...auth, 'Content-Type': 'application/json', 'Prefer': 'return=minimal'},
          body: jsonEncode({'chunk_count': chunkCount, 'status': 'transcribing', 'duration_seconds': durationSeconds}),
        ));
    _check(patch, 'Aufnahme abschließen');

    final summarize = await _authed((auth, _) => _http.post(
          Uri.parse('$url/functions/v1/summarize'),
          headers: {...auth, 'Content-Type': 'application/json'},
          body: jsonEncode({'recording_id': recordingId, 'force': false}),
        ));
    _check(summarize, 'Zusammenfassung starten');
  }

  /// Löscht eine Aufnahme samt Stücken ("on delete cascade" in der Datenbank). Ist sie schon
  /// weg, antwortet der Server trotzdem mit Erfolg – der Schritt ist also wiederholbar.
  @override
  Future<void> discardRecording(String recordingId) async {
    final res = await _authed((auth, _) => _http.delete(
          Uri.parse('$url/rest/v1/recordings?id=eq.$recordingId'),
          headers: {...auth, 'Prefer': 'return=minimal'},
        ));
    _check(res, 'Aufnahme verwerfen');
  }
}
