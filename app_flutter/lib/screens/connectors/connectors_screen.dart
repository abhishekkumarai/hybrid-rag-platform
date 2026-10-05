import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/api_client.dart';
import '../../api/models/connector.dart';
import '../../features/connectors/connector_providers.dart';
import '../../features/workspace/workspace_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';

/// Website connectors (IRA-57): connect a site, keep its pages indexed, cite page URLs.
class ConnectorsScreen extends ConsumerWidget {
  const ConnectorsScreen({super.key, required this.workspaceId});
  final String workspaceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final connectorsAsync = ref.watch(connectorsProvider(workspaceId));
    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Connectors',
                            style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 4),
                        const Text(
                          'Connect a website: its pages are crawled, cleaned up, indexed and kept in sync. '
                          'Answers cite the exact page.',
                          style: TextStyle(fontSize: 13, color: EvergreenColors.metadata),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 16),
                  FilledButton.icon(
                    onPressed: () => showConnectDialog(context, ref, workspaceId),
                    icon: const Icon(Symbols.add_link, size: 18),
                    label: const Text('Connect a website'),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              connectorsAsync.when(
                data: (list) => list.isEmpty
                    ? const EmptyState(
                        message: 'No websites connected yet. Connect one to index its pages.',
                        icon: Symbols.language,
                      )
                    : Column(children: [
                        for (final c in list)
                          _ConnectorCard(
                            connector: c,
                            onOpen: () => context.go('/w/$workspaceId/connectors/${c.id}'),
                          ),
                      ]),
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: 32),
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (e, _) => EmptyState(message: 'Could not load connectors: ${e is ApiException ? e.detail : e}'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String _ago(double? epochSeconds) {
  if (epochSeconds == null || epochSeconds <= 0) return 'never';
  final diff = DateTime.now().millisecondsSinceEpoch ~/ 1000 - epochSeconds.toInt();
  if (diff < 0) {
    final ahead = -diff;
    if (ahead < 3600) return 'in ${ahead ~/ 60}m';
    if (ahead < 86400) return 'in ${ahead ~/ 3600}h';
    return 'in ${ahead ~/ 86400}d';
  }
  if (diff < 60) return 'just now';
  if (diff < 3600) return '${diff ~/ 60}m ago';
  if (diff < 86400) return '${diff ~/ 3600}h ago';
  return '${diff ~/ 86400}d ago';
}

({Color fg, Color bg, String label}) _statusStyle(String status) => switch (status) {
      'ok' => (fg: EvergreenColors.confident, bg: EvergreenColors.confidentTint, label: 'Synced'),
      'partial' => (fg: EvergreenColors.ambiguous, bg: EvergreenColors.fill, label: 'Synced with issues'),
      'error' => (fg: EvergreenColors.refused, bg: EvergreenColors.refusedTint, label: 'Failed'),
      'queued' => (fg: EvergreenColors.primary, bg: EvergreenColors.primaryTint, label: 'Queued'),
      'running' => (fg: EvergreenColors.primary, bg: EvergreenColors.primaryTint, label: 'Syncing…'),
      _ => (fg: EvergreenColors.metadata, bg: EvergreenColors.fill, label: 'Not synced'),
    };

class _StatusChip extends StatelessWidget {
  const _StatusChip(this.status);
  final String status;

  @override
  Widget build(BuildContext context) {
    final s = _statusStyle(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: s.bg, borderRadius: BorderRadius.circular(EvergreenRadii.chip)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (status == 'running' || status == 'queued') ...[
          SizedBox(width: 10, height: 10, child: CircularProgressIndicator(strokeWidth: 1.5, color: s.fg)),
          const SizedBox(width: 6),
        ],
        Text(s.label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: s.fg)),
      ]),
    );
  }
}

class _ConnectorCard extends StatelessWidget {
  const _ConnectorCard({required this.connector, required this.onOpen});
  final WebConnector connector;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final c = connector;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: EvergreenColors.surface,
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        border: Border.all(color: EvergreenColors.border),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: EvergreenColors.primaryTint, borderRadius: BorderRadius.circular(EvergreenRadii.control)),
              child: const Icon(Symbols.language, color: EvergreenColors.primary, size: 20),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Wrap(spacing: 8, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                  Text(c.name, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: EvergreenColors.ink)),
                  _StatusChip(c.status),
                ]),
                const SizedBox(height: 3),
                Text(c.startUrl, overflow: TextOverflow.ellipsis, style: monoStyle(fontSize: 11, color: EvergreenColors.metadata)),
                if (c.lastError != null) ...[
                  const SizedBox(height: 3),
                  Text(c.lastError!, style: const TextStyle(fontSize: 12, color: EvergreenColors.refused)),
                ],
              ]),
            ),
            const SizedBox(width: 12),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text('${c.pageCount} pages', style: monoStyle(fontSize: 12, color: EvergreenColors.ink)),
              const SizedBox(height: 2),
              Text('synced ${_ago(c.lastSyncAt)} · ${c.schedule}', style: const TextStyle(fontSize: 11, color: EvergreenColors.metadata)),
            ]),
            const SizedBox(width: 8),
            const Icon(Symbols.chevron_right, size: 18, color: EvergreenColors.metadata),
          ]),
        ),
      ),
    );
  }
}

// ----------------------------------------------------------------------------- connect dialog

Future<void> showConnectDialog(BuildContext context, WidgetRef ref, String workspaceId, {String? projectId}) =>
    showDialog(context: context, builder: (_) => _ConnectDialog(workspaceId: workspaceId, projectId: projectId));

class _ConnectDialog extends ConsumerStatefulWidget {
  const _ConnectDialog({required this.workspaceId, this.projectId});
  final String workspaceId;
  final String? projectId;

  @override
  ConsumerState<_ConnectDialog> createState() => _ConnectDialogState();
}

class _ConnectDialogState extends ConsumerState<_ConnectDialog> {
  final _url = TextEditingController();
  final _name = TextEditingController();
  final _prefix = TextEditingController();
  final _maxPages = TextEditingController(text: '100');
  final _maxDepth = TextEditingController(text: '3');
  String _render = 'auto';
  String _schedule = 'manual';
  String? _projectId;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _projectId = widget.projectId;
  }

  @override
  void dispose() {
    for (final c in [_url, _name, _prefix, _maxPages, _maxDepth]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    final url = _url.text.trim();
    if (url.isEmpty) {
      setState(() => _error = 'Enter the website address.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final prefix = _prefix.text.trim();
      final connector = await ref.read(connectorActionsProvider).create(
            workspaceId: widget.workspaceId,
            startUrl: url,
            name: _name.text.trim().isEmpty ? null : _name.text.trim(),
            projectId: _projectId,
            scope: prefix.isEmpty && _maxPages.text == '100' && _maxDepth.text == '3'
                ? null
                : CrawlScope(
                    pathPrefix: prefix.isEmpty ? '/' : prefix,
                    maxPages: int.tryParse(_maxPages.text) ?? 100,
                    maxDepth: int.tryParse(_maxDepth.text) ?? 3,
                  ),
            render: _render,
            schedule: _schedule,
          );
      if (mounted) {
        Navigator.of(context).pop();
        context.go('/w/${widget.workspaceId}/connectors/${connector.id}');
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final projects = ref.watch(workspaceProjectsProvider(widget.workspaceId)).valueOrNull ?? const [];
    Widget label(String t) => Padding(
          padding: const EdgeInsets.only(bottom: 6, top: 14),
          child: Text(t, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: EvergreenColors.inkSecondary)),
        );
    return AlertDialog(
      title: const Text('Connect a website'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            TextField(
              controller: _url,
              autofocus: true,
              keyboardType: TextInputType.url,
              decoration: InputDecoration(labelText: 'Start URL', hintText: 'https://docs.example.com/guide/', errorText: _error),
              onSubmitted: (_) => _submit(),
            ),
            const SizedBox(height: 8),
            TextField(controller: _name, decoration: const InputDecoration(labelText: 'Name (optional)')),
            label('Feed pages into a project (optional)'),
            DropdownButtonFormField<String?>(
              initialValue: projects.any((p) => p.id == _projectId) ? _projectId : null,
              isExpanded: true,
              items: [
                const DropdownMenuItem<String?>(value: null, child: Text('Library only')),
                for (final p in projects) DropdownMenuItem<String?>(value: p.id, child: Text(p.title, overflow: TextOverflow.ellipsis)),
              ],
              onChanged: (v) => setState(() => _projectId = v),
            ),
            label('Crawl'),
            Row(children: [
              Expanded(
                flex: 3,
                child: TextField(
                  controller: _prefix,
                  decoration: const InputDecoration(labelText: 'Only pages under', hintText: 'defaults to the start URL\'s folder'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(child: TextField(controller: _maxPages, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Max pages'))),
              const SizedBox(width: 10),
              Expanded(child: TextField(controller: _maxDepth, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Link depth'))),
            ]),
            label('JavaScript pages'),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'auto', label: Text('Auto'), tooltip: 'Static HTML; a headless browser only when a page needs it'),
                ButtonSegment(value: 'static', label: Text('Never'), tooltip: 'Static HTML only (fastest)'),
                ButtonSegment(value: 'browser', label: Text('Always'), tooltip: 'Render every page in a headless browser'),
              ],
              selected: {_render},
              showSelectedIcon: false,
              onSelectionChanged: (s) => setState(() => _render = s.first),
            ),
            label('Keep in sync'),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'manual', label: Text('Manually')),
                ButtonSegment(value: 'daily', label: Text('Daily')),
                ButtonSegment(value: 'weekly', label: Text('Weekly')),
              ],
              selected: {_schedule},
              showSelectedIcon: false,
              onSelectionChanged: (s) => setState(() => _schedule = s.first),
            ),
            const SizedBox(height: 10),
            const Text(
              'Only public pages are fetched. robots.txt and sitemap.xml are respected.',
              style: TextStyle(fontSize: 11, color: EvergreenColors.metadata),
            ),
          ]),
        ),
      ),
      actions: [
        TextButton(onPressed: _saving ? null : () => Navigator.of(context).pop(), child: const Text('Cancel')),
        FilledButton(
          onPressed: _saving ? null : _submit,
          child: _saving
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text('Connect and sync'),
        ),
      ],
    );
  }
}

// ----------------------------------------------------------------------------- detail

class ConnectorDetailScreen extends ConsumerWidget {
  const ConnectorDetailScreen({super.key, required this.workspaceId, required this.connectorId});
  final String workspaceId;
  final String connectorId;

  Future<void> _run(BuildContext context, Future<void> Function() action, String failure) async {
    try {
      await action();
    } on ApiException catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$failure: ${e.detail}')));
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, WebConnector c) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Disconnect ${c.name}?'),
        content: const Text('Its pages are removed from your library and from any linked project.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: EvergreenColors.refused),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Disconnect'),
          ),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    await _run(context, () => ref.read(connectorActionsProvider).delete(c.id), 'Could not disconnect');
    if (context.mounted) context.go('/w/$workspaceId/connectors');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detailAsync = ref.watch(connectorDetailProvider(connectorId));
    final projects = ref.watch(workspaceProjectsProvider(workspaceId)).valueOrNull ?? const [];
    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: detailAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('Could not load connector: ${e is ApiException ? e.detail : e}')),
          data: (d) {
            final c = d.connector;
            final r = d.lastReport;
            return SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                InkWell(
                  onTap: () => context.go('/w/$workspaceId/connectors'),
                  child: const Text('Connectors ›', style: TextStyle(fontSize: 13, color: EvergreenColors.metadata)),
                ),
                const SizedBox(height: 8),
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Wrap(spacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: [
                        Text(c.name, style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
                        _StatusChip(c.status),
                      ]),
                      const SizedBox(height: 4),
                      InkWell(
                        onTap: () => launchUrl(Uri.parse(c.startUrl), webOnlyWindowName: '_blank'),
                        child: Text(c.startUrl, style: monoStyle(fontSize: 12, color: EvergreenColors.primary)),
                      ),
                    ]),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => _delete(context, ref, c),
                    icon: const Icon(Symbols.link_off, size: 16, color: EvergreenColors.refused),
                    label: const Text('Disconnect', style: TextStyle(color: EvergreenColors.refused)),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.icon(
                    onPressed: c.busy ? null : () => _run(context, () => ref.read(connectorActionsProvider).sync(c.id), 'Could not start a sync'),
                    icon: const Icon(Symbols.sync, size: 16),
                    label: Text(c.busy ? 'Syncing…' : 'Sync now'),
                  ),
                ]),
                if (c.busy) ...[const SizedBox(height: 12), const LinearProgressIndicator(minHeight: 2)],
                if (c.lastError != null) ...[
                  const SizedBox(height: 12),
                  Text(c.lastError!, style: const TextStyle(color: EvergreenColors.refused, fontSize: 13)),
                ],
                const SizedBox(height: 20),
                Wrap(spacing: 24, runSpacing: 12, children: [
                  _Fact('Pages indexed', '${c.pageCount}'),
                  _Fact('Last sync', c.lastSyncAt == null ? 'never' : '${_ago(c.lastSyncAt)}'
                      '${c.lastSyncDurationS != null ? ' · ${c.lastSyncDurationS!.toStringAsFixed(1)} s' : ''}'),
                  _Fact('Next sync', c.schedule == 'manual' ? 'manual' : _ago(c.nextSyncAt)),
                  _Fact('Scope', '${c.scope.pathPrefix} · ≤${c.scope.maxPages} pages · depth ${c.scope.maxDepth}'),
                ]),
                const SizedBox(height: 16),
                Wrap(spacing: 16, runSpacing: 12, crossAxisAlignment: WrapCrossAlignment.center, children: [
                  SizedBox(
                    width: 220,
                    child: DropdownButtonFormField<String>(
                      initialValue: c.schedule,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'Keep in sync', isDense: true),
                      items: const [
                        DropdownMenuItem(value: 'manual', child: Text('Manually')),
                        DropdownMenuItem(value: 'daily', child: Text('Daily')),
                        DropdownMenuItem(value: 'weekly', child: Text('Weekly')),
                      ],
                      onChanged: (v) => _run(context, () => ref.read(connectorActionsProvider).update(c.id, {'schedule': v}), 'Could not save'),
                    ),
                  ),
                  SizedBox(
                    width: 220,
                    child: DropdownButtonFormField<String>(
                      initialValue: c.render,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'JavaScript pages', isDense: true),
                      items: const [
                        DropdownMenuItem(value: 'auto', child: Text('Auto')),
                        DropdownMenuItem(value: 'static', child: Text('Never render')),
                        DropdownMenuItem(value: 'browser', child: Text('Always render')),
                      ],
                      onChanged: (v) => _run(context, () => ref.read(connectorActionsProvider).update(c.id, {'render': v}), 'Could not save'),
                    ),
                  ),
                  SizedBox(
                    width: 280,
                    child: DropdownButtonFormField<String?>(
                      initialValue: projects.any((p) => p.id == c.projectId) ? c.projectId : null,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'Feeds project', isDense: true),
                      items: [
                        const DropdownMenuItem<String?>(value: null, child: Text('Library only')),
                        for (final p in projects) DropdownMenuItem<String?>(value: p.id, child: Text(p.title, overflow: TextOverflow.ellipsis)),
                      ],
                      onChanged: (v) => _run(context, () => ref.read(connectorActionsProvider).update(c.id, {'project_id': v}), 'Could not save'),
                    ),
                  ),
                ]),
                if (r != null) ...[
                  const SizedBox(height: 24),
                  SectionHeader(title: 'Last sync · ${_ago(r.finishedAt)}'),
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    _Count('indexed', r.indexed, EvergreenColors.confident),
                    _Count('unchanged', r.unchanged, EvergreenColors.metadata),
                    _Count('removed', r.removed, EvergreenColors.metadata),
                    _Count('skipped', r.skipped, EvergreenColors.metadata),
                    _Count('need JavaScript', r.needsJs, EvergreenColors.ambiguous),
                    _Count('errors', r.errors, EvergreenColors.refused),
                  ]),
                ],
                const SizedBox(height: 24),
                SectionHeader(title: 'Pages (${d.pages.length})'),
                if (d.pages.isEmpty)
                  EmptyState(message: c.busy ? 'Crawling… pages appear when the sync finishes.' : 'No pages yet. Run a sync.', icon: Symbols.description)
                else
                  Container(
                    decoration: BoxDecoration(
                      color: EvergreenColors.surface,
                      borderRadius: BorderRadius.circular(EvergreenRadii.panel),
                      border: Border.all(color: EvergreenColors.border),
                    ),
                    child: Column(children: [
                      for (var i = 0; i < d.pages.length; i++) ...[
                        if (i > 0) const Divider(height: 1, color: EvergreenColors.border),
                        _PageRow(page: d.pages[i]),
                      ],
                    ]),
                  ),
              ]),
            );
          },
        ),
      ),
    );
  }
}

class _Fact extends StatelessWidget {
  const _Fact(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: const TextStyle(fontSize: 11, color: EvergreenColors.metadata)),
        const SizedBox(height: 2),
        Text(value, style: monoStyle(fontSize: 13, color: EvergreenColors.ink)),
      ]);
}

class _Count extends StatelessWidget {
  const _Count(this.label, this.value, this.color);
  final String label;
  final int value;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: EvergreenColors.surface,
          borderRadius: BorderRadius.circular(EvergreenRadii.chip),
          border: Border.all(color: EvergreenColors.border),
        ),
        child: Text('$value $label', style: TextStyle(fontSize: 12, color: value == 0 ? EvergreenColors.metadata : color)),
      );
}

class _PageRow extends StatelessWidget {
  const _PageRow({required this.page});
  final ConnectorPage page;

  @override
  Widget build(BuildContext context) {
    final p = page;
    final (Color fg, String label) = switch (p.status) {
      'indexed' => (EvergreenColors.confident, 'indexed'),
      'unchanged' => (EvergreenColors.metadata, 'unchanged'),
      'needs_js' => (EvergreenColors.ambiguous, 'needs JS'),
      'error' => (EvergreenColors.refused, 'error'),
      _ => (EvergreenColors.metadata, p.status),
    };
    return InkWell(
      onTap: () => launchUrl(Uri.parse(p.url), webOnlyWindowName: '_blank'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(children: [
          SizedBox(width: 84, child: Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: fg))),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(p.title.isEmpty ? p.url : p.title, maxLines: 1, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13, color: EvergreenColors.ink)),
              Text(p.url, maxLines: 1, overflow: TextOverflow.ellipsis, style: monoStyle(fontSize: 11, color: EvergreenColors.metadata)),
              if (p.error != null) Text(p.error!, style: const TextStyle(fontSize: 11, color: EvergreenColors.refused)),
            ]),
          ),
          const SizedBox(width: 12),
          Text(
            p.words > 0 ? '${p.words} words${p.renderedWith == 'browser' ? ' · rendered' : p.renderedWith == 'pdf' ? ' · PDF' : ''}' : '',
            style: monoStyle(fontSize: 11, color: EvergreenColors.metadata),
          ),
        ]),
      ),
    );
  }
}
