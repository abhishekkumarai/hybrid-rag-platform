/// Mirrors contracts/graph.py::Entity.
class GraphEntity {
  final String name;
  final String category;
  final String? docId;
  final int? page;

  const GraphEntity({
    required this.name,
    this.category = 'CONCEPT',
    this.docId,
    this.page,
  });

  factory GraphEntity.fromJson(Map<String, dynamic> json) => GraphEntity(
    name: json['name'] as String,
    category: json['category'] as String? ?? 'CONCEPT',
    docId: json['doc_id'] as String?,
    page: json['page'] as int?,
  );
}

/// Mirrors contracts/graph.py::Relation.
class GraphRelation {
  final String source;
  final String predicate;
  final String target;
  final double weight;

  const GraphRelation({
    required this.source,
    required this.predicate,
    required this.target,
    this.weight = 1.0,
  });

  factory GraphRelation.fromJson(Map<String, dynamic> json) => GraphRelation(
    source: json['source'] as String,
    predicate: json['predicate'] as String,
    target: json['target'] as String,
    weight: (json['weight'] as num?)?.toDouble() ?? 1.0,
  );
}

/// Mirrors contracts/graph.py::GraphRAGResponse.
class GraphRAGResponse {
  final String query;
  final List<GraphEntity> matchedEntities;
  final List<GraphRelation> relations;
  final String subgraphText;
  final List<String> connectedChunkIds;
  final double durationMs;

  const GraphRAGResponse({
    required this.query,
    this.matchedEntities = const [],
    this.relations = const [],
    this.subgraphText = '',
    this.connectedChunkIds = const [],
    this.durationMs = 0,
  });

  factory GraphRAGResponse.fromJson(Map<String, dynamic> json) =>
      GraphRAGResponse(
        query: json['query'] as String? ?? '',
        matchedEntities: (json['matched_entities'] as List<dynamic>? ?? [])
            .map((e) => GraphEntity.fromJson(e as Map<String, dynamic>))
            .toList(),
        relations: (json['relations'] as List<dynamic>? ?? [])
            .map((e) => GraphRelation.fromJson(e as Map<String, dynamic>))
            .toList(),
        subgraphText: json['subgraph_text'] as String? ?? '',
        connectedChunkIds: (json['connected_chunk_ids'] as List<dynamic>? ?? [])
            .map((e) => e as String)
            .toList(),
        durationMs: (json['duration_ms'] as num?)?.toDouble() ?? 0,
      );

  /// Unique node names across matched entities and relation endpoints, for the force layout.
  List<String> get nodeNames {
    final names = <String>{for (final e in matchedEntities) e.name};
    for (final r in relations) {
      names.add(r.source);
      names.add(r.target);
    }
    return names.toList();
  }
}

/// `GET /api/v1/graph/stats` is a loose dict on the wire, not a formal Pydantic contract.
class GraphStats {
  final int entityCount;
  final int relationCount;
  final int communityCount;
  final Map<String, int> categoryCounts;
  final Map<String, int> predicateCounts;

  const GraphStats({
    this.entityCount = 0,
    this.relationCount = 0,
    this.communityCount = 0,
    this.categoryCounts = const {},
    this.predicateCounts = const {},
  });

  factory GraphStats.fromJson(Map<String, dynamic> json) => GraphStats(
    entityCount:
        json['entity_count'] as int? ?? json['num_entities'] as int? ?? 0,
    relationCount:
        json['relation_count'] as int? ?? json['num_relations'] as int? ?? 0,
    communityCount:
        json['community_count'] as int? ?? json['num_communities'] as int? ?? 0,
    categoryCounts:
        ((json['category_counts'] ?? json['categories'])
                    as Map<String, dynamic>? ??
                const {})
            .map((k, v) => MapEntry(k, (v as num).toInt())),
    predicateCounts:
        ((json['predicate_counts'] ?? json['predicates'])
                    as Map<String, dynamic>? ??
                const {})
            .map((k, v) => MapEntry(k, (v as num).toInt())),
  );
}
