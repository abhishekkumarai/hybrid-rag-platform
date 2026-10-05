/// Mirrors contracts/ingest_job.py::IngestJob (IRA-60): a source being parsed, indexed and attached
/// to a project by the gateway in the background.
class IngestJob {
  final String id;
  final String sessionId;
  final String kind; // file | url
  final String source; // filename, or the URL for a web source
  final String status; // queued | running | done | failed
  final String stage;
  final String? docId;
  final int? blocks;
  final String? error;

  const IngestJob({
    required this.id,
    required this.sessionId,
    required this.kind,
    required this.source,
    this.status = 'queued',
    this.stage = 'Queued',
    this.docId,
    this.blocks,
    this.error,
  });

  factory IngestJob.fromJson(Map<String, dynamic> json) => IngestJob(
        id: json['id'] as String,
        sessionId: json['session_id'] as String,
        kind: json['kind'] as String? ?? 'file',
        source: json['source'] as String? ?? '',
        status: json['status'] as String? ?? 'queued',
        stage: json['stage'] as String? ?? '',
        docId: json['doc_id'] as String?,
        blocks: json['blocks'] as int?,
        error: json['error'] as String?,
      );

  bool get isActive => status == 'queued' || status == 'running';
  bool get isFailed => status == 'failed';
  bool get isDone => status == 'done';

  /// True for the placeholder shown while the file is still being sent to the gateway (no server job
  /// exists yet), or for an upload that failed before one was created.
  bool get isLocal => id.startsWith(localPrefix);

  static const localPrefix = 'local_';
}
