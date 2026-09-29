import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../api/models/feedback.dart';
import '../../api/models/graph.dart';
import '../../api/models/metrics.dart';

/// Feedback summary over every project the caller can see — the gateway scopes it (all projects
/// for an admin, the caller's own otherwise).
final ragopsSummaryProvider = FutureProvider<RAGOpsSummary>((ref) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/feedback/summary') as Map<String, dynamic>;
  return RAGOpsSummary.fromJson(json);
});

final ragopsDatasetProvider = FutureProvider<List<Map<String, dynamic>>>((
  ref,
) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/ragops/dataset') as List<dynamic>;
  return json.cast<Map<String, dynamic>>();
});

final hnswStatusProvider = FutureProvider<HnswStatusResponse>((ref) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/admin/hnsw') as Map<String, dynamic>;
  return HnswStatusResponse.fromJson(json);
});

final globalEvalReportProvider = FutureProvider<Map<String, dynamic>>((
  ref,
) async {
  final client = ref.watch(userApiClientProvider);
  return await client.get('/api/v1/eval/report') as Map<String, dynamic>;
});

final queueStatsProvider = FutureProvider<Map<String, int>>((ref) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/queue/stats') as Map<String, dynamic>;
  return json.map((k, v) => MapEntry(k, (v as num).toInt()));
});

final dlqListProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/queue/dlq') as List<dynamic>;
  return json.cast<Map<String, dynamic>>();
});

final graphStatsProvider = FutureProvider<GraphStats>((ref) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/graph/stats') as Map<String, dynamic>;
  return GraphStats.fromJson(json);
});

class AdminActions {
  AdminActions(this._client, this._ref);
  final ApiClient _client;
  final Ref _ref;

  Future<void> replayDlq({String? taskId}) async {
    await _client.post(
      '/api/v1/queue/dlq/replay${taskId != null ? '?task_id=$taskId' : ''}',
    );
    _ref.invalidate(dlqListProvider);
    _ref.invalidate(queueStatsProvider);
  }

  Future<HnswStatusResponse> rebuildHnsw({
    required int hnswM,
    required int hnswEfConstruct,
  }) async {
    final json = await _client.post(
      '/api/v1/admin/hnsw/rebuild',
      body: {'hnsw_m': hnswM, 'hnsw_ef_construct': hnswEfConstruct},
    ) as Map<String, dynamic>;
    final status = HnswStatusResponse.fromJson(json);
    _ref.invalidate(hnswStatusProvider);
    return status;
  }

  Future<Map<String, dynamic>> runGlobalEval() async {
    final json = await _client.post('/api/v1/eval/run') as Map<String, dynamic>;
    _ref.invalidate(globalEvalReportProvider);
    return json;
  }

  Future<Map<String, dynamic>> syncWebStore({bool forceRefresh = false}) async {
    return await _client.post(
      '/api/v1/web/sync',
      body: {'force_refresh': forceRefresh},
    ) as Map<String, dynamic>;
  }

  Future<GraphRAGResponse> queryGraph(
    String queryText, {
    int maxHops = 2,
    double minEdgeWeight = 0.1,
  }) async {
    final json = await _client.post(
      '/api/v1/graph/query',
      body: {
        'query_text': queryText,
        'max_hops': maxHops,
        'min_edge_weight': minEdgeWeight,
      },
    ) as Map<String, dynamic>;
    return GraphRAGResponse.fromJson(json);
  }
}

final adminActionsProvider = Provider<AdminActions>(
  (ref) => AdminActions(ref.watch(userApiClientProvider), ref),
);
