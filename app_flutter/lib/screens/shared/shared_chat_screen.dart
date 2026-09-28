import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../api/models/share.dart';
import '../../features/chat/chat_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/citation_chip.dart';

/// `/s/:token`: a read-only rendering of a shared project's frozen chat, with "Fork to my
/// workspace" for a signed-in viewer. Other users' content only ever renders as markdown text
/// (via `flutter_markdown`, which doesn't execute raw HTML/script) — never as inline HTML or a
/// clickable non-http link, mirroring `ui/index.html`'s `escapeHtmlText`/`htmlSafeCitation`.
class SharedChatScreen extends ConsumerWidget {
  const SharedChatScreen({super.key, required this.token});
  final String token;

  Future<void> _fork(BuildContext context, WidgetRef ref) async {
    final authState = ref.read(authProvider);
    if (authState is! AuthSignedIn) {
      context.go('/signin');
      return;
    }
    try {
      final sessionId = await ref.read(forkSharedChatProvider)(token);
      if (context.mounted) context.go('/w/default/p/$sessionId/chats/default');
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Couldn\'t fork: ${e.detail}')));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshotAsync = ref.watch(sharedChatProvider(token));
    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      appBar: AppBar(
        backgroundColor: EvergreenColors.surface,
        foregroundColor: EvergreenColors.ink,
        title: snapshotAsync.maybeWhen(data: (s) => Text(s.title), orElse: () => const Text('Shared chat')),
        actions: [
          TextButton.icon(
            onPressed: () => _fork(context, ref),
            icon: const Icon(Symbols.call_split, size: 16),
            label: const Text('Fork to my workspace'),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: snapshotAsync.when(
        data: (snapshot) => _SharedConversation(snapshot: snapshot),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Text(
            e is ApiException ? e.detail : 'This shared chat doesn\'t exist or was revoked.',
            style: const TextStyle(color: EvergreenColors.refused),
          ),
        ),
      ),
    );
  }
}

class _SharedConversation extends StatelessWidget {
  const _SharedConversation({required this.snapshot});
  final ShareSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: snapshot.messages.length,
      itemBuilder: (context, i) {
        final m = snapshot.messages[i];
        final isUser = m.role == 'user';
        return Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: Align(
            alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
            child: Container(
              constraints: const BoxConstraints(maxWidth: 640),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: isUser ? EvergreenColors.fill : EvergreenColors.surface,
                border: isUser ? null : Border.all(color: EvergreenColors.border),
                borderRadius: BorderRadius.circular(EvergreenRadii.panel),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  MarkdownBody(data: m.content, shrinkWrap: true, selectable: true),
                  if (m.citations.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [for (final c in m.citations) CitationChip(citation: c)],
                    ),
                  ],
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
