import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Minimal key-value store `AuthStorage` depends on, so tests can inject an in-memory fake
/// instead of going through the real platform channel (unavailable outside a device/emulator).
abstract class SecureKeyValueStore {
  Future<String?> read({required String key});
  Future<void> write({required String key, required String value});
  Future<void> delete({required String key});
}

class FlutterSecureKeyValueStore implements SecureKeyValueStore {
  const FlutterSecureKeyValueStore([this._delegate = const FlutterSecureStorage()]);
  final FlutterSecureStorage _delegate;

  @override
  Future<String?> read({required String key}) => _delegate.read(key: key);

  @override
  Future<void> write({required String key, required String value}) => _delegate.write(key: key, value: value);

  @override
  Future<void> delete({required String key}) => _delegate.delete(key: key);
}

/// The `ri_auth` cookie jar (see services/identity/auth.py::AUTH_COOKIE).
///
/// On web the browser owns the cookie via `Set-Cookie` + same-origin credentials, so this
/// storage is unused there. On mobile/desktop there's no cookie jar, so the gateway's
/// `Set-Cookie: ri_auth=...` value is captured manually and replayed as a `Cookie` header
/// (plus `X-RI-Client: web`) on every request.
class AuthStorage {
  AuthStorage({SecureKeyValueStore? storage}) : _storage = storage ?? const FlutterSecureKeyValueStore();

  final SecureKeyValueStore _storage;
  static const _cookieKey = 'ri_auth_cookie';
  static const _serverUrlKey = 'server_url';

  String? _cachedCookie;

  Future<String?> readCookie() async {
    if (kIsWeb) return null;
    return _cachedCookie ??= await _storage.read(key: _cookieKey);
  }

  Future<void> saveCookie(String cookieValue) async {
    if (kIsWeb) return;
    _cachedCookie = cookieValue;
    await _storage.write(key: _cookieKey, value: cookieValue);
  }

  Future<void> clear() async {
    _cachedCookie = null;
    if (kIsWeb) return;
    await _storage.delete(key: _cookieKey);
  }

  Future<String?> readServerUrl() => _storage.read(key: _serverUrlKey);

  Future<void> saveServerUrl(String url) => _storage.write(key: _serverUrlKey, value: url);

  /// Extracts the `ri_auth=...` pair from a raw `Set-Cookie` response header.
  static String? cookiePairFrom(String? setCookieHeader) {
    if (setCookieHeader == null) return null;
    final match = RegExp(r'ri_auth=[^;]+').firstMatch(setCookieHeader);
    return match?.group(0);
  }
}
