"""Grounded-generation prompt assembly shared by every chat path (direct, graph, agentic).

Order matters for small local models (the 3B/8B targets of this project): they weight the most
recent text most heavily. So the conversation history goes *first* (only to resolve references like
"he" or "that"), the retrieved evidence next, and the current question last together with the
instruction to answer only it. When history sat between the evidence and the question, llama3.2:3b
re-answered the previous turn instead of the current one (REC-75).
"""

from __future__ import annotations

HISTORY_LABEL = "Earlier conversation (only for resolving references like 'he' or 'that'; do not answer it again)"


def build_grounded_prompt(
    question: str,
    evidence: str,
    *,
    history: str = "",
    system_prompt: str | None = None,
    evidence_label: str = "Retrieved document excerpts",
    task_instructions: str = "",
) -> str:
    """Assembles system -> history -> evidence -> current question -> answer instruction."""
    parts: list[str] = []
    if system_prompt:
        parts.append(f"System Persona & Directives:\n{system_prompt}")
    if history:
        parts.append(f"{HISTORY_LABEL}:\n{history}")
    parts.append(f"{evidence_label}:\n{evidence}")
    if task_instructions:
        parts.append(task_instructions)
    parts.append(
        f"Current question: {question}\n"
        "Answer ONLY the current question, using the excerpts above. Use what they say even when it "
        "is indirect or partial (commentary about a person counts). Only if nothing in the excerpts "
        "relates to the question, say so plainly.\n"
        "Answer:"
    )
    return "\n\n".join(parts)
