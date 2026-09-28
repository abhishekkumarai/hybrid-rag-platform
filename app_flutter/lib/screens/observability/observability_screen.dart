import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../features/admin/admin_providers.dart';
import '../../features/workspace/workspace_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';
import '../../widgets/stat_card.dart';

/// DESIGN-evergreen.md Observability page: tiles (retrieval/generation ms, tokens, refusals,
/// Qdrant, BM25, queue, DLQ), recent telemetry table, admin DLQ replay.
class ObservabilityScreen extends ConsumerWidget {
  const ObservabilityScreen({super.key, required this.workspaceId});
  final String workspaceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final metricsAsync = ref.watch(workspaceMetricsProvider(null));
    final queueAsync = ref.watch(queueStatsProvider);
    final auth = ref.watch(authProvider);
    final isAdmin = auth is AuthSignedIn && auth.user.isAdmin;

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Observability',
                style: Theme.of(context).textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 20),
              metricsAsync.when(
                data: (m) => Wrap(
                  spacing: 16,
                  runSpacing: 16,
                  children: [
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Retrieval ms',
                        value: m.avgRetrievalMs.toStringAsFixed(0),
                        icon: Symbols.search,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Generation ms',
                        value: m.avgGenerationMs.toStringAsFixed(0),
                        icon: Symbols.bolt,
                        tint: EvergreenColors.folderSky,
                        tintIcon: EvergreenColors.folderSkyIcon,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Tokens/sec',
                        value: m.avgTokensPerSec.toStringAsFixed(1),
                        icon: Symbols.speed,
                        tint: EvergreenColors.folderSand,
                        tintIcon: EvergreenColors.folderSandIcon,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Refusals',
                        value: '${m.totalRefusals}',
                        icon: Symbols.block,
                        tint: EvergreenColors.refusedTint,
                        tintIcon: EvergreenColors.refused,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Qdrant points',
                        value: '${m.qdrantPoints}',
                        icon: Symbols.database,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Redis queue depth',
                        value: '${m.redisQueueDepth}',
                        icon: Symbols.queue,
                        tint: EvergreenColors.folderSky,
                        tintIcon: EvergreenColors.folderSkyIcon,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'DLQ tasks',
                        value: '${m.dlqTaskCount}',
                        icon: Symbols.error,
                        tint: EvergreenColors.refusedTint,
                        tintIcon: EvergreenColors.refused,
                      ),
                    ),
                  ],
                ),
                loading: () => const SizedBox(
                  height: 96,
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (e, _) => const Text(
                  'Could not reach the gateway for metrics.',
                  style: TextStyle(color: EvergreenColors.caption),
                ),
              ),
              const SizedBox(height: 28),
              const SectionHeader(title: 'Queue'),
              queueAsync.when(
                data: (stats) => Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final entry in stats.entries)
                      _QueueChip(label: entry.key, value: entry.value),
                  ],
                ),
                loading: () => const LinearProgressIndicator(),
                error: (e, _) => const Text(
                  'Could not load queue stats.',
                  style: TextStyle(color: EvergreenColors.caption),
                ),
              ),
              if (isAdmin) ...[
                const SizedBox(height: 28),
                SectionHeader(
                  title: 'Dead-letter queue',
                  action: TextButton.icon(
                    onPressed: () => ref.read(adminActionsProvider).replayDlq(),
                    icon: const Icon(Symbols.replay, size: 16),
                    label: const Text('Replay all'),
                  ),
                ),
                const _DlqTable(),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _QueueChip extends StatelessWidget {
  const _QueueChip({required this.label, required this.value});
  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.control),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: Text('$label: $value', style: monoStyle(fontSize: 12)),
    );
  }
}

class _DlqTable extends ConsumerWidget {
  const _DlqTable();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dlqAsync = ref.watch(dlqListProvider);
    return dlqAsync.when(
      data: (items) {
        if (items.isEmpty) {
          return const EmptyState(
            message: 'No dead-letter tasks.',
            icon: Symbols.check_circle,
          );
        }
        return Container(
          decoration: BoxDecoration(
            color: EvergreenColors.surface,
            borderRadius: BorderRadius.circular(EvergreenRadii.panel),
            border: Border.all(color: EvergreenColors.border),
          ),
          child: Column(
            children: [
              for (final item in items)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 10,
                  ),
                  decoration: const BoxDecoration(
                    border: Border(
                      bottom: BorderSide(color: EvergreenColors.border),
                    ),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          '${item['task_id'] ?? item['id'] ?? 'unknown'}',
                          style: monoStyle(fontSize: 12),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      Text(
                        '${item['error'] ?? ''}',
                        style: const TextStyle(
                          fontSize: 12,
                          color: EvergreenColors.refused,
                        ),
                      ),
                      const SizedBox(width: 12),
                      TextButton(
                        onPressed: () => ref
                            .read(adminActionsProvider)
                            .replayDlq(
                              taskId: '${item['task_id'] ?? item['id']}',
                            ),
                        child: const Text('Replay'),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        );
      },
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => e is ApiException && e.statusCode == 403
          ? const Text(
              'Admin access required.',
              style: TextStyle(color: EvergreenColors.caption),
            )
          : Text(
              'Failed to load DLQ: $e',
              style: const TextStyle(color: EvergreenColors.refused),
            ),
    );
  }
}
