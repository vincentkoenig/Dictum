// Speichert das Refresh-Token der App verschlüsselt.
//
// flutter_secure_storage legt Werte im **Android Keystore** ab: Der Schlüssel liegt in einem
// geschützten Bereich des Handys, den andere Apps nicht auslesen können. Gespeichert wird nur
// das Refresh-Token, nie das Passwort. Mit dem Token kann sich die App wieder anmelden,
// aber niemand kann daraus das Passwort ableiten.

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'cloud_client.dart';

class SecureSessionStore implements SessionStore {
  SecureSessionStore([FlutterSecureStorage? storage]) : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'dictum_refresh_token';
  final FlutterSecureStorage _storage;

  @override
  Future<String?> readRefreshToken() => _storage.read(key: _key);

  @override
  Future<void> writeRefreshToken(String token) => _storage.write(key: _key, value: token);

  @override
  Future<void> clear() => _storage.delete(key: _key);
}
