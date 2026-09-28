import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_provider.dart';
import 'package:app_flutter/api/auth_storage.dart';
import 'package:flutter_test/flutter_test.dart';

import 'auth_storage_test.dart' show InMemorySecureStore;

/// IRA-51 acceptance criterion: "Sign out clears the jar." `AuthNotifier.clear()` used to only
/// flip the in-memory state, leaving a stale `ri_auth` cookie in `flutter_secure_storage` that a
/// later sign-in on mobile would never overwrite until the next `Set-Cookie` — this pins the fix.
void main() {
  test('AuthNotifier.clear() wipes the mobile cookie jar, not just in-memory state', () async {
    final backing = InMemorySecureStore();
    final authStorage = AuthStorage(storage: backing);
    await authStorage.saveCookie('ri_auth=stale-session');

    final notifier = AuthNotifier(ApiClient(baseUrl: 'http://unused.invalid'), authStorage);
    expect(await authStorage.readCookie(), 'ri_auth=stale-session');

    await notifier.clear();

    expect(notifier.state, isA<AuthSignedOut>());
    expect(await AuthStorage(storage: backing).readCookie(), isNull);
  });

  test('AuthNotifier without an AuthStorage still clears state (web has no jar)', () async {
    final notifier = AuthNotifier(ApiClient(baseUrl: 'http://unused.invalid'));
    await notifier.clear();
    expect(notifier.state, isA<AuthSignedOut>());
  });
}
