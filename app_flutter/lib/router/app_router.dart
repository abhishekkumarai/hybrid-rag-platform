import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/auth_provider.dart';
import '../features/workspace/workspace_providers.dart';
import '../screens/evaluation/global_evaluation_screen.dart';
import '../screens/graph/knowledge_graph_screen.dart';
import '../screens/library/library_screen.dart';
import '../screens/models/models_tuning_screen.dart';
import '../screens/observability/observability_screen.dart';
import '../screens/project/project_evaluation_screen.dart';
import '../screens/project/project_overview_screen.dart';
import '../screens/project/project_settings_screen.dart';
import '../screens/project/project_sources_screen.dart';
import '../screens/project/chat/chat_sessions_screen.dart';
import '../screens/ragops/ragops_screen.dart';
import '../screens/settings/settings_screen.dart';
import '../screens/shared/shared_chat_screen.dart';
import '../screens/signin/signin_screen.dart';
import '../screens/workspace/workspace_members_screen.dart';
import '../screens/workspace/workspace_overview_screen.dart';
import '../shell/app_shell.dart';

/// Routes from IRA-47/IRA-50: `/signin`, `/w/:ws`,
/// `/w/:ws/{members,library,evaluation,observability,graph,ragops,models}`,
/// `/w/:ws/p/:project/{overview|sources|chats/:chat|evaluation|settings}`, `/settings`, `/s/:token`.
GoRouter buildRouter(WidgetRef ref) {
  final authListenable = _AuthRefreshListenable(ref);

  return GoRouter(
    initialLocation: '/signin',
    refreshListenable: authListenable,
    redirect: (context, state) {
      final authState = ref.read(authProvider);
      final signedIn = authState is AuthSignedIn;
      final goingToSignIn = state.matchedLocation == '/signin';
      final isShareView = state.matchedLocation.startsWith('/s/');
      if (isShareView) return null; // public, never gated
      if (authState is AuthUnknown) return null; // wait for the session check
      if (!signedIn && !goingToSignIn) return '/signin';
      if (signedIn && goingToSignIn) return '/';
      return null;
    },
    routes: [
      GoRoute(
        path: '/signin',
        builder: (context, state) => const SignInScreen(),
      ),
      GoRoute(
        path: '/s/:token',
        builder: (context, state) =>
            SharedChatScreen(token: state.pathParameters['token']!),
      ),
      GoRoute(
        path: '/settings',
        builder: (context, state) => const SettingsScreen(),
        redirect: _requireWorkspace(ref),
      ),
      ShellRoute(
        builder: (context, state, child) => AppShell(child: child),
        routes: [
          GoRoute(
            path: '/',
            redirect: (context, state) => _defaultWorkspaceRedirect(ref),
          ),
          GoRoute(
            path: '/w/:ws',
            redirect: (context, state) async {
              final ws = state.pathParameters['ws'];
              if (ws == 'default' || ws == 'ws_default') {
                return _defaultWorkspaceRedirect(ref);
              }
              return null;
            },
            builder: (context, state) => WorkspaceOverviewScreen(
              workspaceId: state.pathParameters['ws']!,
            ),
          ),
          GoRoute(
            path: '/w/:ws/overview',
            redirect: (context, state) => '/w/${state.pathParameters['ws']}',
          ),
          GoRoute(
            path: '/w/:ws/members',
            builder: (context, state) => WorkspaceMembersScreen(
              workspaceId: state.pathParameters['ws']!,
            ),
          ),
          GoRoute(
            path: '/w/:ws/library',
            builder: (context, state) =>
                LibraryScreen(workspaceId: state.pathParameters['ws']!),
          ),
          GoRoute(
            path: '/w/:ws/evaluation',
            builder: (context, state) => GlobalEvaluationScreen(
              workspaceId: state.pathParameters['ws']!,
            ),
          ),
          GoRoute(
            path: '/w/:ws/observability',
            builder: (context, state) =>
                ObservabilityScreen(workspaceId: state.pathParameters['ws']!),
          ),
          GoRoute(
            path: '/w/:ws/graph',
            builder: (context, state) =>
                KnowledgeGraphScreen(workspaceId: state.pathParameters['ws']!),
          ),
          GoRoute(
            path: '/w/:ws/ragops',
            builder: (context, state) =>
                RagOpsScreen(workspaceId: state.pathParameters['ws']!),
          ),
          GoRoute(
            path: '/w/:ws/models',
            builder: (context, state) =>
                ModelsTuningScreen(workspaceId: state.pathParameters['ws']!),
          ),
          GoRoute(
            path: '/w/:ws/p/:project/overview',
            builder: (context, state) => ProjectOverviewScreen(
              workspaceId: state.pathParameters['ws']!,
              projectId: state.pathParameters['project']!,
            ),
          ),
          GoRoute(
            path: '/w/:ws/p/:project/sources',
            builder: (context, state) => ProjectSourcesScreen(
              workspaceId: state.pathParameters['ws']!,
              projectId: state.pathParameters['project']!,
            ),
          ),
          GoRoute(
            path: '/w/:ws/p/:project/chats/:chat',
            builder: (context, state) => ChatSessionsScreen(
              workspaceId: state.pathParameters['ws']!,
              projectId: state.pathParameters['project']!,
              conversationId: state.pathParameters['chat']!,
            ),
          ),
          GoRoute(
            path: '/w/:ws/p/:project/evaluation',
            builder: (context, state) => ProjectEvaluationScreen(
              workspaceId: state.pathParameters['ws']!,
              projectId: state.pathParameters['project']!,
            ),
          ),
          GoRoute(
            path: '/w/:ws/p/:project/settings',
            builder: (context, state) => ProjectSettingsScreen(
              workspaceId: state.pathParameters['ws']!,
              projectId: state.pathParameters['project']!,
            ),
          ),
        ],
      ),
    ],
  );
}

GoRouterRedirect _requireWorkspace(WidgetRef ref) =>
    (context, state) => null;

/// Resolves `/` to the caller's actual default (oldest owned) workspace, matching
/// `_default_workspace_id` in `services/gateway/api.py`.
Future<String?> _defaultWorkspaceRedirect(WidgetRef ref) async {
  try {
    final workspaces = await ref.read(workspacesProvider.future);
    if (workspaces.isEmpty) return null;
    return '/w/${workspaces.first.id}';
  } catch (_) {
    return null;
  }
}

class _AuthRefreshListenable extends ChangeNotifier {
  _AuthRefreshListenable(this._ref) {
    _sub = _ref.listenManual(
      authProvider,
      (previous, next) => notifyListeners(),
    );
  }

  final WidgetRef _ref;
  late final ProviderSubscription<AuthState> _sub;

  @override
  void dispose() {
    _sub.close();
    super.dispose();
  }
}
