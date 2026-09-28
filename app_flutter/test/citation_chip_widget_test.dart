import 'package:app_flutter/api/models/retrieval.dart';
import 'package:app_flutter/features/chat/chat_state.dart';
import 'package:app_flutter/theme/evergreen_theme.dart';
import 'package:app_flutter/widgets/answer_state_chip.dart';
import 'package:app_flutter/widgets/citation_chip.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _citation = Citation(
  docId: 'report_ab12cd34',
  page: 14,
  bbox: [10, 20, 30, 40],
  snippet: 'A relevant passage.',
  formattedBadge: '[Doc 2, p. 14]',
);

Widget _wrap(Widget child) => MaterialApp(theme: buildEvergreenTheme(), home: Scaffold(body: child));

void main() {
  testWidgets('CitationChip renders the formatted badge', (tester) async {
    await tester.pumpWidget(_wrap(const CitationChip(citation: _citation)));
    expect(find.text('[Doc 2, p. 14]'), findsOneWidget);
  });

  testWidgets('CitationChip falls back to doc_id/page when no badge', (tester) async {
    const noBadge = Citation(docId: 'doc_1', page: 3, bbox: [0, 0, 1, 1], snippet: '', formattedBadge: '');
    await tester.pumpWidget(_wrap(const CitationChip(citation: noBadge)));
    expect(find.text('doc_1 · p. 3'), findsOneWidget);
  });

  testWidgets('CitationChip tap fires onTap', (tester) async {
    var tapped = false;
    await tester.pumpWidget(_wrap(CitationChip(citation: _citation, onTap: () => tapped = true)));
    await tester.tap(find.byType(CitationChip));
    expect(tapped, isTrue);
  });

  testWidgets('AnswerStateChip shows the right label per state', (tester) async {
    await tester.pumpWidget(_wrap(const AnswerStateChip(state: AnswerState.confident)));
    expect(find.text('Confident'), findsOneWidget);

    await tester.pumpWidget(_wrap(const AnswerStateChip(state: AnswerState.ambiguous)));
    expect(find.text('Ambiguous'), findsOneWidget);

    await tester.pumpWidget(_wrap(const AnswerStateChip(state: AnswerState.refused)));
    expect(find.text('Refused'), findsOneWidget);
  });
}
