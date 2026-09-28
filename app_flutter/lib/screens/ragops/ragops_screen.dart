import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../features/admin/admin_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';
import '../../widgets/stat_card.dart';

/// DESIGN-evergreen.md RAGOps page: feedback totals, satisfaction, hard negatives, dataset export.
class RagOpsScreen extends ConsumerWidget {
  const RagOpsScreen({super.key, required this.workspaceId});
  final String workspaceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summaryAsync = ref.watch(ragopsSummaryProvider);
    final datasetAsync = ref.watch(ragopsDatasetProvider);

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'RAGOps',
                style: Theme.of(context).textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 20),
              summaryAsync.when(
                data: (s) => Wrap(
                  spacing: 16,
                  runSpacing: 16,
                  children: [
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Total feedback',
                        value: '${s.totalFeedback}',
                        icon: Symbols.feedback,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Satisfaction',
                        value: '${s.satisfactionRatePct.toStringAsFixed(1)}%',
                        icon: Symbols.thumb_up,
                        tint: EvergreenColors.confidentTint,
                        tintIcon: EvergreenColors.confident,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Thumbs up',
                        value: '${s.thumbsUp}',
                        icon: Symbols.thumb_up,
                        tint: EvergreenColors.confidentTint,
                        tintIcon: EvergreenColors.confident,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Thumbs down',
                        value: '${s.thumbsDown}',
                        icon: Symbols.thumb_down,
                        tint: EvergreenColors.refusedTint,
                        tintIcon: EvergreenColors.refused,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Hard negatives',
                        value: '${s.hardNegativesCount}',
                        icon: Symbols.science,
                        tint: EvergreenColors.folderSand,
                        tintIcon: EvergreenColors.folderSandIcon,
                      ),
                    ),
                  ],
                ),
                loading: () => const SizedBox(
                  height: 96,
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (e, _) => const Text(
                  'Could not load feedback summary (admin access required for the all-projects view).',
                  style: TextStyle(color: EvergreenColors.caption),
                ),
              ),
              const SizedBox(height: 28),
              SectionHeader(
                title: 'Hard-negative training dataset',
                action: TextButton.icon(
                  onPressed: datasetAsync.value == null
                      ? null
                      : () => _copyDataset(context, datasetAsync.value!),
                  icon: const Icon(Symbols.download, size: 16),
                  label: const Text('Export JSON'),
                ),
              ),
              datasetAsync.when(
                data: (rows) => rows.isEmpty
                    ? const EmptyState(
                        message: 'No hard negatives mined yet.',
                        icon: Symbols.science,
                      )
                    : Text(
                        '${rows.length} mined triplet(s) ready for export.',
                        style: const TextStyle(color: EvergreenColors.metadata),
                      ),
                loading: () => const LinearProgressIndicator(),
                error: (e, _) => const Text(
                  'Could not load the dataset export.',
                  style: TextStyle(color: EvergreenColors.caption),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _copyDataset(BuildContext context, List<Map<String, dynamic>> rows) {
    Clipboard.setData(ClipboardData(text: jsonEncode(rows)));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Copied ${rows.length} rows as JSON to the clipboard.'),
      ),
    );
  }
}
