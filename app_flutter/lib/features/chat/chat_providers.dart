import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../api/models/feedback.dart';
import '../../api/models/session.dart';
import '../../api/models/share.dart';
import '../workspace/workspace_providers.dart';
import 'chat_state.dart';

class ChatConversationKey {
  final String sessionId;
  final String conversationId;
  const ChatConversationKey(this.sessionId, this.conversationId);

  @override
  bool operator ==(Object other) =>
      other is ChatConversationKey && other.sessionId == sessionId && other.conversationId == conversationId;
  @override
  int get hashCode => Object.hash(sessionId, conversationId);
}

/// Streams one project's chat turns. Holds only in-memory UI state (the backend is the source
/// of truth for history — `GET /api/v1/sessions/{id}/conversations/{id}` on first load).
class ChatController extends StateNotifier<ChatConversationState> {
  ChatController(this._client, this.sessionId, this.conversationId) : super(const ChatConversationState());

  final ApiClient _client;
  final String sessionId;
  final String conversationId;

  Future<void> loadHistory() async {
    try {
      final json = await _client.get('/api/v1/sessions/$sessionId/conversations/$conversationId') as Map<String, dynamic>;
      final messages = (json['messages'] as List<dynamic>? ?? []);
      final turns = <ChatTurn>[];
      for (var i = 0; i < messages.length; i++) {
        final m = messages[i] as Map<String, dynamic>;
        if (m['role'] == 'user') {
          final reply = (i + 1 < messages.length) ? messages[i + 1] as Map<String, dynamic> : null;
          final replyMsg = reply != null && reply['role'] == 'assistant' ? ChatMessage.fromJson(reply) : null;
          turns.add(ChatTurn(
            id: (m['id'] as String?) ?? '$i',
            query: m['content'] as String? ?? '',
            answer: replyMsg?.content ?? '',
            citations: replyMsg?.citations ?? const [],
          ));
        }
      }
      state = state.copyWith(turns: turns);
    } on ApiException {
      // A brand-new conversation has no history yet.
    }
  }

  Future<void> send(String query, {String? mode, String? model}) async {
    final turnId = DateTime.now().microsecondsSinceEpoch.toString();
    var turn = ChatTurn(id: turnId, query: query, streaming: true);
    state = state.copyWith(turns: [...state.turns, turn], sending: true);

    try {
      final stream = _client.streamChat({
        'query': query,
        'session_id': sessionId,
        'conversation_id': conversationId,
        'mode': ?mode,
        'model': ?model,
        'stream': true,
      });
      await for (final event in stream) {
        turn = reduceChatEvent(turn, event);
        _replaceTurn(turn);
      }
    } on ApiException catch (e) {
      turn = turn.copyWith(error: e.detail, streaming: false);
      _replaceTurn(turn);
    } finally {
      state = state.copyWith(sending: false);
    }
  }

  void _replaceTurn(ChatTurn turn) {
    state = state.copyWith(
      turns: [for (final t in state.turns) if (t.id == turn.id) turn else t],
    );
  }

  /// Starts a new chat thread in this project (IRA-24's `.../conversations`) and returns its id.
  Future<String> newConversation() async {
    final json = await _client.post('/api/v1/sessions/$sessionId/conversations') as Map<String, dynamic>;
    return json['id'] as String;
  }

  Future<void> rename(String title) async {
    await _client.patch('/api/v1/sessions/$sessionId/conversations/$conversationId', body: {'title': title});
  }

  /// False when the backend refuses — it never deletes a project's last remaining thread.
  Future<bool> deleteConversation() async {
    final json = await _client.delete('/api/v1/sessions/$sessionId/conversations/$conversationId');
    return json is Map && json['deleted'] == true;
  }
}

final chatControllerProvider =
    StateNotifierProvider.family<ChatController, ChatConversationState, ChatConversationKey>((ref, key) {
  final controller = ChatController(ref.watch(userApiClientProvider), key.sessionId, key.conversationId);
  controller.loadHistory();
  return controller;
});

class ChatActions {
  ChatActions(this._client, [this._ref]);
  final ApiClient _client;
  final Ref? _ref;

  Future<FeedbackRecord> submitFeedback({
    required String sessionId,
    required String query,
    required String answer,
    required List<Map<String, dynamic>> citations,
    required bool helpful,
  }) async {
    final json = await _client.post('/api/v1/feedback', body: {
      'session_id': sessionId,
      'query_text': query,
      'response_text': answer,
      'citations': citations,
      'rating': helpful ? 'thumbs_up' : 'thumbs_down',
    }) as Map<String, dynamic>;
    return FeedbackRecord.fromJson(json);
  }

  /// "Fork from here": starts a new project seeded from this project's current documents/prompt,
  /// matching `services/sharing/service.py::fork`'s "continue in a project I own" semantics —
  /// there is no dedicated backend endpoint for forking mid-conversation, so this creates a new
  /// session with the same files/system_prompt and lets the caller continue there.
  Future<String> forkFromHere(ChatSession source) async {
    final json = await _client.post('/api/v1/sessions', body: {
      'title': '${source.title} (forked)',
      'files': source.files,
      'system_prompt': source.systemPrompt,
      'parameters': source.parameters.toJson(),
      'workspace_id': source.workspaceId,
    }) as Map<String, dynamic>;
    _ref?.read(projectsRefreshProvider.notifier).state++;
    return (json['id'] ?? json['session']?['id']) as String;
  }

  Future<CreateShareResponse> createShare(String sessionId) async {
    final json = await _client.post('/api/v1/sessions/$sessionId/shares') as Map<String, dynamic>;
    return CreateShareResponse.fromJson(json);
  }

  Future<List<ShareSummary>> listShares(String sessionId) async {
    final json = await _client.get('/api/v1/sessions/$sessionId/shares') as Map<String, dynamic>;
    return (json['shares'] as List<dynamic>).map((e) => ShareSummary.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> revokeShare(String shareId) async {
    await _client.delete('/api/v1/shares/$shareId');
  }
}

final chatActionsProvider = Provider<ChatActions>((ref) => ChatActions(ref.watch(userApiClientProvider), ref));

// --- Public shared view (/s/:token) — no auth required ---

final sharedChatProvider = FutureProvider.family<ShareSnapshot, String>((ref, token) async {
  final client = ref.watch(userApiClientProvider);
  final json = await client.get('/api/v1/public/shares/$token') as Map<String, dynamic>;
  return ShareSnapshot.fromJson(json);
});

final forkSharedChatProvider = Provider<Future<String> Function(String token)>((ref) {
  final client = ref.watch(userApiClientProvider);
  return (token) async {
    final json = await client.post('/api/v1/public/shares/$token/fork') as Map<String, dynamic>;
    return json['session_id'] as String;
  };
});
