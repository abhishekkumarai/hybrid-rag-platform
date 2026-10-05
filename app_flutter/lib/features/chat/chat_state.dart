import '../../api/models/chat_event.dart';
import '../../api/models/eval.dart';
import '../../api/models/retrieval.dart';

enum AnswerState { confident, ambiguous, refused }

/// One user question + the assistant's (possibly still-streaming) reply.
class ChatTurn {
  final String id;
  final String query;
  final String answer;
  final List<Citation> citations;
  final bool streaming;
  final bool refused;
  final String? error;
  final double topScore;
  final String? mode;
  final List<String> subQueries;
  final RetrievalEvalScores? evalScores;
  final double? latencyMs;
  final double? tokensPerSec;
  final int? tokensGenerated;

  const ChatTurn({
    required this.id,
    required this.query,
    this.answer = '',
    this.citations = const [],
    this.streaming = false,
    this.refused = false,
    this.error,
    this.topScore = 0.0,
    this.mode,
    this.subQueries = const [],
    this.evalScores,
    this.latencyMs,
    this.tokensPerSec,
    this.tokensGenerated,
  });

  /// Evaluates whether the answer is confident, ambiguous, or refused using real metrics.
  AnswerState get answerState {
    if (refused) return AnswerState.refused;
    if (evalScores?.cragStatus != null) {
      final s = evalScores!.cragStatus!.toLowerCase();
      if (s == 'confident') return AnswerState.confident;
      if (s == 'refuse' || s == 'refused') return AnswerState.refused;
      if (s == 'ambiguous') return AnswerState.ambiguous;
    }
    if (evalScores != null && evalScores!.groundedness >= 0.7 && evalScores!.contextRelevance >= 0.25) {
      return AnswerState.confident;
    }
    return (topScore >= 0.35 || citations.isNotEmpty) ? AnswerState.confident : AnswerState.ambiguous;
  }

  ChatTurn copyWith({
    String? answer,
    List<Citation>? citations,
    bool? streaming,
    bool? refused,
    String? error,
    double? topScore,
    String? mode,
    List<String>? subQueries,
    RetrievalEvalScores? evalScores,
    double? latencyMs,
    double? tokensPerSec,
    int? tokensGenerated,
  }) =>
      ChatTurn(
        id: id,
        query: query,
        answer: answer ?? this.answer,
        citations: citations ?? this.citations,
        streaming: streaming ?? this.streaming,
        refused: refused ?? this.refused,
        error: error ?? this.error,
        topScore: topScore ?? this.topScore,
        mode: mode ?? this.mode,
        subQueries: subQueries ?? this.subQueries,
        evalScores: evalScores ?? this.evalScores,
        latencyMs: latencyMs ?? this.latencyMs,
        tokensPerSec: tokensPerSec ?? this.tokensPerSec,
        tokensGenerated: tokensGenerated ?? this.tokensGenerated,
      );
}

class ChatConversationState {
  final List<ChatTurn> turns;
  final bool sending;

  const ChatConversationState({this.turns = const [], this.sending = false});

  ChatConversationState copyWith({List<ChatTurn>? turns, bool? sending}) =>
      ChatConversationState(turns: turns ?? this.turns, sending: sending ?? this.sending);
}

/// Reduces a stream of [ChatEvent]s onto the in-flight [ChatTurn]. Pulled out of the
/// notifier so the SSE→UI reduction can be unit tested without a live server.
ChatTurn reduceChatEvent(ChatTurn turn, ChatEvent event) {
  return switch (event) {
    TokenEvent(:final token) => turn.copyWith(answer: turn.answer + token, streaming: true),
    ChatErrorEvent(:final error) => turn.copyWith(error: error, streaming: false),
    EvalEvent(:final scores) => turn.copyWith(
        evalScores: RetrievalEvalScores.fromJson(scores),
      ),
    TelemetryEvent(:final telemetry) => turn.copyWith(
        latencyMs: (telemetry['total_ms'] as num?)?.toDouble() ?? turn.latencyMs,
        tokensPerSec: (telemetry['tokens_per_sec'] as num?)?.toDouble() ?? turn.tokensPerSec,
        tokensGenerated: (telemetry['tokens_generated'] as num?)?.toInt() ?? turn.tokensGenerated,
        evalScores: telemetry['eval'] is Map
            ? RetrievalEvalScores.fromJson(Map<String, dynamic>.from(telemetry['eval'] as Map))
            : turn.evalScores,
      ),
    DoneEvent(:final refused, :final answer, :final rawAnswer, :final citations, :final topScore, :final mode, :final subQueries, :final error) =>
      turn.copyWith(
        // `answer` is pre-formatted for the legacy HTML client (a markdown "Verified Sources" block
        // with raw bboxes); this client renders citations as chips, so it wants the model's own text.
        answer: (rawAnswer != null && rawAnswer.isNotEmpty) ? rawAnswer : (answer ?? turn.answer),
        citations: citations,
        refused: refused,
        streaming: false,
        topScore: topScore,
        mode: mode,
        subQueries: subQueries,
        error: error,
      ),
    SessionEvent() || ModeEvent() || AgentStepEvent() => turn,
  };
}
