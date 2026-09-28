import 'retrieval.dart';

/// Mirrors contracts/chat.py::ChatEvent. The `kind` discriminates the SSE `event:` name.
sealed class ChatEvent {
  const ChatEvent();

  static ChatEvent fromSse({required String kind, required Map<String, dynamic> data}) {
    switch (kind) {
      case 'session':
        return SessionEvent(
          sessionId: data['session_id'] as String,
          conversationId: data['conversation_id'] as String?,
        );
      case 'mode':
        return ModeEvent(mode: data['mode'] as String);
      case 'agent_step':
        return AgentStepEvent(step: Map<String, dynamic>.from(data['step'] as Map? ?? data));
      case 'token':
        return TokenEvent(token: data['token'] as String? ?? '');
      case 'error':
        return ChatErrorEvent(error: data['error'] as String? ?? '');
      case 'eval':
        return EvalEvent(scores: Map<String, dynamic>.from(data));
      case 'telemetry':
        return TelemetryEvent(telemetry: Map<String, dynamic>.from(data));
      case 'done':
        return DoneEvent(
          refused: data['refused'] as bool? ?? false,
          answer: data['answer'] as String?,
          rawAnswer: data['raw_answer'] as String?,
          citations: (data['citations'] as List<dynamic>? ?? [])
              .map((e) => Citation.fromJson(e as Map<String, dynamic>))
              .toList(),
          topScore: (data['top_score'] as num?)?.toDouble() ?? 0.0,
          isAgentic: data['is_agentic'] as bool? ?? false,
          mode: data['mode'] as String?,
          subQueries: (data['sub_queries'] as List<dynamic>? ?? []).cast<String>(),
          error: data['error'] as String?,
        );
      default:
        throw FormatException('Unknown chat event kind: $kind');
    }
  }
}

class SessionEvent extends ChatEvent {
  final String sessionId;
  final String? conversationId;
  const SessionEvent({required this.sessionId, this.conversationId});
}

class ModeEvent extends ChatEvent {
  final String mode; // agentic | graph
  const ModeEvent({required this.mode});
}

class AgentStepEvent extends ChatEvent {
  final Map<String, dynamic> step;
  const AgentStepEvent({required this.step});
}

class TokenEvent extends ChatEvent {
  final String token;
  const TokenEvent({required this.token});
}

class ChatErrorEvent extends ChatEvent {
  final String error;
  const ChatErrorEvent({required this.error});
}

class EvalEvent extends ChatEvent {
  final Map<String, dynamic> scores;
  const EvalEvent({required this.scores});
}

class TelemetryEvent extends ChatEvent {
  final Map<String, dynamic> telemetry;
  const TelemetryEvent({required this.telemetry});
}

class DoneEvent extends ChatEvent {
  final bool refused;
  final String? answer;
  final String? rawAnswer;
  final List<Citation> citations;
  final double topScore;
  final bool isAgentic;
  final String? mode;
  final List<String> subQueries;
  final String? error;

  const DoneEvent({
    this.refused = false,
    this.answer,
    this.rawAnswer,
    this.citations = const [],
    this.topScore = 0.0,
    this.isAgentic = false,
    this.mode,
    this.subQueries = const [],
    this.error,
  });
}
