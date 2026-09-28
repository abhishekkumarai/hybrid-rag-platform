import 'retrieval.dart';
import 'session.dart';

/// Mirrors contracts/share.py.
class SharedMessage {
  final String role;
  final String content;
  final List<Citation> citations;
  final double timestamp;

  const SharedMessage({
    required this.role,
    required this.content,
    this.citations = const [],
    this.timestamp = 0,
  });

  factory SharedMessage.fromJson(Map<String, dynamic> json) => SharedMessage(
        role: json['role'] as String,
        content: json['content'] as String,
        citations: (json['citations'] as List<dynamic>? ?? [])
            .map((e) => Citation.fromJson(e as Map<String, dynamic>))
            .toList(),
        timestamp: (json['timestamp'] as num?)?.toDouble() ?? 0,
      );
}

class ShareSnapshot {
  final String title;
  final String? systemPrompt;
  final SessionParameters parameters;
  final List<SharedMessage> messages;
  final List<String> docIds;
  final double createdAt;

  const ShareSnapshot({
    required this.title,
    this.systemPrompt,
    this.parameters = const SessionParameters(),
    this.messages = const [],
    this.docIds = const [],
    this.createdAt = 0,
  });

  factory ShareSnapshot.fromJson(Map<String, dynamic> json) => ShareSnapshot(
        title: json['title'] as String,
        systemPrompt: json['system_prompt'] as String?,
        parameters: json['parameters'] != null
            ? SessionParameters.fromJson(json['parameters'] as Map<String, dynamic>)
            : const SessionParameters(),
        messages: (json['messages'] as List<dynamic>? ?? [])
            .map((e) => SharedMessage.fromJson(e as Map<String, dynamic>))
            .toList(),
        docIds: (json['doc_ids'] as List<dynamic>? ?? []).cast<String>(),
        createdAt: (json['created_at'] as num?)?.toDouble() ?? 0,
      );
}

class ShareSummary {
  final String id;
  final String sessionId;
  final double createdAt;
  final int messageCount;
  final bool revoked;

  const ShareSummary({
    required this.id,
    required this.sessionId,
    this.createdAt = 0,
    this.messageCount = 0,
    this.revoked = false,
  });

  factory ShareSummary.fromJson(Map<String, dynamic> json) => ShareSummary(
        id: json['id'] as String,
        sessionId: json['session_id'] as String,
        createdAt: (json['created_at'] as num?)?.toDouble() ?? 0,
        messageCount: json['message_count'] as int? ?? 0,
        revoked: json['revoked'] as bool? ?? false,
      );
}

class CreateShareResponse {
  final String url;
  final String token;
  final ShareSummary share;

  const CreateShareResponse({required this.url, required this.token, required this.share});

  factory CreateShareResponse.fromJson(Map<String, dynamic> json) => CreateShareResponse(
        url: json['url'] as String,
        token: json['token'] as String,
        share: ShareSummary.fromJson(json['share'] as Map<String, dynamic>),
      );
}
