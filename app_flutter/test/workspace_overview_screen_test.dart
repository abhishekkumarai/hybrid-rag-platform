import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_provider.dart';
import 'package:app_flutter/api/models/identity.dart';
import 'package:app_flutter/api/models/metrics.dart';
import 'package:app_flutter/api/models/session.dart';
import 'package:app_flutter/features/workspace/workspace_providers.dart';
import 'package:app_flutter/screens/workspace/workspace_overview_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Covers the workspace Overview screen's All / Mine / Forked project filter (IRA-48) — the
/// piece of client-only logic on this screen worth a widget test, versus the many read-only
/// panels that are just JSON render passthroughs covered by the model round-trip tests.
void main() {
  final projects = [
    const ChatSession(id: 'p1', title: 'Mine, not forked', ownerId: 'me'),
    const ChatSession(id: 'p2', title: 'Someone else', ownerId: 'them'),
    const ChatSession(id: 'p3', title: 'Forked by me', ownerId: 'me', forkedFrom: 'p1'),
  ];

  Widget testApp() => ProviderScope(
        overrides: [
          authProvider.overrideWith(
            (ref) => _FakeAuthNotifier(const AuthSignedIn(User(id: 'me', email: 'me@x.com'))),
          ),
          workspaceProjectsProvider.overrideWith((ref, workspaceId) async => projects),
          workspaceMetricsProvider.overrideWith((ref, sessionId) async => const SystemMetrics()),
        ],
        child: const MaterialApp(home: WorkspaceOverviewScreen(workspaceId: 'ws1')),
      );

  testWidgets('All shows every project; Mine and Forked narrow the list', (tester) async {
    await tester.pumpWidget(testApp());
    await tester.pumpAndSettle();

    expect(find.text('Mine, not forked'), findsOneWidget);
    expect(find.text('Someone else'), findsOneWidget);
    expect(find.text('Forked by me'), findsOneWidget);

    await tester.tap(find.widgetWithText(ChoiceChip, 'Mine'));
    await tester.pumpAndSettle();
    expect(find.text('Mine, not forked'), findsOneWidget);
    expect(find.text('Forked by me'), findsOneWidget);
    expect(find.text('Someone else'), findsNothing);

    await tester.tap(find.widgetWithText(ChoiceChip, 'Forked'));
    await tester.pumpAndSettle();
    expect(find.text('Forked by me'), findsOneWidget);
    expect(find.text('Mine, not forked'), findsNothing);
    expect(find.text('Someone else'), findsNothing);

    await tester.tap(find.widgetWithText(ChoiceChip, 'All'));
    await tester.pumpAndSettle();
    expect(find.text('Mine, not forked'), findsOneWidget);
    expect(find.text('Someone else'), findsOneWidget);
    expect(find.text('Forked by me'), findsOneWidget);
  });

  testWidgets('selecting projects reveals a bulk-delete action with the count', (tester) async {
    await tester.pumpWidget(testApp());
    await tester.pumpAndSettle();

    expect(find.textContaining('Delete'), findsNothing);

    await tester.tap(find.byType(Checkbox).first);
    await tester.pumpAndSettle();
    expect(find.text('Delete 1'), findsOneWidget);

    await tester.tap(find.byType(Checkbox).at(1));
    await tester.pumpAndSettle();
    expect(find.text('Delete 2'), findsOneWidget);
  });

  testWidgets('the search box narrows the project list by title', (tester) async {
    await tester.pumpWidget(testApp());
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'by me');
    await tester.pumpAndSettle();

    expect(find.text('Forked by me'), findsOneWidget);
    expect(find.text('Mine, not forked'), findsNothing);
    expect(find.text('Someone else'), findsNothing);
  });

  testWidgets('Recent activity renders answered and refused telemetry rows', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authProvider.overrideWith(
            (ref) => _FakeAuthNotifier(const AuthSignedIn(User(id: 'me', email: 'me@x.com'))),
          ),
          workspaceProjectsProvider.overrideWith((ref, workspaceId) async => projects),
          workspaceMetricsProvider.overrideWith(
            (ref, sessionId) async => const SystemMetrics(
              recentTelemetry: [
                QueryTelemetry(queryId: 'q1', queryText: 'What is the FY24 margin?', citationsCount: 2, timestamp: 2),
                QueryTelemetry(queryId: 'q2', queryText: 'FY25 guidance?', refused: true, timestamp: 1),
              ],
            ),
          ),
        ],
        child: const MaterialApp(home: WorkspaceOverviewScreen(workspaceId: 'ws1')),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('What is the FY24 margin?'), findsOneWidget);
    expect(find.text('Answered from 2 citations'), findsOneWidget);
    expect(find.text('FY25 guidance?'), findsOneWidget);
    expect(find.text('Refused — not in sources'), findsOneWidget);
  });
}

/// The screen never calls a login/logout method here, so the wrapped `ApiClient` is never used —
/// only the pre-seeded `AuthSignedIn` state matters.
class _FakeAuthNotifier extends AuthNotifier {
  _FakeAuthNotifier(AuthState initial) : super(ApiClient(baseUrl: 'http://unused.invalid')) {
    state = initial;
  }
}
