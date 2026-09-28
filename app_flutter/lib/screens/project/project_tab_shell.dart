import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../features/project/project_providers.dart';
import '../../theme/evergreen_theme.dart';
import 'chat/share_dialog.dart';

enum ProjectTab { overview, sources, chatSessions, evaluation, settings }

/// DESIGN-evergreen.md "Project pages": breadcrumb, title, actions (Share · New chat · Add
/// source), tabs Overview · Sources · Chat sessions · Evaluation · Settings.
class ProjectTabShell extends ConsumerWidget {
  const ProjectTabShell({
    super.key,
    required this.workspaceId,
    required this.projectId,
    required this.activeTab,
    required this.child,
  });

  final String workspaceId;
  final String projectId;
  final ProjectTab activeTab;
  final Widget child;

  static const _tabs = [
    (tab: ProjectTab.overview, label: 'Overview', suffix: 'overview'),
    (tab: ProjectTab.sources, label: 'Sources', suffix: 'sources'),
    (tab: ProjectTab.chatSessions, label: 'Chat sessions', suffix: 'chats/default'),
    (tab: ProjectTab.evaluation, label: 'Evaluation', suffix: 'evaluation'),
    (tab: ProjectTab.settings, label: 'Settings', suffix: 'settings'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projectAsync = ref.watch(projectProvider(projectId));
    final title = projectAsync.value?.title ?? 'Project';
    final sourcesCount = projectAsync.value?.files.length;
    final chatCount = ref.watch(projectConversationsProvider(projectId)).value?.length;

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Breadcrumb(workspaceId: workspaceId, projectTitle: title),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(
                        child: Text(title,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
                      ),
                      Row(
                        children: [
                          OutlinedButton.icon(
                            onPressed: () => showShareDialog(context, projectId),
                            icon: const Icon(Symbols.link, size: 16, color: EvergreenColors.primary),
                            label: const Text('Share'),
                            style: OutlinedButton.styleFrom(foregroundColor: EvergreenColors.primary),
                          ),
                          const SizedBox(width: 8),
                          OutlinedButton.icon(
                            onPressed: () => context.go('/w/$workspaceId/p/$projectId/chats/default'),
                            icon: const Icon(Symbols.add, size: 16),
                            label: const Text('New chat'),
                          ),
                          const SizedBox(width: 8),
                          FilledButton.icon(
                            onPressed: () => context.go('/w/$workspaceId/p/$projectId/sources'),
                            icon: const Icon(Symbols.upload_file, size: 16),
                            label: const Text('Add source'),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  _TabsBar(
                    workspaceId: workspaceId,
                    projectId: projectId,
                    activeTab: activeTab,
                    sourcesCount: sourcesCount,
                    chatCount: chatCount,
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: EvergreenColors.border),
            Expanded(child: child),
          ],
        ),
      ),
    );
  }
}

class _Breadcrumb extends StatelessWidget {
  const _Breadcrumb({required this.workspaceId, required this.projectTitle});
  final String workspaceId;
  final String projectTitle;

  @override
  Widget build(BuildContext context) {
    final style = const TextStyle(fontSize: 13, color: EvergreenColors.metadata);
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        InkWell(onTap: () => context.go('/w/$workspaceId'), child: Text('Workspace', style: style)),
        Text(' › ', style: style),
        InkWell(onTap: () => context.go('/w/$workspaceId'), child: Text('Projects', style: style)),
        Text(' › ', style: style),
        Text(projectTitle, style: style.copyWith(color: EvergreenColors.ink, fontWeight: FontWeight.w500)),
      ],
    );
  }
}

class _TabsBar extends StatelessWidget {
  const _TabsBar({
    required this.workspaceId,
    required this.projectId,
    required this.activeTab,
    this.sourcesCount,
    this.chatCount,
  });
  final String workspaceId;
  final String projectId;
  final ProjectTab activeTab;
  final int? sourcesCount;
  final int? chatCount;

  int? _countFor(ProjectTab tab) => switch (tab) {
        ProjectTab.sources => sourcesCount,
        ProjectTab.chatSessions => chatCount,
        _ => null,
      };

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (final t in ProjectTabShell._tabs)
          _TabItem(
            label: t.label,
            count: _countFor(t.tab),
            selected: t.tab == activeTab,
            onTap: () => context.go('/w/$workspaceId/p/$projectId/${t.suffix}'),
          ),
      ],
    );
  }
}

/// DESIGN-evergreen.md "Tabs": active tab has evergreen text and a 2px underline; counts in
/// grey pills.
class _TabItem extends StatelessWidget {
  const _TabItem({required this.label, required this.selected, required this.onTap, this.count});
  final String label;
  final bool selected;
  final VoidCallback onTap;
  final int? count;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(right: 24),
        padding: const EdgeInsets.only(bottom: 10),
        decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: selected ? EvergreenColors.primary : Colors.transparent, width: 2)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                color: selected ? EvergreenColors.primary : EvergreenColors.inkSecondary,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                fontSize: 14,
              ),
            ),
            if (count != null) ...[
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(
                  color: EvergreenColors.fill,
                  borderRadius: BorderRadius.circular(EvergreenRadii.chip),
                ),
                child: Text(
                  '$count',
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: EvergreenColors.metadata),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
