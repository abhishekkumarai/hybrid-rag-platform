import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../api/auth_provider.dart';
import '../../../features/chat/chat_providers.dart';
import '../../../features/project/project_providers.dart';

enum ForkTarget { thisProject, newProject }

/// "Fork dialog: into this project or a new project" (IRA-49). "Into this project" starts a new
/// chat thread here (`POST .../conversations`, IRA-24's threads); "a new project" copies the
/// current project's documents/prompt into a fresh one via [ChatActions.forkFromHere].
Future<void> showForkDialog(BuildContext context, WidgetRef ref, {required String workspaceId, required String sessionId}) {
  return showDialog(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('Fork from here'),
      content: const Text('Continue this conversation in a new chat thread here, or copy it into a brand new project.'),
      actions: [
        TextButton(onPressed: () => Navigator.of(dialogContext).pop(), child: const Text('Cancel')),
        OutlinedButton(
          onPressed: () async {
            Navigator.of(dialogContext).pop();
            final conversation = await ref.read(userApiClientProvider).post(
              '/api/v1/sessions/$sessionId/conversations',
            ) as Map<String, dynamic>;
            ref.invalidate(projectConversationsProvider(sessionId));
            if (context.mounted) {
              context.go('/w/$workspaceId/p/$sessionId/chats/${conversation['id']}');
            }
          },
          child: const Text('This project'),
        ),
        FilledButton(
          onPressed: () async {
            Navigator.of(dialogContext).pop();
            final source = await ref.read(projectProvider(sessionId).future);
            final newSessionId = await ref.read(chatActionsProvider).forkFromHere(source);
            if (context.mounted) {
              context.go('/w/$workspaceId/p/$newSessionId/chats/default');
            }
          },
          child: const Text('New project'),
        ),
      ],
    ),
  );
}
