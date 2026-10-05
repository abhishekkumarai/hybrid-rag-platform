import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'api/auth_provider.dart';
import 'router/app_router.dart';
import 'theme/appearance_provider.dart';
import 'theme/evergreen_theme.dart';

void main() {
  runApp(const ProviderScope(child: EvergreenApp()));
}

class EvergreenApp extends ConsumerStatefulWidget {
  const EvergreenApp({super.key});

  @override
  ConsumerState<EvergreenApp> createState() => _EvergreenAppState();
}

class _EvergreenAppState extends ConsumerState<EvergreenApp> {
  GoRouter? _router;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Web always talks to its own origin — the stored server-URL setting is mobile/desktop only.
      if (!kIsWeb) {
        final saved = await ref.read(authStorageProvider).readServerUrl();
        if (saved != null && saved.isNotEmpty) {
          ref.read(serverUrlProvider.notifier).state = saved;
        }
      }
      ref.read(authProvider.notifier).checkSession();
    });
  }

  @override
  Widget build(BuildContext context) {
    final appearance = ref.watch(appearanceProvider);
    _router ??= buildRouter(ref);

    return MaterialApp.router(
      title: 'IRA - Intelligent RAG Assistant',
      debugShowCheckedModeBanner: false,
      theme: buildEvergreenTheme(appearance: appearance),
      routerConfig: _router!,
    );
  }
}
