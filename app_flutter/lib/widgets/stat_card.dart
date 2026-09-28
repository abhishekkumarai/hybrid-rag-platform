import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/evergreen_theme.dart';

/// DESIGN-evergreen.md "Stat card": 40px tinted icon square, 24px number, caption, tinted delta pill.
class StatCard extends StatelessWidget {
  const StatCard({
    super.key,
    required this.label,
    required this.value,
    this.icon = Symbols.analytics,
    this.tint = EvergreenColors.primaryTint,
    this.tintIcon = EvergreenColors.primary,
    this.delta,
    this.deltaGood = true,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color tint;
  final Color tintIcon;
  final String? delta;
  final bool deltaGood;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: tint, borderRadius: BorderRadius.circular(EvergreenRadii.control)),
                child: Icon(icon, color: tintIcon, size: 20),
              ),
              if (delta != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: deltaGood ? EvergreenColors.confidentTint : EvergreenColors.refusedTint,
                    borderRadius: BorderRadius.circular(EvergreenRadii.chip),
                  ),
                  child: Text(
                    delta!,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: deltaGood ? EvergreenColors.confident : EvergreenColors.refused,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Text(value, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w600, color: EvergreenColors.ink)),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(fontSize: 13, color: EvergreenColors.caption)),
        ],
      ),
    );
  }
}
