import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../api/models/retrieval.dart';
import '../theme/evergreen_theme.dart';

/// DESIGN-evergreen.md "Citation chip": mono 11/500, on `#E9F2EE`, border `#D1E3DA`, text
/// `#1F6B52`, 4px. Filled `#1F6B52`/white when [active]. Hover swaps the border for a 30%
/// `#1F6B52` ring and adds the spec's `0 1px 3px rgba(28,25,23,.05)` shadow.
class CitationChip extends StatefulWidget {
  const CitationChip({super.key, required this.citation, this.active = false, this.onTap});

  final Citation citation;
  final bool active;
  final VoidCallback? onTap;

  @override
  State<CitationChip> createState() => _CitationChipState();
}

class _CitationChipState extends State<CitationChip> {
  bool _hovering = false;

  IconData get _icon {
    final citation = widget.citation;
    if (citation.isWeb) return Symbols.public;
    if (citation.isFigure) return Symbols.image;
    if (citation.isTable) return Symbols.table;
    return Symbols.description;
  }

  String get _label => widget.citation.formattedBadge.isNotEmpty
      ? widget.citation.formattedBadge
      : '${widget.citation.docId} · p. ${widget.citation.page}';

  @override
  Widget build(BuildContext context) {
    final active = widget.active;
    return MouseRegion(
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: InkWell(
        onTap: widget.onTap,
        borderRadius: BorderRadius.circular(EvergreenRadii.chip),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: active ? EvergreenColors.primary : EvergreenColors.primaryTint,
            border: Border.all(
              color: active
                  ? EvergreenColors.primary
                  : (_hovering ? EvergreenColors.primary.withValues(alpha: 0.3) : EvergreenColors.primaryTintBorder),
            ),
            borderRadius: BorderRadius.circular(EvergreenRadii.chip),
            boxShadow: !active && _hovering
                ? [BoxShadow(color: EvergreenColors.ink.withValues(alpha: 0.05), blurRadius: 3, offset: const Offset(0, 1))]
                : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(_icon, size: 12, color: active ? Colors.white : EvergreenColors.primary),
              const SizedBox(width: 4),
              Text(
                _label,
                style: monoStyle(fontSize: 11, color: active ? Colors.white : EvergreenColors.primary),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
