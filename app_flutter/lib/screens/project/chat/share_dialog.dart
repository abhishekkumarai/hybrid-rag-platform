import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../../api/api_client.dart';
import '../../../api/models/share.dart';
import '../../../features/chat/chat_providers.dart';
import '../../../theme/evergreen_theme.dart';

Future<void> showShareDialog(BuildContext context, String sessionId) {
  return showDialog(context: context, builder: (_) => ShareDialog(sessionId: sessionId));
}

/// "Share dialog: create, copy once, list, revoke" (IRA-49).
class ShareDialog extends ConsumerStatefulWidget {
  const ShareDialog({super.key, required this.sessionId});
  final String sessionId;

  @override
  ConsumerState<ShareDialog> createState() => _ShareDialogState();
}

class _ShareDialogState extends ConsumerState<ShareDialog> {
  List<ShareSummary>? _shares;
  String? _justCreatedUrl;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
      final shares = await ref.read(chatActionsProvider).listShares(widget.sessionId);
      setState(() {
        _shares = shares;
        _loading = false;
      });
    } on ApiException catch (e) {
      setState(() {
        _error = e.detail;
        _loading = false;
      });
    }
  }

  Future<void> _create() async {
    final result = await ref.read(chatActionsProvider).createShare(widget.sessionId);
    setState(() => _justCreatedUrl = result.url);
    await Clipboard.setData(ClipboardData(text: result.url));
    await _refresh();
  }

  Future<void> _revoke(String shareId) async {
    await ref.read(chatActionsProvider).revokeShare(shareId);
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Share this chat'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            FilledButton.icon(
              onPressed: _create,
              icon: const Icon(Symbols.link, size: 16),
              label: const Text('Create share link'),
            ),
            if (_justCreatedUrl != null) ...[
              const SizedBox(height: 12),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: EvergreenColors.confidentTint,
                  borderRadius: BorderRadius.circular(EvergreenRadii.control),
                ),
                child: Row(
                  children: [
                    Expanded(child: Text(_justCreatedUrl!, style: monoStyle(fontSize: 11))),
                    const Icon(Symbols.check_circle, size: 16, color: EvergreenColors.confident),
                  ],
                ),
              ),
              const Text('Copied to clipboard — this URL is shown only once.',
                  style: TextStyle(fontSize: 11, color: EvergreenColors.metadata)),
            ],
            const SizedBox(height: 16),
            const Text('Existing shares', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
            const SizedBox(height: 8),
            if (_loading) const Center(child: Padding(padding: EdgeInsets.all(12), child: CircularProgressIndicator())),
            if (_error != null) Text(_error!, style: const TextStyle(color: EvergreenColors.refused)),
            if (_shares != null && _shares!.isEmpty) const Text('No shares yet.', style: TextStyle(color: EvergreenColors.metadata)),
            if (_shares != null)
              ...(_shares!.map((s) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    title: Text(s.id, style: monoStyle(fontSize: 12)),
                    subtitle: Text('${s.messageCount} messages${s.revoked ? ' · revoked' : ''}',
                        style: const TextStyle(fontSize: 11, color: EvergreenColors.metadata)),
                    trailing: s.revoked
                        ? null
                        : TextButton(onPressed: () => _revoke(s.id), child: const Text('Revoke')),
                  ))),
          ],
        ),
      ),
      actions: [TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Close'))],
    );
  }
}
