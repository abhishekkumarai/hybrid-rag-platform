import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../features/workspace/workspace_providers.dart';
import '../../theme/evergreen_theme.dart';

/// Home for a signed-in user with no workspace yet. Workspaces are never created implicitly, so
/// this is where a new account makes its first one.
class NoWorkspaceHomeScreen extends ConsumerStatefulWidget {
  const NoWorkspaceHomeScreen({super.key});

  @override
  ConsumerState<NoWorkspaceHomeScreen> createState() => _NoWorkspaceHomeScreenState();
}

class _NoWorkspaceHomeScreenState extends ConsumerState<NoWorkspaceHomeScreen> {
  final _name = TextEditingController();
  bool _creating = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _error = 'Give your workspace a name.');
      return;
    }
    setState(() {
      _creating = true;
      _error = null;
    });
    try {
      final ws = await ref.read(workspaceActionsProvider).create(name);
      if (mounted) context.go('/w/${ws.id}');
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _signOut() async {
    final router = GoRouter.of(context);
    await ref.read(authProvider.notifier).logout();
    router.go('/signin');
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final email = auth is AuthSignedIn ? auth.user.email : '';

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Container(
                padding: const EdgeInsets.all(28),
                decoration: BoxDecoration(
                  color: EvergreenColors.surface,
                  borderRadius: BorderRadius.circular(EvergreenRadii.panel),
                  border: Border.all(color: EvergreenColors.border),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: EvergreenColors.primaryTint,
                        borderRadius: BorderRadius.circular(EvergreenRadii.control),
                      ),
                      child: const Icon(Symbols.workspaces, color: EvergreenColors.primary, size: 22),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Create your first workspace',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'A workspace holds your projects and their documents. You can invite others to it later.',
                      style: TextStyle(fontSize: 13, color: EvergreenColors.metadata, height: 1.4),
                    ),
                    const SizedBox(height: 20),
                    TextField(
                      controller: _name,
                      autofocus: true,
                      enabled: !_creating,
                      decoration: InputDecoration(labelText: 'Workspace name', errorText: _error),
                      onSubmitted: (_) => _create(),
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: _creating ? null : _create,
                        child: _creating
                            ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                            : const Text('Create workspace'),
                      ),
                    ),
                    const SizedBox(height: 20),
                    const Divider(height: 1, color: EvergreenColors.border),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            email.isEmpty ? '' : 'Signed in as $email',
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 12, color: EvergreenColors.metadata),
                          ),
                        ),
                        TextButton.icon(
                          onPressed: _signOut,
                          icon: const Icon(Symbols.logout, size: 16),
                          label: const Text('Sign out'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
