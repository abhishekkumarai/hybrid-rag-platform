import 'dart:convert';

import 'package:app_flutter/api/api_client.dart';
import 'package:app_flutter/api/auth_storage.dart';
import 'package:app_flutter/api/models/session.dart';
import 'package:app_flutter/features/chat/chat_providers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

ChatSession _fakeSession({List<String> files = const [], String? systemPrompt}) => ChatSession(
      id: 'sess_1',
      title: 'Source project',
      files: files,
      systemPrompt: systemPrompt,
      workspaceId: 'ws_1',
    );

class _InMemorySecureStore implements SecureKeyValueStore {
  final Map<String, String> _map = {};
  @override
  Future<String?> read({required String key}) async => _map[key];
  @override
  Future<void> write({required String key, required String value}) async => _map[key] = value;
  @override
  Future<void> delete({required String key}) async => _map.remove(key);
}

ApiClient _mockClient(Future<http.Response> Function(http.Request) handler) {
  return ApiClient(
    baseUrl: 'http://gateway.test',
    authStorage: AuthStorage(storage: _InMemorySecureStore()),
    httpClient: MockClient((request) async => handler(request)),
  );
}

http.Response _json(Object body, {int status = 200}) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

void main() {
  group('ChatActions share/fork flow', () {
    test('createShare posts and parses the one-time URL response', () async {
      final client = _mockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/sessions/sess_1/shares');
        return _json({
          'url': 'http://gateway.test/s/tok_abc',
          'token': 'tok_abc',
          'share': {'id': 'share_1', 'session_id': 'sess_1', 'created_at': 0, 'message_count': 4, 'revoked': false},
        });
      });
      final actions = ChatActions(client);
      final result = await actions.createShare('sess_1');
      expect(result.token, 'tok_abc');
      expect(result.share.messageCount, 4);
    });

    test('listShares parses the summaries list', () async {
      final client = _mockClient((request) async {
        expect(request.method, 'GET');
        return _json({
          'shares': [
            {'id': 'share_1', 'session_id': 'sess_1', 'created_at': 0, 'message_count': 2, 'revoked': false},
            {'id': 'share_2', 'session_id': 'sess_1', 'created_at': 0, 'message_count': 5, 'revoked': true},
          ],
        });
      });
      final actions = ChatActions(client);
      final shares = await actions.listShares('sess_1');
      expect(shares, hasLength(2));
      expect(shares[1].revoked, isTrue);
    });

    test('revokeShare DELETEs the share by id', () async {
      var deletedPath = '';
      final client = _mockClient((request) async {
        deletedPath = request.url.path;
        return _json({'revoked': true});
      });
      final actions = ChatActions(client);
      await actions.revokeShare('share_1');
      expect(deletedPath, '/api/v1/shares/share_1');
    });

    test('a 404 revoking an unknown share surfaces as ApiException', () async {
      final client = _mockClient((request) async => _json({'detail': "Share 'nope' not found"}, status: 404));
      final actions = ChatActions(client);
      await expectLater(() => actions.revokeShare('nope'), throwsA(isA<ApiException>()));
    });

    test('forkFromHere creates a new session seeded with the source project\'s files/prompt', () async {
      final client = _mockClient((request) async {
        expect(request.url.path, '/api/v1/sessions');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['files'], ['doc_1', 'doc_2']);
        expect(body['system_prompt'], 'You are helpful.');
        return _json({'id': 'sess_new'});
      });
      final actions = ChatActions(client);
      final newId = await actions.forkFromHere(
        _fakeSession(files: const ['doc_1', 'doc_2'], systemPrompt: 'You are helpful.'),
      );
      expect(newId, 'sess_new');
    });
  });
}
