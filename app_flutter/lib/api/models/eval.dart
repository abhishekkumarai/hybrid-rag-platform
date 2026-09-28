/// Mirrors contracts/metrics.py::RetrievalEvalScores.
class RetrievalEvalScores {
  final double contextRelevance;
  final double groundedness;
  final double citationValidity;
  final String? cragStatus;
  final double? llmJudgeGroundedness;

  const RetrievalEvalScores({
    this.contextRelevance = 0,
    this.groundedness = 0,
    this.citationValidity = 0,
    this.cragStatus,
    this.llmJudgeGroundedness,
  });

  factory RetrievalEvalScores.fromJson(Map<String, dynamic> json) => RetrievalEvalScores(
        contextRelevance: (json['context_relevance'] as num?)?.toDouble() ?? 0,
        groundedness: (json['groundedness'] as num?)?.toDouble() ?? 0,
        citationValidity: (json['citation_validity'] as num?)?.toDouble() ?? 0,
        cragStatus: json['crag_status'] as String?,
        llmJudgeGroundedness: (json['llm_judge_groundedness'] as num?)?.toDouble(),
      );
}

/// Mirrors contracts/metrics.py::TurnEvalPoint.
class TurnEvalPoint {
  final String queryId;
  final String queryText;
  final double timestamp;
  final RetrievalEvalScores eval;

  const TurnEvalPoint({
    required this.queryId,
    required this.queryText,
    this.timestamp = 0,
    this.eval = const RetrievalEvalScores(),
  });

  factory TurnEvalPoint.fromJson(Map<String, dynamic> json) => TurnEvalPoint(
        queryId: json['query_id'] as String,
        queryText: json['query_text'] as String,
        timestamp: (json['timestamp'] as num?)?.toDouble() ?? 0,
        eval: RetrievalEvalScores.fromJson(json['eval'] as Map<String, dynamic>? ?? const {}),
      );
}

/// Mirrors contracts/metrics.py::ProjectEvalSummary.
class ProjectEvalSummary {
  final String sessionId;
  final int turns;
  final int answered;
  final double refusalRate;
  final double? meanGroundedness;
  final double? meanContextRelevance;
  final double? meanCitationValidity;
  final double? meanLlmJudge;
  final int judgedTurns;
  final List<TurnEvalPoint> trend;
  final List<TurnEvalPoint> weakest;

  const ProjectEvalSummary({
    required this.sessionId,
    this.turns = 0,
    this.answered = 0,
    this.refusalRate = 0,
    this.meanGroundedness,
    this.meanContextRelevance,
    this.meanCitationValidity,
    this.meanLlmJudge,
    this.judgedTurns = 0,
    this.trend = const [],
    this.weakest = const [],
  });

  factory ProjectEvalSummary.fromJson(Map<String, dynamic> json) => ProjectEvalSummary(
        sessionId: json['session_id'] as String,
        turns: json['turns'] as int? ?? 0,
        answered: json['answered'] as int? ?? 0,
        refusalRate: (json['refusal_rate'] as num?)?.toDouble() ?? 0,
        meanGroundedness: (json['mean_groundedness'] as num?)?.toDouble(),
        meanContextRelevance: (json['mean_context_relevance'] as num?)?.toDouble(),
        meanCitationValidity: (json['mean_citation_validity'] as num?)?.toDouble(),
        meanLlmJudge: (json['mean_llm_judge'] as num?)?.toDouble(),
        judgedTurns: json['judged_turns'] as int? ?? 0,
        trend: (json['trend'] as List<dynamic>? ?? [])
            .map((e) => TurnEvalPoint.fromJson(e as Map<String, dynamic>))
            .toList(),
        weakest: (json['weakest'] as List<dynamic>? ?? [])
            .map((e) => TurnEvalPoint.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

/// Mirrors contracts/metrics.py::GoldenQueryResult.
class GoldenQueryResult {
  final String question;
  final int? rank;
  final double topScore;
  final bool refused;

  const GoldenQueryResult({required this.question, this.rank, this.topScore = 0, this.refused = false});

  factory GoldenQueryResult.fromJson(Map<String, dynamic> json) => GoldenQueryResult(
        question: json['question'] as String,
        rank: json['rank'] as int?,
        topScore: (json['top_score'] as num?)?.toDouble() ?? 0,
        refused: json['refused'] as bool? ?? false,
      );
}

/// Mirrors contracts/metrics.py::ProjectEvalRun.
class ProjectEvalRun {
  final String sessionId;
  final double startedAt;
  final double durationMs;
  final int numQuestions;
  final double hitRateAt1;
  final double hitRateAt3;
  final double mrr;
  final double ndcgAt3;
  final double refusalRate;
  final List<GoldenQueryResult> results;

  const ProjectEvalRun({
    required this.sessionId,
    this.startedAt = 0,
    this.durationMs = 0,
    this.numQuestions = 0,
    this.hitRateAt1 = 0,
    this.hitRateAt3 = 0,
    this.mrr = 0,
    this.ndcgAt3 = 0,
    this.refusalRate = 0,
    this.results = const [],
  });

  factory ProjectEvalRun.fromJson(Map<String, dynamic> json) => ProjectEvalRun(
        sessionId: json['session_id'] as String,
        startedAt: (json['started_at'] as num?)?.toDouble() ?? 0,
        durationMs: (json['duration_ms'] as num?)?.toDouble() ?? 0,
        numQuestions: json['num_questions'] as int? ?? 0,
        hitRateAt1: (json['hit_rate_at_1'] as num?)?.toDouble() ?? 0,
        hitRateAt3: (json['hit_rate_at_3'] as num?)?.toDouble() ?? 0,
        mrr: (json['mrr'] as num?)?.toDouble() ?? 0,
        ndcgAt3: (json['ndcg_at_3'] as num?)?.toDouble() ?? 0,
        refusalRate: (json['refusal_rate'] as num?)?.toDouble() ?? 0,
        results: (json['results'] as List<dynamic>? ?? [])
            .map((e) => GoldenQueryResult.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
