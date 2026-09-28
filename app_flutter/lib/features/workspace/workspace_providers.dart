import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../api/models/document.dart';
import '../../api/models/identity.dart';
import '../../api/models/metrics.dart';
import '../../api/models/session.dart';

/// The current workspace id, driven by the router's `:ws` path segment (see `AppShell`). Screens
/// read this instead of re-parsing the route themselves.
final currentWorkspaceIdProvider = StateProvider<String>((ref) => 'default');

final workspacesProvider = FutureProvider<List<Workspace>>((ref) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/workspaces') as Map<String, dynamic>;
  return (json['workspaces'] as List<dynamic>).map((e) => Workspace.fromJson(e as Map<String, dynamic>)).toList();
});

/// Projects (ChatSessions) visible in a workspace. `refreshProjectsProvider` bumps its
/// dependents after a create/delete without a full app restart.
final _projectsRefreshProvider = StateProvider<int>((ref) => 0);

final workspaceProjectsProvider = FutureProvider.family<List<ChatSession>, String>((ref, workspaceId) async {
  ref.watch(_projectsRefreshProvider);
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/sessions', query: {'workspace_id': workspaceId}) as Map<String, dynamic>;
  return (json['sessions'] as List<dynamic>).map((e) => ChatSession.fromJson(e as Map<String, dynamic>)).toList();
});

final workspaceMembersProvider = FutureProvider.family<List<WorkspaceMemberEntry>, String>((ref, workspaceId) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/workspaces/$workspaceId/members') as Map<String, dynamic>;
  return (json['members'] as List<dynamic>)
      .map((e) => WorkspaceMemberEntry.fromJson(e as Map<String, dynamic>))
      .toList();
});

final workspaceMetricsProvider = FutureProvider.family<SystemMetrics, String?>((ref, sessionId) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/metrics', query: sessionId == null ? null : {'session_id': sessionId})
      as Map<String, dynamic>;
  return SystemMetrics.fromJson(json);
});

/// Sidebar footer service-health dots (DESIGN-evergreen.md) — `/api/v1/health` is public, so this
/// works for non-admin users too, unlike `workspaceMetricsProvider(null)`'s admin-only cross-project view.
final serviceHealthProvider = FutureProvider<ServiceHealth>((ref) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/health') as Map<String, dynamic>;
  return ServiceHealth.fromJson(json);
});

final documentsProvider = FutureProvider<List<DocumentInfo>>((ref) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.get('/api/v1/documents') as Map<String, dynamic>;
  return (json['documents'] as List<dynamic>).map((e) => DocumentInfo.fromJson(e as Map<String, dynamic>)).toList();
});

class WorkspaceActions {
  WorkspaceActions(this._client, this._ref);
  final ApiClient _client;
  final Ref _ref;

  Future<Workspace> create(String name) async {
    final json = await _client.post('/api/v1/workspaces', body: {'name': name}) as Map<String, dynamic>;
    final ws = Workspace.fromJson(json);
    _ref.read(currentWorkspaceIdProvider.notifier).state = ws.id;
    _ref.invalidate(workspacesProvider);
    return ws;
  }

  Future<ChatSession> createProject(
    String workspaceId,
    String title, {
    String? description,
    String model = 'llama3.2:3b',
    String retrievalMode = 'auto',
  }) async {
    final json = await _client.post('/api/v1/sessions', body: {
      'title': title,
      if (workspaceId.isNotEmpty && workspaceId != 'default' && workspaceId != 'ws_default')
        'workspace_id': workspaceId,
      if (description != null && description.trim().isNotEmpty) 'system_prompt': description.trim(),
      'parameters': {
        'model': model,
        'retrieval_mode': retrievalMode,
      },
    }) as Map<String, dynamic>;
    final session = ChatSession.fromJson(json);
    _ref.read(_projectsRefreshProvider.notifier).state++;
    _ref.invalidate(workspaceProjectsProvider(workspaceId));
    if (session.workspaceId != null && session.workspaceId != workspaceId) {
      _ref.invalidate(workspaceProjectsProvider(session.workspaceId!));
    }
    return session;
  }

  Future<void> deleteProject(String sessionId) async {
    await _client.delete('/api/v1/sessions/$sessionId');
    _ref.read(_projectsRefreshProvider.notifier).state++;
  }

  Future<void> deleteProjects(Iterable<String> sessionIds) async {
    for (final id in sessionIds) {
      await _client.delete('/api/v1/sessions/$id');
    }
    _ref.read(_projectsRefreshProvider.notifier).state++;
  }

  Future<Map<String, dynamic>> openWebRagPreset() async {
    final json = await _client.post('/api/v1/web/preset-project') as Map<String, dynamic>;
    _ref.read(_projectsRefreshProvider.notifier).state++;
    return json;
  }

  Future<void> addMember(String workspaceId, String email, String role) async {
    await _client.post('/api/v1/workspaces/$workspaceId/members', body: {'email': email, 'role': role});
    _ref.invalidate(workspaceMembersProvider);
  }

  Future<void> updateMemberRole(String workspaceId, String userId, String role) async {
    await _client.patch('/api/v1/workspaces/$workspaceId/members/$userId', body: {'role': role});
    _ref.invalidate(workspaceMembersProvider);
  }

  Future<void> removeMember(String workspaceId, String userId) async {
    await _client.delete('/api/v1/workspaces/$workspaceId/members/$userId');
    _ref.invalidate(workspaceMembersProvider);
  }
}

final workspaceActionsProvider = Provider<WorkspaceActions>(
  (ref) => WorkspaceActions(ref.watch(apiClientProvider), ref),
);
