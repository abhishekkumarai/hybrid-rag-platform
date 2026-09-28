import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/models/session.dart';
import '../../features/project/project_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';
import 'project_tab_shell.dart';

const _retrievalModes = ['auto', 'agentic', 'graph', 'direct'];
const _parserRoutes = {'auto': 'Auto-detect', 'fast_text': 'Fast text', 'layout': 'Layout', 'ocr': 'OCR'};

/// DESIGN-evergreen.md project Settings tab: name, model (chat-capable only, VRAM bar), mode,
/// parser route, system prompt + reset, sliders, stream, delete.
class ProjectSettingsScreen extends ConsumerStatefulWidget {
  const ProjectSettingsScreen({super.key, required this.workspaceId, required this.projectId});
  final String workspaceId;
  final String projectId;

  @override
  ConsumerState<ProjectSettingsScreen> createState() => _ProjectSettingsScreenState();
}

class _ProjectSettingsScreenState extends ConsumerState<ProjectSettingsScreen> {
  ChatSession? _draft;
  late TextEditingController _titleController;
  late TextEditingController _promptController;

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController();
    _promptController = TextEditingController();
  }

  @override
  void dispose() {
    _titleController.dispose();
    _promptController.dispose();
    super.dispose();
  }

  void _hydrate(ChatSession project) {
    if (_draft != null) return;
    _draft = project;
    _titleController.text = project.title;
    _promptController.text = project.systemPrompt ?? '';
  }

  @override
  Widget build(BuildContext context) {
    final projectAsync = ref.watch(projectProvider(widget.projectId));
    final modelsAsync = ref.watch(modelsProvider);
    final gpuAsync = ref.watch(gpuStatusProvider);

    return ProjectTabShell(
      workspaceId: widget.workspaceId,
      projectId: widget.projectId,
      activeTab: ProjectTab.settings,
      child: projectAsync.when(
        data: (project) {
          _hydrate(project);
          final draft = _draft!;
          return SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionHeader(title: 'General'),
                TextField(
                  controller: _titleController,
                  decoration: const InputDecoration(labelText: 'Project name'),
                  onSubmitted: (v) => ref.read(projectActionsProvider).updateSettings(widget.projectId, {'title': v}),
                ),
                const SizedBox(height: 24),
                const SectionHeader(title: 'Model'),
                modelsAsync.when(
                  data: (list) => DropdownButtonFormField<String>(
                    initialValue: list.models.any((m) => m.name == draft.parameters.model)
                        ? draft.parameters.model
                        : list.defaultModel,
                    decoration: const InputDecoration(labelText: 'Chat model'),
                    items: [for (final m in list.models) DropdownMenuItem(value: m.name, child: Text(m.name))],
                    onChanged: (v) => _patchParams({'model': v}),
                  ),
                  loading: () => const LinearProgressIndicator(),
                  error: (e, _) => const Text('Could not load models.', style: TextStyle(color: EvergreenColors.caption)),
                ),
                const SizedBox(height: 12),
                gpuAsync.when(
                  data: (gpu) {
                    final used = (gpu['used_vram_mb'] as num?)?.toDouble() ?? 0;
                    final total = (gpu['total_vram_mb'] as num?)?.toDouble() ?? 6144;
                    final ratio = total > 0 ? (used / total).clamp(0, 1).toDouble() : 0.0;
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(EvergreenRadii.chip),
                          child: LinearProgressIndicator(
                            value: ratio,
                            minHeight: 8,
                            backgroundColor: EvergreenColors.fill,
                            color: ratio > 0.85 ? EvergreenColors.refused : EvergreenColors.primary,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text('${used.toStringAsFixed(0)} / ${total.toStringAsFixed(0)} MB VRAM',
                            style: const TextStyle(fontSize: 12, color: EvergreenColors.metadata)),
                      ],
                    );
                  },
                  loading: () => const SizedBox.shrink(),
                  error: (e, _) => const SizedBox.shrink(),
                ),
                const SizedBox(height: 24),
                const SectionHeader(title: 'Retrieval'),
                DropdownButtonFormField<String>(
                  initialValue: draft.parameters.retrievalMode,
                  decoration: const InputDecoration(labelText: 'Mode'),
                  items: [for (final m in _retrievalModes) DropdownMenuItem(value: m, child: Text(m))],
                  onChanged: (v) => _patchParams({'retrieval_mode': v}),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: _parserRoutes.containsKey(draft.parameters.embeddingRoute) ? draft.parameters.embeddingRoute : 'auto',
                  decoration: const InputDecoration(labelText: 'Parser route'),
                  items: [for (final e in _parserRoutes.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
                  onChanged: (v) => _patchParams({'embedding_route': v}),
                ),
                const SizedBox(height: 12),
                _Slider(
                  label: 'Temperature',
                  value: draft.parameters.temperature,
                  min: 0,
                  max: 1.5,
                  onChanged: (v) => _patchParams({'temperature': v}),
                ),
                _Slider(
                  label: 'Top-K',
                  value: draft.parameters.topK.toDouble(),
                  min: 1,
                  max: 50,
                  divisions: 49,
                  onChanged: (v) => _patchParams({'top_k': v.round()}),
                ),
                _Slider(
                  label: 'Top rerank',
                  value: draft.parameters.topRerank.toDouble(),
                  min: 1,
                  max: 20,
                  divisions: 19,
                  onChanged: (v) => _patchParams({'top_rerank': v.round()}),
                ),
                _Slider(
                  label: 'Compactor budget',
                  value: draft.parameters.compactorBudget.toDouble(),
                  min: 512,
                  max: 6144,
                  divisions: 44,
                  onChanged: (v) => _patchParams({'compactor_budget': v.round()}),
                ),
                _Slider(
                  label: 'Min score cutoff',
                  value: draft.parameters.minScoreThreshold,
                  min: 0,
                  max: 1,
                  onChanged: (v) => _patchParams({'min_score_threshold': v}),
                ),
                _Slider(
                  label: 'HNSW ef_search',
                  value: draft.parameters.hnswEfSearch.toDouble(),
                  min: 16,
                  max: 512,
                  divisions: 31,
                  onChanged: (v) => _patchParams({'hnsw_ef_search': v.round()}),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Stream responses'),
                  value: draft.parameters.stream,
                  activeThumbColor: EvergreenColors.primary,
                  onChanged: (v) => _patchParams({'stream': v}),
                ),
                const SizedBox(height: 24),
                SectionHeader(
                  title: 'System prompt',
                  action: TextButton.icon(
                    onPressed: () {
                      setState(() => _promptController.text = '');
                      ref.read(projectActionsProvider).updateSettings(widget.projectId, {'system_prompt': null});
                    },
                    icon: const Icon(Symbols.restore, size: 16),
                    label: const Text('Reset to default'),
                  ),
                ),
                TextField(
                  controller: _promptController,
                  maxLines: 5,
                  decoration: const InputDecoration(hintText: 'Uses the workspace default grounding persona if empty.'),
                  onSubmitted: (v) =>
                      ref.read(projectActionsProvider).updateSettings(widget.projectId, {'system_prompt': v.isEmpty ? null : v}),
                ),
                const SizedBox(height: 32),
                const Divider(color: EvergreenColors.border),
                const SizedBox(height: 16),
                SectionHeader(
                  title: 'Danger zone',
                  action: OutlinedButton.icon(
                    onPressed: () => _confirmDelete(context),
                    icon: const Icon(Symbols.delete_outline, size: 16, color: EvergreenColors.refused),
                    label: const Text('Delete project', style: TextStyle(color: EvergreenColors.refused)),
                    style: OutlinedButton.styleFrom(side: const BorderSide(color: EvergreenColors.refused)),
                  ),
                ),
              ],
            ),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Failed to load project: $e', style: const TextStyle(color: EvergreenColors.refused))),
      ),
    );
  }

  void _patchParams(Map<String, dynamic> patch) {
    final draft = _draft;
    if (draft == null) return;
    ref.read(projectActionsProvider).updateSettings(widget.projectId, {'parameters': {...draft.parameters.toJson(), ...patch}});
  }

  Future<void> _confirmDelete(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this project?'),
        content: const Text('This permanently removes its chat history. This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: EvergreenColors.refused),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await ref.read(projectActionsProvider).deleteProject(widget.projectId);
    if (context.mounted) context.go('/w/${widget.workspaceId}');
  }
}

class _Slider extends StatelessWidget {
  const _Slider({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
    this.divisions,
  });

  final String label;
  final double value;
  final double min;
  final double max;
  final int? divisions;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(fontSize: 13, color: EvergreenColors.inkSecondary)),
            Text(value.toStringAsFixed(value == value.roundToDouble() ? 0 : 2), style: monoStyle(fontSize: 12)),
          ],
        ),
        Slider(
          value: value.clamp(min, max),
          min: min,
          max: max,
          divisions: divisions,
          activeColor: EvergreenColors.primary,
          onChanged: onChanged,
        ),
      ],
    );
  }
}
