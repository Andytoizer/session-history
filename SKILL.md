---
name: session-history
description: Index, summarize, browse, search, and open local Claude Code and Codex JSONL conversation transcripts by project. Use when the user asks for session history, conversation history, transcript lookup, prior Claude/Codex work, a project conversation menu, or a slash-command style way to find past sessions across Claude Code and Codex.
---

# Session History

## Overview

Use this skill to turn local Claude Code and Codex JSONL transcripts into a shared, browsable project history under `~/.session-history`.

Do not treat the transcript `cwd` as the project identity. Claude Code and Codex sessions often live in broad launch folders such as `Documents`, `Projects`, or `New project`; the script infers the real workstream from transcript titles, real user prompts, explicit `project name:` markers, session-relay mentions, and meaningful file paths.

Prefer specific workstream labels over broad channel labels. For example, split newsletter and LinkedIn work into lanes such as `Newsletter Draft / Copy`, `Newsletter Graphics`, `Newsletter Subscriber Analysis`, `LinkedIn Post Review`, `LinkedIn Post Design`, `LinkedIn Profile Research`, and `LinkedIn DMs`. Split broad CRM/outbound labels into concrete threads such as `CRM Dedupe Dry Runs`, `CRM Dedupe Plugin Development`, `HubSpot Dedup Automations`, `Outbound Campaign Research`, `Audience Scoring`, and `Paid Ads Agencies Outbound`.

Treat broad reference material, team memory, or a company brain as context, not as the project identity. Only place a session in that memory system's build or maintenance workstream when the transcript is actually about creating, updating, publishing, or maintaining the memory system itself; otherwise infer the real task from the prompt, title, and meaningful file paths.

The bundled script discovers:

- Codex transcripts in `~/.codex/sessions/**/*.jsonl` and `~/.codex/archived_sessions/*.jsonl`
- Claude Code transcripts in `~/.claude/projects/**/*.jsonl`

It writes a generated library with:

- `session-history.md`: a semantic project/workstream menu ordered by most recent edited conversation
- `projects/<project-slug>/README.md`: one project's conversation list
- `projects/<project-slug>/threads/<thread-slug>/README.md`: one specific artifact/thread inside a workstream
- `artifacts/<thread-slug>/README.md`: a cross-workstream artifact hub that can collect draft, graphics, social, and support sessions for the same newsletter or deliverable
- an `Important Output Files` table on project and thread pages for meaningful generated artifacts such as decks, PDFs, reports, CSV exports, graphics, campaign docs, briefs, and HTML outputs
- `projects/<project-slug>/sessions/*.md`: one Markdown summary per session
- `projects/<project-slug>/transcripts/*.jsonl`: copied raw transcripts
- `index.json`: machine-readable index for search and future tooling

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

For one project, pass a project slug, row number, or a case-insensitive substring of the project name/path:

```bash
python3 scripts/session_history.py project "my app"
python3 scripts/session_history.py project 3
```

For a thread/subfolder inside a project, pass the project row/slug plus the thread row. Use thread row `0` to go back to the parent project view:

```bash
python3 scripts/session_history.py thread 3 2
```

For search across titles, summaries, user prompts, assistant output, project names, and file paths:

```bash
python3 scripts/session_history.py find "deployment fix"
```

To open a generated project README in the local default app on macOS:

```bash
python3 scripts/session_history.py open "my app"
```

## Slash Command Behavior

The matching `/session-history` command should:

1. Run `session_history.py menu` when no arguments are provided.
2. Run `session_history.py project "$ARGUMENTS"` when arguments look like a project name, slug, or menu row number.
3. Run `session_history.py thread "<project row/slug> <thread row>"` when the first argument is `thread`.
4. Run `session_history.py find "<query>"` when the first argument is `find` or `search`.
5. Run `session_history.py open "<project>"` when the first argument is `open`.
6. Print the relevant generated Markdown summary and tell the user where the underlying generated file lives.

If a query is ambiguous, show the top matches and ask the user to rerun with a more specific project name.

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

- Always present menu, project, ambiguous match, and search results as Markdown tables, not bulleted lists.
- Always include a `#` column so the user can navigate by row number instead of typing project or thread names.
- In any multi-table view, row numbers must continue across tables and must not restart at `1`. For example, if the thread/subfolder table has rows `0` and `1`, the first important output file should be row `2`, and the first conversation should continue after the final output-file row.
- For menu results, table columns should include row number, project, last conversation date, session count, and slug or open command.
- For project results, first show a numbered thread/subfolder table. Include row `0` as `Back to Project Menu`. Then show a separate `Important Output Files` table for meaningful created files associated with the project. Then show a numbered conversations table with date, source, conversation title, generated summary, and session file.
- For thread/subfolder results, include row `0` as `Back to <parent project>` and include its own `Important Output Files` table before conversations.
- For search results, table columns should include row number, date, project, source, conversation title, generated summary, and session file.
- Always mention that the raw JSONL transcript copy is linked from each generated session page.

The `Important Output Files` table must be selective. Do not list every file path seen in a transcript. Include only high-signal deliverables and useful artifacts, such as decks, PDFs, reports, CSV/XLSX exports, graphics/images, newsletter or campaign artifacts, briefs, guides, generated HTML, and similar outputs. Each row must include both a clickable file link and the full file path in its own `Path` column. Exclude raw JSONL transcripts, session-history generated copies, dependency folders, caches, lockfiles, source files, and routine project internals unless they are clearly the artifact the session produced.

The script's summaries are deterministic extracts, not deep LLM summaries. If the user wants richer summaries, read the generated session Markdown and raw transcript for the specific sessions they select, then produce a deeper synthesis.
