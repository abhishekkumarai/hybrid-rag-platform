import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_provider.dart';
import 'package:app_flutter/api/auth_storage.dart';
import 'package:app_flutter/api/models/identity.dart';
import 'package:app_flutter/screens/settings/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'auth_storage_test.dart' show InMemorySecureStore;

/// IRA-51: the Settings > Server section persists a mobile/desktop gateway URL through
/// [AuthStorage.saveServerUrl] and updates [serverUrlProvider] so the next `ApiClient` build
/// picks it up immediately, without waiting for an app restart.
void main() {
  testWidgets('editing and saving the server URL persists it and updates the provider', (tester) async {
    final backing = InMemorySecureStore();
    final container = ProviderContainer(
      overrides: [
        authProvider.overrideWith((ref) => _FakeAuthNotifier(const AuthSignedIn(User(id: 'u1', email: 'u1@x.com')))),
        authStorageProvider.overrideWithValue(AuthStorage(storage: backing)),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(container: container, child: const MaterialApp(home: SettingsScreen())),
    );
    await tester.pumpAndSettle();

    expect(find.text('Server'), findsOneWidget);

    await tester.enterText(find.byType(TextField).first, 'http://10.0.2.2:8000');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(container.read(serverUrlProvider), 'http://10.0.2.2:8000');
    expect(await AuthStorage(storage: backing).readServerUrl(), 'http://10.0.2.2:8000');
    expect(find.text('Server URL saved.'), findsOneWidget);
  });
}

class _FakeAuthNotifier extends AuthNotifier {
  _FakeAuthNotifier(AuthState initial) : super(ApiClient(baseUrl: 'http://unused.invalid')) {
    state = initial;
  }
}
