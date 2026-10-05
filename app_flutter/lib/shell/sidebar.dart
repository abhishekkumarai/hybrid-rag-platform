import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../api/auth_provider.dart';
import '../features/workspace/workspace_providers.dart';
import '../theme/evergreen_theme.dart';
import '../widgets/create_project_dialog.dart';
import '../widgets/workspace_switcher_sheet.dart';

/// Rotates project rows through the design's four folder tints (DESIGN-evergreen.md) since the
/// backend doesn't assign a color/tint to a project — a stable per-project choice beats a random
/// one, so this keys off the row's position in the (stably ordered) list.
const _folderTints = [
  (fill: EvergreenColors.folderSage, icon: EvergreenColors.folderSageIcon),
  (fill: EvergreenColors.folderSky, icon: EvergreenColors.folderSkyIcon),
  (fill: EvergreenColors.folderSand, icon: EvergreenColors.folderSandIcon),
  (fill: EvergreenColors.folderRose, icon: EvergreenColors.folderRoseIcon),
];

/// The shared sidebar (`ui/stitch_workspace/DESIGN-evergreen.md`): logo → workspace switcher →
/// nav (Overview · Library · Evaluation · Observability) → PROJECTS list → footer (Settings,
/// services health, user card).
class AppSidebar extends ConsumerWidget {
  const AppSidebar({super.key, required this.workspaceId});

  final String workspaceId;

  /// The four items DESIGN-evergreen.md's sidebar spec names explicitly.
  static const _navItems = [
    (label: 'Overview', icon: Symbols.dashboard, suffix: ''),
    (label: 'Library', icon: Symbols.folder_open, suffix: '/library'),
    (label: 'Evaluation', icon: Symbols.analytics, suffix: '/evaluation'),
    (
      label: 'Observability',
      icon: Symbols.monitoring,
      suffix: '/observability',
    ),
  ];

  /// IRA-50 pages the spec's literal nav list doesn't name but that must still be reachable —
  /// grouped separately below the primary nav, above PROJECTS.
  static const _moreNavItems = [
    (label: 'Knowledge graph', icon: Symbols.hub, suffix: '/graph'),
    (label: 'RAGOps', icon: Symbols.science, suffix: '/ragops'),
    (label: 'Models & tuning', icon: Symbols.tune, suffix: '/models'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final location = GoRouterState.of(context).matchedLocation;

    return Container(
      width: 260,
      color: EvergreenColors.surface,
      // Nav + projects scroll; the footer (health, Settings, account + sign out) stays pinned so it
      // is reachable on short windows without scrolling the sidebar.
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: Scrollbar(
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _Logo(workspaceId: workspaceId),
                    const Divider(height: 1, color: EvergreenColors.border),
                    _WorkspaceSwitcher(workspaceId: workspaceId),
                    const SizedBox(height: 8),
                    for (final item in _navItems)
                      _NavTile(
                        label: item.label,
                        icon: item.icon,
                        selected: location == '/w/$workspaceId${item.suffix}',
                        onTap: () =>
                            context.go('/w/$workspaceId${item.suffix}'),
                      ),
                    const Divider(
                      height: 17,
                      indent: 12,
                      endIndent: 12,
                      color: EvergreenColors.border,
                    ),
                    for (final item in _moreNavItems)
                      _NavTile(
                        label: item.label,
                        icon: item.icon,
                        selected: location == '/w/$workspaceId${item.suffix}',
                        onTap: () =>
                            context.go('/w/$workspaceId${item.suffix}'),
                      ),
                    const SizedBox(height: 16),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              'PROJECTS',
                              style: monoStyle(
                                fontSize: 11,
                                color: EvergreenColors.metadata,
                              ).copyWith(letterSpacing: 1.0),
                            ),
                          ),
                          InkWell(
                            borderRadius: BorderRadius.circular(
                              EvergreenRadii.control,
                            ),
                            onTap: () =>
                                createProjectDialog(context, ref, workspaceId),
                            child: const Padding(
                              padding: EdgeInsets.all(2),
                              child: Icon(
                                Symbols.add,
                                size: 16,
                                color: EvergreenColors.metadata,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 4),
                    _ProjectsList(workspaceId: workspaceId),
                    const SizedBox(height: 16),
                  ],
                ),
              ),
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: Divider(height: 1, color: EvergreenColors.border),
          ),
          const SizedBox(height: 14),
          const _ServiceHealthRow(),
          const SizedBox(height: 8),
          _FooterUserCard(
            email: auth is AuthSignedIn ? auth.user.email : '',
            isDemo: auth is AuthSignedIn && auth.user.isDemo,
          ),
        ],
      ),
    );
  }
}

class _Logo extends StatelessWidget {
  const _Logo({required this.workspaceId});
  final String workspaceId;

  @override
  Widget build(BuildContext context) => Tooltip(
    message: 'Home',
    child: Material(
      color: Colors.transparent,
      child: InkWell(
        // Home = this workspace's overview (the router sends users with no workspace to /home).
        onTap: () => context.go('/w/$workspaceId'),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: EvergreenColors.primary,
                  borderRadius: BorderRadius.circular(EvergreenRadii.control),
                ),
                alignment: Alignment.center,
                child: const Text(
                  'R',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(width: 10),
              Text(
                'IRA',
                style: Theme.of(context).textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class _WorkspaceSwitcher extends ConsumerWidget {
  const _WorkspaceSwitcher({required this.workspaceId});
  final String workspaceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final workspaces = ref.watch(workspacesProvider).valueOrNull;
    final workspace = workspaces?.where((w) => w.id == workspaceId).firstOrNull;
    final name = workspace?.name ?? workspaceId;

    final auth = ref.watch(authProvider);
    final userId = auth is AuthSignedIn ? auth.user.id : null;
    final members = ref
        .watch(workspaceMembersProvider(workspaceId))
        .valueOrNull;
    final myRole = members
        ?.where((m) => m.user.id == userId)
        .firstOrNull
        ?.member
        .role;
    final subtitle = myRole == null ? 'Workspace' : 'Workspace · $myRole';

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Material(
        color: EvergreenColors.fill,
        borderRadius: BorderRadius.circular(EvergreenRadii.control),
        child: Row(
          children: [
            Expanded(
              child: InkWell(
                borderRadius: const BorderRadius.horizontal(
                  left: Radius.circular(EvergreenRadii.control),
                ),
                onTap: () => showWorkspaceSwitcher(
                  context,
                  ref,
                  currentWorkspaceId: workspaceId,
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 8,
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 28,
                        height: 28,
                        decoration: BoxDecoration(
                          color: EvergreenColors.primaryTint,
                          borderRadius: BorderRadius.circular(
                            EvergreenRadii.control,
                          ),
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          name.isNotEmpty ? name[0].toUpperCase() : 'W',
                          style: const TextStyle(
                            color: EvergreenColors.primary,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              name,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            Text(
                              subtitle,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 12,
                                color: EvergreenColors.metadata,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const Icon(
                        Symbols.unfold_more,
                        size: 16,
                        color: EvergreenColors.metadata,
                      ),
                    ],
                  ),
                ),
              ),
            ),
            IconButton(
              icon: const Icon(
                Symbols.add,
                size: 16,
                color: EvergreenColors.metadata,
              ),
              tooltip: 'Create workspace',
              visualDensity: VisualDensity.compact,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
              onPressed: () => showCreateWorkspaceDialog(context, ref),
            ),
            const SizedBox(width: 4),
          ],
        ),
      ),
    );
  }
}

class _NavTile extends StatelessWidget {
  const _NavTile({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      child: Material(
        color: selected ? EvergreenColors.primaryTint : Colors.transparent,
        borderRadius: BorderRadius.circular(EvergreenRadii.control),
        child: InkWell(
          borderRadius: BorderRadius.circular(EvergreenRadii.control),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Row(
              children: [
                Icon(
                  icon,
                  size: 20,
                  color: selected
                      ? EvergreenColors.primary
                      : EvergreenColors.inkSecondary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    label,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: selected
                          ? EvergreenColors.primary
                          : EvergreenColors.ink,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ProjectsList extends ConsumerWidget {
  const _ProjectsList({required this.workspaceId});
  final String workspaceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projectsAsync = ref.watch(workspaceProjectsProvider(workspaceId));
    if (projectsAsync.isLoading && !projectsAsync.hasValue) {
      return const Padding(
        padding: EdgeInsets.symmetric(horizontal: 20, vertical: 8),
        child: LinearProgressIndicator(minHeight: 2),
      );
    }
    if (projectsAsync.hasError && !projectsAsync.hasValue) {
      return const Padding(
        padding: EdgeInsets.symmetric(horizontal: 20, vertical: 8),
        child: Text(
          'Could not load projects',
          style: TextStyle(fontSize: 12, color: EvergreenColors.refused),
        ),
      );
    }
    final list = projectsAsync.valueOrNull ?? const [];
    if (list.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(horizontal: 20, vertical: 8),
        child: Text(
          'No projects yet',
          style: TextStyle(fontSize: 12, color: EvergreenColors.metadata),
        ),
      );
    }
    final location = GoRouterState.of(context).matchedLocation;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final (index, project) in list.indexed)
          _ProjectTile(
            title: project.title,
            tint: _folderTints[index % _folderTints.length],
            selected: location.startsWith('/w/$workspaceId/p/${project.id}'),
            onTap: () => context.go('/w/$workspaceId/p/${project.id}/overview'),
          ),
      ],
    );
  }
}

class _ProjectTile extends StatelessWidget {
  const _ProjectTile({
    required this.title,
    required this.tint,
    required this.selected,
    required this.onTap,
  });
  final String title;
  final ({Color fill, Color icon}) tint;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 1),
      child: Material(
        color: selected ? EvergreenColors.primaryTint : Colors.transparent,
        borderRadius: BorderRadius.circular(EvergreenRadii.control),
        child: InkWell(
          borderRadius: BorderRadius.circular(EvergreenRadii.control),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: [
                Container(
                  width: 20,
                  height: 20,
                  decoration: BoxDecoration(
                    color: tint.fill,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  alignment: Alignment.center,
                  child: Icon(Symbols.folder, size: 13, color: tint.icon),
                ),
                const SizedBox(width: 10),
                if (selected)
                  Container(
                    width: 6,
                    height: 6,
                    margin: const EdgeInsets.only(right: 6),
                    decoration: const BoxDecoration(
                      color: EvergreenColors.primary,
                      shape: BoxShape.circle,
                    ),
                  ),
                Expanded(
                  child: Text(
                    title,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13,
                      color: selected
                          ? EvergreenColors.primary
                          : EvergreenColors.ink,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Services health (Qdrant · Redis · Ollama) — matching 01_workspace_overview.html infra health pill bar.
class _ServiceHealthRow extends ConsumerWidget {
  const _ServiceHealthRow();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final health = ref.watch(serviceHealthProvider).valueOrNull;
    final qdrant = health?.qdrantAlive ?? false;
    final redis = health?.redisAlive ?? false;
    final ollama = health?.ollamaAlive ?? false;
    final aliveCount = (qdrant ? 1 : 0) + (redis ? 1 : 0) + (ollama ? 1 : 0);
    final isFullyHealthy = aliveCount == 3;
    final pct = (aliveCount / 3 * 100).round();

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
        decoration: BoxDecoration(
          color: EvergreenColors.canvas,
          borderRadius: BorderRadius.circular(EvergreenRadii.control),
          border: Border.all(color: EvergreenColors.border),
        ),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: isFullyHealthy
                    ? EvergreenColors.confident
                    : (aliveCount > 0
                          ? EvergreenColors.ambiguous
                          : EvergreenColors.refused),
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Qdrant · Redis · Ollama',
                style: monoStyle(
                  fontSize: 10,
                  color: EvergreenColors.inkSecondary,
                ).copyWith(letterSpacing: -0.2),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
              decoration: BoxDecoration(
                color: isFullyHealthy
                    ? EvergreenColors.confidentTint
                    : EvergreenColors.canvas,
                borderRadius: BorderRadius.circular(4),
                border: Border.all(
                  color: isFullyHealthy
                      ? EvergreenColors.confident.withValues(alpha: 0.3)
                      : EvergreenColors.border,
                ),
              ),
              child: Text(
                '$pct%',
                style: monoStyle(
                  fontSize: 9,
                  weight: FontWeight.w600,
                  color: isFullyHealthy
                      ? EvergreenColors.confident
                      : EvergreenColors.metadata,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FooterUserCard extends ConsumerWidget {
  const _FooterUserCard({required this.email, required this.isDemo});
  final String email;
  final bool isDemo;

  Future<void> _signOut(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sign out?'),
        content: Text(
          isDemo
              ? 'This is a guest account. After signing out you won\'t be able to sign back in to it, '
                    'and its projects will no longer be reachable.'
              : 'You can sign back in with your email and password.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    // A deliberate sign-out must not carry this account's location (`?from=`) to the next sign-in.
    final router = GoRouter.of(context);
    await ref.read(authProvider.notifier).logout();
    router.go('/signin');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final initials = email.isNotEmpty ? email[0].toUpperCase() : 'U';
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 10),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Material(
            color: Colors.transparent,
            borderRadius: BorderRadius.circular(EvergreenRadii.control),
            child: InkWell(
              borderRadius: BorderRadius.circular(EvergreenRadii.control),
              onTap: () => context.push('/settings'),
              child: const Padding(
                padding: EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                child: Row(
                  children: [
                    Icon(
                      Symbols.settings,
                      size: 18,
                      color: EvergreenColors.inkSecondary,
                    ),
                    SizedBox(width: 10),
                    Text(
                      'Settings',
                      style: TextStyle(
                        fontSize: 13,
                        color: EvergreenColors.inkSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 4),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            child: Row(
              children: [
                Container(
                  width: 26,
                  height: 26,
                  decoration: BoxDecoration(
                    color: EvergreenColors.fill,
                    shape: BoxShape.circle,
                    border: Border.all(color: EvergreenColors.border),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    initials,
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: EvergreenColors.ink,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    email.isNotEmpty ? email : 'Signed in',
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 12,
                      color: EvergreenColors.inkSecondary,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Sign out',
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(
                    Symbols.logout,
                    size: 16,
                    color: EvergreenColors.metadata,
                  ),
                  onPressed: () => _signOut(context, ref),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
