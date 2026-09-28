import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/models/identity.dart';
import '../../features/workspace/workspace_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';

/// DESIGN-evergreen.md workspace Members: list, add by email, change role, remove.
class WorkspaceMembersScreen extends ConsumerWidget {
  const WorkspaceMembersScreen({super.key, required this.workspaceId});
  final String workspaceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final membersAsync = ref.watch(workspaceMembersProvider(workspaceId));

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SectionHeader(
                title: 'Members',
                action: FilledButton.icon(
                  onPressed: () => _showAddMemberDialog(context, ref),
                  icon: const Icon(Symbols.person_add, size: 18),
                  label: const Text('Add member'),
                ),
              ),
              membersAsync.when(
                data: (members) {
                  if (members.isEmpty) {
                    return const EmptyState(message: 'No members yet.', icon: Symbols.group);
                  }
                  return Container(
                    decoration: BoxDecoration(
                      color: EvergreenColors.surface,
                      borderRadius: BorderRadius.circular(EvergreenRadii.panel),
                      border: Border.all(color: EvergreenColors.border),
                    ),
                    child: Column(
                      children: [
                        for (var i = 0; i < members.length; i++) ...[
                          _MemberRow(entry: members[i], workspaceId: workspaceId),
                          if (i != members.length - 1) const Divider(height: 1, color: EvergreenColors.border),
                        ],
                      ],
                    ),
                  );
                },
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (e, _) => Text('Failed to load members: $e', style: const TextStyle(color: EvergreenColors.refused)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showAddMemberDialog(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController();
    String role = 'member';
    final result = await showDialog<String>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Add member'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: controller, decoration: const InputDecoration(hintText: 'Email address')),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: role,
                items: const [
                  DropdownMenuItem(value: 'member', child: Text('Member')),
                  DropdownMenuItem(value: 'admin', child: Text('Admin')),
                ],
                onChanged: (v) => setState(() => role = v ?? 'member'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.of(context).pop(role), child: const Text('Add')),
          ],
        ),
      ),
    );
    if (result == null || controller.text.trim().isEmpty) return;
    try {
      await ref.read(workspaceActionsProvider).addMember(workspaceId, controller.text.trim(), result);
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not add member: $e')));
      }
    }
  }
}

class _MemberRow extends ConsumerWidget {
  const _MemberRow({required this.entry, required this.workspaceId});
  final WorkspaceMemberEntry entry;
  final String workspaceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: EvergreenColors.primaryTint,
        child: Text(
          entry.user.displayName.isNotEmpty ? entry.user.displayName[0].toUpperCase() : entry.user.email[0].toUpperCase(),
          style: const TextStyle(color: EvergreenColors.primary),
        ),
      ),
      title: Text(entry.user.displayName.isNotEmpty ? entry.user.displayName : entry.user.email),
      subtitle: Text(entry.user.email, style: const TextStyle(fontSize: 12, color: EvergreenColors.metadata)),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          DropdownButton<String>(
            value: entry.member.role,
            underline: const SizedBox.shrink(),
            items: const [
              DropdownMenuItem(value: 'owner', enabled: false, child: Text('Owner')),
              DropdownMenuItem(value: 'admin', child: Text('Admin')),
              DropdownMenuItem(value: 'member', child: Text('Member')),
            ],
            onChanged: entry.member.role == 'owner'
                ? null
                : (role) {
                    if (role == null) return;
                    ref.read(workspaceActionsProvider).updateMemberRole(workspaceId, entry.user.id, role);
                  },
          ),
          if (entry.member.role != 'owner')
            IconButton(
              icon: const Icon(Symbols.close, size: 18, color: EvergreenColors.refused),
              onPressed: () => ref.read(workspaceActionsProvider).removeMember(workspaceId, entry.user.id),
            ),
        ],
      ),
    );
  }
}
