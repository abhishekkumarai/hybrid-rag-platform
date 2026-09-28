import 'package:flutter/material.dart';

import '../features/chat/chat_state.dart';
import '../theme/evergreen_theme.dart';

/// DESIGN-evergreen.md "Answer-state chip": dot + label on its tint.
class AnswerStateChip extends StatelessWidget {
  const AnswerStateChip({super.key, required this.state});

  final AnswerState state;

  (Color, Color, String) _spec(BuildContext context) {
    final ext = context.evergreen;
    return switch (state) {
      AnswerState.confident => (ext.confident, ext.confidentTint, 'Confident'),
      AnswerState.ambiguous => (ext.ambiguous, ext.ambiguousTint, 'Ambiguous'),
      AnswerState.refused => (ext.refused, ext.refusedTint, 'Refused'),
    };
  }

  @override
  Widget build(BuildContext context) {
    final (color, tint, label) = _spec(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: tint, borderRadius: BorderRadius.circular(EvergreenRadii.chip)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(width: 6, height: 6, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
        ],
      ),
    );
  }
}
