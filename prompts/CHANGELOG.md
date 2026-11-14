# Prompt changelog (one line per version)
- 2026-11-12 · 00_master_prompt v1 · initial master prompt from Iman (verbatim)
- 2026-11-12 · .claude/agents/{analyst,critic,tool-builder}.md v1 · agent definitions written in Phase 0 from the master prompt
- 2026-11-12 · tool-builder.md v1.1 · added: UI/UX is iterative and kept separate from logic (Iman request)
- 2026-11-13 · .claude/agents/{analyst,critic,tool-builder}.md v2 · reviewer feedback: each agent now defines when it runs, inputs, steps, outputs (files + report format), do/don't, and handoffs; tested ranges read from metrics.json instead of a hard-coded $7-$15; consistent with how the roles were actually run
- 2026-11-13 · CLAUDE.md v1 (+ AGENTS.md pointer) · repository-level instructions: overview, shared rules, where context lives, the main session's orchestration role
