import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_provider.dart';
import 'package:app_flutter/api/auth_storage.dart';
import 'package:app_flutter/api/models/identity.dart';
import 'package:app_flutter/features/workspace/workspace_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _InMemorySecureStore implements SecureKeyValueStore {
  final Map<String, String> map = {};
  @override
  Future<String?> read({required String key}) async => map[key];
  @override
  Future<void> write({required String key, required String value}) async => map[key] = value;
  @override
  Future<void> delete({required String key}) async => map.remove(key);
}

class _SwitchableAuth extends AuthNotifier {
  _SwitchableAuth() : super(ApiClient(baseUrl: 'http://unused.invalid'));
  void set(AuthState s) => state = s;
}

const _ana = User(id: 'usr_ana', email: 'ana@x.com');
const _ben = User(id: 'usr_ben', email: 'ben@x.com');

void main() {
  test('switching users rebuilds the data client and resets the workspace', () {
    final auth = _SwitchableAuth();
    final container = ProviderContainer(overrides: [authProvider.overrideWith((ref) => auth)]);
    addTearDown(container.dispose);

    auth.set(const AuthSignedIn(_ana));
    final anaClient = container.read(userApiClientProvider);
    container.read(currentWorkspaceIdProvider.notifier).state = 'ws_ana';
    expect(container.read(currentWorkspaceIdProvider), 'ws_ana');

    auth.set(const AuthSignedOut());
    expect(container.read(currentUserIdProvider), isNull);
    auth.set(const AuthSignedIn(_ben));

    expect(identical(container.read(userApiClientProvider), anaClient), isFalse);
    expect(container.read(currentWorkspaceIdProvider), 'default');
  });

  test('providers built on the data client drop the previous user\'s cached data', () async {
    final auth = _SwitchableAuth();
    var builds = 0;
    final probe = FutureProvider<int>((ref) async {
      ref.watch(userApiClientProvider);
      return ++builds;
    });
    final container = ProviderContainer(overrides: [authProvider.overrideWith((ref) => auth)]);
    addTearDown(container.dispose);
    container.read(authProvider);
    auth.set(const AuthSignedIn(_ana));
    container.listen(probe, (_, _) {});

    expect(await container.read(probe.future), 1);
    auth.set(const AuthSignedIn(_ben));
    expect(await container.read(probe.future), 2);
  });

  test('logout clears the session locally even when the gateway is unreachable', () async {
    final store = _InMemorySecureStore();
    final storage = AuthStorage(storage: store);
    await storage.saveCookie('ri_auth=abc');
    final client = ApiClient(
      baseUrl: 'http://gateway.test',
      authStorage: storage,
      httpClient: MockClient((_) async => throw http.ClientException('connection refused')),
    );
    final notifier = AuthNotifier(client, storage)..state = const AuthSignedIn(_ana);

    await notifier.logout();

    expect(notifier.state, isA<AuthSignedOut>());
    expect(await storage.readCookie(), isNull);
  });
}
