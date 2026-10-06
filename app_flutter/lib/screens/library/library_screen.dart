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
  String? _syncProgress;
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
    setState(() => _uploading = true);
    try {
      final client = ref.read(userApiClientProvider);
      final ingestJson = await client.post(
        '/api/v1/ingest/url',
        body: {'url': url},
      ) as Map<String, dynamic>;
      if (ingestJson['error'] != null) {
        throw ApiException(422, '${ingestJson['error']}');
      }
      await client.post(
        '/api/v1/index',
        body: {'doc_id': ingestJson['doc_id'], 'blocks': ingestJson['blocks']},
      );
      _urlController.clear();
      ref.invalidate(documentsProvider);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not add URL: ${e.detail}')),
        );
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

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
                          label: Text(_syncProgress == null
                              ? 'Sync web sources'
                              : 'Syncing $_syncProgress'),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 20),
              _UploadDropzone(uploading: _uploading, onPick: _pickAndUpload),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _urlController,
                      enabled: !_uploading,
                      keyboardType: TextInputType.url,
                      decoration: const InputDecoration(
                        isDense: true,
                        prefixIcon: Icon(Symbols.public, size: 18),
                        labelText: 'Or add a web page / PDF URL',
                        hintText: 'https://example.com/article',
                      ),
                      onSubmitted: (_) => _addUrl(),
                    ),
                  ),
                  const SizedBox(width: 12),
                  FilledButton.icon(
                    onPressed: _uploading ? null : _addUrl,
                    icon: const Icon(Symbols.add_link, size: 18),
                    label: const Text('Add URL'),
                  ),
                ],
              ),
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
      final client = ref.read(userApiClientProvider);
      final ingestJson =
          await client.ingestFile(bytes, file.name) as Map<String, dynamic>;
      if (ingestJson['error'] != null) {
        throw ApiException(422, '${ingestJson['error']}');
      }
      await client.post(
        '/api/v1/index',
        body: {'doc_id': ingestJson['doc_id'], 'blocks': ingestJson['blocks']},
      );
      ref.invalidate(documentsProvider);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Upload failed: ${e.detail}')));
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<void> _syncWeb() async {
    setState(() => _syncing = true);
    try {
      final result = await ref.read(adminActionsProvider).syncWebStore(
            onProgress: (done, total) {
              if (mounted) setState(() => _syncProgress = '$done/$total');
            },
          );
      ref.invalidate(documentsProvider);
      if (mounted && result['status'] != 'completed') {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Sync ${result['status']}: ${result['error'] ?? ''}'),
        ));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Sync failed: ${e.detail}')));
      }
    } finally {
      if (mounted) {
        setState(() {
          _syncing = false;
          _syncProgress = null;
        });
      }
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
