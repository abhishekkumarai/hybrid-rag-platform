import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../features/workspace/workspace_providers.dart';
import '../theme/evergreen_theme.dart';

Future<void> showWorkspaceSwitcher(BuildContext context, WidgetRef ref, {required String currentWorkspaceId}) async {
  final action = await showModalBottomSheet<String>(
    context: context,
    backgroundColor: EvergreenColors.surface,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(EvergreenRadii.panel))),
    builder: (sheetContext) => _WorkspaceSwitcherSheet(
      currentWorkspaceId: currentWorkspaceId,
      onCreateWorkspace: () => Navigator.of(sheetContext).pop('__create__'),
    ),
  );
  if (action == '__create__' && context.mounted) {
    await showCreateWorkspaceDialog(context, ref);
  }
}

class _WorkspaceSwitcherSheet extends ConsumerWidget {
  const _WorkspaceSwitcherSheet({
    required this.currentWorkspaceId,
    required this.onCreateWorkspace,
  });
  final String currentWorkspaceId;
  final VoidCallback onCreateWorkspace;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final workspaces = ref.watch(workspacesProvider);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Switch workspace', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            workspaces.when(
              data: (list) => Column(
                children: [
                  for (final ws in list)
                    ListTile(
                      leading: CircleAvatar(
                        backgroundColor: EvergreenColors.primaryTint,
                        child: Text(ws.name.isNotEmpty ? ws.name[0].toUpperCase() : 'W',
                            style: const TextStyle(color: EvergreenColors.primary)),
                      ),
                      title: Text(ws.name),
                      trailing: ws.id == currentWorkspaceId ? const Icon(Symbols.check, color: EvergreenColors.primary) : null,
                      onTap: () {
                        ref.read(currentWorkspaceIdProvider.notifier).state = ws.id;
                        Navigator.of(context).pop();
                        context.go('/w/${ws.id}');
                      },
                    ),
                ],
              ),
              loading: () => const Padding(
                padding: EdgeInsets.all(16),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => Padding(padding: const EdgeInsets.all(16), child: Text('Failed to load workspaces: $e')),
            ),
            const Divider(height: 24),
            ListTile(
              leading: const Icon(Symbols.add, color: EvergreenColors.primary),
              title: const Text('Create workspace'),
              onTap: onCreateWorkspace,
            ),
          ],
        ),
      ),
    );
  }
}

Future<void> showCreateWorkspaceDialog(BuildContext context, WidgetRef ref) async {
  final name = await showDialog<String>(
    context: context,
    barrierDismissible: true,
    builder: (dialogContext) => const _CreateWorkspaceModal(),
  );
  if (name == null || name.trim().isEmpty) return;
  try {
    final workspace = await ref.read(workspaceActionsProvider).create(name.trim());
    ref.read(currentWorkspaceIdProvider.notifier).state = workspace.id;
    ref.invalidate(workspacesProvider);
    if (context.mounted) {
      context.go('/w/${workspace.id}');
    }
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to create workspace: $e')),
      );
    }
  }
}

class _CreateWorkspaceModal extends StatefulWidget {
  const _CreateWorkspaceModal();

  @override
  State<_CreateWorkspaceModal> createState() => _CreateWorkspaceModalState();
}

class _CreateWorkspaceModalState extends State<_CreateWorkspaceModal> {
  final _controller = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final text = _controller.text.trim();
    if (text.isEmpty) {
      setState(() => _error = 'Workspace name is required');
      return;
    }
    Navigator.of(context).pop(text);
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: EvergreenColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        side: const BorderSide(color: EvergreenColors.border),
      ),
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: EvergreenColors.primaryTint,
                      borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    ),
                    alignment: Alignment.center,
                    child: const Icon(
                      Symbols.workspaces,
                      color: EvergreenColors.primary,
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const [
                        Text(
                          'Create Workspace',
                          style: TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: EvergreenColors.ink,
                            letterSpacing: -0.3,
                          ),
                        ),
                        SizedBox(height: 2),
                        Text(
                          'Create an isolated workspace for filings and chat projects.',
                          style: TextStyle(fontSize: 12, color: EvergreenColors.metadata),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Symbols.close, size: 18, color: EvergreenColors.metadata),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              const Divider(height: 1, color: EvergreenColors.border),
              const SizedBox(height: 18),
              if (_error != null) ...[
                Container(
                  padding: const EdgeInsets.all(10),
                  margin: const EdgeInsets.only(bottom: 14),
                  decoration: BoxDecoration(
                    color: EvergreenColors.refusedTint,
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    border: Border.all(color: EvergreenColors.refused.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Symbols.error, size: 16, color: EvergreenColors.refused),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _error!,
                          style: const TextStyle(fontSize: 12, color: EvergreenColors.refused),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              const Text(
                'Workspace Name',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: EvergreenColors.ink),
              ),
              const SizedBox(height: 6),
              TextField(
                controller: _controller,
                autofocus: true,
                style: const TextStyle(fontSize: 14),
                decoration: InputDecoration(
                  hintText: 'e.g. Equity Research, Credit Risk, M&A Due Diligence',
                  hintStyle: const TextStyle(color: EvergreenColors.metadata, fontSize: 13),
                  isDense: true,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  filled: true,
                  fillColor: EvergreenColors.fill,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.border),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.border),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.primary, width: 1.5),
                  ),
                ),
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 24),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  OutlinedButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: EvergreenColors.inkSecondary,
                      side: const BorderSide(color: EvergreenColors.border),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(EvergreenRadii.control),
                      ),
                    ),
                    child: const Text('Cancel'),
                  ),
                  const SizedBox(width: 12),
                  FilledButton(
                    onPressed: _submit,
                    style: FilledButton.styleFrom(
                      backgroundColor: EvergreenColors.primary,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(EvergreenRadii.control),
                      ),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Symbols.add, size: 16),
                        SizedBox(width: 6),
                        Text('Create workspace', style: TextStyle(fontWeight: FontWeight.w600)),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
