import 'package:flutter/material.dart';
import '../api/models/eval.dart';
import '../theme/evergreen_theme.dart';

/// Compact evaluation scores strip rendering real verification telemetry
/// (groundedness, context relevance, citation validity, CRAG status, latency/throughput).
class EvalStrip extends StatelessWidget {
  const EvalStrip({
    super.key,
    this.evalScores,
    this.latencyMs,
    this.tokensPerSec,
  });

  final RetrievalEvalScores? evalScores;
  final double? latencyMs;
  final double? tokensPerSec;

  static String _pct(double val) => '${(val * 100).round()}%';

  @override
  Widget build(BuildContext context) {
    final ev = evalScores;
    final hasLatency = latencyMs != null && latencyMs! > 0;
    final hasSpeed = tokensPerSec != null && tokensPerSec! > 0;

    if (ev == null && !hasLatency) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: EvergreenColors.fill,
        borderRadius: BorderRadius.circular(EvergreenRadii.chip),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: Wrap(
        spacing: 12,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          if (ev != null && ev.groundedness > 0)
            _EvalBadge(
              label: 'grounded',
              value: _pct(ev.groundedness),
              isLow: ev.groundedness < 0.5,
              tooltip: 'Answer sentences directly supported by retrieved evidence (${_pct(ev.groundedness)})',
            ),
          if (ev != null && ev.contextRelevance > 0)
            _EvalBadge(
              label: 'relevance',
              value: _pct(ev.contextRelevance),
              isLow: ev.contextRelevance < 0.25,
              tooltip: 'Mean cross-encoder relevance score of retrieved passages (${_pct(ev.contextRelevance)})',
            ),
          if (ev != null && ev.citationValidity > 0)
            _EvalBadge(
              label: 'citations',
              value: _pct(ev.citationValidity),
              tooltip: 'Citations verified with document ID, page, and visual bounding box',
            ),
          if (ev?.llmJudgeGroundedness != null)
            _EvalBadge(
              label: 'judge',
              value: _pct(ev!.llmJudgeGroundedness!),
              tooltip: 'Background sampled LLM-judge groundedness verdict',
            ),
          if (ev?.cragStatus != null && ev!.cragStatus!.isNotEmpty)
            _EvalBadge(
              label: 'crag',
              value: ev.cragStatus!.toLowerCase(),
              tooltip: 'Corrective-RAG reflection confidence status',
            ),
          if (hasLatency)
            Tooltip(
              message: 'Total pipeline execution time${hasSpeed ? ' and token generation throughput' : ''}',
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'speed ',
                    style: monoStyle(fontSize: 10, color: EvergreenColors.caption),
                  ),
                  Text(
                    '${(latencyMs! / 1000).toStringAsFixed(1)}s${hasSpeed ? ' · ${tokensPerSec!.toStringAsFixed(1)} t/s' : ''}',
                    style: monoStyle(fontSize: 11, weight: FontWeight.w600, color: EvergreenColors.inkSecondary),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _EvalBadge extends StatelessWidget {
  const _EvalBadge({
    required this.label,
    required this.value,
    this.isLow = false,
    required this.tooltip,
  });

  final String label;
  final String value;
  final bool isLow;
  final String tooltip;

  @override
  Widget build(BuildContext context) {
    final valueColor = isLow ? EvergreenColors.refused : EvergreenColors.ink;
    return Tooltip(
      message: tooltip,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '$label ',
            style: monoStyle(
              fontSize: 10,
              color: isLow ? EvergreenColors.refused.withValues(alpha: 0.8) : EvergreenColors.caption,
            ),
          ),
          Text(
            value,
            style: monoStyle(
              fontSize: 11,
              weight: FontWeight.w600,
              color: valueColor,
            ),
          ),
        ],
      ),
    );
  }
}
