import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../features/project/project_providers.dart';
import '../theme/evergreen_theme.dart';

/// "All chats" or one of the project's chat threads. `null` means the whole project.
class ChatScopeSelector extends ConsumerWidget {
  const ChatScopeSelector({
    super.key,
    required this.projectId,
    required this.value,
    required this.onChanged,
  });

  final String projectId;
  final String? value;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final conversations =
        ref.watch(projectConversationsProvider(projectId)).valueOrNull ??
        const [];
    // A chat deleted elsewhere falls back to "All chats" rather than an invalid selection.
    final selected = conversations.any((c) => c.id == value) ? value : null;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.control),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String?>(
          value: selected,
          isDense: true,
          icon: const Icon(Symbols.expand_more, size: 18),
          items: [
            const DropdownMenuItem<String?>(
              value: null,
              child: Row(
                children: [
                  Icon(
                    Symbols.forum,
                    size: 16,
                    color: EvergreenColors.metadata,
                  ),
                  SizedBox(width: 8),
                  Text('All chats', style: TextStyle(fontSize: 13)),
                ],
              ),
            ),
            for (final c in conversations)
              DropdownMenuItem<String?>(
                value: c.id,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 260),
                  child: Row(
                    children: [
                      const Icon(
                        Symbols.chat_bubble_outline,
                        size: 16,
                        color: EvergreenColors.metadata,
                      ),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          c.title,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 13),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
          onChanged: onChanged,
        ),
      ),
    );
  }
}
