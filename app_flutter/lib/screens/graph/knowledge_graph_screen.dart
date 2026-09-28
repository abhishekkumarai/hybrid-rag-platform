import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../api/models/graph.dart';
import '../../features/admin/admin_providers.dart';
import '../../theme/evergreen_theme.dart';
import '../../widgets/section_header.dart';
import '../../widgets/stat_card.dart';

/// DESIGN-evergreen.md Knowledge graph page: CustomPainter force layout, trace query,
/// entity/relation/community stats, weight and hop controls.
class KnowledgeGraphScreen extends ConsumerStatefulWidget {
  const KnowledgeGraphScreen({super.key, required this.workspaceId});
  final String workspaceId;

  @override
  ConsumerState<KnowledgeGraphScreen> createState() =>
      _KnowledgeGraphScreenState();
}

class _KnowledgeGraphScreenState extends ConsumerState<KnowledgeGraphScreen> {
  final _queryController = TextEditingController();
  int _maxHops = 2;
  double _minEdgeWeight = 0.1;
  GraphRAGResponse? _result;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _queryController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final statsAsync = ref.watch(graphStatsProvider);

    return Scaffold(
      backgroundColor: EvergreenColors.canvas,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Knowledge graph',
                style: Theme.of(context).textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 20),
              statsAsync.when(
                data: (stats) => Wrap(
                  spacing: 16,
                  runSpacing: 16,
                  children: [
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Entities',
                        value: '${stats.entityCount}',
                        icon: Symbols.category,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Relations',
                        value: '${stats.relationCount}',
                        icon: Symbols.hub,
                        tint: EvergreenColors.folderSky,
                        tintIcon: EvergreenColors.folderSkyIcon,
                      ),
                    ),
                    SizedBox(
                      width: 200,
                      child: StatCard(
                        label: 'Communities',
                        value: '${stats.communityCount}',
                        icon: Symbols.group_work,
                        tint: EvergreenColors.folderSand,
                        tintIcon: EvergreenColors.folderSandIcon,
                      ),
                    ),
                  ],
                ),
                loading: () => const SizedBox(
                  height: 96,
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (e, _) => const Text(
                  'Could not load graph stats.',
                  style: TextStyle(color: EvergreenColors.caption),
                ),
              ),
              const SizedBox(height: 28),
              const SectionHeader(title: 'Trace a query'),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: TextField(
                      controller: _queryController,
                      decoration: const InputDecoration(
                        hintText:
                            'e.g. How does retrieval relate to reranking?',
                      ),
                      onSubmitted: (_) => _runQuery(),
                    ),
                  ),
                  const SizedBox(width: 12),
                  FilledButton.icon(
                    onPressed: _loading ? null : _runQuery,
                    icon: _loading
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Symbols.route, size: 18),
                    label: const Text('Trace'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Max hops: $_maxHops',
                          style: const TextStyle(
                            fontSize: 13,
                            color: EvergreenColors.inkSecondary,
                          ),
                        ),
                        Slider(
                          value: _maxHops.toDouble(),
                          min: 1,
                          max: 5,
                          divisions: 4,
                          activeColor: EvergreenColors.primary,
                          onChanged: (v) =>
                              setState(() => _maxHops = v.round()),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 24),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Min edge weight: ${_minEdgeWeight.toStringAsFixed(2)}',
                          style: const TextStyle(
                            fontSize: 13,
                            color: EvergreenColors.inkSecondary,
                          ),
                        ),
                        Slider(
                          value: _minEdgeWeight,
                          min: 0,
                          max: 1,
                          activeColor: EvergreenColors.primary,
                          onChanged: (v) => setState(() => _minEdgeWeight = v),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Text(
                    _error!,
                    style: const TextStyle(color: EvergreenColors.refused),
                  ),
                ),
              if (_result != null) ...[
                Container(
                  height: 420,
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: EvergreenColors.surface,
                    borderRadius: BorderRadius.circular(EvergreenRadii.panel),
                    border: Border.all(color: EvergreenColors.border),
                  ),
                  child: _result!.nodeNames.isEmpty
                      ? const Center(
                          child: Text(
                            'No entities matched this query.',
                            style: TextStyle(color: EvergreenColors.caption),
                          ),
                        )
                      : ForceGraphView(result: _result!),
                ),
                const SizedBox(height: 16),
                if (_result!.subgraphText.isNotEmpty)
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: EvergreenColors.fill,
                      borderRadius: BorderRadius.circular(
                        EvergreenRadii.control,
                      ),
                    ),
                    child: Text(
                      _result!.subgraphText,
                      style: monoStyle(fontSize: 12),
                    ),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _runQuery() async {
    final text = _queryController.text.trim();
    if (text.isEmpty) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await ref
          .read(adminActionsProvider)
          .queryGraph(text, maxHops: _maxHops, minEdgeWeight: _minEdgeWeight);
      if (mounted) setState(() => _result = result);
    } catch (e) {
      if (mounted) setState(() => _error = 'Query failed: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }
}

/// A simple spring/repulsion force-directed layout — not a physics engine, just enough to spread
/// nodes out without overlap and show relation edges as directed, weighted lines.
class ForceGraphView extends StatefulWidget {
  const ForceGraphView({super.key, required this.result});
  final GraphRAGResponse result;

  @override
  State<ForceGraphView> createState() => _ForceGraphViewState();
}

class _ForceGraphViewState extends State<ForceGraphView>
    with SingleTickerProviderStateMixin {
  late List<String> _nodes;
  late Map<String, Offset> _positions;
  late Ticker _ticker;

  @override
  void initState() {
    super.initState();
    _layout();
    _ticker = createTicker(_tick)..start();
  }

  @override
  void didUpdateWidget(covariant ForceGraphView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.result != widget.result) _layout();
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  void _layout() {
    _nodes = widget.result.nodeNames;
    final rand = math.Random(_nodes.length);
    _positions = {
      for (final n in _nodes)
        n: Offset(rand.nextDouble() * 400, rand.nextDouble() * 300),
    };
  }

  void _tick(Duration elapsed) {
    if (_nodes.length < 2) return;
    const repulsion = 2200.0;
    const springLength = 90.0;
    const springStrength = 0.02;
    const damping = 0.9;
    final forces = {for (final n in _nodes) n: Offset.zero};

    for (var i = 0; i < _nodes.length; i++) {
      for (var j = i + 1; j < _nodes.length; j++) {
        final a = _nodes[i], b = _nodes[j];
        final delta = _positions[a]! - _positions[b]!;
        final dist = math.max(delta.distance, 1.0);
        final force = delta / dist * (repulsion / (dist * dist));
        forces[a] = forces[a]! + force;
        forces[b] = forces[b]! - force;
      }
    }
    for (final r in widget.result.relations) {
      if (!_positions.containsKey(r.source) || !_positions.containsKey(r.target)) {
        continue;
      }
      final delta = _positions[r.target]! - _positions[r.source]!;
      final dist = math.max(delta.distance, 1.0);
      final force = delta / dist * ((dist - springLength) * springStrength);
      forces[r.source] = forces[r.source]! + force;
      forces[r.target] = forces[r.target]! - force;
    }
    setState(() {
      for (final n in _nodes) {
        _positions[n] = (_positions[n]! + forces[n]! * damping).clamp(
          const Offset(20, 20),
          const Offset(2000, 2000),
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(EvergreenRadii.panel),
      child: CustomPaint(
        painter: _GraphPainter(
          nodes: _nodes,
          positions: _positions,
          relations: widget.result.relations,
        ),
        size: Size.infinite,
      ),
    );
  }
}

extension on Offset {
  Offset clamp(Offset min, Offset max) =>
      Offset(dx.clamp(min.dx, max.dx), dy.clamp(min.dy, max.dy));
}

class _GraphPainter extends CustomPainter {
  _GraphPainter({
    required this.nodes,
    required this.positions,
    required this.relations,
  });
  final List<String> nodes;
  final Map<String, Offset> positions;
  final List<GraphRelation> relations;

  @override
  void paint(Canvas canvas, Size size) {
    final edgePaint = Paint()
      ..color = EvergreenColors.border
      ..strokeWidth = 1.2;
    for (final r in relations) {
      final a = positions[r.source];
      final b = positions[r.target];
      if (a == null || b == null) continue;
      canvas.drawLine(a, b, edgePaint..strokeWidth = (0.6 + r.weight * 1.4));
    }
    final nodePaint = Paint()..color = EvergreenColors.primaryTint;
    final nodeBorder = Paint()
      ..color = EvergreenColors.primary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    for (final n in nodes) {
      final p = positions[n];
      if (p == null) continue;
      canvas.drawCircle(p, 6, nodePaint);
      canvas.drawCircle(p, 6, nodeBorder);
      final tp = TextPainter(
        text: TextSpan(
          text: n,
          style: const TextStyle(fontSize: 10, color: EvergreenColors.ink),
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: 120);
      tp.paint(canvas, p + const Offset(8, -6));
    }
  }

  @override
  bool shouldRepaint(covariant _GraphPainter oldDelegate) => true;
}
