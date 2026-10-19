/// Mirrors contracts/connector.py (IRA-57).
library;

double? _opt(Object? v) => (v as num?)?.toDouble();

class CrawlScope {
  final String pathPrefix;
  final int maxPages;
  final int maxDepth;
  final bool includeSubdomains;
  final bool useSitemap;
  final List<String> excludePatterns;

  const CrawlScope({
    this.pathPrefix = '/',
    this.maxPages = 100,
    this.maxDepth = 3,
    this.includeSubdomains = false,
    this.useSitemap = true,
    this.excludePatterns = const [],
  });

  factory CrawlScope.fromJson(Map<String, dynamic> json) => CrawlScope(
        pathPrefix: json['path_prefix'] as String? ?? '/',
        maxPages: json['max_pages'] as int? ?? 100,
        maxDepth: json['max_depth'] as int? ?? 3,
        includeSubdomains: json['include_subdomains'] as bool? ?? false,
        useSitemap: json['use_sitemap'] as bool? ?? true,
        excludePatterns: (json['exclude_patterns'] as List<dynamic>? ?? []).cast<String>(),
      );

  Map<String, dynamic> toJson() => {
        'path_prefix': pathPrefix,
        'max_pages': maxPages,
        'max_depth': maxDepth,
        'include_subdomains': includeSubdomains,
        'use_sitemap': useSitemap,
        'exclude_patterns': excludePatterns,
      };
}

class WebConnector {
  final String id;
  final String name;
  final String startUrl;
  final String? workspaceId;
  final String? projectId;
  final CrawlScope scope;
  final String render; // auto | static | browser
  final String schedule; // manual | daily | weekly
  final String status; // idle | queued | running | ok | partial | error
  final double? lastSyncAt;
  final double? lastSyncDurationS;
  final double? nextSyncAt;
  final int pageCount;
  final String? lastError;

  const WebConnector({
    required this.id,
    required this.name,
    required this.startUrl,
    this.workspaceId,
    this.projectId,
    this.scope = const CrawlScope(),
    this.render = 'auto',
    this.schedule = 'manual',
    this.status = 'idle',
    this.lastSyncAt,
    this.lastSyncDurationS,
    this.nextSyncAt,
    this.pageCount = 0,
    this.lastError,
  });

  bool get busy => status == 'queued' || status == 'running';

  factory WebConnector.fromJson(Map<String, dynamic> json) => WebConnector(
        id: json['id'] as String,
        name: json['name'] as String? ?? '',
        startUrl: json['start_url'] as String? ?? '',
        workspaceId: json['workspace_id'] as String?,
        projectId: json['project_id'] as String?,
        scope: CrawlScope.fromJson(json['scope'] as Map<String, dynamic>? ?? const {}),
        render: json['render'] as String? ?? 'auto',
        schedule: json['schedule'] as String? ?? 'manual',
        status: json['status'] as String? ?? 'idle',
        lastSyncAt: _opt(json['last_sync_at']),
        lastSyncDurationS: _opt(json['last_sync_duration_s']),
        nextSyncAt: _opt(json['next_sync_at']),
        pageCount: json['page_count'] as int? ?? 0,
        lastError: json['last_error'] as String?,
      );
}

class ConnectorPage {
  final String url;
  final String title;
  final String? docId;
  final String status; // indexed | unchanged | skipped | needs_js | error | removed
  final String renderedWith; // static | browser | pdf
  final int blocks;
  final int words;
  final int depth;
  final double? changedAt;
  final String? error;

  const ConnectorPage({
    required this.url,
    this.title = '',
    this.docId,
    this.status = 'indexed',
    this.renderedWith = 'static',
    this.blocks = 0,
    this.words = 0,
    this.depth = 0,
    this.changedAt,
    this.error,
  });

  factory ConnectorPage.fromJson(Map<String, dynamic> json) => ConnectorPage(
        url: json['url'] as String,
        title: json['title'] as String? ?? '',
        docId: json['doc_id'] as String?,
        status: json['status'] as String? ?? 'indexed',
        renderedWith: json['rendered_with'] as String? ?? 'static',
        blocks: json['blocks'] as int? ?? 0,
        words: json['words'] as int? ?? 0,
        depth: json['depth'] as int? ?? 0,
        changedAt: _opt(json['changed_at']),
        error: json['error'] as String?,
      );
}

class SyncReport {
  final double startedAt;
  final double finishedAt;
  final int pagesSeen;
  final int indexed;
  final int unchanged;
  final int removed;
  final int skipped;
  final int needsJs;
  final int errors;
  final String status;

  const SyncReport({
    this.startedAt = 0,
    this.finishedAt = 0,
    this.pagesSeen = 0,
    this.indexed = 0,
    this.unchanged = 0,
    this.removed = 0,
    this.skipped = 0,
    this.needsJs = 0,
    this.errors = 0,
    this.status = 'ok',
  });

  factory SyncReport.fromJson(Map<String, dynamic> json) => SyncReport(
        startedAt: _opt(json['started_at']) ?? 0,
        finishedAt: _opt(json['finished_at']) ?? 0,
        pagesSeen: json['pages_seen'] as int? ?? 0,
        indexed: json['indexed'] as int? ?? 0,
        unchanged: json['unchanged'] as int? ?? 0,
        removed: json['removed'] as int? ?? 0,
        skipped: json['skipped'] as int? ?? 0,
        needsJs: json['needs_js'] as int? ?? 0,
        errors: json['errors'] as int? ?? 0,
        status: json['status'] as String? ?? 'ok',
      );
}

class ConnectorDetail {
  final WebConnector connector;
  final List<ConnectorPage> pages;
  final SyncReport? lastReport;

  const ConnectorDetail({required this.connector, this.pages = const [], this.lastReport});

  factory ConnectorDetail.fromJson(Map<String, dynamic> json) => ConnectorDetail(
        connector: WebConnector.fromJson(json['connector'] as Map<String, dynamic>),
        pages: (json['pages'] as List<dynamic>? ?? []).map((e) => ConnectorPage.fromJson(e as Map<String, dynamic>)).toList(),
        lastReport: json['last_report'] == null ? null : SyncReport.fromJson(json['last_report'] as Map<String, dynamic>),
      );
}
