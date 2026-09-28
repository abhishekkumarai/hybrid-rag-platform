import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/api_client.dart';
import '../../api/auth_provider.dart';
import '../../api/models/document.dart';
import '../../features/admin/admin_providers.dart';
import '../../features/workspace/workspace_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';

enum _LibraryScope { all, mine, web }

/// DESIGN-evergreen.md Library page: documents table, scope, drag-drop upload, admin web sync,
/// open Web RAG project.
class LibraryScreen extends ConsumerStatefulWidget {
  const LibraryScreen({super.key, required this.workspaceId});
  final String workspaceId;

  @override
  ConsumerState<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends ConsumerState<LibraryScreen> {
  _LibraryScope _scope = _LibraryScope.all;
  bool _uploading = false;
  bool _syncing = false;

  @override
  Widget build(BuildContext context) {
    final documentsAsync = ref.watch(documentsProvider);
    final auth = ref.watch(authProvider);
    final isAdmin = auth is AuthSignedIn && auth.user.isAdmin;

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Library',
                    style: Theme.of(context).textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  Row(
                    children: [
                      if (isAdmin) ...[
                        OutlinedButton.icon(
                          onPressed: _syncing ? null : _syncWeb,
                          icon: _syncing
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Symbols.sync, size: 18),
                          label: const Text('Sync web sources'),
                        ),
                        const SizedBox(width: 8),
                      ],
                      FilledButton.icon(
                        onPressed: () => ref
                            .read(workspaceActionsProvider)
                            .openWebRagPreset(),
                        icon: const Icon(Symbols.public, size: 18),
                        label: const Text('Open Web RAG project'),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 20),
              _UploadDropzone(uploading: _uploading, onPick: _pickAndUpload),
              const SizedBox(height: 24),
              SectionHeader(
                title: 'Documents',
                action: SegmentedButton<_LibraryScope>(
                  segments: const [
                    ButtonSegment(value: _LibraryScope.all, label: Text('All')),
                    ButtonSegment(
                      value: _LibraryScope.mine,
                      label: Text('Mine'),
                    ),
                    ButtonSegment(value: _LibraryScope.web, label: Text('Web')),
                  ],
                  selected: {_scope},
                  onSelectionChanged: (s) => setState(() => _scope = s.first),
                ),
              ),
              documentsAsync.when(
                data: (docs) {
                  final filtered = switch (_scope) {
                    _LibraryScope.all => docs,
                    _LibraryScope.mine =>
                      docs.where((d) => !d.readOnly && !d.isWeb).toList(),
                    _LibraryScope.web => docs.where((d) => d.isWeb).toList(),
                  };
                  if (filtered.isEmpty) {
                    return const EmptyState(
                      message: 'No documents in this scope yet.',
                      icon: Symbols.folder_open,
                    );
                  }
                  return _DocumentsTable(documents: filtered);
                },
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: 32),
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (e, _) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 24),
                  child: Text(
                    'Failed to load documents: $e',
                    style: const TextStyle(color: EvergreenColors.refused),
                  ),
                ),
              ),
            ],
          ),
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
    setState(() => _uploading = true);
    try {
      final client = ref.read(apiClientProvider);
      final ingestJson =
          await client.ingestFile(bytes, file.name) as Map<String, dynamic>;
      await client.post(
        '/api/v1/index',
        body: {'doc_id': ingestJson['doc_id'], 'blocks': ingestJson['blocks']},
      );
      ref.invalidate(documentsProvider);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Upload failed: ${e.detail}')));
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<void> _syncWeb() async {
    setState(() => _syncing = true);
    try {
      await ref.read(adminActionsProvider).syncWebStore();
      ref.invalidate(documentsProvider);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Sync failed: ${e.detail}')));
      }
    } finally {
      if (mounted) setState(() => _syncing = false);
    }
  }
}

class _UploadDropzone extends StatelessWidget {
  const _UploadDropzone({required this.uploading, required this.onPick});
  final bool uploading;
  final VoidCallback onPick;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: uploading ? null : onPick,
      borderRadius: BorderRadius.circular(EvergreenRadii.panel),
      child: DottedBorderBox(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 32),
          child: Center(
            child: Column(
              children: [
                if (uploading)
                  const SizedBox(
                    width: 24,
                    height: 24,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                else
                  const Icon(
                    Symbols.cloud_upload,
                    size: 28,
                    color: EvergreenColors.primary,
                  ),
                const SizedBox(height: 10),
                Text(
                  uploading
                      ? 'Uploading and indexing…'
                      : 'Drag a PDF here, or click to choose a file',
                  style: const TextStyle(
                    fontSize: 13,
                    color: EvergreenColors.metadata,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class DottedBorderBox extends StatelessWidget {
  const DottedBorderBox({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: EvergreenColors.fill,
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        border: Border.all(color: EvergreenColors.border, width: 1.5),
      ),
      child: child,
    );
  }
}

class _DocumentsTable extends StatelessWidget {
  const _DocumentsTable({required this.documents});
  final List<DocumentInfo> documents;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: Column(
        children: [
          for (final doc in documents)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: const BoxDecoration(
                border: Border(
                  bottom: BorderSide(color: EvergreenColors.border),
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    doc.isWeb ? Symbols.public : Symbols.description,
                    size: 16,
                    color: EvergreenColors.primary,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(doc.name, overflow: TextOverflow.ellipsis),
                  ),
                  Text(
                    '${doc.pages} pp',
                    style: monoStyle(
                      fontSize: 12,
                      color: EvergreenColors.metadata,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Text(
                    '${doc.sizeKb.toStringAsFixed(0)} KB',
                    style: monoStyle(
                      fontSize: 12,
                      color: EvergreenColors.metadata,
                    ),
                  ),
                  const SizedBox(width: 16),
                  if (doc.readOnly)
                    const Icon(
                      Symbols.lock,
                      size: 14,
                      color: EvergreenColors.caption,
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
