import 'package:flutter/material.dart';

/// Stub content for routes not yet built out (IRA-48/49/50 fill these in) — IRA-47 only needs
/// the shell chrome and routing to work.
class PlaceholderScreen extends StatelessWidget {
  const PlaceholderScreen({super.key, required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Text(title, style: Theme.of(context).textTheme.titleMedium),
    );
  }
}
