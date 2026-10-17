import 'dart:convert';
import 'dart:io';

import 'package:dictum_mobile/bridge/native_bridge.dart';
import 'package:dictum_mobile/services/cloud_client.dart';
import 'package:dictum_mobile/services/recording_controller.dart';
import 'package:dictum_mobile/services/upload_queue.dart';
import 'package:dictum_mobile/services/uploader.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

class FakeAuth implements AuthBackend {
  bool fail = false;
  Object? error;
  bool signedOut = false;
  @override
  bool hasSession = false;
  final calls = <String>[];

  @override
  Future<void> signIn(String email, String password) async {
    calls.add('$email|$password');
    if (error != null) throw error!;
    hasSession = true;
  }

  @override
  Future<void> signOut() async {
    signedOut = true;
    hasSession = false;
  }
}

void main() {
  group('parseBridgeMessage', () {
    test('gültige Nachrichten werden erkannt', () {
      expect(parseBridgeMessage('{"type":"record_stop"}'), isA<RecordStopMessage>());
      expect(parseBridgeMessage('{"type":"status"}'), isA<StatusMessage>());
      expect(parseBridgeMessage('{"type":"logout"}'), isA<LogoutMessage>());
      final start = parseBridgeMessage('{"type":"record_start","template":"lecture","language":"en"}') as RecordStartMessage;
      expect((start.template, start.language), ('lecture', 'en'));
      final login = parseBridgeMessage('{"type":"credentials","email":"a@b.de","password":"x"}') as CredentialsMessage;
      expect((login.email, login.password), ('a@b.de', 'x'));
    });

    test('record_start hat Standardwerte', () {
      final start = parseBridgeMessage('{"type":"record_start"}') as RecordStartMessage;
      expect((start.template, start.language), ('meeting', 'de'));
    });

    test('ungültiges wird ignoriert (null), statt etwas Unerwartetes auszuführen', () {
      for (final bad in [
        'kein json',
        '[]',
        '"text"',
        '{}',
        '{"type":"unbekannt"}',
        '{"type":42}',
        '{"type":"record_start","template":"ueberweisung"}',
        '{"type":"record_start","template":7}',
        '{"type":"record_start","language":"de; drop table"}',
        '{"type":"credentials","email":"a@b.de"}',
        '{"type":"credentials","email":"","password":"x"}',
        '{"type":"credentials","email":"a@b.de","password":${jsonEncode("x" * 300)}}',
      ]) {
        expect(parseBridgeMessage(bad), isNull, reason: bad);
      }
    });
  });

  group('eventScript', () {
    test('baut ein CustomEvent mit den Daten', () {
      final js = eventScript({'type': 'recording', 'state': 'recording', 'seconds': 3});
      expect(js, startsWith("window.dispatchEvent(new CustomEvent('dictum-native',{detail:"));
      expect(js, contains('"seconds":3'));
    });

    test('Text in den Daten kann nie als Code ausbrechen', () {
      final js = eventScript({'error': '"});alert(1);//'});
      expect(js, contains(r'\"});alert(1);//')); // Anführungszeichen maskiert
      expect(js.split('alert(1)').length - 1, 1); // steht nur als Text im String
    });
  });

  group('BridgeHandler', () {
    late Directory tmp;
    late FakeAuth auth;
    late FakeBackend backend;
    late Uploader uploader;
    late RecordingController controller;
    late List<Map<String, Object?>> out;
    late BridgeHandler handler;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('dictum_bridge_');
      final queue = UploadQueue(Directory('${tmp.path}/queue'));
      backend = FakeBackend();
      uploader = Uploader(queue: queue, backend: backend);
      auth = FakeAuth();
      controller = RecordingController(
        queue: queue,
        uploader: uploader,
        service: FakeService(),
        sourceFactory: FakeSource.new,
        workDir: Directory('${tmp.path}/work'),
        hasSession: () => auth.hasSession,
        chunkSeconds: 5,
      );
      out = [];
      handler = BridgeHandler(auth: auth, controller: controller, uploader: uploader, emit: out.add);
    });

    tearDown(() async {
      await controller.stop();
      uploader.dispose();
      await controller.dispose();
      await removeDir(tmp);
    });

    test('Anmeldedaten: Erfolg', () async {
      await handler.handle('{"type":"credentials","email":"a@b.de","password":"geheim"}');
      expect(auth.calls, ['a@b.de|geheim']);
      expect(out.last, {'type': 'auth', 'ok': true});
    });

    test('Anmeldedaten: falsches Passwort, Serverfehler und offline werden unterschieden', () async {
      auth.error = CloudException('x', status: 400);
      await handler.handle('{"type":"credentials","email":"a@b.de","password":"x"}');
      expect(out.last, {'type': 'auth', 'ok': false, 'error': 'invalid_credentials'});

      auth.error = CloudException('x', status: 500);
      await handler.handle('{"type":"credentials","email":"a@b.de","password":"x"}');
      expect(out.last['error'], 'failed');

      auth.error = const SocketException('kein Netz');
      await handler.handle('{"type":"credentials","email":"a@b.de","password":"x"}');
      expect(out.last['error'], 'offline');
    });

    test('Passwort taucht in keiner Antwort an die Web-App auf', () async {
      await handler.handle('{"type":"credentials","email":"a@b.de","password":"supergeheim"}');
      expect(jsonEncode(out), isNot(contains('supergeheim')));
    });

    test('Abmelden', () async {
      auth.hasSession = true;
      await handler.handle('{"type":"logout"}');
      expect(auth.signedOut, isTrue);
      expect(out.last['error'], 'logged_out');
    });

    test('Status meldet Anmeldung und Aufnahmezustand', () async {
      await handler.handle('{"type":"status"}');
      expect(out[0], {'type': 'auth', 'ok': false});
      expect(out[1]['type'], 'recording');
      expect(out[1]['state'], 'idle');
    });

    test('Ungültiges bleibt folgenlos', () async {
      await handler.handle('{"type":"record_start","template":"quatsch"}');
      await handler.handle('müll');
      expect(out, isEmpty);
      expect(controller.state, RecState.idle);
    });
  });
}
