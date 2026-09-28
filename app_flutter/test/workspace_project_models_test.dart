import 'package:app_flutter/api/models/document.dart';
import 'package:app_flutter/api/models/eval.dart';
import 'package:app_flutter/api/models/identity.dart';
import 'package:app_flutter/api/models/metrics.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Workspace + members (IRA-48)', () {
    test('Workspace.fromJson parses owner and name', () {
      final ws = Workspace.fromJson({'id': 'ws_1', 'name': 'Acme', 'owner_id': 'usr_1', 'created_at': 10.0});
      expect(ws.id, 'ws_1');
      expect(ws.name, 'Acme');
      expect(ws.ownerId, 'usr_1');
    });

    test('WorkspaceMemberEntry.fromJson nests member and user', () {
      final entry = WorkspaceMemberEntry.fromJson({
        'member': {'workspace_id': 'ws_1', 'user_id': 'usr_2', 'role': 'admin', 'added_at': 5.0},
        'user': {'id': 'usr_2', 'email': 'b@c.com'},
      });
      expect(entry.member.role, 'admin');
      expect(entry.user.email, 'b@c.com');
    });
  });

  group('Document + ingest/index (IRA-48 Sources tab)', () {
    test('DocumentInfo.fromJson falls back to doc_id when name is missing', () {
      final doc = DocumentInfo.fromJson({'doc_id': 'doc_9', 'pages': 3, 'size_kb': 12.5});
      expect(doc.name, 'doc_9');
      expect(doc.pages, 3);
      expect(doc.readOnly, false);
    });

    test('IngestResponse.fromJson round-trips blocks opaquely for /api/v1/index', () {
      final ingest = IngestResponse.fromJson({
        'doc_id': 'doc_1_abcd1234',
        'file_path': 'data/documents/u1/f.pdf',
        'profile': {'route': 'fast_text', 'page_count': 4, 'sample_pages': [1, 2], 'text_coverage': 0.9,
          'chars_per_page': 100.0, 'image_ratio': 0.1, 'columns': 1, 'table_score': 0.0, 'reason': 'text-heavy'},
        'blocks': [
          {'id': 'doc_1_p1_b0', 'doc_id': 'doc_1_abcd1234', 'page': 1, 'bbox': [0, 0, 1, 1], 'text': 'hi', 'order': 0},
        ],
        'duration_ms': 42.0,
      });
      expect(ingest.docId, 'doc_1_abcd1234');
      expect(ingest.profile.route, 'fast_text');
      expect(ingest.blocks, hasLength(1));
      expect(ingest.error, isNull);
    });

    test('IngestResponse.fromJson surfaces a parse error', () {
      final ingest = IngestResponse.fromJson({
        'doc_id': '',
        'file_path': '',
        'profile': {'route': 'ocr', 'page_count': 0, 'sample_pages': [], 'text_coverage': 0.0,
          'chars_per_page': 0.0, 'image_ratio': 0.0, 'columns': 1, 'table_score': 0.0, 'reason': 'failed'},
        'blocks': [],
        'duration_ms': 0.0,
        'error': 'Could not open file',
      });
      expect(ingest.error, 'Could not open file');
    });

    test('IndexResponse.fromJson parses indexed counts', () {
      final res = IndexResponse.fromJson({'doc_id': 'doc_1', 'indexed_count': 12});
      expect(res.indexedCount, 12);
      expect(res.denseIndexed, true);
    });
  });

  group('Evaluation (IRA-48 Evaluation tab)', () {
    test('ProjectEvalSummary.fromJson parses trend and weakest turns', () {
      final summary = ProjectEvalSummary.fromJson({
        'session_id': 'sess_1',
        'turns': 10,
        'answered': 8,
        'refusal_rate': 0.2,
        'mean_groundedness': 0.75,
        'trend': [
          {'query_id': 'q1', 'query_text': 'what is x', 'timestamp': 1.0, 'eval': {'groundedness': 0.5}},
        ],
        'weakest': [
          {'query_id': 'q2', 'query_text': 'weak one', 'timestamp': 2.0, 'eval': {'groundedness': 0.1}},
        ],
      });
      expect(summary.turns, 10);
      expect(summary.trend.single.eval.groundedness, 0.5);
      expect(summary.weakest.single.queryText, 'weak one');
    });

    test('ProjectEvalRun.fromJson parses golden-set metrics', () {
      final run = ProjectEvalRun.fromJson({
        'session_id': 'sess_1',
        'num_questions': 20,
        'hit_rate_at_1': 0.6,
        'hit_rate_at_3': 0.85,
        'mrr': 0.7,
        'ndcg_at_3': 0.72,
        'results': [
          {'question': 'q1', 'target_chunk_id': 'c1', 'rank': 1, 'top_score': 0.9},
        ],
      });
      expect(run.numQuestions, 20);
      expect(run.results.single.rank, 1);
    });
  });

  group('Metrics + models (IRA-48 Settings tab)', () {
    test('SystemMetrics.fromJson parses recent_telemetry for the workspace Recent activity card', () {
      final metrics = SystemMetrics.fromJson({
        'recent_telemetry': [
          {'query_id': 'q1', 'query_text': 'What is the FY24 margin?', 'refused': false, 'citations_count': 2, 'timestamp': 5.0},
          {'query_id': 'q2', 'query_text': 'FY25 guidance?', 'refused': true, 'citations_count': 0, 'timestamp': 1.0},
        ],
      });
      expect(metrics.recentTelemetry, hasLength(2));
      expect(metrics.recentTelemetry.first.refused, false);
      expect(metrics.recentTelemetry.first.citationsCount, 2);
      expect(metrics.recentTelemetry.last.refused, true);
    });

    test('SystemMetrics.isHealthy reads bool and string service states', () {
      final metrics = SystemMetrics.fromJson({
        'services': {'qdrant': true, 'redis': 'ok', 'ollama': 'down'},
      });
      expect(metrics.isHealthy('qdrant'), true);
      expect(metrics.isHealthy('redis'), true);
      expect(metrics.isHealthy('ollama'), false);
      expect(metrics.isHealthy('missing'), false);
    });

    test('ModelListResponse.fromJson parses chat-capable models only', () {
      final res = ModelListResponse.fromJson({
        'models': [
          {'name': 'llama3.2:3b', 'is_default': true},
          {'name': 'llama3.1:latest', 'is_default': false},
        ],
        'default_model': 'llama3.2:3b',
        'hardware_profile': 'fast',
        'ollama_alive': true,
      });
      expect(res.models, hasLength(2));
      expect(res.models.first.isDefault, true);
      expect(res.ollamaAlive, true);
    });
  });
}
