import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/auth_provider.dart';
import '../../api/models/metrics.dart';
import '../../api/models/session.dart';
import '../../features/project/project_providers.dart';
import '../../features/workspace/workspace_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/create_project_dialog.dart';

enum _ProjectFilter { all, mine, forked }

const _folderTints = [
  (fill: EvergreenColors.folderSage, icon: EvergreenColors.folderSageIcon),
  (fill: EvergreenColors.folderSky, icon: EvergreenColors.folderSkyIcon),
  (fill: EvergreenColors.folderSand, icon: EvergreenColors.folderSandIcon),
  (fill: EvergreenColors.folderRose, icon: EvergreenColors.folderRoseIcon),
];

/// Exactly mirrors `ui/stitch_workspace/01_workspace_overview.html`:
/// Top banner, 4 stat cards grid, 2-column layout (projects list on left, recent activity & infra on right).
class WorkspaceOverviewScreen extends ConsumerStatefulWidget {
  const WorkspaceOverviewScreen({super.key, required this.workspaceId});
  final String workspaceId;

  @override
  ConsumerState<WorkspaceOverviewScreen> createState() =>
      _WorkspaceOverviewScreenState();
}

class _WorkspaceOverviewScreenState
    extends ConsumerState<WorkspaceOverviewScreen> {
  _ProjectFilter _filter = _ProjectFilter.all;
  final Set<String> _selected = {};
  String _search = '';

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final currentUserId = auth is AuthSignedIn ? auth.user.id : null;
    final projectsAsync = ref.watch(
      workspaceProjectsProvider(widget.workspaceId),
    );
    final metricsAsync = ref.watch(workspaceMetricsProvider(null));

    final projects = projectsAsync.valueOrNull ?? const <ChatSession>[];
    final metrics = metricsAsync.valueOrNull;
    final isLoading = projectsAsync.isLoading && !projectsAsync.hasValue;
    final workspaceName =
        ref
            .watch(workspacesProvider)
            .valueOrNull
            ?.where((w) => w.id == widget.workspaceId)
            .firstOrNull
            ?.name ??
        'Workspace';

    final screenWidth = MediaQuery.sizeOf(context).width;
    final isDesktop = screenWidth >= 1100;

    if (isLoading) {
      return const Scaffold(
        backgroundColor: EvergreenColors.canvas,
        body: Center(child: CircularProgressIndicator()),
      );
    }
    if (projectsAsync.hasError) {
      return Scaffold(
        backgroundColor: EvergreenColors.canvas,
        body: Center(
          child: Text(
            'Failed to load workspace: ${projectsAsync.error}',
            style: const TextStyle(color: EvergreenColors.refused),
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: EdgeInsets.symmetric(
            horizontal: isDesktop ? 32 : 16,
            vertical: isDesktop ? 20 : 12,
          ),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1400),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Title on the left; vector storage + New project pinned to the top-right corner on
                  // wide screens, stacked under the title on narrow ones.
                  Builder(
                    builder: (context) {
                      final title = Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            workspaceName,
                            style: Theme.of(context).textTheme.headlineMedium
                                ?.copyWith(
                                  fontWeight: FontWeight.w700,
                                  color: EvergreenColors.ink,
                                  letterSpacing: -0.5,
                                ),
                          ),
                          const SizedBox(height: 4),
                          const Text(
                            'Grounded, cited answers over this workspace\'s documents.',
                            style: TextStyle(
                              fontSize: 14,
                              color: EvergreenColors.metadata,
                            ),
                          ),
                        ],
                      );
                      final actions = Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 6,
                            ),
                            decoration: BoxDecoration(
                              color: EvergreenColors.surface,
                              borderRadius: BorderRadius.circular(
                                EvergreenRadii.control,
                              ),
                              border: Border.all(color: EvergreenColors.border),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Text(
                                  'Vector Storage: ',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: EvergreenColors.metadata,
                                  ),
                                ),
                                Text(
                                  metrics == null
                                      ? '—'
                                      : '${metrics.qdrantPoints} chunks',
                                  style: monoStyle(
                                    fontSize: 12,
                                    weight: FontWeight.w600,
                                    color: EvergreenColors.ink,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          FilledButton.icon(
                            onPressed: () => createProjectDialog(
                              context,
                              ref,
                              widget.workspaceId,
                            ),
                            icon: const Icon(Symbols.add, size: 16),
                            label: const Text('New project'),
                            style: FilledButton.styleFrom(
                              backgroundColor: EvergreenColors.primary,
                              padding: const EdgeInsets.symmetric(
                                horizontal: 16,
                                vertical: 10,
                              ),
                            ),
                          ),
                        ],
                      );
                      return isDesktop
                          ? Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Expanded(child: title),
                                const SizedBox(width: 16),
                                actions,
                              ],
                            )
                          : Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                title,
                                const SizedBox(height: 12),
                                actions,
                              ],
                            );
                    },
                  ),
                  SizedBox(height: isDesktop ? 16 : 8),

                  // 4 Stat Cards Grid (from 01_workspace_overview.html)
                  _FourStatCardsGrid(
                    projects: projects,
                    metrics: metrics,
                    documentCount: ref
                        .watch(documentsProvider)
                        .valueOrNull
                        ?.length,
                  ),
                  SizedBox(height: isDesktop ? 16 : 8),

                  // 2-Column Split: Projects List on Left, Recent Activity & Infra on Right
                  if (isDesktop)
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          flex: 8,
                          child: _buildProjectsColumn(
                            context,
                            projects,
                            currentUserId,
                          ),
                        ),
                        const SizedBox(width: 24),
                        Expanded(
                          flex: 4,
                          child: _buildRightInfoColumn(context, metrics),
                        ),
                      ],
                    )
                  else
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildProjectsColumn(context, projects, currentUserId),
                        const SizedBox(height: 24),
                        _buildRightInfoColumn(context, metrics),
                      ],
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildProjectsColumn(
    BuildContext context,
    List<ChatSession> projects,
    String? currentUserId,
  ) {
    final filtered = _applyFilter(projects, currentUserId);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Projects Toolbar
        Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 12,
          runSpacing: 8,
          children: [
            Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 8,
              runSpacing: 4,
              children: [
                const Text(
                  'Projects',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: EvergreenColors.ink,
                  ),
                ),
                _FilterTabs(
                  filter: _filter,
                  onChanged: (f) => setState(() => _filter = f),
                ),
                IconButton(
                  icon: const Icon(
                    Symbols.refresh,
                    size: 16,
                    color: EvergreenColors.metadata,
                  ),
                  tooltip: 'Refresh projects',
                  visualDensity: VisualDensity.compact,
                  onPressed: () {
                    ref.invalidate(
                      workspaceProjectsProvider(widget.workspaceId),
                    );
                  },
                ),
                if (_selected.isNotEmpty)
                  TextButton.icon(
                    onPressed: () => _deleteSelected(context),
                    icon: const Icon(
                      Symbols.delete,
                      size: 16,
                      color: EvergreenColors.refused,
                    ),
                    label: Text(
                      'Delete ${_selected.length}',
                      style: const TextStyle(
                        color: EvergreenColors.refused,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
              ],
            ),
            SizedBox(
              width: 180,
              child: TextField(
                onChanged: (v) => setState(() => _search = v),
                style: const TextStyle(fontSize: 12),
                decoration: InputDecoration(
                  isDense: true,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 8,
                  ),
                  prefixIcon: const Icon(
                    Symbols.search,
                    size: 16,
                    color: EvergreenColors.metadata,
                  ),
                  hintText: 'Filter projects…',
                  fillColor: EvergreenColors.surface,
                  filled: true,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.border),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.border),
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),

        // Projects Card Container
        Container(
          decoration: BoxDecoration(
            color: EvergreenColors.surface,
            borderRadius: BorderRadius.circular(EvergreenRadii.panel),
            border: Border.all(color: EvergreenColors.border),
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(
            children: [
              if (filtered.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(
                    vertical: 40,
                    horizontal: 20,
                  ),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(
                          Symbols.folder_open,
                          size: 36,
                          color: EvergreenColors.border,
                        ),
                        const SizedBox(height: 10),
                        Text(
                          _search.isNotEmpty
                              ? 'No projects match "$_search"'
                              : 'No projects in this workspace yet',
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            color: EvergreenColors.inkSecondary,
                          ),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          'Click "New project" above to create your first project.',
                          style: TextStyle(
                            fontSize: 12,
                            color: EvergreenColors.metadata,
                          ),
                        ),
                      ],
                    ),
                  ),
                )
              else
                for (var i = 0; i < filtered.length; i++) ...[
                  _ProjectListRow(
                    index: i,
                    project: filtered[i],
                    workspaceId: widget.workspaceId,
                    selected: _selected.contains(filtered[i].id),
                    onSelect: (val) => setState(() {
                      if (val) {
                        _selected.add(filtered[i].id);
                      } else {
                        _selected.remove(filtered[i].id);
                      }
                    }),
                  ),
                  if (i != filtered.length - 1)
                    const Divider(height: 1, color: EvergreenColors.border),
                ],
            ],
          ),
        ),
        const SizedBox(height: 10),

        // Bottom Micro-tip
        Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 12,
          runSpacing: 6,
          children: [
            const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Symbols.info, size: 14, color: EvergreenColors.metadata),
                SizedBox(width: 6),
                Flexible(
                  child: Text(
                    'All RAG queries cite passage doc_ids and token-level offsets.',
                    style: TextStyle(
                      fontSize: 11,
                      color: EvergreenColors.metadata,
                    ),
                  ),
                ),
              ],
            ),
            Text(
              'Embedding: bge-m3',
              style: monoStyle(fontSize: 11, color: EvergreenColors.metadata),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildRightInfoColumn(BuildContext context, SystemMetrics? metrics) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Recent Activity Card
        Container(
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
                  const Text(
                    'Recent activity',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: EvergreenColors.ink,
                    ),
                  ),
                  Text(
                    'View all',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: EvergreenColors.primary,
                    ),
                  ),
                ],
              ),
              const Divider(height: 20, color: EvergreenColors.border),
              Builder(
                builder: (context) {
                  final telemetry = metrics?.recentTelemetry ?? const [];
                  if (telemetry.isEmpty) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Text(
                        'No queries yet.',
                        style: TextStyle(
                          fontSize: 12,
                          color: EvergreenColors.metadata,
                        ),
                      ),
                    );
                  }
                  return Column(
                    children: [
                      for (var i = 0; i < telemetry.length; i++) ...[
                        _ActivityItem(
                          initials: 'AK',
                          initialsColor: EvergreenColors.ink,
                          initialsBg: const Color(0xFFE7E5E4),
                          query: telemetry[i].queryText,
                          subtitle: telemetry[i].sessionId != null
                              ? 'Asked in ${telemetry[i].sessionId} · recently'
                              : 'Asked recently',
                          statusLabel: telemetry[i].refused
                              ? 'Refused — not in sources'
                              : 'Answered from ${telemetry[i].citationsCount} citations',
                          statusColor: telemetry[i].refused
                              ? EvergreenColors.refused
                              : EvergreenColors.primary,
                          statusBg: telemetry[i].refused
                              ? EvergreenColors.refusedTint
                              : EvergreenColors.primaryTint,
                        ),
                        if (i != telemetry.length - 1)
                          const Divider(height: 18, color: Color(0xFFF5F5F4)),
                      ],
                    ],
                  );
                },
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Infrastructure & Models Card
        Builder(
          builder: (context) {
            final health = ref.watch(serviceHealthProvider).valueOrNull;
            final gpu = ref.watch(gpuStatusProvider).valueOrNull;
            final models = ref.watch(modelsProvider).valueOrNull;
            final allHealthy =
                health != null &&
                health.qdrantAlive &&
                health.redisAlive &&
                health.ollamaAlive;
            final usedMb = (gpu?['used_vram_mb'] as num?)?.toDouble();
            final totalMb = (gpu?['total_vram_mb'] as num?)?.toDouble();
            final vramRatio = (usedMb != null && totalMb != null && totalMb > 0)
                ? (usedMb / totalMb).clamp(0.0, 1.0).toDouble()
                : null;
            String state(bool? alive) =>
                alive == null ? 'unknown' : (alive ? 'up' : 'down');
            final defaultModel = models?.defaultModel ?? '';
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
                      const Expanded(
                        child: Text(
                          'Infrastructure & Models',
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: EvergreenColors.ink,
                          ),
                        ),
                      ),
                      Row(
                        children: [
                          Container(
                            width: 6,
                            height: 6,
                            decoration: BoxDecoration(
                              color: allHealthy
                                  ? EvergreenColors.confident
                                  : EvergreenColors.refused,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 4),
                          Text(
                            health == null
                                ? 'Checking…'
                                : (allHealthy ? 'Healthy' : 'Degraded'),
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w500,
                              color: allHealthy
                                  ? EvergreenColors.primary
                                  : EvergreenColors.refused,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const Divider(height: 20, color: EvergreenColors.border),
                  _InfraItem(
                    title: 'Qdrant Vector DB',
                    detail: metrics == null
                        ? state(health?.qdrantAlive)
                        : '${state(health?.qdrantAlive)} · ${metrics.qdrantPoints} vectors',
                    healthy: health?.qdrantAlive ?? false,
                  ),
                  const SizedBox(height: 8),
                  _InfraItem(
                    title: 'Redis Cache',
                    detail: metrics == null
                        ? state(health?.redisAlive)
                        : '${state(health?.redisAlive)} · queue ${metrics.redisQueueDepth}',
                    healthy: health?.redisAlive ?? false,
                  ),
                  const SizedBox(height: 8),
                  _InfraItem(
                    title: 'Ollama Engine',
                    detail:
                        '${state(health?.ollamaAlive)} · ${models?.models.length ?? 0} models',
                    healthy: health?.ollamaAlive ?? false,
                  ),
                  const SizedBox(height: 14),
                  const Divider(height: 1, color: EvergreenColors.border),
                  const SizedBox(height: 10),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        vramRatio == null
                            ? 'VRAM —'
                            : 'VRAM ${(usedMb! / 1024).toStringAsFixed(1)} / ${(totalMb! / 1024).toStringAsFixed(1)} GB',
                        style: monoStyle(
                          fontSize: 11,
                          weight: FontWeight.w600,
                          color: EvergreenColors.ink,
                        ),
                      ),
                      Text(
                        vramRatio == null
                            ? ''
                            : '${(vramRatio * 100).round()}%',
                        style: monoStyle(
                          fontSize: 10,
                          color: EvergreenColors.metadata,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(999),
                    child: LinearProgressIndicator(
                      value: vramRatio ?? 0,
                      minHeight: 6,
                      backgroundColor: const Color(0xFFF5F5F4),
                      valueColor: const AlwaysStoppedAnimation<Color>(
                        EvergreenColors.primary,
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    defaultModel.isEmpty
                        ? 'No chat model available'
                        : 'Default model: $defaultModel',
                    style: monoStyle(
                      fontSize: 10,
                      color: EvergreenColors.metadata,
                    ),
                  ),
                ],
              ),
            );
          },
        ),
        const SizedBox(height: 16),

        // Zero-hallucination constraint card
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: EvergreenColors.fill,
            borderRadius: BorderRadius.circular(EvergreenRadii.panel),
            border: Border.all(color: EvergreenColors.border),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                Symbols.fact_check,
                size: 16,
                color: EvergreenColors.primary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: const [
                    Text(
                      'Zero-hallucination constraint',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: EvergreenColors.ink,
                      ),
                    ),
                    SizedBox(height: 3),
                    Text(
                      'Every numeric answer must correlate to a raw bounding box or audited filing markdown cell. Unmatched questions will be strictly refused.',
                      style: TextStyle(
                        fontSize: 11,
                        color: EvergreenColors.metadata,
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Future<void> _deleteSelected(BuildContext context) async {
    final count = _selected.length;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete $count project${count == 1 ? '' : 's'}?'),
        content: const Text(
          'This permanently removes their chat history. This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: EvergreenColors.refused,
            ),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final ids = List<String>.from(_selected);
    await ref.read(workspaceActionsProvider).deleteProjects(ids);
    if (mounted) setState(() => _selected.clear());
  }

  List<ChatSession> _applyFilter(
    List<ChatSession> projects,
    String? currentUserId,
  ) {
    Iterable<ChatSession> result = switch (_filter) {
      _ProjectFilter.all => projects,
      _ProjectFilter.mine => projects.where(
        (p) => currentUserId != null
            ? (p.ownerId == currentUserId || p.ownerId == null)
            : true,
      ),
      _ProjectFilter.forked => projects.where((p) => p.forkedFrom != null),
    };
    if (_search.trim().isNotEmpty) {
      final query = _search.trim().toLowerCase();
      result = result.where((p) => p.title.toLowerCase().contains(query));
    }
    return result.toList();
  }
}

class _FourStatCardsGrid extends StatelessWidget {
  const _FourStatCardsGrid({
    required this.projects,
    required this.metrics,
    required this.documentCount,
  });
  final List<ChatSession> projects;
  final SystemMetrics? metrics;
  final int? documentCount;

  @override
  Widget build(BuildContext context) {
    final m = metrics;
    final totalQueries = m?.totalQueries ?? 0;
    final answered = totalQueries - (m?.totalRefusals ?? 0);
    final groundedPct = totalQueries > 0
        ? (answered * 100 / totalQueries).round()
        : null;
    final sourced = projects.where((p) => p.files.isNotEmpty).length;
    return LayoutBuilder(
      builder: (context, constraints) {
        final count = constraints.maxWidth >= 1000
            ? 4
            : (constraints.maxWidth >= 480 ? 2 : 1);
        final width = (constraints.maxWidth - ((count - 1) * 12)) / count;

        return Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            SizedBox(
              width: width,
              child: _StatCardItem(
                icon: Symbols.folder_open,
                label: 'Projects',
                value: '${projects.length} Active',
                chipLabel: '$sourced with sources',
                chipColor: EvergreenColors.primary,
                chipBg: EvergreenColors.primaryTint,
              ),
            ),
            SizedBox(
              width: width,
              child: _StatCardItem(
                icon: Symbols.description,
                label: 'Documents',
                value: documentCount == null ? '—' : '$documentCount Files',
                chipLabel: m == null ? '— chunks' : '${m.qdrantPoints} chunks',
                chipColor: EvergreenColors.inkSecondary,
                chipBg: const Color(0xFFF5F5F4),
                isMono: true,
              ),
            ),
            SizedBox(
              width: width,
              child: _StatCardItem(
                icon: Symbols.chat_bubble_outline,
                label: 'Questions asked',
                value: m == null ? '—' : '$totalQueries Queries',
                chipLabel: m == null ? 'no data' : '${m.totalRefusals} refused',
                chipColor: EvergreenColors.primary,
                chipBg: EvergreenColors.primaryTint,
              ),
            ),
            SizedBox(
              width: width,
              child: _StatCardItem(
                icon: Symbols.verified,
                label: 'Groundedness',
                value: groundedPct == null ? '—' : '$groundedPct% Score',
                chipLabel: groundedPct == null ? 'no queries' : 'answered rate',
                chipColor: EvergreenColors.metadata,
                chipBg: const Color(0xFFF5F5F4),
                isMono: true,
              ),
            ),
          ],
        );
      },
    );
  }
}

class _StatCardItem extends StatelessWidget {
  const _StatCardItem({
    required this.icon,
    required this.label,
    required this.value,
    required this.chipLabel,
    required this.chipColor,
    required this.chipBg,
    this.isMono = false,
  });

  final IconData icon;
  final String label;
  final String value;
  final String chipLabel;
  final Color chipColor;
  final Color chipBg;
  final bool isMono;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: EvergreenColors.primaryTint,
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                  ),
                  child: Icon(icon, color: EvergreenColors.primary, size: 20),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 12,
                          color: EvergreenColors.metadata,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        value,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: EvergreenColors.ink,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: chipBg,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: chipColor.withValues(alpha: 0.2)),
            ),
            child: Text(
              chipLabel,
              style: isMono
                  ? monoStyle(
                      fontSize: 10,
                      weight: FontWeight.w500,
                      color: chipColor,
                    )
                  : TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: chipColor,
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProjectListRow extends StatelessWidget {
  const _ProjectListRow({
    required this.index,
    required this.project,
    required this.workspaceId,
    required this.selected,
    required this.onSelect,
  });

  final int index;
  final ChatSession project;
  final String workspaceId;
  final bool selected;
  final ValueChanged<bool> onSelect;

  @override
  Widget build(BuildContext context) {
    final tint = _folderTints[index % _folderTints.length];
    final isWebRag = project.title.toLowerCase().contains('web');
    final isForked = project.forkedFrom != null;

    final String description;
    if (project.description != null && project.description!.isNotEmpty) {
      description = project.description!;
    } else {
      description = project.files.isNotEmpty
          ? '${project.files.length} sources attached · Ready for query'
          : 'Ready for document ingestion';
    }

    final sourcesCount = project.files.length;
    final chatsCount = project.messageCount;

    final String timeAgo;
    if (project.updatedAt > 0) {
      final nowSec = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final diff = nowSec - project.updatedAt;
      if (diff < 60) {
        timeAgo = 'Just now';
      } else if (diff < 3600) {
        timeAgo = '${diff ~/ 60}m ago';
      } else if (diff < 86400) {
        timeAgo = '${diff ~/ 3600}h ago';
      } else {
        timeAgo = '${diff ~/ 86400}d ago';
      }
    } else {
      timeAgo = '—';
    }

    final rawMode = project.parameters.retrievalMode;
    final modeLabel = rawMode.isNotEmpty
        ? (rawMode[0].toUpperCase() + rawMode.substring(1))
        : 'Auto';

    return InkWell(
      onTap: () => context.go('/w/$workspaceId/p/${project.id}/overview'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        child: Row(
          children: [
            Checkbox(
              value: selected,
              onChanged: (v) => onSelect(v ?? false),
              visualDensity: VisualDensity.compact,
            ),
            const SizedBox(width: 8),
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: tint.fill,
                borderRadius: BorderRadius.circular(EvergreenRadii.control),
              ),
              child: Icon(
                isWebRag ? Symbols.public : Symbols.folder,
                color: tint.icon,
                size: 18,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    crossAxisAlignment: WrapCrossAlignment.center,
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      Text(
                        project.title,
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: EvergreenColors.ink,
                        ),
                      ),
                      if (isWebRag) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 1,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF5F5F4),
                            borderRadius: BorderRadius.circular(
                              EvergreenRadii.chip,
                            ),
                            border: Border.all(color: EvergreenColors.border),
                          ),
                          child: Text(
                            'preset',
                            style: monoStyle(
                              fontSize: 9,
                              color: EvergreenColors.inkSecondary,
                            ),
                          ),
                        ),
                      ],
                      if (isForked) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 1,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF5F5F4),
                            borderRadius: BorderRadius.circular(
                              EvergreenRadii.chip,
                            ),
                            border: Border.all(color: EvergreenColors.border),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Symbols.fork_right,
                                size: 10,
                                color: EvergreenColors.metadata,
                              ),
                              const SizedBox(width: 2),
                              Text(
                                'forked',
                                style: monoStyle(
                                  fontSize: 9,
                                  color: EvergreenColors.metadata,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 1,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF5F5F4),
                          borderRadius: BorderRadius.circular(
                            EvergreenRadii.chip,
                          ),
                          border: Border.all(color: EvergreenColors.border),
                        ),
                        child: Text(
                          project.parameters.model,
                          style: monoStyle(
                            fontSize: 10,
                            color: EvergreenColors.ink,
                          ),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 1,
                        ),
                        decoration: BoxDecoration(
                          color: EvergreenColors.primaryTint,
                          borderRadius: BorderRadius.circular(
                            EvergreenRadii.chip,
                          ),
                        ),
                        child: Text(
                          modeLabel,
                          style: const TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: EvergreenColors.primary,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text(
                    // System prompts can run to paragraphs; the row only needs a preview.
                    description.replaceAll(RegExp(r'\s+'), ' ').trim(),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 12,
                      color: EvergreenColors.metadata,
                    ),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  '$sourcesCount sources · $chatsCount chats',
                  style: monoStyle(
                    fontSize: 11,
                    color: EvergreenColors.inkSecondary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  timeAgo,
                  style: const TextStyle(
                    fontSize: 11,
                    color: EvergreenColors.metadata,
                  ),
                ),
              ],
            ),
            const SizedBox(width: 8),
            const Icon(
              Symbols.chevron_right,
              size: 16,
              color: EvergreenColors.metadata,
            ),
          ],
        ),
      ),
    );
  }
}

class _FilterTabs extends StatelessWidget {
  const _FilterTabs({required this.filter, required this.onChanged});
  final _ProjectFilter filter;
  final ValueChanged<_ProjectFilter> onChanged;

  @override
  Widget build(BuildContext context) {
    const labels = {
      _ProjectFilter.all: 'All',
      _ProjectFilter.mine: 'Mine',
      _ProjectFilter.forked: 'Forked',
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final f in _ProjectFilter.values) ...[
          ChoiceChip(
            label: Text(labels[f]!),
            selected: filter == f,
            onSelected: (_) => onChanged(f),
            visualDensity: VisualDensity.compact,
            showCheckmark: false,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(6),
            ),
          ),
          if (f != _ProjectFilter.values.last) const SizedBox(width: 4),
        ],
      ],
    );
  }
}

class _ActivityItem extends StatelessWidget {
  const _ActivityItem({
    required this.initials,
    required this.initialsColor,
    required this.initialsBg,
    required this.query,
    required this.subtitle,
    required this.statusLabel,
    required this.statusColor,
    required this.statusBg,
  });

  final String initials;
  final Color initialsColor;
  final Color initialsBg;
  final String query;
  final String subtitle;
  final String statusLabel;
  final Color statusColor;
  final Color statusBg;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(color: initialsBg, shape: BoxShape.circle),
          alignment: Alignment.center,
          child: Text(
            initials,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w700,
              color: initialsColor,
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                query,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: EvergreenColors.ink,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                subtitle,
                style: const TextStyle(
                  fontSize: 11,
                  color: EvergreenColors.metadata,
                ),
              ),
              const SizedBox(height: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: statusBg,
                  borderRadius: BorderRadius.circular(EvergreenRadii.chip),
                ),
                child: Text(
                  statusLabel,
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: statusColor,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _InfraItem extends StatelessWidget {
  const _InfraItem({
    required this.title,
    required this.detail,
    required this.healthy,
  });
  final String title;
  final String detail;
  final bool healthy;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Row(
            children: [
              Container(
                width: 5,
                height: 5,
                decoration: BoxDecoration(
                  color: healthy
                      ? EvergreenColors.confident
                      : EvergreenColors.refused,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  title,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: EvergreenColors.ink,
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        Text(
          detail,
          style: monoStyle(fontSize: 10, color: EvergreenColors.inkSecondary),
        ),
      ],
    );
  }
}
