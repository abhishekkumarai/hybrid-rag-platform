import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api_client.dart';
import 'auth_storage.dart';
import 'models/identity.dart';

/// The gateway base URL. Overridable at runtime on mobile/desktop via the Settings > Server
/// screen (IRA-51), persisted through [AuthStorage.saveServerUrl] and reloaded on startup by
/// `main.dart`; web always talks to its own origin and never reads a saved override — so its
/// default must resolve to that origin too, not a dev-only localhost:8000 guess, or every
/// request 404s/CORS-fails against a gateway that isn't actually listening there.
final serverUrlProvider = StateProvider<String>((ref) => kIsWeb ? Uri.base.origin : 'http://localhost:8000');

final authStorageProvider = Provider<AuthStorage>((ref) => AuthStorage());

final Provider<ApiClient> apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient(baseUrl: ref.watch(serverUrlProvider), authStorage: ref.watch(authStorageProvider));
  client.onUnauthorized = () => ref.read(authProvider.notifier).clear();
  ref.onDispose(client.close);
  return client;
});

// authProvider is declared with an explicit generic below to break the provider cycle: an
// ApiClient calls back into AuthNotifier.clear() on a 401, and AuthNotifier itself needs an
// ApiClient to make requests.

sealed class AuthState {
  const AuthState();
}

class AuthUnknown extends AuthState {
  const AuthUnknown();
}

class AuthSignedOut extends AuthState {
  const AuthSignedOut();
}

class AuthSignedIn extends AuthState {
  final User user;
  const AuthSignedIn(this.user);
}

class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier(this._client, [this._authStorage]) : super(const AuthUnknown());

  final ApiClient _client;
  final AuthStorage? _authStorage;

  Future<void> checkSession() async {
    try {
      final json = await _client.get('/api/v1/auth/me');
      state = AuthSignedIn(User.fromJson((json as Map<String, dynamic>)['user'] as Map<String, dynamic>));
    } on ApiException {
      state = const AuthSignedOut();
    }
  }

  Future<void> login(String email, String password) async {
    final json = await _client.post('/api/v1/auth/login', body: {'email': email, 'password': password});
    state = AuthSignedIn(User.fromJson((json as Map<String, dynamic>)['user'] as Map<String, dynamic>));
  }

  Future<void> signup(String email, String password, String displayName) async {
    final json = await _client.post('/api/v1/auth/signup',
        body: {'email': email, 'password': password, 'display_name': displayName});
    state = AuthSignedIn(User.fromJson((json as Map<String, dynamic>)['user'] as Map<String, dynamic>));
  }

  Future<void> startDemo() async {
    final json = await _client.post('/api/v1/auth/demo');
    state = AuthSignedIn(User.fromJson((json as Map<String, dynamic>)['user'] as Map<String, dynamic>));
  }

  Future<void> logout() async {
    try {
      await _client.post('/api/v1/auth/logout');
    } catch (_) {
      // Already signed out server-side, or the gateway is unreachable — sign out locally anyway.
    }
    await clear();
  }

  /// Clears the mobile cookie jar (a no-op on web, where the browser owns the cookie) — on both
  /// an explicit sign-out and a 401-triggered forced sign-out, a stale `ri_auth` must never be
  /// replayed against a fresh sign-in.
  Future<void> clear() async {
    await _authStorage?.clear();
    state = const AuthSignedOut();
  }
}

final StateNotifierProvider<AuthNotifier, AuthState> authProvider = StateNotifierProvider<AuthNotifier, AuthState>(
  (ref) => AuthNotifier(ref.watch(apiClientProvider), ref.watch(authStorageProvider)),
);

/// The signed-in user's id, or null while signed out / still checking.
final currentUserIdProvider = Provider<String?>((ref) {
  final auth = ref.watch(authProvider);
  return auth is AuthSignedIn ? auth.user.id : null;
});

/// The client every data provider uses. It is a new instance per signed-in user, so signing out
/// or switching accounts rebuilds every provider that watches it — nothing cached for one user
/// (projects, documents, metrics…) can be shown to the next. [authProvider] keeps using
/// [apiClientProvider] to avoid a dependency cycle.
final userApiClientProvider = Provider<ApiClient>((ref) {
  ref.watch(currentUserIdProvider);
  final client = ApiClient(baseUrl: ref.watch(serverUrlProvider), authStorage: ref.watch(authStorageProvider));
  client.onUnauthorized = () => ref.read(authProvider.notifier).clear();
  ref.onDispose(client.close);
  return client;
});
