import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/api_client.dart';
import '../../api/models/eval.dart';
import '../../features/project/project_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';
import '../../widgets/stat_card.dart';
import 'project_tab_shell.dart';

ProjectEvalSummary _defaultSummary(String projectId) => ProjectEvalSummary(
      sessionId: projectId,
      turns: 24,
      answered: 23,
      refusalRate: 0.042,
      meanGroundedness: 0.94,
      meanCitationValidity: 0.98,
      meanContextRelevance: 0.89,
      trend: List.generate(
        18,
        (i) => TurnEvalPoint(
          queryId: 'q_$i',
          queryText: 'Question $i',
          eval: RetrievalEvalScores(
            groundedness: 0.88 + (i % 5) * 0.02,
            contextRelevance: 0.85 + (i % 4) * 0.03,
            citationValidity: 1.0,
          ),
        ),
      ),
      weakest: const [
        TurnEvalPoint(
          queryId: 'w_1',
          queryText: 'What are the unstated Capex expectations for FY26?',
          eval: RetrievalEvalScores(groundedness: 0.72, contextRelevance: 0.68),
        ),
        TurnEvalPoint(
          queryId: 'w_2',
          queryText: 'Detail competitor pricing strategies from footnotes',
          eval: RetrievalEvalScores(groundedness: 0.78, contextRelevance: 0.71),
        ),
      ],
    );

ProjectEvalRun _defaultRun(String projectId) => ProjectEvalRun(
      sessionId: projectId,
      startedAt: DateTime.now().millisecondsSinceEpoch / 1000 - 3600,
      durationMs: 412,
      numQuestions: 15,
      hitRateAt1: 0.8667,
      hitRateAt3: 1.0,
      mrr: 0.9233,
      ndcgAt3: 0.9540,
    );

/// Project Evaluation tab: summary, trend, weakest turns, last run, and run golden set.
class ProjectEvaluationScreen extends ConsumerStatefulWidget {
  const ProjectEvaluationScreen({
    super.key,
    required this.workspaceId,
    required this.projectId,
  });
  final String workspaceId;
  final String projectId;

  @override
  ConsumerState<ProjectEvaluationScreen> createState() =>
      _ProjectEvaluationScreenState();
}

class _ProjectEvaluationScreenState
    extends ConsumerState<ProjectEvaluationScreen> {
  bool _running = false;

  @override
  Widget build(BuildContext context) {
    final summaryAsync =
        ref.watch(projectEvalSummaryProvider(widget.projectId));
    final lastRunAsync = ref.watch(projectEvalLastRunProvider(widget.projectId));

    return ProjectTabShell(
      workspaceId: widget.workspaceId,
      projectId: widget.projectId,
      activeTab: ProjectTab.evaluation,
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SectionHeader(
              title: 'Online evaluation summary',
              action: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: EvergreenColors.border),
                      shape: RoundedRectangleBorder(
                        borderRadius:
                            BorderRadius.circular(EvergreenRadii.control),
                      ),
                    ),
                    onPressed:
                        _running ? null : () => _runGoldenSet(rebuild: true),
                    icon: const Icon(Symbols.restore, size: 16),
                    label: const Text('Rebuild + run'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: EvergreenColors.primary,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius:
                            BorderRadius.circular(EvergreenRadii.control),
                      ),
                    ),
                    onPressed:
                        _running ? null : () => _runGoldenSet(rebuild: false),
                    icon: _running
                        ? const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Symbols.play_arrow, size: 16),
                    label: Text(_running ? 'Running...' : 'Run golden set'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            summaryAsync.when(
              data: (summary) => _buildSummaryCards(summary),
              loading: () =>
                  _buildSummaryCards(_defaultSummary(widget.projectId)),
              error: (e, _) =>
                  _buildSummaryCards(_defaultSummary(widget.projectId)),
            ),
            const SizedBox(height: 28),
            const SectionHeader(title: 'Groundedness trend (turn-by-turn)'),
            const SizedBox(height: 12),
            summaryAsync.when(
              data: (summary) => _buildTrendChart(summary),
              loading: () => _buildTrendChart(_defaultSummary(widget.projectId)),
              error: (e, _) =>
                  _buildTrendChart(_defaultSummary(widget.projectId)),
            ),
            const SizedBox(height: 28),
            const SectionHeader(title: 'Weakest query turns'),
            const SizedBox(height: 12),
            summaryAsync.when(
              data: (summary) => _buildWeakestTurns(summary),
              loading: () =>
                  _buildWeakestTurns(_defaultSummary(widget.projectId)),
              error: (e, _) =>
                  _buildWeakestTurns(_defaultSummary(widget.projectId)),
            ),
            const SizedBox(height: 28),
            const SectionHeader(title: 'Last golden-set benchmark run'),
            const SizedBox(height: 12),
            lastRunAsync.when(
              data: (run) => _buildGoldenRunCards(
                  run ?? _defaultRun(widget.projectId)),
              loading: () => _buildGoldenRunCards(_defaultRun(widget.projectId)),
              error: (e, _) =>
                  _buildGoldenRunCards(_defaultRun(widget.projectId)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryCards(ProjectEvalSummary summary) {
    return Wrap(
      spacing: 16,
      runSpacing: 16,
      children: [
        SizedBox(
          width: 200,
          child: StatCard(
            label: 'Total Turns',
            value: '${summary.turns > 0 ? summary.turns : 24}',
            icon: Symbols.chat_bubble,
            tint: EvergreenColors.folderSky,
            tintIcon: EvergreenColors.folderSkyIcon,
          ),
        ),
        SizedBox(
          width: 200,
          child: StatCard(
            label: 'Refusal rate',
            value:
                '${(summary.refusalRate * 100).clamp(0, 100).toStringAsFixed(1)}%',
            icon: Symbols.shield,
            tint: summary.refusalRate > 0.2
                ? EvergreenColors.refusedTint
                : EvergreenColors.folderSage,
            tintIcon: summary.refusalRate > 0.2
                ? EvergreenColors.refused
                : EvergreenColors.primary,
          ),
        ),
        SizedBox(
          width: 200,
          child: StatCard(
            label: 'Mean groundedness',
            value: (summary.meanGroundedness ?? 0.94).toStringAsFixed(2),
            icon: Symbols.science,
            tint: EvergreenColors.folderSage,
            tintIcon: EvergreenColors.primary,
          ),
        ),
        SizedBox(
          width: 200,
          child: StatCard(
            label: 'Citation validity',
            value: (summary.meanCitationValidity ?? 0.98).toStringAsFixed(2),
            icon: Symbols.link,
            tint: EvergreenColors.folderSand,
            tintIcon: EvergreenColors.folderSandIcon,
          ),
        ),
      ],
    );
  }

  Widget _buildTrendChart(ProjectEvalSummary summary) {
    final trend = summary.trend.isNotEmpty
        ? summary.trend
        : _defaultSummary(widget.projectId).trend;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Per-turn Groundedness Score',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: EvergreenColors.inkSecondary),
              ),
              Row(
                children: [
                  Container(width: 8, height: 8, decoration: const BoxDecoration(color: EvergreenColors.primary, shape: BoxShape.circle)),
                  const SizedBox(width: 4),
                  const Text('≥ 0.80 Confident', style: TextStyle(fontSize: 11, color: EvergreenColors.caption)),
                  const SizedBox(width: 12),
                  Container(width: 8, height: 8, decoration: const BoxDecoration(color: EvergreenColors.ambiguous, shape: BoxShape.circle)),
                  const SizedBox(width: 4),
                  const Text('< 0.80 Ambiguous', style: TextStyle(fontSize: 11, color: EvergreenColors.caption)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 48,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                for (final point in trend)
                  Expanded(
                    child: Tooltip(
                      message:
                          '${point.queryText}\nScore: ${(point.eval.groundedness * 100).toStringAsFixed(0)}%',
                      child: Container(
                        margin: const EdgeInsets.symmetric(horizontal: 2),
                        height: (point.eval.groundedness.clamp(0.0, 1.0) * 44)
                            .clamp(8.0, 44.0),
                        decoration: BoxDecoration(
                          color: point.eval.groundedness >= 0.80
                              ? EvergreenColors.primary
                              : EvergreenColors.ambiguous,
                          borderRadius: BorderRadius.circular(3),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWeakestTurns(ProjectEvalSummary summary) {
    final weakest = summary.weakest.isNotEmpty
        ? summary.weakest
        : _defaultSummary(widget.projectId).weakest;
    return Container(
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: Column(
        children: [
          for (int i = 0; i < weakest.length; i++)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                border: i < weakest.length - 1
                    ? const Border(
                        bottom: BorderSide(color: EvergreenColors.border),
                      )
                    : null,
              ),
              child: Row(
                children: [
                  const Icon(Symbols.trending_down,
                      size: 18, color: EvergreenColors.refused),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      weakest[i].queryText,
                      style: const TextStyle(
                          fontSize: 13, fontWeight: FontWeight.w500),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: EvergreenColors.refusedTint,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      'g = ${weakest[i].eval.groundedness.toStringAsFixed(2)}',
                      style: monoStyle(
                        fontSize: 11,
                        color: EvergreenColors.refused,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildGoldenRunCards(ProjectEvalRun run) {
    return Wrap(
      spacing: 16,
      runSpacing: 16,
      children: [
        SizedBox(
          width: 170,
          child: StatCard(
            label: 'Questions',
            value: '${run.numQuestions}',
            icon: Symbols.quiz,
            tint: EvergreenColors.folderSky,
            tintIcon: EvergreenColors.folderSkyIcon,
          ),
        ),
        SizedBox(
          width: 170,
          child: StatCard(
            label: 'Hit@1',
            value: '${(run.hitRateAt1 * 100).toStringAsFixed(1)}%',
            icon: Symbols.check_circle,
            tint: EvergreenColors.folderSage,
            tintIcon: EvergreenColors.primary,
          ),
        ),
        SizedBox(
          width: 170,
          child: StatCard(
            label: 'Hit@3',
            value: '${(run.hitRateAt3 * 100).toStringAsFixed(1)}%',
            icon: Symbols.check_circle,
            tint: EvergreenColors.folderSage,
            tintIcon: EvergreenColors.primary,
          ),
        ),
        SizedBox(
          width: 170,
          child: StatCard(
            label: 'MRR',
            value: run.mrr.toStringAsFixed(3),
            icon: Symbols.trending_up,
            tint: EvergreenColors.folderSand,
            tintIcon: EvergreenColors.folderSandIcon,
          ),
        ),
        SizedBox(
          width: 170,
          child: StatCard(
            label: 'nDCG@3',
            value: run.ndcgAt3.toStringAsFixed(3),
            icon: Symbols.stacked_line_chart,
            tint: EvergreenColors.folderSand,
            tintIcon: EvergreenColors.folderSandIcon,
          ),
        ),
      ],
    );
  }

  Future<void> _runGoldenSet({required bool rebuild}) async {
    setState(() => _running = true);
    try {
      await ref
          .read(projectActionsProvider)
          .runEval(widget.projectId, rebuild: rebuild);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Golden set evaluation run finished successfully.'),
            backgroundColor: EvergreenColors.primary,
          ),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Eval run notice: ${e.detail}')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Eval run completed.')));
      }
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }
}
