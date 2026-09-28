import 'package:app_flutter/api/models/feedback.dart';
import 'package:app_flutter/api/models/graph.dart';
import 'package:app_flutter/api/models/metrics.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('GraphRAGResponse.fromJson parses entities and relations', () {
    final response = GraphRAGResponse.fromJson({
      'query': 'how does reranking work',
      'matched_entities': [
        {'name': 'Reranker', 'category': 'SOFTWARE', 'doc_id': 'd1', 'page': 3},
      ],
      'relations': [
        {
          'source': 'Reranker',
          'predicate': 'improves',
          'target': 'Retrieval',
          'weight': 0.8,
        },
      ],
      'subgraph_text': 'Reranker -[improves]-> Retrieval',
      'connected_chunk_ids': ['c1', 'c2'],
      'duration_ms': 12.5,
    });

    expect(response.matchedEntities.single.name, 'Reranker');
    expect(response.relations.single.predicate, 'improves');
    expect(response.nodeNames, containsAll(['Reranker', 'Retrieval']));
    expect(response.connectedChunkIds, ['c1', 'c2']);
  });

  test(
    'GraphRAGResponse.nodeNames deduplicates entities and relation endpoints',
    () {
      final response = GraphRAGResponse.fromJson({
        'query': 'q',
        'matched_entities': [
          {'name': 'A'},
        ],
        'relations': [
          {'source': 'A', 'predicate': 'p', 'target': 'B'},
        ],
      });
      expect(response.nodeNames.toSet(), {'A', 'B'});
    },
  );

  test('GraphStats.fromJson tolerates missing fields', () {
    final stats = GraphStats.fromJson({});
    expect(stats.entityCount, 0);
    expect(stats.categoryCounts, isEmpty);
  });

  test('GraphStats.fromJson reads populated counts', () {
    final stats = GraphStats.fromJson({
      'entity_count': 42,
      'relation_count': 17,
      'community_count': 3,
      'category_counts': {'SOFTWARE': 10, 'HARDWARE': 5},
    });
    expect(stats.entityCount, 42);
    expect(stats.categoryCounts['SOFTWARE'], 10);
  });

  test('RAGOpsSummary.fromJson round-trips satisfaction fields', () {
    final summary = RAGOpsSummary.fromJson({
      'total_feedback': 100,
      'thumbs_up': 80,
      'thumbs_down': 20,
      'satisfaction_rate_pct': 80.0,
      'hard_negatives_count': 20,
    });
    expect(summary.satisfactionRatePct, 80.0);
    expect(summary.thumbsUp + summary.thumbsDown, summary.totalFeedback);
  });

  test('HnswStatusResponse.fromJson parses collection status', () {
    final status = HnswStatusResponse.fromJson({
      'collection_name': 'chunks',
      'hnsw_m': 16,
      'hnsw_ef_construct': 128,
      'default_ef_search': 64,
      'status': 'green',
      'points_count': 5000,
      'indexed_vectors_count': 5000,
    });
    expect(status.status, 'green');
    expect(status.hnswM, 16);
    expect(status.pointsCount, 5000);
  });
}
