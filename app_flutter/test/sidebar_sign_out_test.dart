import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_provider.dart';
import 'package:app_flutter/api/models/identity.dart';
import 'package:app_flutter/api/models/metrics.dart';
import 'package:app_flutter/api/models/session.dart';
import 'package:app_flutter/features/workspace/workspace_providers.dart';
import 'package:app_flutter/shell/sidebar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

class _FakeAuth extends AuthNotifier {
  _FakeAuth(User user) : super(ApiClient(baseUrl: 'http://unused.invalid')) {
    state = AuthSignedIn(user);
  }
  var loggedOut = false;
  @override
  Future<void> logout() async {
    loggedOut = true;
    state = const AuthSignedOut();
  }
}

void main() {
  Future<_FakeAuth> pumpSidebar(WidgetTester tester, {required double height, int projects = 30}) async {
    tester.view.physicalSize = Size(1400, height);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final auth = _FakeAuth(const User(id: 'u1', email: 'someone-with-a-long-address@example.com'));
    final router = GoRouter(initialLocation: '/w/ws1', routes: [
      GoRoute(path: '/w/:ws', builder: (_, _) => const Scaffold(body: Row(children: [AppSidebar(workspaceId: 'ws1')]))),
    ]);
    await tester.pumpWidget(ProviderScope(
      overrides: [
        authProvider.overrideWith((ref) => auth),
        workspaceProjectsProvider.overrideWith((ref, ws) async =>
            [for (var i = 0; i < projects; i++) ChatSession(id: 's$i', title: 'Project $i')]),
        workspacesProvider.overrideWith((ref) async => const <Workspace>[]),
        serviceHealthProvider.overrideWith((ref) async => const ServiceHealth()),
      ],
      child: MaterialApp.router(routerConfig: router),
    ));
    await tester.pumpAndSettle();
    return auth;
  }

  testWidgets('sign out stays on screen in a short window with many projects', (tester) async {
    await pumpSidebar(tester, height: 560);
    final button = find.byTooltip('Sign out');
    expect(button, findsOneWidget);
    final rect = tester.getRect(button);
    expect(rect.bottom, lessThanOrEqualTo(560));
    expect(rect.top, greaterThanOrEqualTo(0));
    expect(button.hitTestable(), findsOneWidget);
  });

  testWidgets('tapping sign out asks to confirm, then logs out', (tester) async {
    final auth = await pumpSidebar(tester, height: 800, projects: 2);
    await tester.tap(find.byTooltip('Sign out'));
    await tester.pumpAndSettle();
    expect(find.text('Sign out?'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Sign out'));
    await tester.pumpAndSettle();
    expect(auth.loggedOut, isTrue);
  });
}
