import 'package:app_flutter/api/auth_storage.dart';
import 'package:flutter_test/flutter_test.dart';

class InMemorySecureStore implements SecureKeyValueStore {
  final Map<String, String> _map = {};

  @override
  Future<String?> read({required String key}) async => _map[key];

  @override
  Future<void> write({required String key, required String value}) async => _map[key] = value;

  @override
  Future<void> delete({required String key}) async => _map.remove(key);
}

void main() {
  group('AuthStorage.cookiePairFrom', () {
    test('extracts ri_auth pair from a full Set-Cookie header', () {
      final pair = AuthStorage.cookiePairFrom(
        'ri_auth=abc123def; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800',
      );
      expect(pair, 'ri_auth=abc123def');
    });

    test('returns null when the header has no ri_auth cookie', () {
      final pair = AuthStorage.cookiePairFrom('other_cookie=xyz; Path=/');
      expect(pair, isNull);
    });

    test('returns null for a null header', () {
      expect(AuthStorage.cookiePairFrom(null), isNull);
    });
  });

  group('AuthStorage cookie jar', () {
    test('save then read returns the same cookie value', () async {
      final storage = AuthStorage(storage: InMemorySecureStore());
      await storage.saveCookie('ri_auth=cached-value');
      expect(await storage.readCookie(), 'ri_auth=cached-value');
    });

    test('clear removes the cookie', () async {
      final storage = AuthStorage(storage: InMemorySecureStore());
      await storage.saveCookie('ri_auth=x');
      await storage.clear();
      expect(await storage.readCookie(), isNull);
    });

    test('readCookie falls back to the underlying store after process restart (no cache)', () async {
      final backing = InMemorySecureStore();
      await AuthStorage(storage: backing).saveCookie('ri_auth=persisted');
      final freshInstance = AuthStorage(storage: backing);
      expect(await freshInstance.readCookie(), 'ri_auth=persisted');
    });
  });
}
