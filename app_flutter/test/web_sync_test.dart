import 'dart:convert';

import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_storage.dart';
import 'package:app_flutter/features/admin/admin_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _InMemorySecureStore implements SecureKeyValueStore {
  final Map<String, String> _map = {};
  @override
  Future<String?> read({required String key}) async => _map[key];
  @override
  Future<void> write({required String key, required String value}) async => _map[key] = value;
  @override
  Future<void> delete({required String key}) async => _map.remove(key);
}

http.Response _json(Object body, {int status = 200}) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

/// A gateway whose background sync finishes on the third status poll.
class _FakeGateway {
  final requests = <String>[];
  Object? syncBody;
  int polls = 0;

  Future<http.Response> handle(http.Request r) async {
    requests.add('${r.method} ${r.url.path}');
    if (r.url.path == '/api/v1/web/sync' && r.method == 'POST') {
      syncBody = jsonDecode(r.body);
      return _json({'status': 'running', 'synced_pages': []});
    }
    if (r.url.path == '/api/v1/web/sync/status') {
      polls++;
      final finished = polls >= 3;
      return _json({
        'running': !finished,
        'done': polls,
        'total': 3,
        'result': finished ? {'status': 'completed', 'total_pages': 3} : null,
      });
    }
    return _json({'detail': 'unexpected ${r.method} ${r.url.path}'}, status: 500);
  }
}

AdminActions _actions(_FakeGateway g, ProviderContainer c) => AdminActions(
      ApiClient(
        baseUrl: 'http://gateway.test',
        authStorage: AuthStorage(storage: _InMemorySecureStore()),
        httpClient: MockClient(g.handle),
      ),
      c.read(Provider((ref) => ref)),
    );

void main() {
  test('syncWebStore starts a background sync and polls until the result arrives', () async {
    final gw = _FakeGateway();
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final progress = <String>[];

    final result = await _actions(gw, container).syncWebStore(
      forceRefresh: true,
      pollInterval: const Duration(milliseconds: 1),
      onProgress: (done, total) => progress.add('$done/$total'),
    );

    expect(gw.syncBody, {'force_refresh': true, 'background': true});
    expect(progress, ['1/3', '2/3', '3/3']);
    expect(result['status'], 'completed');
    expect(gw.requests.first, 'POST /api/v1/web/sync');
  });
}
