import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../api/models/connector.dart';
import '../workspace/workspace_providers.dart';

/// The workspace's website connectors (IRA-57). Re-polls every 2 s while any of them is syncing.
final connectorsProvider = StreamProvider.family<List<WebConnector>, String>((ref, workspaceId) async* {
  final client = ref.watch(userApiClientProvider);
  while (true) {
    final json = await client.get('/api/v1/connectors', query: {'workspace_id': workspaceId}) as Map<String, dynamic>;
    final list = (json['connectors'] as List<dynamic>).map((e) => WebConnector.fromJson(e as Map<String, dynamic>)).toList();
    yield list;
    if (!list.any((c) => c.busy)) return;
    await Future<void>.delayed(const Duration(seconds: 2));
  }
});

/// One connector with its pages; follows a running sync live.
final connectorDetailProvider = StreamProvider.family<ConnectorDetail, String>((ref, connectorId) async* {
  final client = ref.watch(userApiClientProvider);
  while (true) {
    final detail = ConnectorDetail.fromJson(await client.get('/api/v1/connectors/$connectorId') as Map<String, dynamic>);
    yield detail;
    if (!detail.connector.busy) return;
    await Future<void>.delayed(const Duration(seconds: 2));
  }
});

class ConnectorActions {
  ConnectorActions(this._client, this._ref);
  final ApiClient _client;
  final Ref _ref;

  void _refresh([String? id]) {
    _ref.invalidate(connectorsProvider);
    if (id != null) _ref.invalidate(connectorDetailProvider(id));
    _ref.invalidate(documentsProvider);
  }

  Future<WebConnector> create({
    required String workspaceId,
    required String startUrl,
    String? name,
    String? projectId,
    CrawlScope? scope,
    String render = 'auto',
    String schedule = 'manual',
  }) async {
    final json = await _client.post('/api/v1/connectors', body: {
      'start_url': startUrl,
      'name': ?name,
      'workspace_id': workspaceId,
      'project_id': ?projectId,
      'scope': ?scope?.toJson(),
      'render': render,
      'schedule': schedule,
    }) as Map<String, dynamic>;
    _refresh();
    return WebConnector.fromJson(json);
  }

  Future<void> sync(String id) async {
    await _client.post('/api/v1/connectors/$id/sync');
    _refresh(id);
  }

  Future<void> update(String id, Map<String, dynamic> patch) async {
    await _client.patch('/api/v1/connectors/$id', body: patch);
    _refresh(id);
  }

  Future<void> delete(String id) async {
    await _client.delete('/api/v1/connectors/$id');
    _refresh(id);
  }
}

final connectorActionsProvider = Provider<ConnectorActions>((ref) => ConnectorActions(ref.watch(userApiClientProvider), ref));
