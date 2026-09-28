import 'package:app_flutter/api/models/identity.dart';
import 'package:app_flutter/api/models/retrieval.dart';
import 'package:app_flutter/api/models/session.dart';
import 'package:app_flutter/api/models/share.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Citation round-trips through JSON', () {
    final json = {
      'doc_id': 'doc_1',
      'page': 2,
      'bbox': [0.0, 1.0, 2.0, 3.0],
      'snippet': 'text',
      'formatted_badge': '[doc_1: Page 2]',
      'is_table': false,
      'is_figure': false,
      'image_path': null,
      'is_web': false,
      'web_url': null,
      'resource_url': null,
      'resource_title': null,
    };
    final citation = Citation.fromJson(json);
    expect(citation.toJson(), json);
  });

  test('User.fromJson parses required and optional fields', () {
    final user = User.fromJson({
      'id': 'usr_1',
      'email': 'a@b.com',
      'display_name': 'A',
      'is_admin': true,
      'is_demo': false,
      'created_at': 123.0,
    });
    expect(user.id, 'usr_1');
    expect(user.isAdmin, true);
  });

  test('ChatSession.fromJson parses nested SessionParameters', () {
    final session = ChatSession.fromJson({
      'id': 'sess_1',
      'title': 'My project',
      'files': ['doc_a', 'doc_b'],
      'parameters': {'model': 'llama3.1:latest', 'top_k': 10},
    });
    expect(session.title, 'My project');
    expect(session.files, ['doc_a', 'doc_b']);
    expect(session.parameters.model, 'llama3.1:latest');
    expect(session.parameters.topK, 10);
    expect(session.parameters.topRerank, 6); // default preserved
  });

  test('ChatSession.fromJson tolerates missing optional fields', () {
    final session = ChatSession.fromJson({'id': 'sess_2'});
    expect(session.title, 'New Conversation');
    expect(session.files, isEmpty);
    expect(session.parameters.stream, true);
  });

  test('ShareSnapshot round-trips messages and doc_ids', () {
    final snapshot = ShareSnapshot.fromJson({
      'title': 'Shared chat',
      'messages': [
        {'role': 'user', 'content': 'hi', 'timestamp': 1.0},
      ],
      'doc_ids': ['doc_1'],
    });
    expect(snapshot.messages.single.role, 'user');
    expect(snapshot.docIds, ['doc_1']);
  });
}
