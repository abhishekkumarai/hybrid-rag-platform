import 'package:app_flutter/api/models/session.dart';
import 'package:app_flutter/features/workspace/workspace_providers.dart';
import 'package:app_flutter/shell/app_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

/// Verifies the three IRA-47/48 shell breakpoints render structurally distinct layouts: a
/// permanent sidebar at ≥1200px, a `NavigationRail` at 600-1199px, and a `Drawer` (app bar +
/// hamburger) below 600px.
void main() {
  Widget testApp() {
    final router = GoRouter(
      initialLocation: '/w/ws1',
      routes: [
        ShellRoute(
          builder: (context, state, child) => AppShell(child: child),
          routes: [
            GoRoute(path: '/w/:ws', builder: (context, state) => const SizedBox()),
          ],
        ),
      ],
    );
    return ProviderScope(
      overrides: [
        // The sidebar's PROJECTS list would otherwise hit the real network via apiClientProvider
        // and never settle (a spinning CircularProgressIndicator blocks pumpAndSettle forever).
        workspaceProjectsProvider.overrideWith((ref, workspaceId) async => <ChatSession>[]),
      ],
      child: MaterialApp.router(routerConfig: router),
    );
  }

  Future<void> setSurfaceWidth(WidgetTester tester, double width) async {
    await tester.binding.setSurfaceSize(Size(width, 900));
    tester.view.physicalSize = Size(width, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
  }

  testWidgets('wide (>=1200px) renders a permanent sidebar, no drawer', (tester) async {
    await setSurfaceWidth(tester, 1400);
    await tester.pumpWidget(testApp());
    await tester.pumpAndSettle();
    expect(find.byType(NavigationRail), findsNothing);
    expect(find.byType(Drawer), findsNothing);
    expect(find.byType(Scaffold), findsOneWidget);
  });

  testWidgets('medium (600-1199px) renders a NavigationRail with an end drawer', (tester) async {
    await setSurfaceWidth(tester, 900);
    await tester.pumpWidget(testApp());
    await tester.pumpAndSettle();
    expect(find.byType(NavigationRail), findsOneWidget);
    final scaffold = tester.widget<Scaffold>(find.byType(Scaffold));
    expect(scaffold.endDrawer, isNotNull);
  });

  testWidgets('narrow (<600px) renders an app bar with a drawer', (tester) async {
    await setSurfaceWidth(tester, 400);
    await tester.pumpWidget(testApp());
    await tester.pumpAndSettle();
    expect(find.byType(AppBar), findsOneWidget);
    final scaffold = tester.widget<Scaffold>(find.byType(Scaffold));
    expect(scaffold.drawer, isNotNull);
    expect(find.byType(NavigationRail), findsNothing);
  });
}
