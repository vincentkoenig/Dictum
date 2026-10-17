import 'dart:convert';
import 'dart:typed_data';

import 'package:dictum_mobile/services/cloud_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class MemoryStore implements SessionStore {
  String? token;

  @override
  Future<void> clear() async => token = null;

  @override
  Future<String?> readRefreshToken() async => token;

  @override
  Future<void> writeRefreshToken(String t) async => token = t;
}

/// Eine Attrappe des Servers: merkt sich jede Anfrage und antwortet mit gültigen Tokens.
class Fake {
  final requests = <http.Request>[];
  int refreshCount = 0;
  int unauthorizedOnce = 0; // so oft antwortet ein Datenzugriff mit 401

  Future<http.Response> handle(http.Request r) async {
    requests.add(r);
    if (r.url.path == '/auth/v1/token') {
      final grant = r.url.queryParameters['grant_type'];
      if (grant == 'refresh_token') refreshCount++;
      return http.Response(
        jsonEncode({
          'access_token': 'access-$grant-$refreshCount',
          'refresh_token': 'refresh-$refreshCount',
          'expires_in': 3600,
          'user': {'id': 'user-123'},
        }),
        200,
      );
    }
    if (unauthorizedOnce > 0 && !r.url.path.startsWith('/auth')) {
      unauthorizedOnce--;
      return http.Response('JWT expired', 401);
    }
    return http.Response('', 201);
  }

  http.Request last(String pathPart) => requests.lastWhere((r) => r.url.path.contains(pathPart));
}

void main() {
  late Fake fake;
  late MemoryStore store;
  late DateTime clock;
  late DictumCloud cloud;

  setUp(() {
    fake = Fake();
    store = MemoryStore();
    clock = DateTime(2026, 10, 17, 12);
    cloud = DictumCloud(
      url: 'https://x.supabase.co',
      key: 'pk',
      store: store,
      client: MockClient((r) => fake.handle(r)),
      now: () => clock,
    );
  });

  test('Anmeldung speichert das Refresh-Token sicher', () async {
    await cloud.signIn('a@b.de', 'geheim');
    expect(cloud.hasSession, isTrue);
    expect(store.token, 'refresh-0');
    final r = fake.last('/auth/v1/token');
    expect(r.headers['apikey'], 'pk');
    expect(jsonDecode(r.body), {'email': 'a@b.de', 'password': 'geheim'});
  });

  test('falsches Passwort wirft eine verständliche Ausnahme', () async {
    final bad = DictumCloud(
      url: 'https://x.supabase.co',
      key: 'pk',
      store: store,
      client: MockClient((_) async => http.Response('{"msg":"Invalid login credentials"}', 400)),
    );
    expect(() => bad.signIn('a@b.de', 'falsch'), throwsA(isA<CloudException>()));
    expect(bad.hasSession, isFalse);
  });

  test('restore meldet mit dem gespeicherten Token wieder an', () async {
    store.token = 'alt';
    expect(await cloud.restore(), isTrue);
    expect(jsonDecode(fake.last('/auth/v1/token').body), {'refresh_token': 'alt'});
    expect(store.token, 'refresh-1'); // das NEUE Token ersetzt das alte
  });

  test('restore ohne Token oder mit abgelehntem Token gibt false', () async {
    expect(await cloud.restore(), isFalse);
    store.token = 'ungueltig';
    final rejecting = DictumCloud(
      url: 'https://x.supabase.co',
      key: 'pk',
      store: store,
      client: MockClient((_) async => http.Response('invalid', 400)),
    );
    expect(await rejecting.restore(), isFalse);
    expect(store.token, isNull); // abgelehntes Token wird verworfen
  });

  test('restore ohne Netz behält das Token (später nochmal versuchen)', () async {
    store.token = 'alt';
    final offline = DictumCloud(
      url: 'https://x.supabase.co',
      key: 'pk',
      store: store,
      client: MockClient((_) async => throw http.ClientException('kein Netz')),
    );
    await expectLater(offline.restore(), throwsA(isA<http.ClientException>()));
    expect(store.token, 'alt');
  });

  test('Aufnahme mit fester ID anlegen ist wiederholbar (ignore-duplicates)', () async {
    await cloud.signIn('a@b.de', 'x');
    await cloud.createRecording(id: 'rec-1', template: 'interview', language: 'de');
    final r = fake.last('/rest/v1/recordings');
    expect(r.headers['Prefer'], contains('ignore-duplicates'));
    expect(r.headers['Authorization'], startsWith('Bearer access-password'));
    expect(jsonDecode(r.body), containsPair('id', 'rec-1'));
    expect(jsonDecode(r.body), containsPair('template', 'interview'));
  });

  test('Upload-Pfad beginnt mit der Nutzer-ID und trägt das Stück ein', () async {
    await cloud.signIn('a@b.de', 'x');
    await cloud.uploadChunk(recordingId: 'rec-1', idx: 2, bytes: Uint8List.fromList([1, 2]), durationSeconds: 299.5);
    final up = fake.last('/storage/v1/object/recordings/');
    expect(up.url.path, '/storage/v1/object/recordings/user-123/rec-1/2.ogg');
    expect(up.headers['Content-Type'], 'audio/ogg');
    expect(up.headers['x-upsert'], 'true');
    final row = jsonDecode(fake.last('/rest/v1/recording_chunks').body);
    expect(row, containsPair('storage_path', 'user-123/rec-1/2.ogg'));
    expect(row, containsPair('duration_seconds', 299.5));
  });

  test('finish ändert nur Aufnahmen im Status "uploading" und startet die Zusammenfassung', () async {
    await cloud.signIn('a@b.de', 'x');
    await cloud.finish('rec-1', 3, 842);
    final patch = fake.requests.firstWhere((r) => r.method == 'PATCH');
    expect(patch.url.query, 'id=eq.rec-1&status=eq.uploading');
    expect(jsonDecode(patch.body), containsPair('chunk_count', 3));
    expect(fake.last('/functions/v1/summarize').method, 'POST');
  });

  test('Token wird kurz vor Ablauf erneuert', () async {
    await cloud.signIn('a@b.de', 'x');
    clock = clock.add(const Duration(minutes: 59)); // < 2 Minuten bis zum Ablauf
    await cloud.transcribeChunk('rec-1', 0);
    expect(fake.refreshCount, 1);
    expect(fake.last('/functions/v1/transcribe').headers['Authorization'], 'Bearer access-refresh_token-1');
  });

  test('bei 401 wird einmal erneuert und wiederholt', () async {
    await cloud.signIn('a@b.de', 'x');
    fake.unauthorizedOnce = 1;
    await cloud.createRecording(id: 'rec-1', template: 'meeting', language: 'de');
    expect(fake.refreshCount, 1);
    expect(fake.requests.where((r) => r.url.path == '/rest/v1/recordings').length, 2);
  });

  test('bleibt es bei 401, gibt es eine Ausnahme statt einer Endlosschleife', () async {
    await cloud.signIn('a@b.de', 'x');
    fake.unauthorizedOnce = 5;
    await expectLater(
      cloud.createRecording(id: 'rec-1', template: 'meeting', language: 'de'),
      throwsA(isA<CloudException>().having((e) => e.isAuthError, 'isAuthError', isTrue)),
    );
  });

  test('ohne Anmeldung wird nichts gesendet', () async {
    await expectLater(cloud.createRecording(id: 'r', template: 'meeting', language: 'de'), throwsA(isA<CloudException>()));
    expect(fake.requests, isEmpty);
  });
}
