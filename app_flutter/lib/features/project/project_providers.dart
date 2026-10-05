import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../api/models/eval.dart';
import '../../api/models/ingest_job.dart';
import '../../api/models/metrics.dart';
import '../../api/models/session.dart';
import '../workspace/workspace_providers.dart';

final _projectRefreshProvider = StateProvider.family<int, String>((ref, sessionId) => 0);

final projectProvider = FutureProvider.family<ChatSession, String>((ref, sessionId) async {
  ref.watch(_projectRefreshProvider(sessionId));
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/sessions/$sessionId') as Map<String, dynamic>;
  return ChatSession.fromJson(json['session'] as Map<String, dynamic>);
});

final projectEvalSummaryProvider = FutureProvider.family<ProjectEvalSummary, String>((ref, sessionId) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/sessions/$sessionId/eval/summary') as Map<String, dynamic>;
  return ProjectEvalSummary.fromJson(json);
});

final projectEvalLastRunProvider = FutureProvider.family<ProjectEvalRun?, String>((ref, sessionId) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/sessions/$sessionId/eval/run');
  if (json == null) return null;
  return ProjectEvalRun.fromJson(json as Map<String, dynamic>);
});

final projectConversationsProvider = FutureProvider.family<List<Conversation>, String>((ref, sessionId) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/sessions/$sessionId/conversations') as Map<String, dynamic>;
  return (json['conversations'] as List<dynamic>).map((e) => Conversation.fromJson(e as Map<String, dynamic>)).toList();
});

final modelsProvider = FutureProvider<ModelListResponse>((ref) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/models') as Map<String, dynamic>;
  return ModelListResponse.fromJson(json);
});

final gpuStatusProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final client = ref.watch(userApiClientProvider);
  return await client.get('/api/v1/hardware/gpu') as Map<String, dynamic>;
});

/// Sources being added to a project (IRA-60). The gateway does the work — parse, index, attach — and
/// records each stage; this notifier submits a source and polls those records. It is a plain
/// (non-autoDispose) provider, so leaving the Sources tab never drops a job's progress, and a reload
/// re-reads it from the server.
class IngestJobsNotifier extends StateNotifier<List<IngestJob>> {
  IngestJobsNotifier(this._ref, this._client, this.sessionId, {this.pollInterval = defaultPollInterval})
      : super(const []) {
    refresh();
  }

  final Ref _ref;
  final ApiClient _client;
  final String sessionId;
  Timer? _timer;
  int _localSeq = 0;

  final Duration pollInterval;

  static const defaultPollInterval = Duration(milliseconds: 1500);

  /// Uploads a file; the returned future completes once the gateway has accepted it (not once it is
  /// indexed). Progress then shows through [state].
  Future<void> submitUpload(List<int> bytes, String filename, {String? route}) => _submit(
        filename,
        'file',
        () => _client.createIngestJob(bytes, filename, sessionId, route: route),
      );

  /// Queues a web page or PDF link; the gateway fetches it.
  Future<void> submitUrl(String url, {String? route}) => _submit(
        url,
        'url',
        () => _client.post('/api/v1/ingest/jobs/url', body: {
          'url': url,
          'session_id': sessionId,
          'route': ?route,
        }),
      );

  Future<void> _submit(String source, String kind, Future<dynamic> Function() send) async {
    final local = IngestJob(
      id: '${IngestJob.localPrefix}${_localSeq++}',
      sessionId: sessionId,
      kind: kind,
      source: source,
      status: 'running',
      stage: kind == 'file' ? 'Uploading' : 'Sending',
    );
    state = [local, ...state];
    try {
      final job = IngestJob.fromJson(await send() as Map<String, dynamic>);
      if (!mounted) return;
      state = [job, ...state.where((j) => j.id != local.id && j.id != job.id)];
      _schedule();
    } on ApiException catch (e) {
      _fail(local, e.detail);
    } catch (e) {
      _fail(local, '$e');
    }
  }

  void _fail(IngestJob local, String message) {
    if (!mounted) return;
    state = [
      for (final j in state)
        if (j.id == local.id)
          IngestJob(
            id: j.id,
            sessionId: sessionId,
            kind: j.kind,
            source: j.source,
            status: 'failed',
            stage: 'Failed',
            error: message,
          )
        else
          j,
    ];
  }

  Future<void> refresh() async {
    try {
      final json = await _client.get('/api/v1/ingest/jobs', query: {'session_id': sessionId}) as Map<String, dynamic>;
      final fetched = (json['jobs'] as List<dynamic>).map((e) => IngestJob.fromJson(e as Map<String, dynamic>)).toList();
      if (!mounted) return;
      final before = {for (final j in state) j.id: j};
      // Uploads still travelling to the gateway (or that failed before getting a job) exist only here.
      state = [...state.where((j) => j.isLocal), ...fetched];
      final finished = fetched.any((j) => j.isDone && (before[j.id]?.isActive ?? false));
      if (finished) {
        _ref.invalidate(projectProvider(sessionId));
        _ref.invalidate(documentsProvider);
      }
    } catch (_) {
      // Transient (gateway restarting, offline): keep what we have and try again below.
    }
    _schedule();
  }

  void _schedule() {
    _timer?.cancel();
    if (!mounted || !state.any((j) => j.isActive && !j.isLocal)) return;
    _timer = Timer(pollInterval, refresh);
  }

  Future<void> dismiss(IngestJob job) async {
    state = state.where((j) => j.id != job.id).toList();
    if (job.isLocal) return;
    try {
      await _client.delete('/api/v1/ingest/jobs/${job.id}');
    } catch (_) {
      // Already gone, or still running; the next refresh reconciles.
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

final ingestJobsProvider = StateNotifierProvider.family<IngestJobsNotifier, List<IngestJob>, String>(
  (ref, sessionId) => IngestJobsNotifier(ref, ref.watch(userApiClientProvider), sessionId),
);

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

  Future<void> updateSettings(String sessionId, Map<String, dynamic> patch) async {
    await _client.patch('/api/v1/sessions/$sessionId', body: patch);
    _touch(sessionId);
  }

  Future<String> newConversation(String sessionId) async {
    final json = await _client.post('/api/v1/sessions/$sessionId/conversations') as Map<String, dynamic>;
    _ref.invalidate(projectConversationsProvider(sessionId));
    return json['id'] as String;
  }

  Future<void> deleteProject(String sessionId) async {
    await _client.delete('/api/v1/sessions/$sessionId');
    _ref.read(projectsRefreshProvider.notifier).state++;
  }

  Future<ProjectEvalRun> runEval(String sessionId, {bool rebuild = false}) async {
    final json = await _client.post('/api/v1/sessions/$sessionId/eval/run?rebuild=$rebuild') as Map<String, dynamic>;
    final run = ProjectEvalRun.fromJson(json);
    _ref.invalidate(projectEvalLastRunProvider(sessionId));
    _ref.invalidate(projectEvalSummaryProvider(sessionId));
    return run;
  }
}

final projectActionsProvider = Provider<ProjectActions>((ref) => ProjectActions(ref.watch(userApiClientProvider), ref));
