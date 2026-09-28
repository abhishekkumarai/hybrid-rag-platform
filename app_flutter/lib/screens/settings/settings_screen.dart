import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/auth_provider.dart';
import '../../features/admin/admin_providers.dart';
import '../../theme/appearance_provider.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';

/// DESIGN-evergreen.md Settings page: appearance (density, reduced motion, high contrast),
/// API & security, danger zone (purge DLQ, reset) for admins. Mobile/desktop (IRA-51) also gets
/// a Server URL section — web always talks to its own origin and never shows it.
class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late final TextEditingController _serverUrlController;

  @override
  void initState() {
    super.initState();
    _serverUrlController = TextEditingController(text: ref.read(serverUrlProvider));
  }

  @override
  void dispose() {
    _serverUrlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final appearance = ref.watch(appearanceProvider);
    final auth = ref.watch(authProvider);
    final isAdmin = auth is AuthSignedIn && auth.user.isAdmin;

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      appBar: AppBar(
        backgroundColor: EvergreenColors.canvas,
        elevation: 0,
        title: const Text('Settings'),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SectionHeader(title: 'Appearance'),
              Container(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(EvergreenRadii.panel),
                  border: Border.all(color: EvergreenColors.border),
                ),
                clipBehavior: Clip.antiAlias,
                child: Material(
                  color: EvergreenColors.surface,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Density',
                          style: TextStyle(fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 8),
                        SegmentedButton<AppDensity>(
                          segments: const [
                            ButtonSegment(
                              value: AppDensity.compact,
                              label: Text('Compact'),
                            ),
                            ButtonSegment(
                              value: AppDensity.comfortable,
                              label: Text('Comfortable'),
                            ),
                            ButtonSegment(
                              value: AppDensity.spacious,
                              label: Text('Spacious'),
                            ),
                          ],
                          selected: {appearance.density},
                          onSelectionChanged: (s) => ref
                              .read(appearanceProvider.notifier)
                              .setDensity(s.first),
                        ),
                        const Divider(
                          height: 32,
                          color: EvergreenColors.border,
                        ),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Reduced motion'),
                          subtitle: const Text(
                            'Use simple fades instead of page transitions.',
                          ),
                          value: appearance.reducedMotion,
                          activeThumbColor: EvergreenColors.primary,
                          onChanged: (v) => ref
                              .read(appearanceProvider.notifier)
                              .setReducedMotion(v),
                        ),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('High contrast'),
                          subtitle: const Text(
                            'Darker borders across cards and inputs.',
                          ),
                          value: appearance.highContrast,
                          activeThumbColor: EvergreenColors.primary,
                          onChanged: (v) => ref
                              .read(appearanceProvider.notifier)
                              .setHighContrast(v),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              if (!kIsWeb) ...[
                const SizedBox(height: 28),
                const SectionHeader(title: 'Server'),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: EvergreenColors.surface,
                    borderRadius: BorderRadius.circular(EvergreenRadii.panel),
                    border: Border.all(color: EvergreenColors.border),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Gateway URL — use http://10.0.2.2:8000 on the Android emulator to reach the host machine.',
                        style: TextStyle(fontSize: 12, color: EvergreenColors.metadata),
                      ),
                      const SizedBox(height: 10),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _serverUrlController,
                              decoration: const InputDecoration(hintText: 'http://10.0.2.2:8000'),
                              keyboardType: TextInputType.url,
                            ),
                          ),
                          const SizedBox(width: 12),
                          FilledButton(onPressed: _saveServerUrl, child: const Text('Save')),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 28),
              const SectionHeader(title: 'API & security'),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: EvergreenColors.surface,
                  borderRadius: BorderRadius.circular(EvergreenRadii.panel),
                  border: Border.all(color: EvergreenColors.border),
                ),
                child: const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Sign-in uses a random token in an HttpOnly cookie; state-changing requests also send '
                      'X-RI-Client: web. There are no user-visible API keys to manage.',
                      style: TextStyle(
                        fontSize: 13,
                        color: EvergreenColors.metadata,
                      ),
                    ),
                  ],
                ),
              ),
              if (isAdmin) ...[
                const SizedBox(height: 28),
                const SectionHeader(title: 'Danger zone'),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: EvergreenColors.refusedTint,
                    borderRadius: BorderRadius.circular(EvergreenRadii.panel),
                    border: Border.all(color: EvergreenColors.refused),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'These actions affect every workspace.',
                        style: TextStyle(color: EvergreenColors.refused),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: () => _confirmAndPurgeDlq(context, ref),
                        icon: const Icon(
                          Symbols.delete_sweep,
                          size: 18,
                          color: EvergreenColors.refused,
                        ),
                        label: const Text(
                          'Purge dead-letter queue',
                          style: TextStyle(color: EvergreenColors.refused),
                        ),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(
                            color: EvergreenColors.refused,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _saveServerUrl() async {
    final url = _serverUrlController.text.trim();
    if (url.isEmpty) return;
    ref.read(serverUrlProvider.notifier).state = url;
    await ref.read(authStorageProvider).saveServerUrl(url);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Server URL saved.')));
    }
  }

  Future<void> _confirmAndPurgeDlq(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Purge the dead-letter queue?'),
        content: const Text(
          'All failed tasks across every workspace will be replayed back to pending. This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: EvergreenColors.refused,
            ),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Purge'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await ref.read(adminActionsProvider).replayDlq();
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Dead-letter queue replayed.')),
      );
    }
  }
}
