# CLAUDE.md

## Project

This repository packages the `session-history` skill and CLI. The tool scans local Claude Code and Codex JSONL transcripts, infers project/thread groupings, and writes a browsable Markdown library.

## Guardrails

- Do not commit generated transcript libraries, raw user transcripts, or `~/.session-history` output.
- Keep the public package free of personal paths, customer names, private project taxonomies, API keys, and secrets.
- Prefer portable defaults and configurable roots over hard-coded user-specific paths.
- The script should remain standard-library only unless there is a strong reason to add dependencies.

## Useful Commands

```bash
python3 scripts/session_history.py menu
python3 scripts/session_history.py find "search terms"
python3 -m py_compile scripts/session_history.py
```

For test fixtures, use `--codex-root`, `--claude-root`, and `--output` against temporary directories so real transcripts are not copied into the repository.
