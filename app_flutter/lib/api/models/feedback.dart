/// Mirrors contracts/feedback.py::FeedbackRequest/FeedbackRecord.
class FeedbackRecord {
  final String id;
  final String rating; // thumbs_up | thumbs_down
  final String? comment;

  const FeedbackRecord({required this.id, required this.rating, this.comment});

  factory FeedbackRecord.fromJson(Map<String, dynamic> json) => FeedbackRecord(
    id: json['id'] as String,
    rating: json['rating'] as String,
    comment: json['comment'] as String?,
  );
}

/// Mirrors contracts/feedback.py::RAGOpsSummary.
class RAGOpsSummary {
  final int totalFeedback;
  final int thumbsUp;
  final int thumbsDown;
  final double satisfactionRatePct;
  final int hardNegativesCount;

  const RAGOpsSummary({
    this.totalFeedback = 0,
    this.thumbsUp = 0,
    this.thumbsDown = 0,
    this.satisfactionRatePct = 0,
    this.hardNegativesCount = 0,
  });

  factory RAGOpsSummary.fromJson(Map<String, dynamic> json) => RAGOpsSummary(
    totalFeedback: json['total_feedback'] as int? ?? 0,
    thumbsUp: json['thumbs_up'] as int? ?? 0,
    thumbsDown: json['thumbs_down'] as int? ?? 0,
    satisfactionRatePct:
        (json['satisfaction_rate_pct'] as num?)?.toDouble() ?? 0,
    hardNegativesCount: json['hard_negatives_count'] as int? ?? 0,
  );
}
