// Die Brücke zwischen der Web-App (in der WebView) und dem nativen Teil der App.
//
// Die Web-App ist die Oberfläche, der native Teil macht, was ein Browser nicht kann: im
// Hintergrund aufnehmen. Beide sprechen über zwei einfache Wege miteinander:
//
//   Web → nativ   `DictumNative.postMessage('{"type":"record_start", …}')`
//                 (webview_flutter stellt der Seite ein Objekt dieses Namens bereit)
//   nativ → Web   ein JavaScript-Ereignis `dictum-native` auf `window`,
//                 dessen `detail` die Nachricht ist
//
// Nachrichten sind JSON mit einem Feld "type". Alles Eingehende gilt als **nicht vertrauenswürdig**
// und wird geprüft: unbekannte Typen, falsche Datentypen oder unzulässige Werte werden
// ignoriert (`parseBridgeMessage` gibt dann null zurück).
//
// Sicherheit: Die Brücke steht nur Seiten zur Verfügung, die die WebView laden darf (config.dart:
// `allowedHost`). Jede Navigation zu einem anderen Host wird blockiert.
//
// Web → nativ:
//   credentials   {email, password}      Anmeldedaten übergeben (siehe unten)
//   logout
//   record_start  {template, language}   Aufnahme starten
//   record_pause / record_resume / record_stop
//   status                               aktuellen Zustand erfragen
//
// nativ → Web:
//   {type: "auth",      ok, error?}
//   {type: "recording", state, recordingId, seconds, chunks, pending, error?}
//
// Warum bekommt der native Teil die Anmeldedaten und nicht das Token der Web-App?
// Siehe services/cloud_client.dart: Zwei Nutzer desselben Refresh-Tokens würden sich gegenseitig
// die Sitzung entziehen. Deshalb meldet sich der native Teil mit den Daten, die der Nutzer
// gerade in der Web-App eingegeben hat, selbst an und speichert nur sein eigenes Token (nie das
// Passwort).

import 'dart:async';
import 'dart:convert';

import '../services/cloud_client.dart';
import '../services/recording_controller.dart';
import '../services/uploader.dart';

sealed class BridgeMessage {
  const BridgeMessage();
}

final class CredentialsMessage extends BridgeMessage {
  const CredentialsMessage(this.email, this.password);

  final String email;
  final String password;
}

final class LogoutMessage extends BridgeMessage {
  const LogoutMessage();
}

final class RecordStartMessage extends BridgeMessage {
  const RecordStartMessage(this.template, this.language);

  final String template;
  final String language;
}

final class RecordPauseMessage extends BridgeMessage {
  const RecordPauseMessage();
}

final class RecordResumeMessage extends BridgeMessage {
  const RecordResumeMessage();
}

final class RecordStopMessage extends BridgeMessage {
  const RecordStopMessage();
}

final class StatusMessage extends BridgeMessage {
  const StatusMessage();
}

const validTemplates = {'meeting', 'interview', 'lecture', 'note'};
final _languagePattern = RegExp(r'^(auto|[a-z]{2,3})$');

/// Prüft eine Nachricht aus der WebView. Null = ungültig, wird ignoriert.
BridgeMessage? parseBridgeMessage(String raw) {
  try {
    final data = jsonDecode(raw);
    if (data is! Map<String, dynamic>) return null;
    switch (data['type']) {
      case 'credentials':
        final email = data['email'];
        final password = data['password'];
        if (email is! String || password is! String) return null;
        if (email.isEmpty || email.length > 320 || password.isEmpty || password.length > 256) return null;
        return CredentialsMessage(email, password);
      case 'logout':
        return const LogoutMessage();
      case 'record_start':
        final template = data['template'] ?? 'meeting';
        final language = data['language'] ?? 'de';
        if (template is! String || !validTemplates.contains(template)) return null;
        if (language is! String || !_languagePattern.hasMatch(language)) return null;
        return RecordStartMessage(template, language);
      case 'record_pause':
        return const RecordPauseMessage();
      case 'record_resume':
        return const RecordResumeMessage();
      case 'record_stop':
        return const RecordStopMessage();
      case 'status':
        return const StatusMessage();
    }
  } catch (_) {
    // kein gültiges JSON
  }
  return null;
}

/// JavaScript, das ein Ereignis an die Web-App schickt. `jsonEncode` macht aus dem Wert ein
/// korrekt maskiertes JavaScript-Literal, so kann in der Nachricht enthaltener Text nie als
/// Code ausgeführt werden.
String eventScript(Map<String, Object?> event) =>
    "window.dispatchEvent(new CustomEvent('dictum-native',{detail:${jsonEncode(event)}}));";

/// Setzt eingehende Nachrichten in Aktionen um.
class BridgeHandler {
  BridgeHandler({required this.auth, required this.controller, required this.uploader, required this.emit});

  final AuthBackend auth;
  final RecordingController controller;
  final Uploader uploader;
  final void Function(Map<String, Object?> event) emit;

  Future<void> handle(String raw) async {
    final message = parseBridgeMessage(raw);
    if (message == null) return;
    switch (message) {
      case CredentialsMessage(:final email, :final password):
        await _signIn(email, password);
      case LogoutMessage():
        await auth.signOut();
        emit({'type': 'auth', 'ok': false, 'error': 'logged_out'});
      case RecordStartMessage(:final template, :final language):
        await controller.start(template: template, language: language);
      case RecordPauseMessage():
        await controller.pause();
      case RecordResumeMessage():
        await controller.resume();
      case RecordStopMessage():
        await controller.stop();
      case StatusMessage():
        emit({'type': 'auth', 'ok': auth.hasSession});
        emit(controller.status());
    }
  }

  Future<void> _signIn(String email, String password) async {
    try {
      await auth.signIn(email, password);
      emit({'type': 'auth', 'ok': true});
      unawaited(uploader.kick()); // evtl. wartet schon etwas auf die Anmeldung
    } on CloudException catch (e) {
      emit({'type': 'auth', 'ok': false, 'error': e.status == 400 ? 'invalid_credentials' : 'failed'});
    } catch (_) {
      emit({'type': 'auth', 'ok': false, 'error': 'offline'});
    }
  }
}
