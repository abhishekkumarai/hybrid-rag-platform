import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/models/metrics.dart';
import 'package:app_flutter/api/models/session.dart';
import 'package:app_flutter/features/chat/chat_providers.dart';
import 'package:app_flutter/features/project/project_providers.dart';
import 'package:app_flutter/features/workspace/workspace_providers.dart';
import 'package:app_flutter/screens/project/chat/chat_sessions_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

class _FakeChat extends ChatController {
  _FakeChat() : super(ApiClient(baseUrl: 'http://unused.invalid'), 'sess_1', 'c1');
  final sent = <({String query, String? mode, String? model})>[];

  @override
  Future<void> loadHistory() async {}

  @override
  Future<void> send(String query, {String? mode, String? model}) async => sent.add((query: query, mode: mode, model: model));
}

void main() {
  late _FakeChat chat;

  Future<void> pump(WidgetTester tester, {required bool ollamaAlive}) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    chat = _FakeChat();
    final router = GoRouter(initialLocation: '/w/ws/p/sess_1/chats/c1', routes: [
      GoRoute(
        path: '/w/:ws/p/:project/chats/:chat',
        builder: (_, s) => const ChatSessionsScreen(workspaceId: 'ws', projectId: 'sess_1', conversationId: 'c1'),
      ),
    ]);
    await tester.pumpWidget(ProviderScope(
      overrides: [
        chatControllerProvider.overrideWith((ref, key) => chat),
        liveServiceHealthProvider.overrideWith(
            (ref) => Stream.value(ServiceHealth(qdrantAlive: true, redisAlive: true, ollamaAlive: ollamaAlive))),
        projectProvider.overrideWith((ref, id) async => const ChatSession(
              id: 'sess_1',
              title: 'P',
              parameters: SessionParameters(model: 'llama3.1:latest', retrievalMode: 'graph'),
            )),
        projectConversationsProvider.overrideWith((ref, id) async => [Conversation(id: 'c1', sessionId: 'sess_1', title: 'Chat')]),
        modelsProvider.overrideWith((ref) async => const ModelListResponse(
              models: [ModelInfo(name: 'llama3.2:3b'), ModelInfo(name: 'llama3.1:latest')],
              defaultModel: 'llama3.2:3b',
              ollamaAlive: true,
            )),
      ],
      child: MaterialApp.router(routerConfig: router),
    ));
    await tester.pumpAndSettle();
  }

  Finder composer() => find.byWidgetPredicate((w) => w is TextField && (w.decoration?.hintText ?? '').contains('Ask a question'));

  testWidgets('Enter sends, Shift+Enter adds a newline, project settings are not overridden', (tester) async {
    await pump(tester, ollamaAlive: true);
    // The pickers show the project's own mode and model, not hardcoded defaults.
    expect(find.text('Graph'), findsOneWidget);
    expect(find.text('llama3.1:latest'), findsOneWidget);

    await tester.tap(composer());
    await tester.enterText(composer(), 'first line');
    await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
    await tester.pump();
    expect(chat.sent, isEmpty);

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(chat.sent, hasLength(1));
    expect(chat.sent.single.query, 'first line');
    expect(chat.sent.single.mode, isNull); // gateway applies the project's mode
    expect(chat.sent.single.model, isNull);
  });

  testWidgets('chat is disabled with a banner while Ollama is down', (tester) async {
    await pump(tester, ollamaAlive: false);
    expect(find.textContaining('Ollama is not running'), findsOneWidget);
    final field = tester.widget<TextField>(
      find.byWidgetPredicate((w) => w is TextField && (w.decoration?.hintText ?? '').contains('paused')),
    );
    expect(field.enabled, isFalse);
    final send = tester.widget<IconButton>(
      find.ancestor(of: find.byTooltip('Ollama is not running'), matching: find.byType(IconButton)).first,
    );
    expect(send.onPressed, isNull);
  });
}
