Built by [Andy Toizer](https://www.linkedin.com/in/andy-toizer/) — I'm the head of growth at [Freckle.io](https://freckle.io/) and write [AgentOperator](https://agentoperator.substack.com/), a newsletter about what it actually looks like to build real systems with coding agents as a non-engineer.

# Session History

Session History indexes local Claude Code and Codex JSONL transcripts into a browsable Markdown library. It groups conversations into inferred projects and threads, copies the raw transcripts next to generated session summaries, and provides a small CLI for browsing, searching, and opening prior work.

## What It Builds

- `session-history.md`: top-level project menu
- `projects/<project-slug>/README.md`: project-level conversation lists
- `projects/<project-slug>/threads/<thread-slug>/README.md`: thread-level conversation lists
- `artifacts/<thread-slug>/README.md`: cross-project artifact hubs
- `projects/<project-slug>/sessions/*.md`: deterministic session summaries
- `projects/<project-slug>/transcripts/*.jsonl`: raw transcript copies
- `index.json`: machine-readable index

## Install

Clone or copy this repository, then run the script directly with Python 3. It uses only the Python standard library.

```bash
python3 scripts/session_history.py menu
```

By default it reads:

- `~/.codex/sessions/**/*.jsonl`
- `~/.codex/archived_sessions/*.jsonl`
- `~/.claude/projects/**/*.jsonl`

And writes to:

- `~/.session-history`

## CLI

```bash
python3 scripts/session_history.py menu
python3 scripts/session_history.py build
python3 scripts/session_history.py project "project name or row"
python3 scripts/session_history.py thread "project row or slug" "thread row or slug"
python3 scripts/session_history.py find "search terms"
python3 scripts/session_history.py open "project name or row"
```

Use custom roots when testing or when your transcript folders live somewhere else:

```bash
python3 scripts/session_history.py menu \
  --codex-root /path/to/codex \
  --claude-root /path/to/claude \
  --output /path/to/session-history
```

## Codex Skill

This repo includes a Codex-compatible `SKILL.md`. To install it as a local skill, copy the repository folder into your Codex skills directory.

The optional `agents/openai.yaml` file provides display metadata for environments that read agent descriptors.

## Privacy Notes

This tool is local-first, but generated output can contain sensitive content because it copies raw transcript JSONL files and extracts prompts, assistant messages, file paths, and tool names. Review generated output before sharing it.

The public package intentionally ships without private project overrides, private customer names, personal workstream taxonomy, or secrets.

## Requirements

- Python 3.10 or newer
- macOS, Linux, or another Unix-like environment for the default path conventions

No third-party Python dependencies are required.
