import 'package:app_flutter/api/models/metrics.dart';
import 'package:app_flutter/api/models/session.dart';
import 'package:app_flutter/features/project/project_providers.dart';
import 'package:app_flutter/screens/project/project_observability_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

void main() {
  testWidgets('lists every chat and narrows totals to the chat you pick', (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final requested = <String?>[];
    ProjectObservability obs(String? conv) => ProjectObservability(
          sessionId: 'sess_1',
          conversationId: conv,
          totals: ChatLatencyStats(queries: conv == null ? 3 : 1, avgTotalMs: 1500),
          conversations: const [
            ConversationStats(conversationId: 'c1', title: 'Margins', stats: ChatLatencyStats(queries: 2, avgTotalMs: 800)),
            ConversationStats(conversationId: 'c2', title: 'Risk', stats: ChatLatencyStats(queries: 1, refusals: 1)),
          ],
        );

    final router = GoRouter(initialLocation: '/w/ws/p/sess_1/observability', routes: [
      GoRoute(
        path: '/w/:ws/p/:project/observability',
        builder: (_, s) => ProjectObservabilityScreen(workspaceId: 'ws', projectId: 'sess_1'),
      ),
    ]);
    await tester.pumpWidget(ProviderScope(
      overrides: [
        projectObservabilityProvider.overrideWith((ref, scope) async {
          requested.add(scope.conversationId);
          return obs(scope.conversationId);
        }),
        projectProvider.overrideWith((ref, id) async => const ChatSession(id: 'sess_1', title: 'P')),
        projectConversationsProvider.overrideWith((ref, id) async => [
              Conversation(id: 'c1', sessionId: 'sess_1', title: 'Margins'),
              Conversation(id: 'c2', sessionId: 'sess_1', title: 'Risk'),
            ]),
      ],
      child: MaterialApp.router(routerConfig: router),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Observability — all chats'), findsOneWidget);
    expect(find.text('Margins'), findsWidgets);
    expect(find.text('Risk'), findsWidgets);
    expect(find.text('No queries yet. Ask something in a chat to see it here.'), findsOneWidget);

    await tester.tap(find.text('Risk').last);
    await tester.pumpAndSettle();
    expect(find.text('Observability — this chat'), findsOneWidget);
    expect(requested, [null, 'c2']);
  });
}
