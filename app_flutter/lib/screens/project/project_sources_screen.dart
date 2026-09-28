import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/api_client.dart';
import '../../api/models/document.dart';
import '../../features/project/project_providers.dart';
import '../../features/workspace/workspace_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';
import 'project_tab_shell.dart';

const _parserRoutes = {
  'fast_text': 'Fast text (PyMuPDF)',
  'layout': 'Layout (Docling — tables, columns)',
  'ocr': 'OCR (RapidOCR — scans)',
};

/// DESIGN-evergreen.md project Sources tab: attach/detach; upload → ingest → index with
/// progress; parser route.
class ProjectSourcesScreen extends ConsumerStatefulWidget {
  const ProjectSourcesScreen({super.key, required this.workspaceId, required this.projectId});
  final String workspaceId;
  final String projectId;

  @override
  ConsumerState<ProjectSourcesScreen> createState() => _ProjectSourcesScreenState();
}

class _ProjectSourcesScreenState extends ConsumerState<ProjectSourcesScreen> {
  String? _routeOverride;
  bool _uploading = false;
  String? _progressLabel;

  @override
  Widget build(BuildContext context) {
    final projectAsync = ref.watch(projectProvider(widget.projectId));
    final documentsAsync = ref.watch(documentsProvider);

    return ProjectTabShell(
      workspaceId: widget.workspaceId,
      projectId: widget.projectId,
      activeTab: ProjectTab.sources,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
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
                  const Text('Upload a source', style: TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: DropdownButtonFormField<String?>(
                          initialValue: _routeOverride,
                          decoration: const InputDecoration(labelText: 'Parser route'),
                          items: [
                            const DropdownMenuItem(value: null, child: Text('Auto-detect')),
                            for (final entry in _parserRoutes.entries)
                              DropdownMenuItem(value: entry.key, child: Text(entry.value)),
                          ],
                          onChanged: (v) => setState(() => _routeOverride = v),
                        ),
                      ),
                      const SizedBox(width: 12),
                      FilledButton.icon(
                        onPressed: _uploading ? null : _pickAndUpload,
                        icon: const Icon(Symbols.cloud_upload, size: 18),
                        label: const Text('Choose file'),
                      ),
                    ],
                  ),
                  if (_uploading) ...[
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                        const SizedBox(width: 10),
                        Text(_progressLabel ?? 'Working…', style: const TextStyle(fontSize: 13, color: EvergreenColors.metadata)),
                      ],
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 28),
            const SectionHeader(title: 'Attached sources'),
            projectAsync.when(
              data: (project) {
                if (project.files.isEmpty) {
                  return const EmptyState(message: 'No sources attached to this project yet.', icon: Symbols.description);
                }
                return Column(
                  children: [
                    for (final docId in project.files)
                      _SourceRow(
                        docId: docId,
                        documentsAsync: documentsAsync,
                        onDetach: () => ref.read(projectActionsProvider).detachFile(widget.projectId, docId),
                      ),
                  ],
                );
              },
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => Text('Failed to load project: $e', style: const TextStyle(color: EvergreenColors.refused)),
            ),
            const SizedBox(height: 28),
            const SectionHeader(title: 'Available in library'),
            documentsAsync.when(
              data: (docs) {
                final project = projectAsync.value;
                final attached = project?.files.toSet() ?? {};
                final available = docs.where((d) => !attached.contains(d.docId)).toList();
                if (available.isEmpty) {
                  return const EmptyState(message: 'No other documents in your library.');
                }
                return Column(
                  children: [
                    for (final doc in available)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Symbols.description, size: 18, color: EvergreenColors.metadata),
                        title: Text(doc.name, overflow: TextOverflow.ellipsis),
                        subtitle: Text('${doc.pages} pages · ${doc.sizeKb.toStringAsFixed(0)} KB', style: const TextStyle(fontSize: 12)),
                        trailing: OutlinedButton(
                          onPressed: () => ref.read(projectActionsProvider).attachFiles(widget.projectId, [doc.docId]),
                          child: const Text('Attach'),
                        ),
                      ),
                  ],
                );
              },
              loading: () => const SizedBox.shrink(),
              error: (e, _) => const SizedBox.shrink(),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _pickAndUpload() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf'],
      withData: true,
    );
    if (result == null || result.files.isEmpty) return;
    final file = result.files.single;
    final bytes = file.bytes;
    if (bytes == null) return;

    setState(() {
      _uploading = true;
      _progressLabel = 'Uploading and parsing…';
    });
    try {
      await ref.read(projectActionsProvider).uploadIngestIndexAndAttach(
            widget.projectId,
            bytes,
            file.name,
            route: _routeOverride,
            onStage: (stage) {
              if (mounted) setState(() => _progressLabel = stage);
            },
          );
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Upload failed: ${e.detail}')));
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }
}

class _SourceRow extends StatelessWidget {
  const _SourceRow({required this.docId, required this.documentsAsync, required this.onDetach});
  final String docId;
  final AsyncValue<List<DocumentInfo>> documentsAsync;
  final VoidCallback onDetach;

  @override
  Widget build(BuildContext context) {
    DocumentInfo? doc;
    for (final d in documentsAsync.value ?? const <DocumentInfo>[]) {
      if (d.docId == docId) {
        doc = d;
        break;
      }
    }
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.control),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: Row(
        children: [
          const Icon(Symbols.description, size: 16, color: EvergreenColors.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Text(doc?.name ?? docId, overflow: TextOverflow.ellipsis, style: monoStyle(fontSize: 12)),
          ),
          IconButton(
            icon: const Icon(Symbols.delete_outline, size: 18, color: EvergreenColors.refused),
            onPressed: onDetach,
          ),
        ],
      ),
    );
  }
}
