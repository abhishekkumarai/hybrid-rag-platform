import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'breakpoints.dart';
import 'sidebar.dart';

/// The responsive shared shell (IRA-42/47): sidebar at ≥1200px, a rail with an end drawer at
/// 600-1199px, and a drawer with stacked pages below 600px.
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.child});

  final Widget child;

  String _workspaceIdFrom(BuildContext context) {
    final match = RegExp(r'^/w/([^/]+)').firstMatch(GoRouterState.of(context).matchedLocation);
    return match?.group(1) ?? 'default';
  }

  @override
  Widget build(BuildContext context) {
    final workspaceId = _workspaceIdFrom(context);

    return LayoutBuilder(
      builder: (context, constraints) {
        final breakpoint = breakpointFor(constraints.maxWidth);
        switch (breakpoint) {
          case ShellBreakpoint.wide:
            return Scaffold(
              body: Row(
                children: [
                  AppSidebar(workspaceId: workspaceId),
                  const VerticalDivider(width: 1),
                  Expanded(child: child),
                ],
              ),
            );
          case ShellBreakpoint.medium:
            return Scaffold(
              key: const ValueKey('medium-shell'),
              endDrawer: const Drawer(child: SizedBox.expand()), // IRA-49 fills the inspector in
              body: Row(
                children: [
                  _NavigationRail(workspaceId: workspaceId),
                  const VerticalDivider(width: 1),
                  Expanded(child: child),
                ],
              ),
            );
          case ShellBreakpoint.narrow:
            return Scaffold(
              key: const ValueKey('narrow-shell'),
              appBar: AppBar(title: const Text('IRA'), backgroundColor: Colors.white, foregroundColor: Colors.black),
              drawer: Drawer(child: AppSidebar(workspaceId: workspaceId)),
              body: child,
            );
        }
      },
    );
  }
}

class _NavigationRail extends StatelessWidget {
  const _NavigationRail({required this.workspaceId});
  final String workspaceId;

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    const items = [
      (label: 'Overview', icon: Symbols.dashboard, suffix: ''),
      (label: 'Library', icon: Symbols.folder_open, suffix: '/library'),
      (label: 'Connectors', icon: Symbols.language, suffix: '/connectors'),
      (label: 'Evaluation', icon: Symbols.analytics, suffix: '/evaluation'),
      (label: 'Observability', icon: Symbols.monitoring, suffix: '/observability'),
    ];
    final selectedIndex = items.indexWhere((i) {
      final path = '/w/$workspaceId${i.suffix}';
      return location == path || (i.suffix.isNotEmpty && location.startsWith('$path/'));
    });

    return NavigationRail(
      selectedIndex: selectedIndex < 0 ? 0 : selectedIndex,
      onDestinationSelected: (i) => context.go('/w/$workspaceId${items[i].suffix}'),
      labelType: NavigationRailLabelType.all,
      destinations: [
        for (final item in items) NavigationRailDestination(icon: Icon(item.icon), label: Text(item.label)),
      ],
    );
  }
}
