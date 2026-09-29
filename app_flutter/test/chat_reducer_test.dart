import 'package:app_flutter/api/models/chat_event.dart';
import 'package:app_flutter/api/models/retrieval.dart';
import 'package:app_flutter/features/chat/chat_state.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('reduceChatEvent', () {
    test('accumulates tokens and marks streaming', () {
      var turn = const ChatTurn(id: 't1', query: 'q');
      turn = reduceChatEvent(turn, const TokenEvent(token: 'Hel'));
      turn = reduceChatEvent(turn, const TokenEvent(token: 'lo'));
      expect(turn.answer, 'Hello');
      expect(turn.streaming, isTrue);
    });

    test('done event finalizes citations, score and stops streaming', () {
      var turn = const ChatTurn(id: 't1', query: 'q', streaming: true);
      const citation = Citation(docId: 'doc_1', page: 2, bbox: [0, 0, 1, 1], snippet: 's', formattedBadge: '[doc_1]');
      turn = reduceChatEvent(
        turn,
        const DoneEvent(answer: 'Final answer', citations: [citation], topScore: 0.8),
      );
      expect(turn.answer, 'Final answer');
      expect(turn.citations, [citation]);
      expect(turn.streaming, isFalse);
      expect(turn.answerState, AnswerState.confident);
    });

    test('refused done event yields the refused answer state', () {
      var turn = const ChatTurn(id: 't1', query: 'q', streaming: true);
      turn = reduceChatEvent(turn, const DoneEvent(refused: true, answer: 'No grounded answer.'));
      expect(turn.refused, isTrue);
      expect(turn.answerState, AnswerState.refused);
    });

    test('low top_score without refusal is ambiguous', () {
      var turn = const ChatTurn(id: 't1', query: 'q');
      turn = reduceChatEvent(turn, const DoneEvent(answer: 'Answer', topScore: 0.2));
      expect(turn.answerState, AnswerState.ambiguous);
    });

    test('done keeps the model text, not the legacy sources-formatted answer', () {
      var turn = const ChatTurn(id: 't1', query: 'q', answer: '• A100', streaming: true);
      turn = reduceChatEvent(
        turn,
        const DoneEvent(answer: '• A100\n\n---\n### 📑 Verified Sources & Provenance:\n1. [doc: Page 1, (72.0, 88.2)]', rawAnswer: '• A100'),
      );
      expect(turn.answer, '• A100');
    });

    test('done falls back to answer when raw_answer is empty (refusals)', () {
      var turn = const ChatTurn(id: 't1', query: 'q', streaming: true);
      turn = reduceChatEvent(turn, const DoneEvent(refused: true, answer: 'The documents do not contain this.', rawAnswer: ''));
      expect(turn.answer, 'The documents do not contain this.');
    });

    test('error event surfaces the error and stops streaming', () {
      var turn = const ChatTurn(id: 't1', query: 'q', streaming: true);
      turn = reduceChatEvent(turn, const ChatErrorEvent(error: 'model unavailable'));
      expect(turn.error, 'model unavailable');
      expect(turn.streaming, isFalse);
    });

    test('session/mode/eval/telemetry events are no-ops on the turn', () {
      const turn = ChatTurn(id: 't1', query: 'q', answer: 'unchanged');
      final afterSession = reduceChatEvent(turn, const SessionEvent(sessionId: 's1'));
      expect(afterSession.answer, 'unchanged');
    });
  });
}
