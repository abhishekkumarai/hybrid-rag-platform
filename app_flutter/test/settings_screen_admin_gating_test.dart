import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_provider.dart';
import 'package:app_flutter/api/models/identity.dart';
import 'package:app_flutter/screens/settings/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Covers the Settings screen's admin-gated Danger zone (IRA-50) — the piece of client-only
/// logic worth a widget test, versus appearance controls already exercised via [appearanceProvider].
void main() {
  Widget testApp(User user) => ProviderScope(
    overrides: [
      authProvider.overrideWith((ref) => _FakeAuthNotifier(AuthSignedIn(user))),
    ],
    child: const MaterialApp(home: SettingsScreen()),
  );

  testWidgets('Danger zone is hidden for a non-admin user', (tester) async {
    await tester.pumpWidget(
      testApp(const User(id: 'u1', email: 'u1@x.com', isAdmin: false)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Danger zone'), findsNothing);
    expect(find.text('Purge dead-letter queue'), findsNothing);
  });

  testWidgets('Danger zone is shown for an admin user', (tester) async {
    await tester.pumpWidget(
      testApp(const User(id: 'admin1', email: 'admin@x.com', isAdmin: true)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Danger zone'), findsOneWidget);
    expect(find.text('Purge dead-letter queue'), findsOneWidget);
  });
}

class _FakeAuthNotifier extends AuthNotifier {
  _FakeAuthNotifier(AuthState initial)
    : super(ApiClient(baseUrl: 'http://unused.invalid')) {
    state = initial;
  }
}
