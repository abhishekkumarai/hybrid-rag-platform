import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../api/auth_provider.dart';
import '../../../api/models/retrieval.dart';
import '../../../theme/evergreen_theme.dart';

final _previewBytesProvider = FutureProvider.family<Uint8List, Citation>((ref, citation) async {
  final client = ref.watch(userApiClientProvider);
  if (citation.isFigure && citation.imagePath != null) {
    final name = citation.imagePath!.split('/').last;
    return client.getBytes('/api/v1/figures/$name');
  }
  return client.getBytes('/api/v1/preview', query: {
    'doc_id': citation.docId,
    'page': citation.page,
    'bbox': citation.bbox.join(','),
  });
});

/// DESIGN-evergreen.md inspector: for documents, the page preview with the citation's bbox highlighted
/// (or the figure); for web pages (IRA-57), the page address and a link to open it. Prev/next walks
/// the turn's citations.
class CitationInspectorPanel extends ConsumerWidget {
  const CitationInspectorPanel({
    super.key,
    required this.citations,
    required this.selected,
    required this.onSelect,
    this.onClose,
  });

  final List<Citation> citations;
  final Citation selected;
  final ValueChanged<Citation> onSelect;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final index = citations.indexOf(selected);
    final webUrl = selected.webUrl;

    return Container(
      color: EvergreenColors.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 8, 8),
            child: Row(
              children: [
                Expanded(
                  child: Text('Citation ${index + 1} of ${citations.length}',
                      style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                ),
                IconButton(
                  tooltip: 'Previous',
                  icon: const Icon(Symbols.chevron_left, size: 20),
                  onPressed: index > 0 ? () => onSelect(citations[index - 1]) : null,
                ),
                IconButton(
                  tooltip: 'Next',
                  icon: const Icon(Symbols.chevron_right, size: 20),
                  onPressed: index < citations.length - 1 ? () => onSelect(citations[index + 1]) : null,
                ),
                if (onClose != null) IconButton(icon: const Icon(Symbols.close, size: 20), onPressed: onClose),
              ],
            ),
          ),
          if (webUrl == null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                selected.formattedBadge.isNotEmpty ? selected.formattedBadge : '${selected.docId} · p. ${selected.page}',
                style: monoStyle(fontSize: 12, color: EvergreenColors.metadata),
              ),
            ),
          const SizedBox(height: 12),
          Expanded(
            child: webUrl != null
                ? _WebSource(url: webUrl)
                : ref.watch(_previewBytesProvider(selected)).when(
                      data: (bytes) => InteractiveViewer(
                        minScale: 0.5,
                        maxScale: 4,
                        child: Image.memory(bytes, fit: BoxFit.contain, width: double.infinity),
                      ),
                      loading: () => const Center(child: CircularProgressIndicator()),
                      error: (e, _) => const Center(
                        child: Padding(
                          padding: EdgeInsets.all(24),
                          child: Text(
                            'The page preview is not available for this source.',
                            textAlign: TextAlign.center,
                            style: TextStyle(fontSize: 13, color: EvergreenColors.metadata),
                          ),
                        ),
                      ),
                    ),
          ),
          if (selected.snippet.isNotEmpty)
            Container(
              width: double.infinity,
              margin: const EdgeInsets.fromLTRB(16, 8, 16, 16),
              clipBehavior: Clip.antiAlias,
              // A rounded border must be uniform, so the accent is its own strip, not a thicker left side.
              decoration: BoxDecoration(
                color: EvergreenColors.canvas,
                border: Border.all(color: EvergreenColors.border),
                borderRadius: BorderRadius.circular(EvergreenRadii.control),
              ),
              child: IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Container(width: 3, color: EvergreenColors.primary),
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'CITED PASSAGE',
                              style: monoStyle(fontSize: 10, weight: FontWeight.w600, color: EvergreenColors.metadata),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              '"${selected.snippet}"',
                              style: const TextStyle(
                                  fontSize: 12, fontStyle: FontStyle.italic, color: EvergreenColors.ink, height: 1.4),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// A web page has no PDF page to render; show where it came from and let the user open it.
class _WebSource extends StatelessWidget {
  const _WebSource({required this.url});
  final String url;

  @override
  Widget build(BuildContext context) {
    final uri = Uri.tryParse(url);
    final section = uri?.fragment ?? '';
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Symbols.public, size: 18, color: EvergreenColors.primary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  uri?.host ?? url,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: EvergreenColors.ink),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          SelectableText(url, style: monoStyle(fontSize: 11, color: EvergreenColors.metadata)),
          if (section.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text('Section: #$section', style: const TextStyle(fontSize: 12, color: EvergreenColors.inkSecondary)),
          ],
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: uri == null ? null : () => launchUrl(uri, mode: LaunchMode.externalApplication, webOnlyWindowName: '_blank'),
            icon: const Icon(Symbols.open_in_new, size: 16),
            label: const Text('Open page'),
          ),
        ],
      ),
    );
  }
}
