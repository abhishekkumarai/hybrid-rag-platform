import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/models/document.dart';
import '../../api/models/session.dart';
import '../../features/project/project_providers.dart';
import '../../features/workspace/workspace_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';
import 'project_tab_shell.dart';

/// Matches `ui/stitch_workspace/02_project_overview.html`:
/// 3 stat cards, recently added sources list, and recent chats list.
class ProjectOverviewScreen extends ConsumerWidget {
  const ProjectOverviewScreen({
    super.key,
    required this.workspaceId,
    required this.projectId,
  });
  final String workspaceId;
  final String projectId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projectAsync = ref.watch(projectProvider(projectId));
    final conversationsAsync = ref.watch(projectConversationsProvider(projectId));
    final documents = ref.watch(documentsProvider).valueOrNull ?? const <DocumentInfo>[];
    final evalSummary = ref.watch(projectEvalSummaryProvider((sessionId: projectId, conversationId: null))).valueOrNull;

    if (!projectAsync.hasValue) {
      return ProjectTabShell(
        workspaceId: workspaceId,
        projectId: projectId,
        activeTab: ProjectTab.overview,
        child: Center(
          child: projectAsync.hasError
              ? Text('Failed to load project: ${projectAsync.error}',
                  style: const TextStyle(color: EvergreenColors.refused))
              : const CircularProgressIndicator(),
        ),
      );
    }
    final project = projectAsync.requireValue;
    final conversations = conversationsAsync.valueOrNull ?? const <Conversation>[];
    final files = project.files;
    final docsById = {for (final d in documents) d.docId: d};
    final attachedDocs = [for (final f in files) docsById[f]];
    final totalPages = attachedDocs.fold<int>(0, (sum, d) => sum + (d?.pages ?? 0));
    final webCount = attachedDocs.where((d) => d?.isWeb ?? false).length;
    final grounded = evalSummary?.meanGroundedness;
    // Backend lists threads oldest first; "Recent chats" wants newest first.
    final recentChats = ([...conversations]..sort((a, b) => b.updatedAt.compareTo(a.updatedAt))).take(4).toList();

    return ProjectTabShell(
      workspaceId: workspaceId,
      projectId: projectId,
      activeTab: ProjectTab.overview,
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1400),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 3 Stat Cards Grid (from 02_project_overview.html)
                Row(
                  children: [
                    Expanded(
                      child: _ProjectStatCard(
                        title: 'Indexed sources',
                        value: '${files.length}',
                        chipText: '$webCount web',
                        chipColor: const Color(0xFFB45309),
                        chipBg: const Color(0xFFFEF3C7),
                        subIcon: Symbols.description,
                        subText: files.isEmpty ? 'No sources attached yet' : '$totalPages pages',
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: _ProjectStatCard(
                        title: 'Chats',
                        value: '${conversations.length}',
                        chipText: '${project.messageCount} messages',
                        chipColor: EvergreenColors.inkSecondary,
                        chipBg: const Color(0xFFF5F5F4),
                        subIcon: Symbols.data_array,
                        subText: 'Mode: ${project.parameters.retrievalMode} · ${project.parameters.model}',
                        isMono: true,
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: _ProjectStatCard(
                        title: 'Grounded',
                        value: grounded == null ? '—' : '${(grounded * 100).round()}%',
                        chipText: evalSummary == null
                            ? 'no data'
                            : '${(evalSummary.refusalRate * 100).round()}% refused',
                        chipColor: EvergreenColors.primary,
                        chipBg: EvergreenColors.primaryTint,
                        subIcon: Symbols.verified,
                        subText: evalSummary == null || evalSummary.turns == 0
                            ? 'No chat turns scored yet'
                            : 'Scored across ${evalSummary.turns} turns',
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 28),

                // Bento Grid: Sources on Left (7 cols), Recent Chats on Right (5 cols)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Sources Section (7 flex)
                    Expanded(
                      flex: 7,
                      child: Container(
                        padding: const EdgeInsets.all(20),
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
                                Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Text(
                                      'Recently added',
                                      style: TextStyle(
                                        fontSize: 14,
                                        fontWeight: FontWeight.w600,
                                        color: EvergreenColors.ink,
                                      ),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      '${files.length} documents attached to this project corpus',
                                      style: const TextStyle(
                                        fontSize: 12,
                                        color: EvergreenColors.metadata,
                                      ),
                                    ),
                                  ],
                                ),
                                InkWell(
                                  onTap: () => context.go('/w/$workspaceId/p/$projectId/sources'),
                                  child: Row(
                                    children: [
                                      Text(
                                        'View all',
                                        style: TextStyle(
                                          fontSize: 12,
                                          fontWeight: FontWeight.w500,
                                          color: EvergreenColors.primary,
                                        ),
                                      ),
                                      const SizedBox(width: 2),
                                      const Icon(Symbols.chevron_right, size: 14, color: EvergreenColors.primary),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                            const Divider(height: 24, color: EvergreenColors.border),
                            if (files.isEmpty)
                              const EmptyState(
                                message: 'No sources attached yet. Add one from the Sources tab.',
                                icon: Symbols.description,
                              ),
                            for (var i = 0; i < files.length; i++) ...[
                              _SourceRowItem(docId: files[i], doc: attachedDocs[i]),
                              if (i != files.length - 1)
                                const Divider(height: 1, color: Color(0xFFF5F5F4)),
                            ],
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 24),

                    // Recent Chats Section (5 flex)
                    Expanded(
                      flex: 5,
                      child: Container(
                        padding: const EdgeInsets.all(20),
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
                                  'Recent chats',
                                  style: TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w600,
                                    color: EvergreenColors.ink,
                                  ),
                                ),
                                InkWell(
                                  onTap: () => context.go(
                                    '/w/$workspaceId/p/$projectId/chats/${recentChats.isEmpty ? 'default' : recentChats.first.id}',
                                  ),
                                  child: Text(
                                    'Open chat',
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w500,
                                      color: EvergreenColors.primary,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const Divider(height: 24, color: EvergreenColors.border),
                            if (recentChats.isEmpty)
                              const EmptyState(message: 'No chats yet.', icon: Symbols.chat_bubble_outline),
                            for (var i = 0; i < recentChats.length; i++) ...[
                              _ConversationRowItem(
                                conversation: recentChats[i],
                                onTap: () => context.go(
                                  '/w/$workspaceId/p/$projectId/chats/${recentChats[i].id}',
                                ),
                              ),
                              if (i != recentChats.length - 1)
                                const Divider(height: 1, color: Color(0xFFF5F5F4)),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ProjectStatCard extends StatelessWidget {
  const _ProjectStatCard({
    required this.title,
    required this.value,
    required this.chipText,
    required this.chipColor,
    required this.chipBg,
    required this.subIcon,
    required this.subText,
    this.isMono = false,
  });

  final String title;
  final String value;
  final String chipText;
  final Color chipColor;
  final Color chipBg;
  final IconData subIcon;
  final String subText;
  final bool isMono;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
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
                title,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                  color: EvergreenColors.metadata,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: chipBg,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: chipColor.withValues(alpha: 0.2)),
                ),
                child: Text(
                  chipText,
                  style: isMono
                      ? monoStyle(fontSize: 10, color: chipColor, weight: FontWeight.w500)
                      : TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: chipColor),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            value,
            style: const TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.w700,
              color: EvergreenColors.ink,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Icon(subIcon, size: 14, color: EvergreenColors.metadata),
              const SizedBox(width: 6),
              Text(
                subText,
                style: const TextStyle(fontSize: 11, color: EvergreenColors.metadata),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SourceRowItem extends StatelessWidget {
  const _SourceRowItem({required this.docId, required this.doc});
  final String docId;
  final DocumentInfo? doc;

  @override
  Widget build(BuildContext context) {
    final filename = doc?.name ?? docId;
    final isPdf = filename.toLowerCase().endsWith('.pdf');
    final isTable = filename.contains('table');
    final meta = doc == null
        ? 'Not in your library'
        : '${doc!.isWeb ? 'Web' : (isPdf ? 'PDF' : 'Text')} · ${doc!.pages} pages · ${doc!.sizeKb.toStringAsFixed(0)} KB';

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: EvergreenColors.primaryTint,
                  borderRadius: BorderRadius.circular(EvergreenRadii.control),
                ),
                child: Icon(
                  isTable
                      ? Symbols.table_chart
                      : (isPdf ? Symbols.picture_as_pdf : Symbols.description),
                  size: 16,
                  color: EvergreenColors.primary,
                ),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    filename,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: EvergreenColors.ink,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    meta,
                    style: monoStyle(fontSize: 11, color: EvergreenColors.metadata),
                  ),
                ],
              ),
            ],
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: EvergreenColors.confidentTint,
              borderRadius: BorderRadius.circular(EvergreenRadii.chip),
              border: Border.all(color: EvergreenColors.confident.withValues(alpha: 0.3)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 5,
                  height: 5,
                  decoration: const BoxDecoration(
                    color: EvergreenColors.confident,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 4),
                const Text(
                  'Indexed',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: EvergreenColors.confident,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

String _ago(num epochSeconds) {
  if (epochSeconds <= 0) return '—';
  final diff = DateTime.now().millisecondsSinceEpoch ~/ 1000 - epochSeconds.toInt();
  if (diff < 60) return 'Just now';
  if (diff < 3600) return '${diff ~/ 60}m ago';
  if (diff < 86400) return '${diff ~/ 3600}h ago';
  return '${diff ~/ 86400}d ago';
}

class _ConversationRowItem extends StatelessWidget {
  const _ConversationRowItem({required this.conversation, required this.onTap});
  final Conversation conversation;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          children: [
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                color: const Color(0xFFF5F5F4),
                borderRadius: BorderRadius.circular(EvergreenRadii.control),
              ),
              child: const Icon(Symbols.chat_bubble_outline, size: 14, color: EvergreenColors.primary),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    conversation.title,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: EvergreenColors.ink,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${conversation.messageCount} messages · ${_ago(conversation.updatedAt)}',
                    style: monoStyle(fontSize: 10, color: EvergreenColors.metadata),
                  ),
                ],
              ),
            ),
            const Icon(Symbols.chevron_right, size: 14, color: EvergreenColors.metadata),
          ],
        ),
      ),
    );
  }
}
