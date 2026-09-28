/// A row of `GET /api/v1/documents` (dict-shaped on the wire, not a formal Pydantic contract).
class DocumentInfo {
  final String name;
  final String docId;
  final int pages;
  final double sizeKb;
  final bool isWeb;
  final bool readOnly;
  final String? url;
  final String? category;

  const DocumentInfo({
    required this.name,
    required this.docId,
    this.pages = 1,
    this.sizeKb = 0,
    this.isWeb = false,
    this.readOnly = false,
    this.url,
    this.category,
  });

  factory DocumentInfo.fromJson(Map<String, dynamic> json) => DocumentInfo(
        name: json['name'] as String? ?? json['doc_id'] as String,
        docId: json['doc_id'] as String,
        pages: json['pages'] as int? ?? 1,
        sizeKb: (json['size_kb'] as num?)?.toDouble() ?? 0,
        isWeb: json['is_web'] as bool? ?? false,
        readOnly: json['read_only'] as bool? ?? false,
        url: json['url'] as String?,
        category: json['category'] as String?,
      );
}

/// Mirrors contracts/document.py::DocumentProfile.
class DocumentProfile {
  final String route; // fast_text | layout | ocr | paddleocr
  final int pageCount;
  final String reason;

  const DocumentProfile({required this.route, this.pageCount = 0, this.reason = ''});

  factory DocumentProfile.fromJson(Map<String, dynamic> json) => DocumentProfile(
        route: json['route'] as String,
        pageCount: json['page_count'] as int? ?? 0,
        reason: json['reason'] as String? ?? '',
      );
}

/// Mirrors contracts/document.py::IngestResponse. `blocks` is round-tripped opaquely (raw JSON)
/// straight into `/api/v1/index` — the UI never needs to inspect block fields itself.
class IngestResponse {
  final String docId;
  final DocumentProfile profile;
  final List<dynamic> blocks;
  final double durationMs;
  final String? error;

  const IngestResponse({
    required this.docId,
    required this.profile,
    this.blocks = const [],
    this.durationMs = 0,
    this.error,
  });

  factory IngestResponse.fromJson(Map<String, dynamic> json) => IngestResponse(
        docId: json['doc_id'] as String,
        profile: DocumentProfile.fromJson(json['profile'] as Map<String, dynamic>),
        blocks: json['blocks'] as List<dynamic>? ?? [],
        durationMs: (json['duration_ms'] as num?)?.toDouble() ?? 0,
        error: json['error'] as String?,
      );
}

/// Mirrors contracts/chunk.py::IndexResponse.
class IndexResponse {
  final String docId;
  final int indexedCount;
  final bool denseIndexed;
  final bool sparseIndexed;
  final bool graphIndexed;

  const IndexResponse({
    required this.docId,
    this.indexedCount = 0,
    this.denseIndexed = true,
    this.sparseIndexed = true,
    this.graphIndexed = true,
  });

  factory IndexResponse.fromJson(Map<String, dynamic> json) => IndexResponse(
        docId: json['doc_id'] as String,
        indexedCount: json['indexed_count'] as int? ?? 0,
        denseIndexed: json['dense_indexed'] as bool? ?? true,
        sparseIndexed: json['sparse_indexed'] as bool? ?? true,
        graphIndexed: json['graph_indexed'] as bool? ?? true,
      );
}
