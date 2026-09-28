import 'package:flutter/material.dart';

import '../theme/evergreen_theme.dart';

class SectionHeader extends StatelessWidget {
  const SectionHeader({super.key, required this.title, this.action});

  final String title;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: EvergreenColors.ink)),
          ?action,
        ],
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.message, this.icon});

  final String message;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24),
      child: Center(
        child: Column(
          children: [
            if (icon case final ic?) ...[
              Icon(ic, color: EvergreenColors.caption, size: 28),
              const SizedBox(height: 8),
            ],
            Text(message, style: const TextStyle(fontSize: 13, color: EvergreenColors.caption)),
          ],
        ),
      ),
    );
  }
}
