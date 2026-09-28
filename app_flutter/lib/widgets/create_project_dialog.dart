import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../api/models/session.dart';
import '../features/workspace/workspace_providers.dart';
import '../theme/evergreen_theme.dart';

/// Shared "New project" modal dialog matching the Evergreen Craft aesthetic
/// (DESIGN-evergreen.md) — used by the sidebar's PROJECTS (+) affordance and
/// the workspace Overview's "New project" button.
Future<ChatSession?> createProjectDialog(
  BuildContext context,
  WidgetRef ref,
  String workspaceId,
) async {
  final session = await showDialog<ChatSession>(
    context: context,
    barrierDismissible: true,
    builder: (dialogContext) => _CreateProjectModal(
      workspaceId: workspaceId,
    ),
  );
  if (session != null && context.mounted) {
    final targetWs = (session.workspaceId != null && session.workspaceId!.isNotEmpty)
        ? session.workspaceId!
        : (workspaceId != 'default' && workspaceId != 'ws_default' ? workspaceId : null);
    if (targetWs != null) {
      context.go('/w/$targetWs/p/${session.id}/overview');
    }
  }
  return session;
}

class _CreateProjectModal extends ConsumerStatefulWidget {
  const _CreateProjectModal({
    required this.workspaceId,
  });

  final String workspaceId;

  @override
  ConsumerState<_CreateProjectModal> createState() => _CreateProjectModalState();
}

class _CreateProjectModalState extends ConsumerState<_CreateProjectModal> {
  final _titleController = TextEditingController();
  final _descriptionController = TextEditingController();
  String _selectedModel = 'llama3.2:3b';
  String _selectedMode = 'auto';
  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final title = _titleController.text.trim();
    if (title.isEmpty) {
      setState(() => _errorMessage = 'Project title is required.');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    try {
      final project = await ref.read(workspaceActionsProvider).createProject(
            widget.workspaceId,
            title,
            description: _descriptionController.text.trim(),
            model: _selectedModel,
            retrievalMode: _selectedMode,
          );
      if (mounted) {
        Navigator.of(context).pop(project);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
          _errorMessage = 'Failed to create project: $e';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.sizeOf(context).height;

    return Dialog(
      backgroundColor: EvergreenColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvergreenRadii.panel),
        side: const BorderSide(color: EvergreenColors.border),
      ),
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: 540,
          maxHeight: screenHeight * 0.88,
        ),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      color: EvergreenColors.primaryTint,
                      borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    ),
                    alignment: Alignment.center,
                    child: const Icon(
                      Symbols.create_new_folder,
                      color: EvergreenColors.primary,
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const [
                        Text(
                          'New Project',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: EvergreenColors.ink,
                            letterSpacing: -0.3,
                          ),
                        ),
                        SizedBox(height: 2),
                        Text(
                          'Create a scoped RAG corpus with model and retrieval settings.',
                          style: TextStyle(
                            fontSize: 12,
                            color: EvergreenColors.metadata,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Symbols.close, size: 18, color: EvergreenColors.metadata),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              const Divider(height: 1, color: EvergreenColors.border),
              const SizedBox(height: 18),

              // Error notification
              if (_errorMessage != null) ...[
                Container(
                  padding: const EdgeInsets.all(10),
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: EvergreenColors.refusedTint,
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    border: Border.all(color: EvergreenColors.refused.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Symbols.error, size: 16, color: EvergreenColors.refused),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _errorMessage!,
                          style: const TextStyle(fontSize: 12, color: EvergreenColors.refused),
                        ),
                      ),
                    ],
                  ),
                ),
              ],

              // Project Title Input
              const Text(
                'Project Title',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: EvergreenColors.ink,
                ),
              ),
              const SizedBox(height: 6),
              TextField(
                controller: _titleController,
                autofocus: true,
                style: const TextStyle(fontSize: 14),
                decoration: InputDecoration(
                  hintText: 'e.g. FY25 10-K Due Diligence',
                  hintStyle: const TextStyle(color: EvergreenColors.metadata, fontSize: 13),
                  isDense: true,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  filled: true,
                  fillColor: EvergreenColors.fill,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.border),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.border),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.primary, width: 1.5),
                  ),
                ),
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 16),

              // Description / Focus Area
              const Text(
                'Description / Focus (optional)',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: EvergreenColors.ink,
                ),
              ),
              const SizedBox(height: 6),
              TextField(
                controller: _descriptionController,
                style: const TextStyle(fontSize: 13),
                maxLines: 2,
                decoration: InputDecoration(
                  hintText: 'e.g. NVIDIA and semiconductor transcripts, capex and gross margin commentary',
                  hintStyle: const TextStyle(color: EvergreenColors.metadata, fontSize: 12),
                  isDense: true,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  filled: true,
                  fillColor: EvergreenColors.fill,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.border),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.border),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvergreenRadii.control),
                    borderSide: const BorderSide(color: EvergreenColors.primary, width: 1.5),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Retrieval Pipeline Selection
              const Text(
                'Retrieval Pipeline',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: EvergreenColors.ink,
                ),
              ),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                decoration: BoxDecoration(
                  color: EvergreenColors.fill,
                  borderRadius: BorderRadius.circular(EvergreenRadii.control),
                  border: Border.all(color: EvergreenColors.border),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: _selectedMode,
                    isExpanded: true,
                    icon: const Icon(Symbols.expand_more, size: 18, color: EvergreenColors.metadata),
                    items: const [
                      DropdownMenuItem(
                        value: 'auto',
                        child: Text(
                          'Auto — Hybrid (RRF k=60) + FlashRank Cross-Encoder',
                          style: TextStyle(fontSize: 13),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'agentic',
                        child: Text(
                          'Agentic — Multi-hop CRAG with query decomposition',
                          style: TextStyle(fontSize: 13),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'graph',
                        child: Text(
                          'Graph — Hybrid RAG + Neo4j entity traversal',
                          style: TextStyle(fontSize: 13),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'direct',
                        child: Text(
                          'Direct — Fast dense cosine search only',
                          style: TextStyle(fontSize: 13),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                    onChanged: (val) {
                      if (val != null) setState(() => _selectedMode = val);
                    },
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // LLM Model Selection
              const Text(
                'LLM Model',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: EvergreenColors.ink,
                ),
              ),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                decoration: BoxDecoration(
                  color: EvergreenColors.fill,
                  borderRadius: BorderRadius.circular(EvergreenRadii.control),
                  border: Border.all(color: EvergreenColors.border),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: _selectedModel,
                    isExpanded: true,
                    icon: const Icon(Symbols.expand_more, size: 18, color: EvergreenColors.metadata),
                    items: const [
                      DropdownMenuItem(
                        value: 'llama3.2:3b',
                        child: Text(
                          'llama3.2:3b (Local fast, low VRAM footprint)',
                          style: TextStyle(fontSize: 13),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'llama3.1:latest',
                        child: Text(
                          'llama3.1:latest (8B parameters, production standard)',
                          style: TextStyle(fontSize: 13),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'qwen2.5:7b',
                        child: Text(
                          'qwen2.5:7b (High quality reasoning & synthesis)',
                          style: TextStyle(fontSize: 13),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                    onChanged: (val) {
                      if (val != null) setState(() => _selectedModel = val);
                    },
                  ),
                ),
              ),
              const SizedBox(height: 24),

              // Action Buttons
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  OutlinedButton(
                    onPressed: _isSubmitting ? null : () => Navigator.of(context).pop(),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: EvergreenColors.inkSecondary,
                      side: const BorderSide(color: EvergreenColors.border),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(EvergreenRadii.control),
                      ),
                    ),
                    child: const Text('Cancel'),
                  ),
                  const SizedBox(width: 12),
                  FilledButton(
                    onPressed: _isSubmitting ? null : _submit,
                    style: FilledButton.styleFrom(
                      backgroundColor: EvergreenColors.primary,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(EvergreenRadii.control),
                      ),
                    ),
                    child: _isSubmitting
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Symbols.add, size: 16),
                              SizedBox(width: 6),
                              Text('Create project', style: TextStyle(fontWeight: FontWeight.w600)),
                            ],
                          ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
