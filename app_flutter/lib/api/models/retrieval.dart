/// Mirrors contracts/retrieval.py.
class Citation {
  final String docId;
  final int page;
  final List<double> bbox;
  final String snippet;
  final String formattedBadge;
  final bool isTable;
  final bool isFigure;
  final String? imagePath;
  final bool isWeb;
  final String? webUrl;
  final String? resourceUrl;
  final String? resourceTitle;

  const Citation({
    required this.docId,
    required this.page,
    required this.bbox,
    required this.snippet,
    required this.formattedBadge,
    this.isTable = false,
    this.isFigure = false,
    this.imagePath,
    this.isWeb = false,
    this.webUrl,
    this.resourceUrl,
    this.resourceTitle,
  });

  factory Citation.fromJson(Map<String, dynamic> json) => Citation(
        docId: json['doc_id'] as String,
        page: json['page'] as int,
        bbox: (json['bbox'] as List).map((e) => (e as num).toDouble()).toList(),
        snippet: json['snippet'] as String,
        formattedBadge: json['formatted_badge'] as String,
        isTable: json['is_table'] as bool? ?? false,
        isFigure: json['is_figure'] as bool? ?? false,
        imagePath: json['image_path'] as String?,
        isWeb: json['is_web'] as bool? ?? false,
        webUrl: json['web_url'] as String?,
        resourceUrl: json['resource_url'] as String?,
        resourceTitle: json['resource_title'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'doc_id': docId,
        'page': page,
        'bbox': bbox,
        'snippet': snippet,
        'formatted_badge': formattedBadge,
        'is_table': isTable,
        'is_figure': isFigure,
        'image_path': imagePath,
        'is_web': isWeb,
        'web_url': webUrl,
        'resource_url': resourceUrl,
        'resource_title': resourceTitle,
      };
}
