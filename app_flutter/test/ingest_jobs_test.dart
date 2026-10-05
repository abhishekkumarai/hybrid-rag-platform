import 'dart:convert';

import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_storage.dart';
import 'package:app_flutter/features/project/project_providers.dart';
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

Map<String, dynamic> _job(String status, String stage, {String? error}) => {
      'id': 'job_1',
      'session_id': 'sess_1',
      'kind': 'file',
      'source': 'report.pdf',
      'status': status,
      'stage': stage,
      'doc_id': status == 'done' ? 'report_ab12cd34' : null,
      'blocks': status == 'done' ? 12 : null,
      'error': error,
      'created_at': 1.0,
      'updated_at': 2.0,
    };

/// A gateway whose single job advances one stage on every poll.
class _FakeGateway {
  final stages = [
    ['queued', 'Queued'],
    ['running', 'Parsing'],
    ['running', 'Indexing 12 blocks'],
    ['done', 'Ready'],
  ];
  int polls = 0;
  bool accepted = false;
  int acceptStatus = 202;

  Future<http.Response> handle(http.Request r) async {
    if (r.url.path == '/api/v1/ingest/jobs' && r.method == 'POST') {
      if (acceptStatus != 202) return _json({'detail': 'disk full'}, status: acceptStatus);
      accepted = true;
      return _json(_job('queued', 'Queued'), status: 202);
    }
    if (r.url.path == '/api/v1/ingest/jobs' && r.method == 'GET') {
      if (!accepted) return _json({'jobs': []});
      final s = stages[polls.clamp(0, stages.length - 1)];
      polls++;
      return _json({'jobs': [_job(s[0], s[1])]});
    }
    if (r.method == 'DELETE') return _json({'deleted': true});
    return _json({'detail': 'unexpected ${r.method} ${r.url.path}'}, status: 500);
  }
}

ApiClient _client(_FakeGateway g) => ApiClient(
      baseUrl: 'http://gateway.test',
      authStorage: AuthStorage(storage: _InMemorySecureStore()),
      httpClient: MockClient(g.handle),
    );

final _fast = Duration(milliseconds: 5);

Provider<IngestJobsNotifier> _provider(ApiClient c) =>
    Provider((ref) => IngestJobsNotifier(ref, c, 'sess_1', pollInterval: _fast));

Future<void> _until(bool Function() cond) async {
  for (var i = 0; i < 200 && !cond(); i++) {
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
  expect(cond(), isTrue, reason: 'condition not reached in time');
}

void main() {
  test('an upload shows as a job immediately and is polled through to done', () async {
    final gw = _FakeGateway();
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final notifier = container.read(_provider(_client(gw)));

    await notifier.submitUpload([1, 2, 3], 'report.pdf');
    expect(notifier.state.single.id, 'job_1'); // the server job replaced the local placeholder
    expect(notifier.state.single.isActive, isTrue);

    await _until(() => notifier.state.single.isDone);
    expect(notifier.state.single.docId, 'report_ab12cd34');
    expect(notifier.state.single.blocks, 12);
  });

  test('progress keeps advancing with no screen listening (tab switched away)', () async {
    final gw = _FakeGateway();
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final provider = _provider(_client(gw));
    final notifier = container.read(provider);
    await notifier.submitUpload([1], 'report.pdf');

    // Nothing ever listens to `provider` here, as when the Sources screen is disposed.
    await _until(() => gw.polls >= 3);
    // A screen that mounts later reads the up-to-date job, not an empty list.
    expect(container.read(provider).state.single.stage, isNot('Queued'));
  });

  test('a fresh app (page reload) rediscovers a job that is still running on the server', () async {
    final gw = _FakeGateway()..accepted = true; // submitted before the "reload"
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final notifier = container.read(_provider(_client(gw)));

    await _until(() => notifier.state.isNotEmpty);
    expect(notifier.state.single.source, 'report.pdf');
    await _until(() => notifier.state.single.isDone);
  });

  test('a rejected upload becomes a dismissible failed row, not a vanished file', () async {
    final gw = _FakeGateway()..acceptStatus = 500;
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final notifier = container.read(_provider(_client(gw)));

    await notifier.submitUpload([1], 'report.pdf');
    final row = notifier.state.single;
    expect(row.isFailed, isTrue);
    expect(row.error, 'disk full');
    expect(row.source, 'report.pdf');

    await notifier.dismiss(row);
    expect(notifier.state, isEmpty);
  });
}
