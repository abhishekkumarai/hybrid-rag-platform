import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/models/document.dart';
import '../../api/models/ingest_job.dart';
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
  const ProjectSourcesScreen({
    super.key,
    required this.workspaceId,
    required this.projectId,
  });
  final String workspaceId;
  final String projectId;

  @override
  ConsumerState<ProjectSourcesScreen> createState() =>
      _ProjectSourcesScreenState();
}

enum _SourceKind { file, web }

class _ProjectSourcesScreenState extends ConsumerState<ProjectSourcesScreen> {
  String? _routeOverride;
  _SourceKind _kind = _SourceKind.file;
  final _urlController = TextEditingController();

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _addUrl() async {
    var url = _urlController.text.trim();
    if (url.isEmpty) return;
    if (!url.contains('://')) url = 'https://$url';
    final parsed = Uri.tryParse(url);
    if (parsed == null ||
        !(parsed.scheme == 'http' || parsed.scheme == 'https') ||
        parsed.host.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid http(s) URL.')),
      );
      return;
    }
    _urlController.clear();
    await ref
        .read(ingestJobsProvider(widget.projectId).notifier)
        .submitUrl(url);
  }

  @override
  Widget build(BuildContext context) {
    final projectAsync = ref.watch(projectProvider(widget.projectId));
    final documentsAsync = ref.watch(documentsProvider);
    // Owned by the app, not this screen: leaving the tab and coming back shows the same progress.
    final jobs = ref
        .watch(ingestJobsProvider(widget.projectId))
        .where((j) => !j.isDone)
        .toList();

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
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'Add a source',
                          style: TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ),
                      SegmentedButton<_SourceKind>(
                        segments: const [
                          ButtonSegment(
                            value: _SourceKind.file,
                            icon: Icon(Symbols.upload_file, size: 16),
                            label: Text('File'),
                          ),
                          ButtonSegment(
                            value: _SourceKind.web,
                            icon: Icon(Symbols.public, size: 16),
                            label: Text('Web'),
                          ),
                        ],
                        selected: {_kind},
                        onSelectionChanged: (s) =>
                            setState(() => _kind = s.first),
                        showSelectedIcon: false,
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  if (_kind == _SourceKind.file)
                    Row(
                      children: [
                        Expanded(
                          child: DropdownButtonFormField<String?>(
                            initialValue: _routeOverride,
                            decoration: const InputDecoration(
                              labelText: 'Parser route',
                            ),
                            items: [
                              const DropdownMenuItem(
                                value: null,
                                child: Text('Auto-detect'),
                              ),
                              for (final entry in _parserRoutes.entries)
                                DropdownMenuItem(
                                  value: entry.key,
                                  child: Text(entry.value),
                                ),
                            ],
                            onChanged: (v) =>
                                setState(() => _routeOverride = v),
                          ),
                        ),
                        const SizedBox(width: 12),
                        FilledButton.icon(
                          onPressed: _pickAndUpload,
                          icon: const Icon(Symbols.cloud_upload, size: 18),
                          label: const Text('Choose file'),
                        ),
                      ],
                    )
                  else
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _urlController,
                            keyboardType: TextInputType.url,
                            decoration: const InputDecoration(
                              labelText: 'Web page or PDF URL',
                              hintText: 'https://example.com/article',
                            ),
                            onSubmitted: (_) => _addUrl(),
                          ),
                        ),
                        const SizedBox(width: 12),
                        FilledButton.icon(
                          onPressed: _addUrl,
                          icon: const Icon(Symbols.add_link, size: 18),
                          label: const Text('Add URL'),
                        ),
                      ],
                    ),
                  for (final job in jobs) ...[
                    const SizedBox(height: 12),
                    _JobRow(
                      job: job,
                      onDismiss: () => ref
                          .read(ingestJobsProvider(widget.projectId).notifier)
                          .dismiss(job),
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
                  return const EmptyState(
                    message: 'No sources attached to this project yet.',
                    icon: Symbols.description,
                  );
                }
                return Column(
                  children: [
                    for (final docId in project.files)
                      _SourceRow(
                        docId: docId,
                        documentsAsync: documentsAsync,
                        onDetach: () => ref
                            .read(projectActionsProvider)
                            .detachFile(widget.projectId, docId),
                      ),
                  ],
                );
              },
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => Text(
                'Failed to load project: $e',
                style: const TextStyle(color: EvergreenColors.refused),
              ),
            ),
            const SizedBox(height: 28),
            const SectionHeader(title: 'Available in library'),
            documentsAsync.when(
              data: (docs) {
                final project = projectAsync.valueOrNull;
                final attached = project?.files.toSet() ?? {};
                final available = docs
                    .where((d) => !attached.contains(d.docId))
                    .toList();
                if (available.isEmpty) {
                  return const EmptyState(
                    message: 'No other documents in your library.',
                  );
                }
                return Column(
                  children: [
                    for (final doc in available)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(
                          Symbols.description,
                          size: 18,
                          color: EvergreenColors.metadata,
                        ),
                        title: Text(doc.name, overflow: TextOverflow.ellipsis),
                        subtitle: Text(
                          '${doc.pages} pages · ${doc.sizeKb.toStringAsFixed(0)} KB',
                          style: const TextStyle(fontSize: 12),
                        ),
                        trailing: OutlinedButton(
                          onPressed: () => ref
                              .read(projectActionsProvider)
                              .attachFiles(widget.projectId, [doc.docId]),
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

    await ref
        .read(ingestJobsProvider(widget.projectId).notifier)
        .submitUpload(bytes, file.name, route: _routeOverride);
  }
}

class _JobRow extends StatelessWidget {
  const _JobRow({required this.job, required this.onDismiss});
  final IngestJob job;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final failed = job.isFailed;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: failed
              ? const Icon(
                  Symbols.error,
                  size: 16,
                  color: EvergreenColors.refused,
                )
              : const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                job.source,
                overflow: TextOverflow.ellipsis,
                style: monoStyle(fontSize: 12),
              ),
              const SizedBox(height: 2),
              Text(
                failed ? (job.error ?? 'Failed') : '${job.stage}…',
                style: TextStyle(
                  fontSize: 13,
                  color: failed
                      ? EvergreenColors.refused
                      : EvergreenColors.metadata,
                ),
              ),
            ],
          ),
        ),
        if (failed)
          IconButton(
            tooltip: 'Dismiss',
            visualDensity: VisualDensity.compact,
            icon: const Icon(Symbols.close, size: 16),
            onPressed: onDismiss,
          ),
      ],
    );
  }
}

class _SourceRow extends StatelessWidget {
  const _SourceRow({
    required this.docId,
    required this.documentsAsync,
    required this.onDetach,
  });
  final String docId;
  final AsyncValue<List<DocumentInfo>> documentsAsync;
  final VoidCallback onDetach;

  @override
  Widget build(BuildContext context) {
    DocumentInfo? doc;
    for (final d in documentsAsync.valueOrNull ?? const <DocumentInfo>[]) {
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
          const Icon(
            Symbols.description,
            size: 16,
            color: EvergreenColors.primary,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              doc?.name ?? docId,
              overflow: TextOverflow.ellipsis,
              style: monoStyle(fontSize: 12),
            ),
          ),
          IconButton(
            icon: const Icon(
              Symbols.delete_outline,
              size: 18,
              color: EvergreenColors.refused,
            ),
            onPressed: onDetach,
          ),
        ],
      ),
    );
  }
}
