import 'retrieval.dart';

/// Mirrors contracts/session.py::SessionParameters.
class SessionParameters {
  final String model;
  final double temperature;
  final String retrievalMode; // auto | agentic | graph | direct
  final String embeddingRoute;
  final int topK;
  final int topRerank;
  final double minScoreThreshold;
  final int compactorBudget;
  final int hnswEfSearch;
  final bool stream;

  const SessionParameters({
    this.model = 'llama3.2:3b',
    this.temperature = 0.7,
    this.retrievalMode = 'auto',
    this.embeddingRoute = 'auto',
    this.topK = 20,
    this.topRerank = 6,
    this.minScoreThreshold = 0.15,
    this.compactorBudget = 3072,
    this.hnswEfSearch = 128,
    this.stream = true,
  });

  factory SessionParameters.fromJson(Map<String, dynamic> json) => SessionParameters(
        model: json['model'] as String? ?? 'llama3.2:3b',
        temperature: (json['temperature'] as num?)?.toDouble() ?? 0.7,
        retrievalMode: json['retrieval_mode'] as String? ?? 'auto',
        embeddingRoute: json['embedding_route'] as String? ?? 'auto',
        topK: json['top_k'] as int? ?? 20,
        topRerank: json['top_rerank'] as int? ?? 6,
        minScoreThreshold: (json['min_score_threshold'] as num?)?.toDouble() ?? 0.15,
        compactorBudget: json['compactor_budget'] as int? ?? 3072,
        hnswEfSearch: json['hnsw_ef_search'] as int? ?? 128,
        stream: json['stream'] as bool? ?? true,
      );

  Map<String, dynamic> toJson() => {
        'model': model,
        'temperature': temperature,
        'retrieval_mode': retrievalMode,
        'embedding_route': embeddingRoute,
        'top_k': topK,
        'top_rerank': topRerank,
        'min_score_threshold': minScoreThreshold,
        'compactor_budget': compactorBudget,
        'hnsw_ef_search': hnswEfSearch,
        'stream': stream,
      };
}

class ChatMessage {
  final String id;
  final String role; // user | assistant | system
  final String content;
  final List<Citation> citations;
  final double timestamp;
  final double? latencyMs;
  final Map<String, dynamic> metadata;

  const ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    this.citations = const [],
    this.timestamp = 0,
    this.latencyMs,
    this.metadata = const {},
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
        id: json['id'] as String,
        role: json['role'] as String,
        content: json['content'] as String,
        citations: (json['citations'] as List<dynamic>? ?? [])
            .map((e) => Citation.fromJson(e as Map<String, dynamic>))
            .toList(),
        timestamp: (json['timestamp'] as num?)?.toDouble() ?? 0,
        latencyMs: (json['latency_ms'] as num?)?.toDouble(),
        metadata: Map<String, dynamic>.from(json['metadata'] as Map? ?? const {}),
      );
}

/// The UI calls this a "Project" (see CLAUDE.md); the wire/JS name stays ChatSession.
class ChatSession {
  final String id;
  final String title;
  final double createdAt;
  final double updatedAt;
  final int messageCount;
  final List<String> files;
  final String? systemPrompt;
  final String? description;
  final SessionParameters parameters;
  final String? ownerId;
  final String? forkedFrom;
  final String? workspaceId;

  const ChatSession({
    required this.id,
    this.title = 'New Conversation',
    this.createdAt = 0,
    this.updatedAt = 0,
    this.messageCount = 0,
    this.files = const [],
    this.systemPrompt,
    this.description,
    this.parameters = const SessionParameters(),
    this.ownerId,
    this.forkedFrom,
    this.workspaceId,
  });

  factory ChatSession.fromJson(Map<String, dynamic> json) => ChatSession(
        id: json['id'] as String,
        title: json['title'] as String? ?? 'New Conversation',
        createdAt: (json['created_at'] as num?)?.toDouble() ?? 0,
        updatedAt: (json['updated_at'] as num?)?.toDouble() ?? 0,
        messageCount: json['message_count'] as int? ?? 0,
        files: (json['files'] as List<dynamic>? ?? []).cast<String>(),
        systemPrompt: json['system_prompt'] as String?,
        description: json['description'] as String?,
        parameters: json['parameters'] != null
            ? SessionParameters.fromJson(json['parameters'] as Map<String, dynamic>)
            : const SessionParameters(),
        ownerId: json['owner_id'] as String?,
        forkedFrom: json['forked_from'] as String?,
        workspaceId: json['workspace_id'] as String?,
      );
}

class Conversation {
  final String id;
  final String sessionId;
  final String title;
  final double createdAt;
  final double updatedAt;
  final int messageCount;

  const Conversation({
    required this.id,
    required this.sessionId,
    this.title = 'New Chat',
    this.createdAt = 0,
    this.updatedAt = 0,
    this.messageCount = 0,
  });

  factory Conversation.fromJson(Map<String, dynamic> json) => Conversation(
        id: json['id'] as String,
        sessionId: json['session_id'] as String,
        title: json['title'] as String? ?? 'New Chat',
        createdAt: (json['created_at'] as num?)?.toDouble() ?? 0,
        updatedAt: (json['updated_at'] as num?)?.toDouble() ?? 0,
        messageCount: json['message_count'] as int? ?? 0,
      );
}
