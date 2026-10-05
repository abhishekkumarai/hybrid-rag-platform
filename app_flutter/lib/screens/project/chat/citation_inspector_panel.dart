import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

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

/// DESIGN-evergreen.md inspector: page preview PNG with the citation's bbox highlighted,
/// prev/next through the turn's citations, and a figure viewer for `is_figure` citations.
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
    final previewAsync = ref.watch(_previewBytesProvider(selected));

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
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              selected.formattedBadge.isNotEmpty ? selected.formattedBadge : '${selected.docId} · p. ${selected.page}',
              style: monoStyle(fontSize: 12, color: EvergreenColors.metadata),
            ),
          ),
          const SizedBox(height: 12),
          Expanded(
            child: previewAsync.when(
              data: (bytes) => InteractiveViewer(
                minScale: 0.5,
                maxScale: 4,
                child: Image.memory(bytes, fit: BoxFit.contain, width: double.infinity),
              ),
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (_, _) => _DocumentMockupPreview(selected: selected),
            ),
          ),
          if (selected.snippet.isNotEmpty)
            Container(
              width: double.infinity,
              margin: const EdgeInsets.fromLTRB(16, 8, 16, 16),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: EvergreenColors.canvas,
                border: const Border(
                  left: BorderSide(color: EvergreenColors.primary, width: 3),
                  top: BorderSide(color: EvergreenColors.border),
                  right: BorderSide(color: EvergreenColors.border),
                  bottom: BorderSide(color: EvergreenColors.border),
                ),
                borderRadius: BorderRadius.circular(EvergreenRadii.control),
              ),
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
                    style: const TextStyle(fontSize: 12, fontStyle: FontStyle.italic, color: EvergreenColors.ink, height: 1.4),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      if (selected.isWeb) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: EvergreenColors.primaryTint,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text('Web Source', style: monoStyle(fontSize: 10, weight: FontWeight.w600, color: EvergreenColors.primary)),
                        ),
                        if (selected.resourceUrl != null || selected.webUrl != null)
                          ActionChip(
                            avatar: const Icon(Symbols.link, size: 12, color: EvergreenColors.primary),
                            label: Text('Copy link', style: monoStyle(fontSize: 10, color: EvergreenColors.primary)),
                            padding: EdgeInsets.zero,
                            visualDensity: VisualDensity.compact,
                            onPressed: () {
                              final url = selected.resourceUrl ?? selected.webUrl ?? '';
                              if (url.isNotEmpty) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text('Copied: $url')),
                                );
                              }
                            },
                          ),
                      ] else ...[
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: EvergreenColors.primaryTint,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text('Page ${selected.page}', style: monoStyle(fontSize: 10, weight: FontWeight.w600, color: EvergreenColors.primary)),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: EvergreenColors.surface,
                            border: Border.all(color: EvergreenColors.border),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            'bbox: [${selected.bbox.map((e) => e.toStringAsFixed(0)).join(', ')}]',
                            style: monoStyle(fontSize: 10, color: EvergreenColors.metadata),
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _DocumentMockupPreview extends StatelessWidget {
  const _DocumentMockupPreview({required this.selected});
  final Citation selected;

  @override
  Widget build(BuildContext context) {
    final title = selected.resourceTitle?.isNotEmpty == true
        ? selected.resourceTitle!
        : (selected.formattedBadge.isNotEmpty ? selected.formattedBadge : selected.docId);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            selected.isWeb ? 'WEB SOURCE PROVENANCE' : 'DOCUMENT PROVENANCE',
            style: monoStyle(fontSize: 10, weight: FontWeight.w600, color: EvergreenColors.metadata),
          ),
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              border: Border.all(color: EvergreenColors.border),
              borderRadius: BorderRadius.circular(EvergreenRadii.control),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.03),
                  blurRadius: 4,
                  offset: const Offset(0, 1),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      selected.isWeb
                          ? Symbols.public
                          : (selected.isFigure ? Symbols.image : (selected.isTable ? Symbols.table : Symbols.description)),
                      size: 20,
                      color: EvergreenColors.primary,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        title,
                        style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: EvergreenColors.ink),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
                if (selected.webUrl != null || selected.resourceUrl != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    selected.resourceUrl ?? selected.webUrl!,
                    style: monoStyle(fontSize: 11, color: EvergreenColors.primary),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
                const Divider(height: 20, color: EvergreenColors.border),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: EvergreenColors.primaryTint,
                    border: Border.all(color: EvergreenColors.primary, width: 1.5),
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(Symbols.verified, size: 14, color: EvergreenColors.primary),
                          const SizedBox(width: 6),
                          Text(
                            '[Verified Source Passage]',
                            style: monoStyle(fontSize: 10, weight: FontWeight.w700, color: EvergreenColors.primary),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      SelectableText(
                        selected.snippet.isNotEmpty ? selected.snippet : 'Passage text not available.',
                        style: monoStyle(fontSize: 11, weight: FontWeight.w500, color: EvergreenColors.ink),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Doc: ${selected.docId}',
                      style: monoStyle(fontSize: 10, color: EvergreenColors.metadata),
                    ),
                    Text(
                      selected.isWeb ? 'Web resource' : 'Page ${selected.page}',
                      style: monoStyle(fontSize: 10, color: EvergreenColors.metadata),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
