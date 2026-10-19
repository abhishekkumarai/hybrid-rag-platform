import 'package:app_flutter/api/models/connector.dart';
import 'package:app_flutter/api/models/retrieval.dart';
import 'package:app_flutter/api/models/session.dart';
import 'package:app_flutter/features/connectors/connector_providers.dart';
import 'package:app_flutter/features/workspace/workspace_providers.dart';
import 'package:app_flutter/screens/connectors/connectors_screen.dart';
import 'package:app_flutter/screens/project/chat/citation_inspector_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

const _connector = WebConnector(
  id: 'conn_1',
  name: 'Falcon docs',
  startUrl: 'https://docs.example.com/falcon',
  status: 'partial',
  pageCount: 2,
  schedule: 'daily',
);

Widget _app(Widget child, List<Override> overrides) => ProviderScope(
      overrides: [
        workspaceProjectsProvider.overrideWith((ref, ws) async => const <ChatSession>[]),
        ...overrides,
      ],
      child: MaterialApp(home: child),
    );

void main() {
  setUp(() {});

  testWidgets('empty state invites connecting a website', (tester) async {
    await tester.pumpWidget(_app(
      const ConnectorsScreen(workspaceId: 'ws'),
      [connectorsProvider.overrideWith((ref, ws) => Stream.value(const <WebConnector>[]))],
    ));
    await tester.pumpAndSettle();
    expect(find.text('No websites connected yet. Connect one to index its pages.'), findsOneWidget);
    await tester.tap(find.text('Connect a website'));
    await tester.pumpAndSettle();
    expect(find.text('Start URL'), findsOneWidget);
    expect(find.text('Connect and sync'), findsOneWidget);
  });

  testWidgets('a connector card shows status and page count', (tester) async {
    await tester.pumpWidget(_app(
      const ConnectorsScreen(workspaceId: 'ws'),
      [connectorsProvider.overrideWith((ref, ws) => Stream.value(const [_connector]))],
    ));
    await tester.pumpAndSettle();
    expect(find.text('Falcon docs'), findsOneWidget);
    expect(find.text('Synced with issues'), findsOneWidget);
    expect(find.text('2 pages'), findsOneWidget);
  });

  testWidgets('detail lists pages with their status and the last report', (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_app(
      const ConnectorDetailScreen(workspaceId: 'ws', connectorId: 'conn_1'),
      [
        connectorDetailProvider.overrideWith((ref, id) => Stream.value(const ConnectorDetail(
              connector: _connector,
              pages: [
                ConnectorPage(url: 'https://docs.example.com/falcon/app', status: 'needs_js', error: 'Too little text without JavaScript'),
                ConnectorPage(url: 'https://docs.example.com/falcon', title: 'Falcon', status: 'indexed', words: 120),
              ],
              lastReport: SyncReport(indexed: 1, needsJs: 1, status: 'partial'),
            ))),
      ],
    ));
    await tester.pumpAndSettle();
    expect(find.text('Pages (2)'), findsOneWidget);
    expect(find.text('needs JS'), findsOneWidget);
    expect(find.text('Too little text without JavaScript'), findsOneWidget);
    expect(find.text('1 need JavaScript'), findsOneWidget);
    expect(find.text('Sync now'), findsOneWidget);
  });

  testWidgets('a web citation offers the page link instead of a fake preview', (tester) async {
    const citation = Citation(
      docId: 'docs_example_com_falcon_ab12cd34',
      page: 1,
      bbox: [0, 0, 600, 18],
      snippet: 'The Falcon cluster has 48 GB of memory.',
      formattedBadge: '',
      webUrl: 'https://docs.example.com/falcon#perf',
    );
    await tester.pumpWidget(_app(
      Scaffold(body: CitationInspectorPanel(citations: const [citation], selected: citation, onSelect: (_) {})),
      const [],
    ));
    await tester.pumpAndSettle();
    expect(find.text('Open page'), findsOneWidget);
    expect(find.text('Section: #perf'), findsOneWidget);
    expect(find.textContaining('Sim:'), findsNothing);
  });
}
