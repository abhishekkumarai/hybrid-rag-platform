import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../api/models/document.dart';
import '../../api/models/eval.dart';
import '../../api/models/metrics.dart';
import '../../api/models/session.dart';
import '../workspace/workspace_providers.dart';

final _projectRefreshProvider = StateProvider.family<int, String>((ref, sessionId) => 0);

final projectProvider = FutureProvider.family<ChatSession, String>((ref, sessionId) async {
  ref.watch(_projectRefreshProvider(sessionId));
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/sessions/$sessionId') as Map<String, dynamic>;
  return ChatSession.fromJson(json['session'] as Map<String, dynamic>);
});

final projectEvalSummaryProvider = FutureProvider.family<ProjectEvalSummary, String>((ref, sessionId) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/sessions/$sessionId/eval/summary') as Map<String, dynamic>;
  return ProjectEvalSummary.fromJson(json);
});

final projectEvalLastRunProvider = FutureProvider.family<ProjectEvalRun?, String>((ref, sessionId) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/sessions/$sessionId/eval/run');
  if (json == null) return null;
  return ProjectEvalRun.fromJson(json as Map<String, dynamic>);
});

final projectConversationsProvider = FutureProvider.family<List<Conversation>, String>((ref, sessionId) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/sessions/$sessionId/conversations') as Map<String, dynamic>;
  return (json['conversations'] as List<dynamic>).map((e) => Conversation.fromJson(e as Map<String, dynamic>)).toList();
});

final modelsProvider = FutureProvider<ModelListResponse>((ref) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/models') as Map<String, dynamic>;
  return ModelListResponse.fromJson(json);
});

final gpuStatusProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final client = ref.watch(apiClientProvider);
  return await client.get('/api/v1/hardware/gpu') as Map<String, dynamic>;
});

class ProjectActions {
  ProjectActions(this._client, this._ref);
  final ApiClient _client;
  final Ref _ref;

  void _touch(String sessionId) => _ref.read(_projectRefreshProvider(sessionId).notifier).state++;

  Future<void> attachFiles(String sessionId, List<String> docIds) async {
    await _client.post('/api/v1/sessions/$sessionId/files', body: {'files': docIds});
    _touch(sessionId);
  }

  Future<void> detachFile(String sessionId, String docId) async {
    await _client.delete('/api/v1/sessions/$sessionId/files/$docId');
    _touch(sessionId);
  }

  /// Upload → ingest → index → attach, in one call, for the Sources tab's "Add source" flow.
  /// `onStage` reports each step so the UI can show progress.
  Future<void> uploadIngestIndexAndAttach(
    String sessionId,
    List<int> bytes,
    String filename, {
    String? route,
    void Function(String stage)? onStage,
  }) async {
    onStage?.call('Uploading and parsing…');
    final ingestJson = await _client.ingestFile(bytes, filename, route: route) as Map<String, dynamic>;
    final ingested = IngestResponse.fromJson(ingestJson);
    if (ingested.error != null) {
      throw ApiException(422, ingested.error!);
    }
    onStage?.call('Indexing ${ingested.blocks.length} blocks…');
    await _client.post('/api/v1/index', body: {'doc_id': ingested.docId, 'blocks': ingested.blocks});
    onStage?.call('Attaching to project…');
    await attachFiles(sessionId, [ingested.docId]);
    _ref.invalidate(documentsProvider);
  }

  Future<void> updateSettings(String sessionId, Map<String, dynamic> patch) async {
    await _client.patch('/api/v1/sessions/$sessionId', body: patch);
    _touch(sessionId);
  }

  Future<void> deleteProject(String sessionId) async {
    await _client.delete('/api/v1/sessions/$sessionId');
  }

  Future<ProjectEvalRun> runEval(String sessionId, {bool rebuild = false}) async {
    final json = await _client.post('/api/v1/sessions/$sessionId/eval/run?rebuild=$rebuild') as Map<String, dynamic>;
    final run = ProjectEvalRun.fromJson(json);
    _ref.invalidate(projectEvalLastRunProvider(sessionId));
    _ref.invalidate(projectEvalSummaryProvider(sessionId));
    return run;
  }
}

final projectActionsProvider = Provider<ProjectActions>((ref) => ProjectActions(ref.watch(apiClientProvider), ref));
