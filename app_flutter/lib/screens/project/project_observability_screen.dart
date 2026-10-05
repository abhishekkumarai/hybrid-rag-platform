import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/models/metrics.dart';
import '../../features/project/project_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/chat_scope_selector.dart';
import '../../widgets/section_header.dart';
import '../../widgets/stat_card.dart';
import 'project_tab_shell.dart';

/// Project Observability tab (IRA-56): query volume and latency for every chat in the project, with
/// totals and recent queries for the whole project or one chat.
class ProjectObservabilityScreen extends ConsumerStatefulWidget {
  const ProjectObservabilityScreen({
    super.key,
    required this.workspaceId,
    required this.projectId,
  });
  final String workspaceId;
  final String projectId;

  @override
  ConsumerState<ProjectObservabilityScreen> createState() =>
      _ProjectObservabilityScreenState();
}

class _ProjectObservabilityScreenState
    extends ConsumerState<ProjectObservabilityScreen> {
  String? _conversationId; // null = all chats

  @override
  Widget build(BuildContext context) {
    final scope = (
      sessionId: widget.projectId,
      conversationId: _conversationId,
    );
    final obsAsync = ref.watch(projectObservabilityProvider(scope));

    return ProjectTabShell(
      workspaceId: widget.workspaceId,
      projectId: widget.projectId,
      activeTab: ProjectTab.observability,
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SectionHeader(
              title: _conversationId == null
                  ? 'Observability — all chats'
                  : 'Observability — this chat',
              action: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ChatScopeSelector(
                    projectId: widget.projectId,
                    value: _conversationId,
                    onChanged: (v) => setState(() => _conversationId = v),
                  ),
                  IconButton(
                    tooltip: 'Refresh',
                    icon: const Icon(
                      Symbols.refresh,
                      size: 18,
                      color: EvergreenColors.metadata,
                    ),
                    onPressed: () {
                      ref.invalidate(projectObservabilityProvider);
                      ref.invalidate(
                        projectConversationsProvider(widget.projectId),
                      );
                    },
                  ),
                ],
              ),
            ),
            obsAsync.when(
              data: (obs) => Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Totals(stats: obs.totals),
                  const SizedBox(height: 28),
                  const SectionHeader(title: 'Chats'),
                  _ChatsTable(
                    rows: obs.conversations,
                    selected: _conversationId,
                    onSelect: (id) => setState(
                      () => _conversationId = id == _conversationId ? null : id,
                    ),
                    onOpen: (id) => context.go(
                      '/w/${widget.workspaceId}/p/${widget.projectId}/chats/$id',
                    ),
                  ),
                  const SizedBox(height: 28),
                  const SectionHeader(title: 'Recent queries'),
                  _RecentQueries(records: obs.recent),
                ],
              ),
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 32),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) =>
                  EmptyState(message: 'Could not load observability: $e'),
            ),
          ],
        ),
      ),
    );
  }
}

String _ms(double v) => v <= 0
    ? '—'
    : (v >= 1000 ? '${(v / 1000).toStringAsFixed(1)} s' : '${v.round()} ms');

String _ago(double? epochSeconds) {
  if (epochSeconds == null || epochSeconds <= 0) return '—';
  final diff =
      DateTime.now().millisecondsSinceEpoch ~/ 1000 - epochSeconds.toInt();
  if (diff < 60) return 'just now';
  if (diff < 3600) return '${diff ~/ 60}m ago';
  if (diff < 86400) return '${diff ~/ 3600}h ago';
  return '${diff ~/ 86400}d ago';
}

class _Totals extends StatelessWidget {
  const _Totals({required this.stats});
  final ChatLatencyStats stats;

  @override
  Widget build(BuildContext context) {
    final refusalPct = stats.queries == 0
        ? null
        : stats.refusals * 100 / stats.queries;
    Widget card(
      String label,
      String value,
      IconData icon, {
      Color? tint,
      Color? tintIcon,
    }) => SizedBox(
      width: 190,
      child: StatCard(
        label: label,
        value: value,
        icon: icon,
        tint: tint ?? EvergreenColors.folderSage,
        tintIcon: tintIcon ?? EvergreenColors.primary,
      ),
    );
    return Wrap(
      spacing: 16,
      runSpacing: 16,
      children: [
        card(
          'Queries',
          '${stats.queries}',
          Symbols.chat_bubble,
          tint: EvergreenColors.folderSky,
          tintIcon: EvergreenColors.folderSkyIcon,
        ),
        card(
          'Refusal rate',
          refusalPct == null ? '—' : '${refusalPct.toStringAsFixed(1)}%',
          Symbols.shield,
          tint: (refusalPct ?? 0) > 20 ? EvergreenColors.refusedTint : null,
          tintIcon: (refusalPct ?? 0) > 20 ? EvergreenColors.refused : null,
        ),
        card('Avg end-to-end', _ms(stats.avgTotalMs), Symbols.timer),
        card(
          'Avg retrieval',
          _ms(stats.avgRetrievalMs),
          Symbols.manage_search,
          tint: EvergreenColors.folderSand,
          tintIcon: EvergreenColors.folderSandIcon,
        ),
        card('Avg first token', _ms(stats.avgTtftMs), Symbols.bolt),
        card(
          'Tokens / s',
          stats.avgTokensPerSec <= 0
              ? '—'
              : stats.avgTokensPerSec.toStringAsFixed(1),
          Symbols.speed,
          tint: EvergreenColors.folderRose,
          tintIcon: EvergreenColors.folderRoseIcon,
        ),
      ],
    );
  }
}

class _ChatsTable extends StatelessWidget {
  const _ChatsTable({
    required this.rows,
    required this.selected,
    required this.onSelect,
    required this.onOpen,
  });
  final List<ConversationStats> rows;
  final String? selected;
  final ValueChanged<String> onSelect;
  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return const EmptyState(
        message: 'No chats in this project yet.',
        icon: Symbols.forum,
      );
    }
    const head = TextStyle(
      fontSize: 11,
      fontWeight: FontWeight.w600,
      color: EvergreenColors.metadata,
    );
    return Container(
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        border: Border.all(color: EvergreenColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 10, 16, 10),
            child: Row(
              children: [
                Expanded(flex: 4, child: Text('CHAT', style: head)),
                Expanded(
                  flex: 2,
                  child: Text(
                    'QUERIES',
                    style: head,
                    textAlign: TextAlign.right,
                  ),
                ),
                Expanded(
                  flex: 2,
                  child: Text(
                    'REFUSED',
                    style: head,
                    textAlign: TextAlign.right,
                  ),
                ),
                Expanded(
                  flex: 2,
                  child: Text(
                    'AVG LATENCY',
                    style: head,
                    textAlign: TextAlign.right,
                  ),
                ),
                Expanded(
                  flex: 2,
                  child: Text('TOK/S', style: head, textAlign: TextAlign.right),
                ),
                Expanded(
                  flex: 2,
                  child: Text('LAST', style: head, textAlign: TextAlign.right),
                ),
                SizedBox(width: 40),
              ],
            ),
          ),
          for (final r in rows) ...[
            const Divider(height: 1, color: EvergreenColors.border),
            Material(
              color: r.conversationId == selected
                  ? EvergreenColors.primaryTint
                  : Colors.transparent,
              child: InkWell(
                onTap: () => onSelect(r.conversationId),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 6, 8, 6),
                  child: Row(
                    children: [
                      Expanded(
                        flex: 4,
                        child: Text(
                          r.title,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                            color: EvergreenColors.ink,
                          ),
                        ),
                      ),
                      Expanded(
                        flex: 2,
                        child: Text(
                          '${r.stats.queries}',
                          textAlign: TextAlign.right,
                          style: monoStyle(fontSize: 12),
                        ),
                      ),
                      Expanded(
                        flex: 2,
                        child: Text(
                          '${r.stats.refusals}',
                          textAlign: TextAlign.right,
                          style: monoStyle(
                            fontSize: 12,
                            color: r.stats.refusals > 0
                                ? EvergreenColors.refused
                                : EvergreenColors.ink,
                          ),
                        ),
                      ),
                      Expanded(
                        flex: 2,
                        child: Text(
                          _ms(r.stats.avgTotalMs),
                          textAlign: TextAlign.right,
                          style: monoStyle(fontSize: 12),
                        ),
                      ),
                      Expanded(
                        flex: 2,
                        child: Text(
                          r.stats.avgTokensPerSec <= 0
                              ? '—'
                              : r.stats.avgTokensPerSec.toStringAsFixed(1),
                          textAlign: TextAlign.right,
                          style: monoStyle(fontSize: 12),
                        ),
                      ),
                      Expanded(
                        flex: 2,
                        child: Text(
                          _ago(r.stats.lastQueryAt),
                          textAlign: TextAlign.right,
                          style: const TextStyle(
                            fontSize: 12,
                            color: EvergreenColors.metadata,
                          ),
                        ),
                      ),
                      SizedBox(
                        width: 40,
                        child: IconButton(
                          tooltip: 'Open chat',
                          visualDensity: VisualDensity.compact,
                          icon: const Icon(
                            Symbols.open_in_new,
                            size: 16,
                            color: EvergreenColors.metadata,
                          ),
                          onPressed: () => onOpen(r.conversationId),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _RecentQueries extends StatelessWidget {
  const _RecentQueries({required this.records});
  final List<QueryTelemetry> records;

  @override
  Widget build(BuildContext context) {
    if (records.isEmpty) {
      return const EmptyState(
        message: 'No queries yet. Ask something in a chat to see it here.',
        icon: Symbols.monitoring,
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
          for (var i = 0; i < records.length; i++) ...[
            if (i > 0) const Divider(height: 1, color: EvergreenColors.border),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          records[i].queryText,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 13,
                            color: EvergreenColors.ink,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${_ago(records[i].timestamp)} · ${_ms(records[i].totalMs)} · '
                          '${records[i].citationsCount} citations · top ${records[i].topScore.toStringAsFixed(2)}',
                          style: monoStyle(
                            fontSize: 11,
                            color: EvergreenColors.metadata,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: records[i].refused
                          ? EvergreenColors.refusedTint
                          : EvergreenColors.primaryTint,
                      borderRadius: BorderRadius.circular(EvergreenRadii.chip),
                    ),
                    child: Text(
                      records[i].refused ? 'Refused' : 'Answered',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: records[i].refused
                            ? EvergreenColors.refused
                            : EvergreenColors.primary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
