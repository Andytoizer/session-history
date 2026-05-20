---
name: session-history
description: Index, summarize, browse, search, and open local Claude Code and Codex JSONL conversation transcripts by project.
---

# Session History

## Overview

Use this skill to turn local Claude Code and Codex JSONL transcripts into a shared, browsable project history under `~/.session-history`.

The bundled script discovers:

- Codex transcripts in `~/.codex/sessions/**/*.jsonl` and `~/.codex/archived_sessions/*.jsonl`
- Claude Code transcripts in `~/.claude/projects/**/*.jsonl`

It writes:

- `session-history.md`: a project/workstream menu ordered by most recent conversation
- `projects/<project-slug>/README.md`: one project's conversation list
- `projects/<project-slug>/threads/<thread-slug>/README.md`: one thread inside a project
- `artifacts/<thread-slug>/README.md`: a cross-project artifact hub
- `projects/<project-slug>/sessions/*.md`: one Markdown summary per session
- `projects/<project-slug>/transcripts/*.jsonl`: copied raw transcripts
- `index.json`: machine-readable index

## Quick Start

Run the indexer with Python:

```bash
python3 scripts/session_history.py menu
```

Then summarize the printed menu for the user. Include the generated `~/.session-history/session-history.md` path as a clickable file link when responding from Codex Desktop.

## Common Tasks

For a top-level project menu:

```bash
python3 scripts/session_history.py menu
```

For one project, pass a project slug, row number, or case-insensitive project substring:

```bash
python3 scripts/session_history.py project "my app"
python3 scripts/session_history.py project 3
```

For a thread inside a project:

```bash
python3 scripts/session_history.py thread 3 2
```

For search across titles, summaries, prompts, assistant output, project names, and file paths:

```bash
python3 scripts/session_history.py find "deployment fix"
```

To open a generated project README in the local default app on macOS:

```bash
python3 scripts/session_history.py open "my app"
```

## Custom Roots

Use custom source and output folders for testing or nonstandard installs:

```bash
python3 scripts/session_history.py menu \
  --codex-root ~/.codex \
  --claude-root ~/.claude \
  --output ~/.session-history
```

## Output Style

Keep responses compact:

- Present menu, project, ambiguous match, and search results as Markdown tables.
- Always include a `#` column so the user can navigate by row number.
- In multi-table views, row numbers should continue across tables.
- Mention that the raw JSONL transcript copy is linked from each generated session page.

The script's summaries are deterministic extracts, not deep LLM summaries. If the user wants richer summaries, read the generated session Markdown and raw transcript for the selected sessions, then produce a deeper synthesis.
