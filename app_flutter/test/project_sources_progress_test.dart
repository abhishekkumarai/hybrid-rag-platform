import 'dart:convert';

import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_storage.dart';
import 'package:app_flutter/api/models/document.dart';
import 'package:app_flutter/api/models/session.dart';
import 'package:app_flutter/features/project/project_providers.dart';
import 'package:app_flutter/features/workspace/workspace_providers.dart';
import 'package:app_flutter/screens/project/project_sources_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _Store implements SecureKeyValueStore {
  final _m = <String, String>{};
  @override
  Future<String?> read({required String key}) async => _m[key];
  @override
  Future<void> write({required String key, required String value}) async => _m[key] = value;
  @override
  Future<void> delete({required String key}) async => _m.remove(key);
}

/// A gateway whose upload job stays "Parsing" forever, like a big scan.
ApiClient _gateway() {
  const job = {
    'id': 'job_1', 'session_id': 'sess_1', 'kind': 'file', 'source': 'scan.pdf',
    'status': 'running', 'stage': 'Parsing', 'created_at': 1.0, 'updated_at': 1.0,
  };
  http.Response ok(Object b) => http.Response(jsonEncode(b), 200, headers: {'content-type': 'application/json'});
  var accepted = false;
  return ApiClient(
    baseUrl: 'http://gateway.test',
    authStorage: AuthStorage(storage: _Store()),
    httpClient: MockClient((r) async {
      if (r.method == 'POST') {
        accepted = true;
        return ok(job);
      }
      return ok({'jobs': accepted ? [job] : []});
    }),
  );
}

void main() {
  testWidgets('an upload in progress is still shown after leaving the Sources tab and coming back', (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final client = _gateway();
    final router = GoRouter(initialLocation: '/sources', routes: [
      GoRoute(
        path: '/sources',
        builder: (_, _) => const ProjectSourcesScreen(workspaceId: 'ws', projectId: 'sess_1'),
      ),
      GoRoute(path: '/elsewhere', builder: (_, _) => const Scaffold(body: Text('another tab'))),
    ]);
    await tester.pumpWidget(ProviderScope(
      overrides: [
        ingestJobsProvider.overrideWith(
          (ref, id) => IngestJobsNotifier(ref, client, id, pollInterval: const Duration(seconds: 30)),
        ),
        projectProvider.overrideWith((ref, id) async => const ChatSession(id: 'sess_1', title: 'P')),
        projectConversationsProvider.overrideWith((ref, id) async => []),
        documentsProvider.overrideWith((ref) async => <DocumentInfo>[]),
      ],
      child: MaterialApp.router(routerConfig: router),
    ));
    await tester.pumpAndSettle();
    expect(find.text('scan.pdf'), findsNothing);

    final container = ProviderScope.containerOf(tester.element(find.byType(ProjectSourcesScreen)));
    await container.read(ingestJobsProvider('sess_1').notifier).submitUpload([1, 2, 3], 'scan.pdf');
    await tester.pump();
    expect(find.text('scan.pdf'), findsOneWidget);
    expect(find.text('Parsing…'), findsOneWidget);

    // The job row's spinner animates forever, so pumpAndSettle would never settle while it is shown.
    router.go('/elsewhere'); // switch tabs: the Sources screen is disposed
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500)); // route transition completes, old page is removed
    expect(find.byType(ProjectSourcesScreen), findsNothing);

    router.go('/sources'); // ...and back: a brand-new screen State
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('scan.pdf'), findsOneWidget);
    expect(find.text('Parsing…'), findsOneWidget);

    await tester.pumpWidget(const SizedBox()); // unmount so the poll timer is cancelled
  });
}
