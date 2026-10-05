import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../../api/models/retrieval.dart';
import '../../../api/models/session.dart';
import '../../../features/chat/chat_providers.dart';
import '../../../features/chat/chat_state.dart';
import '../../../features/project/project_providers.dart';
import '../../../features/workspace/workspace_providers.dart';
import '../../../widgets/section_header.dart';
import '../../../theme/evergreen_theme.dart';
import '../../../widgets/answer_state_chip.dart';
import '../../../widgets/citation_chip.dart';
import '../../../widgets/eval_strip.dart';
import '../project_tab_shell.dart';
import 'citation_inspector_panel.dart';
import 'fork_dialog.dart';

/// DESIGN-evergreen.md "Chat sessions tab": sessions list · conversation · citation inspector ·
/// docked composer. ≥900px available width shows all three panes; narrower shows the
/// conversation with the inspector as a bottom sheet (the sessions list becomes a picker button).
class ChatSessionsScreen extends ConsumerStatefulWidget {
  const ChatSessionsScreen({
    super.key,
    required this.workspaceId,
    required this.projectId,
    required this.conversationId,
  });

  final String workspaceId;
  final String projectId;
  final String conversationId;

  @override
  ConsumerState<ChatSessionsScreen> createState() => _ChatSessionsScreenState();
}

class _ChatSessionsScreenState extends ConsumerState<ChatSessionsScreen> {
  final _composerController = TextEditingController();
  String? _mode; // null = the project's retrieval mode
  String? _model;
  Citation? _inspectorCitation;
  List<Citation> _inspectorList = const [];

  @override
  void dispose() {
    _composerController.dispose();
    super.dispose();
  }

  ChatConversationKey get _key => ChatConversationKey(widget.projectId, widget.conversationId);

  void _openInspector(List<Citation> all, Citation citation) {
    setState(() {
      _inspectorList = all;
      _inspectorCitation = citation;
    });
    final width = MediaQuery.sizeOf(context).width;
    if (width < 900) {
      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        builder: (_) => SizedBox(
          height: MediaQuery.sizeOf(context).height * 0.8,
          child: CitationInspectorPanel(
            citations: all,
            selected: citation,
            onSelect: (c) => setState(() => _inspectorCitation = c),
            onClose: () => Navigator.of(context).pop(),
          ),
        ),
      );
    }
  }

  Future<void> _send() async {
    final text = _composerController.text.trim();
    if (text.isEmpty || ref.read(chatControllerProvider(_key)).sending) return;
    _composerController.clear();
    await ref.read(chatControllerProvider(_key).notifier).send(text, mode: _mode, model: _model);
    ref.invalidate(projectConversationsProvider(widget.projectId));
  }

  @override
  Widget build(BuildContext context) {
    // `chats/default` is a UI alias; the backend only knows real thread ids, so resolve it to the
    // project's default (oldest) thread — listing conversations creates it if none exists yet.
    if (widget.conversationId == 'default') {
      final conversationsAsync = ref.watch(projectConversationsProvider(widget.projectId));
      final list = conversationsAsync.valueOrNull;
      if (list != null && list.isNotEmpty) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (context.mounted) {
            context.go('/w/${widget.workspaceId}/p/${widget.projectId}/chats/${list.first.id}');
          }
        });
      }
      return ProjectTabShell(
        workspaceId: widget.workspaceId,
        projectId: widget.projectId,
        activeTab: ProjectTab.chatSessions,
        child: Center(
          child: conversationsAsync.hasError
              ? Text('Failed to load chats: ${conversationsAsync.error}',
                  style: const TextStyle(color: EvergreenColors.refused))
              : const CircularProgressIndicator(),
        ),
      );
    }
    return ProjectTabShell(
      workspaceId: widget.workspaceId,
      projectId: widget.projectId,
      activeTab: ProjectTab.chatSessions,
      child: LayoutBuilder(builder: (context, constraints) {
      final wide = constraints.maxWidth >= 900;
      return Row(
        children: [
          if (wide) SizedBox(width: 260, child: _SessionsList(workspaceId: widget.workspaceId, projectId: widget.projectId, activeConversationId: widget.conversationId)),
          if (wide) const VerticalDivider(width: 1, color: EvergreenColors.border),
          Expanded(
            child: Column(
              children: [
                if (!wide) _SessionsPickerBar(workspaceId: widget.workspaceId, projectId: widget.projectId, activeConversationId: widget.conversationId),
                Expanded(
                  child: _Conversation(
                    conversationKey: _key,
                    projectId: widget.projectId,
                    onCiteTap: _openInspector,
                    onForkFromHere: () => showForkDialog(context, ref, workspaceId: widget.workspaceId, sessionId: widget.projectId),
                  ),
                ),
                _Composer(
                  projectId: widget.projectId,
                  controller: _composerController,
                  mode: _mode,
                  model: _model,
                  onModeChanged: (m) => setState(() => _mode = m),
                  onModelChanged: (m) => setState(() => _model = m),
                  onSend: _send,
                  sending: ref.watch(chatControllerProvider(_key)).sending,
                ),
              ],
            ),
          ),
          if (wide && _inspectorCitation != null) ...[
            const VerticalDivider(width: 1, color: EvergreenColors.border),
            SizedBox(
              width: 360,
              child: CitationInspectorPanel(
                citations: _inspectorList,
                selected: _inspectorCitation!,
                onSelect: (c) => setState(() => _inspectorCitation = c),
                onClose: () => setState(() => _inspectorCitation = null),
              ),
            ),
          ],
        ],
      );
      }),
    );
  }
}

class _SessionsPickerBar extends ConsumerWidget {
  const _SessionsPickerBar({required this.workspaceId, required this.projectId, required this.activeConversationId});
  final String workspaceId;
  final String projectId;
  final String activeConversationId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: EvergreenColors.border))),
      child: Row(
        children: [
          IconButton(
            icon: const Icon(Symbols.forum, size: 18),
            tooltip: 'Chat threads',
            onPressed: () => showModalBottomSheet(
              context: context,
              isScrollControlled: true,
              builder: (_) => SizedBox(
                height: MediaQuery.sizeOf(context).height * 0.7,
                child: _SessionsList(workspaceId: workspaceId, projectId: projectId, activeConversationId: activeConversationId),
              ),
            ),
          ),
          const Text('Chat threads', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}

String _dayBucket(DateTime dt) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final that = DateTime(dt.year, dt.month, dt.day);
  final diff = today.difference(that).inDays;
  if (diff <= 0) return 'Today';
  if (diff == 1) return 'Yesterday';
  return 'Earlier';
}

class _SessionsList extends ConsumerStatefulWidget {
  const _SessionsList({required this.workspaceId, required this.projectId, required this.activeConversationId});
  final String workspaceId;
  final String projectId;
  final String activeConversationId;

  @override
  ConsumerState<_SessionsList> createState() => _SessionsListState();
}

class _SessionsListState extends ConsumerState<_SessionsList> {
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _newChat() async {
    final newId = await ref
        .read(chatControllerProvider(ChatConversationKey(widget.projectId, widget.activeConversationId)).notifier)
        .newConversation();
    ref.invalidate(projectConversationsProvider(widget.projectId));
    if (mounted) context.go('/w/${widget.workspaceId}/p/${widget.projectId}/chats/$newId');
  }

  @override
  Widget build(BuildContext context) {
    final conversationsAsync = ref.watch(projectConversationsProvider(widget.projectId));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: FilledButton.icon(
            onPressed: _newChat,
            icon: const Icon(Symbols.add, size: 16),
            label: const Text('New chat'),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: TextField(
            controller: _search,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(
              isDense: true,
              hintText: 'Search',
              prefixIcon: Icon(Symbols.search, size: 18),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Expanded(
          child: Builder(builder: (context) {
            if (conversationsAsync.isLoading && !conversationsAsync.hasValue) {
              return const Center(child: CircularProgressIndicator());
            }
            if (conversationsAsync.hasError && !conversationsAsync.hasValue) {
              return EmptyState(message: 'Could not load chats: ${conversationsAsync.error}');
            }
            final conversations = conversationsAsync.valueOrNull ?? const <Conversation>[];
            if (conversations.isEmpty) {
              return const EmptyState(message: 'No chats yet.', icon: Symbols.forum);
            }
            final query = _search.text.trim().toLowerCase();
            final filtered = query.isEmpty
                ? conversations
                : conversations.where((c) => c.title.toLowerCase().contains(query)).toList();
            final groups = <String, List<Conversation>>{};
            for (final c in filtered.reversed) {
              final bucket = _dayBucket(DateTime.fromMillisecondsSinceEpoch((c.updatedAt * 1000).toInt()));
              groups.putIfAbsent(bucket, () => []).add(c);
            }
            return ListView(
              children: [
                for (final bucket in ['Today', 'Yesterday', 'Earlier'])
                  if (groups[bucket]?.isNotEmpty ?? false) ...[
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                      child: Text(bucket,
                          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: EvergreenColors.caption)),
                    ),
                    for (final c in groups[bucket]!)
                      _ConversationTile(
                        conversation: c,
                        active: c.id == widget.activeConversationId,
                        workspaceId: widget.workspaceId,
                        projectId: widget.projectId,
                      ),
                  ],
              ],
            );
          }),
        ),
      ],
    );
  }
}

class _ConversationTile extends ConsumerWidget {
  const _ConversationTile({
    required this.conversation,
    required this.active,
    required this.workspaceId,
    required this.projectId,
  });

  final Conversation conversation;
  final bool active;
  final String workspaceId;
  final String projectId;

  Future<void> _rename(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController(text: conversation.title);
    final newTitle = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Rename chat'),
        content: TextField(controller: controller, autofocus: true),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialogContext).pop(), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(dialogContext).pop(controller.text.trim()), child: const Text('Save')),
        ],
      ),
    );
    if (newTitle != null && newTitle.isNotEmpty) {
      await ref.read(chatControllerProvider(ChatConversationKey(projectId, conversation.id)).notifier).rename(newTitle);
      ref.invalidate(projectConversationsProvider(projectId));
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final deleted = await ref
        .read(chatControllerProvider(ChatConversationKey(projectId, conversation.id)).notifier)
        .deleteConversation();
    ref.invalidate(projectConversationsProvider(projectId));
    if (!context.mounted) return;
    if (!deleted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('A project must keep at least one chat.')),
      );
      return;
    }
    if (active) context.go('/w/$workspaceId/p/$projectId/chats/default');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isFork = conversation.title.toLowerCase().contains('forked');
    return Material(
      color: active ? EvergreenColors.primaryTint : Colors.transparent,
      child: ListTile(
        dense: true,
        title: Text(conversation.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        trailing: PopupMenuButton<String>(
          icon: const Icon(Symbols.more_horiz, size: 18),
          onSelected: (action) {
            if (action == 'rename') _rename(context, ref);
            if (action == 'delete') _delete(context, ref);
          },
          itemBuilder: (_) => const [
            PopupMenuItem(value: 'rename', child: Text('Rename')),
            PopupMenuItem(value: 'delete', child: Text('Delete')),
          ],
        ),
        leading: isFork ? const Icon(Symbols.call_split, size: 16, color: EvergreenColors.metadata) : null,
        onTap: () => context.go('/w/$workspaceId/p/$projectId/chats/${conversation.id}'),
      ),
    );
  }
}

class _Conversation extends ConsumerStatefulWidget {
  const _Conversation({
    required this.conversationKey,
    required this.projectId,
    required this.onCiteTap,
    required this.onForkFromHere,
  });

  final ChatConversationKey conversationKey;
  final String projectId;
  final void Function(List<Citation> all, Citation selected) onCiteTap;
  final VoidCallback onForkFromHere;

  @override
  ConsumerState<_Conversation> createState() => _ConversationState();
}

class _ConversationState extends ConsumerState<_Conversation> {
  final _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(chatControllerProvider(widget.conversationKey));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
    final turns = state.turns;
    if (turns.isEmpty) {
      return const EmptyState(
        message: 'No messages yet. Ask a question about this project\'s sources.',
        icon: Symbols.chat_bubble_outline,
      );
    }
    return ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.all(16),
      itemCount: turns.length,
      itemBuilder: (context, i) => _TurnCard(
        turn: turns[i],
        sessionId: widget.projectId,
        onCiteTap: widget.onCiteTap,
        onForkFromHere: widget.onForkFromHere,
      ),
    );
  }
}

class _TurnCard extends ConsumerWidget {
  const _TurnCard({required this.turn, required this.sessionId, required this.onCiteTap, required this.onForkFromHere});

  final ChatTurn turn;
  final String sessionId;
  final void Function(List<Citation> all, Citation selected) onCiteTap;
  final VoidCallback onForkFromHere;

  Future<void> _feedback(WidgetRef ref, bool helpful) async {
    await ref.read(chatActionsProvider).submitFeedback(
          sessionId: sessionId,
          query: turn.query,
          answer: turn.answer,
          citations: turn.citations.map((c) => c.toJson()).toList(),
          helpful: helpful,
        );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cleanAnswer = turn.answer
        .replaceFirst(RegExp(r'\n+---\n#+[^\n]*Verified Sources[\s\S]*$'), '')
        .trim();
    final displayAnswer = cleanAnswer.isEmpty ? (turn.streaming ? '…' : '') : cleanAnswer;

    final markdownStyle = MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
      p: const TextStyle(fontSize: 14, height: 1.55, color: EvergreenColors.ink),
      code: monoStyle(
        fontSize: 12,
        weight: FontWeight.w500,
        color: EvergreenColors.primary,
      ),
      codeblockDecoration: BoxDecoration(
        color: EvergreenColors.fill,
        border: Border.all(color: EvergreenColors.border),
        borderRadius: BorderRadius.circular(EvergreenRadii.control),
      ),
      blockquoteDecoration: BoxDecoration(
        color: EvergreenColors.primaryTint,
        border: const Border(left: BorderSide(color: EvergreenColors.primary, width: 3)),
        borderRadius: BorderRadius.circular(4),
      ),
      tableBorder: TableBorder.all(color: EvergreenColors.border, width: 1),
      tableHead: const TextStyle(fontWeight: FontWeight.w600, color: EvergreenColors.ink),
      tableBody: const TextStyle(fontSize: 13, color: EvergreenColors.inkSecondary),
    );

    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Align(
            alignment: Alignment.centerRight,
            child: Container(
              constraints: const BoxConstraints(maxWidth: 560),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: EvergreenColors.fill,
                border: Border.all(color: EvergreenColors.border),
                borderRadius: BorderRadius.circular(EvergreenRadii.control),
              ),
              child: Text(
                turn.query,
                style: const TextStyle(fontSize: 14, height: 1.4, color: EvergreenColors.ink),
              ),
            ),
          ),
          const SizedBox(height: 10),
          if (turn.error != null)
            _ErrorCard(message: turn.error!)
          else if (turn.refused && !turn.streaming)
            _RefusedCard(answer: displayAnswer.isEmpty ? turn.answer : displayAnswer)
          else
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: EvergreenColors.surface,
                border: Border.all(color: EvergreenColors.border),
                borderRadius: BorderRadius.circular(EvergreenRadii.panel),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.02),
                    blurRadius: 6,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      AnswerStateChip(state: turn.answerState),
                      if (turn.mode != null) ...[
                        const SizedBox(width: 8),
                        Text(
                          '${turn.mode} mode',
                          style: monoStyle(fontSize: 11, color: EvergreenColors.caption),
                        ),
                      ],
                      const Spacer(),
                      if (turn.streaming)
                        Row(
                          children: [
                            Text('generating…', style: monoStyle(fontSize: 11, color: EvergreenColors.primary)),
                            const SizedBox(width: 6),
                            const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2)),
                          ],
                        ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  MarkdownBody(
                    data: displayAnswer.isEmpty ? '…' : displayAnswer,
                    shrinkWrap: true,
                    selectable: true,
                    styleSheet: markdownStyle,
                  ),
                  if (turn.citations.isNotEmpty) ...[
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        const Icon(Symbols.verified, size: 14, color: EvergreenColors.primary),
                        const SizedBox(width: 6),
                        Text(
                          'Verified Sources (${turn.citations.length})',
                          style: monoStyle(fontSize: 11, weight: FontWeight.w600, color: EvergreenColors.primary),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        for (final c in turn.citations)
                          CitationChip(citation: c, onTap: () => onCiteTap(turn.citations, c)),
                      ],
                    ),
                  ],
                  if (turn.evalScores != null || (turn.latencyMs != null && !turn.streaming))
                    EvalStrip(
                      evalScores: turn.evalScores,
                      latencyMs: turn.latencyMs,
                      tokensPerSec: turn.tokensPerSec,
                    ),
                  if (!turn.streaming) ...[
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        IconButton(
                          tooltip: 'Helpful',
                          icon: const Icon(Symbols.thumb_up, size: 16),
                          onPressed: () => _feedback(ref, true),
                        ),
                        IconButton(
                          tooltip: 'Inaccurate',
                          icon: const Icon(Symbols.thumb_down, size: 16),
                          onPressed: () => _feedback(ref, false),
                        ),
                        IconButton(
                          tooltip: 'Copy answer',
                          icon: const Icon(Symbols.content_copy, size: 16),
                          onPressed: () {
                            Clipboard.setData(ClipboardData(text: displayAnswer));
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Answer copied to clipboard')),
                            );
                          },
                        ),
                        const Spacer(),
                        TextButton.icon(
                          onPressed: onForkFromHere,
                          icon: const Icon(Symbols.call_split, size: 14),
                          label: const Text('Fork from here'),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _RefusedCard extends StatelessWidget {
  const _RefusedCard({required this.answer});
  final String answer;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: EvergreenColors.refusedTint,
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Symbols.block, size: 18, color: EvergreenColors.refused),
          const SizedBox(width: 10),
          Expanded(
            child: Text(answer.isEmpty ? 'This couldn\'t be answered from the available documents.' : answer,
                style: const TextStyle(color: EvergreenColors.refused)),
          ),
        ],
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: EvergreenColors.refusedTint,
        border: Border.all(color: EvergreenColors.refused),
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
      ),
      child: Row(
        children: [
          const Icon(Symbols.error, size: 18, color: EvergreenColors.refused),
          const SizedBox(width: 10),
          Expanded(child: Text(message, style: const TextStyle(color: EvergreenColors.refused))),
        ],
      ),
    );
  }
}

class _Composer extends ConsumerWidget {
  const _Composer({
    required this.projectId,
    required this.controller,
    required this.mode,
    required this.model,
    required this.onModeChanged,
    required this.onModelChanged,
    required this.onSend,
    required this.sending,
  });

  final String projectId;
  final TextEditingController controller;
  // null = use the project's own setting (Project -> Settings); only an explicit pick overrides it.
  final String? mode;
  final String? model;
  final ValueChanged<String?> onModeChanged;
  final ValueChanged<String?> onModelChanged;
  final VoidCallback onSend;
  final bool sending;

  static const _modes = ['auto', 'agentic', 'graph', 'direct'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final health = ref.watch(liveServiceHealthProvider).valueOrNull;
    // Unknown (not checked yet / health call failed) stays enabled; only a confirmed-down Ollama blocks.
    final ollamaDown = health != null && !health.ollamaAlive;
    final project = ref.watch(projectProvider(projectId)).valueOrNull;
    final canSend = !ollamaDown && !sending;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: const BoxDecoration(
        color: EvergreenColors.surface,
        border: Border(top: BorderSide(color: EvergreenColors.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (ollamaDown) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: EvergreenColors.refusedTint,
                borderRadius: BorderRadius.circular(EvergreenRadii.control),
              ),
              child: const Row(
                children: [
                  Icon(Symbols.power_off, size: 16, color: EvergreenColors.refused),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Ollama is not running, so chat is paused. Start Ollama and this re-enables on its own.',
                      style: TextStyle(fontSize: 12, color: EvergreenColors.refused),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
          ],
          Row(
            children: [
              DropdownButton<String>(
                value: mode ?? project?.parameters.retrievalMode ?? 'auto',
                underline: const SizedBox.shrink(),
                items: [
                  for (final m in _modes) DropdownMenuItem(value: m, child: Text(_modeLabel(m))),
                ],
                onChanged: ollamaDown
                    ? null
                    : (v) => onModeChanged(v == project?.parameters.retrievalMode ? null : v),
              ),
              const SizedBox(width: 12),
              Consumer(builder: (context, ref, _) {
                final list = ref.watch(modelsProvider).valueOrNull;
                if (list == null || list.models.isEmpty) return const SizedBox.shrink();
                final names = list.models.map((m) => m.name).toList();
                final projectModel = project?.parameters.model;
                final shown = model ??
                    (names.contains(projectModel)
                        ? projectModel
                        : (names.contains(list.defaultModel) ? list.defaultModel : names.first));
                return Theme(
                  data: Theme.of(context).copyWith(
                    scrollbarTheme: const ScrollbarThemeData(
                      thumbVisibility: WidgetStatePropertyAll(true),
                    ),
                  ),
                  child: DropdownButton<String>(
                    value: shown,
                    underline: const SizedBox.shrink(),
                    menuMaxHeight: 280,
                    items: [
                      for (final m in list.models)
                        DropdownMenuItem(value: m.name, child: Text(m.name, style: monoStyle(fontSize: 13))),
                    ],
                    onChanged: ollamaDown ? null : (v) => onModelChanged(v == projectModel ? null : v),
                  ),
                );
              }),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: Focus(
                  // Enter sends; Shift+Enter falls through to the field and inserts a newline.
                  onKeyEvent: (node, event) {
                    final isEnter = event.logicalKey == LogicalKeyboardKey.enter ||
                        event.logicalKey == LogicalKeyboardKey.numpadEnter;
                    if (event is! KeyDownEvent || !isEnter || HardwareKeyboard.instance.isShiftPressed) {
                      return KeyEventResult.ignored;
                    }
                    if (canSend) onSend();
                    return KeyEventResult.handled;
                  },
                  child: TextField(
                    controller: controller,
                    enabled: !ollamaDown,
                    minLines: 1,
                    maxLines: 6,
                    keyboardType: TextInputType.multiline,
                    textInputAction: TextInputAction.newline,
                    decoration: InputDecoration(
                      hintText: ollamaDown
                          ? 'Chat is paused while Ollama is down'
                          : 'Ask a question...  (Shift+Enter for a new line)',
                      isDense: true,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filled(
                tooltip: ollamaDown ? 'Ollama is not running' : 'Send (Enter)',
                onPressed: canSend ? onSend : null,
                icon: sending
                    ? const SizedBox(
                        width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Symbols.send, size: 18),
                style: IconButton.styleFrom(backgroundColor: EvergreenColors.primary),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _modeLabel(String m) => switch (m) {
        'auto' => 'Auto',
        'agentic' => 'Agentic',
        'graph' => 'Graph',
        'direct' => 'Direct',
        _ => m,
      };
}
