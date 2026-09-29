import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../features/admin/admin_providers.dart';
import '../../features/project/project_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';

/// DESIGN-evergreen.md Models & tuning page: models, HNSW status and rebuild.
class ModelsTuningScreen extends ConsumerStatefulWidget {
  const ModelsTuningScreen({super.key, required this.workspaceId});
  final String workspaceId;

  @override
  ConsumerState<ModelsTuningScreen> createState() => _ModelsTuningScreenState();
}

class _ModelsTuningScreenState extends ConsumerState<ModelsTuningScreen> {
  int _hnswM = 16;
  int _hnswEfConstruct = 128;
  bool _rebuilding = false;
  bool _seeded = false;

  @override
  Widget build(BuildContext context) {
    final modelsAsync = ref.watch(modelsProvider);
    final gpuAsync = ref.watch(gpuStatusProvider);
    final hnswAsync = ref.watch(hnswStatusProvider);
    final auth = ref.watch(authProvider);
    final isAdmin = auth is AuthSignedIn && auth.user.isAdmin;

    hnswAsync.whenData((status) {
      if (!_seeded) {
        _seeded = true;
        _hnswM = status.hnswM;
        _hnswEfConstruct = status.hnswEfConstruct;
      }
    });

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Models & tuning',
                style: Theme.of(context).textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 20),
              const SectionHeader(title: 'Chat models'),
              modelsAsync.when(
                data: (list) => list.models.isEmpty
                    ? EmptyState(
                        message: list.ollamaAlive
                            ? 'No chat models installed in Ollama. Pull one, e.g. `ollama pull llama3.2:3b`.'
                            : 'Ollama is unreachable, so no models can be listed.',
                        icon: Symbols.smart_toy,
                      )
                    : Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(
                            EvergreenRadii.panel,
                          ),
                          border: Border.all(color: EvergreenColors.border),
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: Material(
                          color: EvergreenColors.surface,
                          child: Column(
                            children: [
                              for (final m in list.models)
                                ListTile(
                                  leading: Icon(
                                    Symbols.smart_toy,
                                    color: m.isDefault
                                        ? EvergreenColors.primary
                                        : EvergreenColors.metadata,
                                    size: 18,
                                  ),
                                  title: Text(
                                    m.name,
                                    style: monoStyle(fontSize: 13),
                                  ),
                                  trailing: m.isDefault
                                      ? const Text(
                                          'default',
                                          style: TextStyle(
                                            fontSize: 11,
                                            color: EvergreenColors.primary,
                                          ),
                                        )
                                      : null,
                                ),
                            ],
                          ),
                        ),
                      ),
                loading: () => const LinearProgressIndicator(),
                error: (e, _) => const Text(
                  'Ollama unreachable.',
                  style: TextStyle(color: EvergreenColors.refused),
                ),
              ),
              const SizedBox(height: 12),
              gpuAsync.when(
                data: (gpu) {
                  final used = (gpu['used_vram_mb'] as num?)?.toDouble() ?? 0;
                  final total =
                      (gpu['total_vram_mb'] as num?)?.toDouble() ?? 6144;
                  final ratio = total > 0
                      ? (used / total).clamp(0, 1).toDouble()
                      : 0.0;
                  final rawName = gpu['gpu_name'] as String?;
                  final gpuName =
                      (rawName == null ||
                          rawName.toLowerCase().startsWith('unknown'))
                      ? null
                      : rawName;
                  final loaded = [
                    for (final m
                        in (gpu['models'] as List<dynamic>? ?? const []))
                      if (m is Map && m['name'] != null)
                        '${m['name']}${m['size_vram_gb'] != null ? ' (${m['size_vram_gb']} GB)' : ''}',
                  ];
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(
                          EvergreenRadii.chip,
                        ),
                        child: LinearProgressIndicator(
                          value: ratio,
                          minHeight: 8,
                          backgroundColor: EvergreenColors.fill,
                          color: ratio > 0.85
                              ? EvergreenColors.refused
                              : EvergreenColors.primary,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${used.toStringAsFixed(0)} / ${total.toStringAsFixed(0)} MB VRAM'
                        '${gpuName != null ? ' ($gpuName)' : ''}',
                        style: const TextStyle(
                          fontSize: 12,
                          color: EvergreenColors.metadata,
                        ),
                      ),
                      if (loaded.isNotEmpty) ...[
                        const SizedBox(height: 2),
                        Text(
                          'Loaded now: ${loaded.join(', ')}',
                          style: monoStyle(
                            fontSize: 11,
                            color: EvergreenColors.metadata,
                          ),
                        ),
                      ],
                    ],
                  );
                },
                loading: () => const SizedBox.shrink(),
                error: (e, _) => const SizedBox.shrink(),
              ),
              const SizedBox(height: 28),
              SectionHeader(
                title: 'Qdrant HNSW index',
                action: IconButton(
                  tooltip: 'Refresh status',
                  icon: const Icon(
                    Symbols.refresh,
                    size: 18,
                    color: EvergreenColors.metadata,
                  ),
                  onPressed: () => ref.invalidate(hnswStatusProvider),
                ),
              ),
              hnswAsync.when(
                data: (status) => Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      spacing: 24,
                      runSpacing: 8,
                      children: [
                        Text(
                          'Collection: ${status.collectionName}',
                          style: monoStyle(fontSize: 12),
                        ),
                        Text(
                          'Status: ${status.status}',
                          style: monoStyle(fontSize: 12),
                        ),
                        Text(
                          'Points: ${status.pointsCount ?? '—'}',
                          style: monoStyle(fontSize: 12),
                        ),
                        Text(
                          'Indexed vectors: ${status.indexedVectorsCount ?? '—'}',
                          style: monoStyle(fontSize: 12),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    if (isAdmin) ...[
                      Text(
                        'm: $_hnswM',
                        style: const TextStyle(
                          fontSize: 13,
                          color: EvergreenColors.inkSecondary,
                        ),
                      ),
                      Slider(
                        value: _hnswM.toDouble(),
                        min: 4,
                        max: 64,
                        divisions: 60,
                        activeColor: EvergreenColors.primary,
                        onChanged: (v) => setState(() => _hnswM = v.round()),
                      ),
                      Text(
                        'ef_construct: $_hnswEfConstruct',
                        style: const TextStyle(
                          fontSize: 13,
                          color: EvergreenColors.inkSecondary,
                        ),
                      ),
                      Slider(
                        value: _hnswEfConstruct.toDouble(),
                        min: 16,
                        max: 512,
                        divisions: 31,
                        activeColor: EvergreenColors.primary,
                        onChanged: (v) =>
                            setState(() => _hnswEfConstruct = v.round()),
                      ),
                      const SizedBox(height: 8),
                      OutlinedButton.icon(
                        onPressed: _rebuilding ? null : _rebuild,
                        icon: _rebuilding
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Symbols.build, size: 18),
                        label: const Text('Rebuild index'),
                      ),
                    ] else
                      const Text(
                        'Admin access required to rebuild the index.',
                        style: TextStyle(color: EvergreenColors.caption),
                      ),
                  ],
                ),
                loading: () => const LinearProgressIndicator(),
                error: (e, _) => const Text(
                  'Could not load HNSW status.',
                  style: TextStyle(color: EvergreenColors.caption),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _rebuild() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Rebuild the vector index?'),
        content: Text(
          'Applies m=$_hnswM, ef_construct=$_hnswEfConstruct to the shared collection and re-indexes '
          'every document for all users. Search quality may dip until it finishes.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Rebuild'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _rebuilding = true);
    try {
      await ref
          .read(adminActionsProvider)
          .rebuildHnsw(hnswM: _hnswM, hnswEfConstruct: _hnswEfConstruct);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Rebuild started. Refresh the status to follow progress.',
            ),
          ),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Rebuild failed: ${e.detail}')));
      }
    } finally {
      if (mounted) setState(() => _rebuilding = false);
    }
  }
}
