/// Mirrors contracts/metrics.py::QueryTelemetry (the subset the workspace Overview's "Recent
/// activity" card needs — matches `ui/stitch_workspace/01_workspace_overview.html`'s per-question
/// rows: text, refused, timestamp).
class QueryTelemetry {
  final String queryId;
  final String? sessionId;
  final String? conversationId;
  final String queryText;
  final bool refused;
  final int citationsCount;
  final double timestamp;
  final double totalMs;
  final double topScore;

  const QueryTelemetry({
    required this.queryId,
    this.sessionId,
    this.conversationId,
    this.queryText = '',
    this.refused = false,
    this.citationsCount = 0,
    this.timestamp = 0,
    this.totalMs = 0,
    this.topScore = 0,
  });

  factory QueryTelemetry.fromJson(Map<String, dynamic> json) => QueryTelemetry(
    queryId: json['query_id'] as String? ?? '',
    sessionId: json['session_id'] as String?,
    conversationId: json['conversation_id'] as String?,
    queryText: json['query_text'] as String? ?? '',
    refused: json['refused'] as bool? ?? false,
    citationsCount: json['citations_count'] as int? ?? 0,
    timestamp: (json['timestamp'] as num?)?.toDouble() ?? 0,
    totalMs: (json['total_ms'] as num?)?.toDouble() ?? 0,
    topScore: (json['top_score'] as num?)?.toDouble() ?? 0,
  );
}

/// Mirrors contracts/metrics.py::SystemMetrics (services health + pipeline telemetry).
class SystemMetrics {
  final double uptimeSeconds;
  final int totalQueries;
  final int totalRefusals;
  final double avgRetrievalMs;
  final double avgRerankMs;
  final double avgGenerationMs;
  final double avgTokensPerSec;
  final int qdrantPoints;
  final int redisQueueDepth;
  final int dlqTaskCount;
  final Map<String, dynamic> services;
  final List<QueryTelemetry> recentTelemetry;

  const SystemMetrics({
    this.uptimeSeconds = 0,
    this.totalQueries = 0,
    this.totalRefusals = 0,
    this.avgRetrievalMs = 0,
    this.avgRerankMs = 0,
    this.avgGenerationMs = 0,
    this.avgTokensPerSec = 0,
    this.qdrantPoints = 0,
    this.redisQueueDepth = 0,
    this.dlqTaskCount = 0,
    this.services = const {},
    this.recentTelemetry = const [],
  });

  factory SystemMetrics.fromJson(Map<String, dynamic> json) => SystemMetrics(
    uptimeSeconds: (json['uptime_seconds'] as num?)?.toDouble() ?? 0,
    totalQueries: json['total_queries'] as int? ?? 0,
    totalRefusals: json['total_refusals'] as int? ?? 0,
    avgRetrievalMs: (json['avg_retrieval_ms'] as num?)?.toDouble() ?? 0,
    avgRerankMs: (json['avg_rerank_ms'] as num?)?.toDouble() ?? 0,
    avgGenerationMs: (json['avg_generation_ms'] as num?)?.toDouble() ?? 0,
    avgTokensPerSec: (json['avg_tokens_per_sec'] as num?)?.toDouble() ?? 0,
    qdrantPoints: json['qdrant_points'] as int? ?? 0,
    redisQueueDepth: json['redis_queue_depth'] as int? ?? 0,
    dlqTaskCount: json['dlq_task_count'] as int? ?? 0,
    services: (json['services'] as Map<String, dynamic>?) ?? const {},
    recentTelemetry: (json['recent_telemetry'] as List<dynamic>? ?? [])
        .map((e) => QueryTelemetry.fromJson(e as Map<String, dynamic>))
        .toList(),
  );

  /// `services` values are booleans/strings depending on the check; true-ish means healthy.
  bool isHealthy(String name) {
    final v = services[name];
    if (v is bool) return v;
    if (v is String) {
      return v.toLowerCase() == 'ok' || v.toLowerCase() == 'healthy' || v.toLowerCase() == 'up';
    }
    return false;
  }
}

/// Mirrors services/gateway/api.py::ModelInfo.
class ModelInfo {
  final String name;
  final int? sizeBytes;
  final bool isDefault;

  const ModelInfo({required this.name, this.sizeBytes, this.isDefault = false});

  factory ModelInfo.fromJson(Map<String, dynamic> json) => ModelInfo(
    name: json['name'] as String,
    sizeBytes: json['size_bytes'] as int?,
    isDefault: json['is_default'] as bool? ?? false,
  );
}

/// Mirrors services/gateway/api.py::ModelListResponse.
class ModelListResponse {
  final List<ModelInfo> models;
  final String defaultModel;
  final String systemDefaultModel;
  final bool ollamaAlive;

  const ModelListResponse({
    this.models = const [],
    this.defaultModel = '',
    this.systemDefaultModel = '',
    this.ollamaAlive = false,
  });

  factory ModelListResponse.fromJson(Map<String, dynamic> json) =>
      ModelListResponse(
        models: (json['models'] as List<dynamic>? ?? [])
            .map((e) => ModelInfo.fromJson(e as Map<String, dynamic>))
            .toList(),
        defaultModel: json['default_model'] as String? ?? '',
        systemDefaultModel: json['system_default_model'] as String? ?? '',
        ollamaAlive: json['ollama_alive'] as bool? ?? false,
      );
}

/// Mirrors the `services` block of `GET /api/v1/health` — public (no auth), unlike
/// `SystemMetrics`'s cross-project `/api/v1/metrics`, so the sidebar footer's service-health
/// dots (DESIGN-evergreen.md) can use it for a non-admin guest too.
class ServiceHealth {
  final bool qdrantAlive;
  final bool redisAlive;
  final bool ollamaAlive;

  const ServiceHealth({this.qdrantAlive = false, this.redisAlive = false, this.ollamaAlive = false});

  factory ServiceHealth.fromJson(Map<String, dynamic> json) {
    final services = (json['services'] as Map<String, dynamic>?) ?? const {};
    bool alive(String key) => (services[key] as Map<String, dynamic>?)?['alive'] as bool? ?? false;
    return ServiceHealth(qdrantAlive: alive('qdrant'), redisAlive: alive('redis'), ollamaAlive: alive('ollama'));
  }
}

/// Mirrors services/gateway/api.py::HnswStatusResponse.
class HnswStatusResponse {
  final String collectionName;
  final int hnswM;
  final int hnswEfConstruct;
  final int defaultEfSearch;
  final String status;
  final int? pointsCount;
  final int? indexedVectorsCount;

  const HnswStatusResponse({
    required this.collectionName,
    required this.hnswM,
    required this.hnswEfConstruct,
    required this.defaultEfSearch,
    required this.status,
    this.pointsCount,
    this.indexedVectorsCount,
  });

  factory HnswStatusResponse.fromJson(Map<String, dynamic> json) =>
      HnswStatusResponse(
        collectionName: json['collection_name'] as String? ?? '',
        hnswM: json['hnsw_m'] as int? ?? 0,
        hnswEfConstruct: json['hnsw_ef_construct'] as int? ?? 0,
        defaultEfSearch: json['default_ef_search'] as int? ?? 0,
        status: json['status'] as String? ?? 'unknown',
        pointsCount: json['points_count'] as int?,
        indexedVectorsCount: json['indexed_vectors_count'] as int?,
      );
}

double _d(Object? v) => (v as num?)?.toDouble() ?? 0;

/// Mirrors contracts/metrics.py::ChatLatencyStats.
class ChatLatencyStats {
  final int queries;
  final int refusals;
  final double avgTotalMs;
  final double avgRetrievalMs;
  final double avgTtftMs;
  final double avgGenerationMs;
  final double avgTokensPerSec;
  final double avgTopScore;
  final double? lastQueryAt;

  const ChatLatencyStats({
    this.queries = 0,
    this.refusals = 0,
    this.avgTotalMs = 0,
    this.avgRetrievalMs = 0,
    this.avgTtftMs = 0,
    this.avgGenerationMs = 0,
    this.avgTokensPerSec = 0,
    this.avgTopScore = 0,
    this.lastQueryAt,
  });

  factory ChatLatencyStats.fromJson(Map<String, dynamic> json) => ChatLatencyStats(
        queries: json['queries'] as int? ?? 0,
        refusals: json['refusals'] as int? ?? 0,
        avgTotalMs: _d(json['avg_total_ms']),
        avgRetrievalMs: _d(json['avg_retrieval_ms']),
        avgTtftMs: _d(json['avg_ttft_ms']),
        avgGenerationMs: _d(json['avg_generation_ms']),
        avgTokensPerSec: _d(json['avg_tokens_per_sec']),
        avgTopScore: _d(json['avg_top_score']),
        lastQueryAt: (json['last_query_at'] as num?)?.toDouble(),
      );
}

/// Mirrors contracts/metrics.py::ConversationStats — one chat's row.
class ConversationStats {
  final String conversationId;
  final String title;
  final ChatLatencyStats stats;

  const ConversationStats({required this.conversationId, required this.title, required this.stats});

  factory ConversationStats.fromJson(Map<String, dynamic> json) => ConversationStats(
        conversationId: json['conversation_id'] as String,
        title: json['title'] as String? ?? 'Chat',
        stats: ChatLatencyStats.fromJson(json),
      );
}

/// Mirrors contracts/metrics.py::ProjectObservability (IRA-56).
class ProjectObservability {
  final String sessionId;
  final String? conversationId;
  final ChatLatencyStats totals;
  final List<ConversationStats> conversations;
  final List<QueryTelemetry> recent;

  const ProjectObservability({
    required this.sessionId,
    this.conversationId,
    this.totals = const ChatLatencyStats(),
    this.conversations = const [],
    this.recent = const [],
  });

  factory ProjectObservability.fromJson(Map<String, dynamic> json) => ProjectObservability(
        sessionId: json['session_id'] as String,
        conversationId: json['conversation_id'] as String?,
        totals: ChatLatencyStats.fromJson(json['totals'] as Map<String, dynamic>? ?? const {}),
        conversations: (json['conversations'] as List<dynamic>? ?? [])
            .map((e) => ConversationStats.fromJson(e as Map<String, dynamic>))
            .toList(),
        recent: (json['recent'] as List<dynamic>? ?? [])
            .map((e) => QueryTelemetry.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
