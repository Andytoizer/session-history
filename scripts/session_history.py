#!/usr/bin/env python3
"""Build and browse a local Claude Code + Codex session history library."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


HOME = Path.home()
DEFAULT_OUTPUT = HOME / ".session-history"
CODEX_ROOT = HOME / ".codex"
CLAUDE_ROOT = HOME / ".claude"
SCRIPT_PATH = Path(__file__).resolve()

MAX_TEXT = 700
MAX_FINAL_OUTPUT = 1800
GENERIC_WORKSPACE_NAMES = {
    "Code",
    "Config",
    "Desktop",
    "Documents",
    "Downloads",
    "New",
    "New project",
    "Projects",
    "Workspace",
}
OUTPUT_TABLE_LIMIT = 10
HIGH_SIGNAL_OUTPUT_EXTENSIONS = {
    ".csv",
    ".docx",
    ".gif",
    ".html",
    ".jpeg",
    ".jpg",
    ".json",
    ".md",
    ".pdf",
    ".png",
    ".pptx",
    ".tsv",
    ".webp",
    ".xlsx",
}
ALWAYS_OUTPUT_EXTENSIONS = {
    ".csv",
    ".docx",
    ".gif",
    ".html",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pptx",
    ".tsv",
    ".webp",
    ".xlsx",
}
OUTPUT_PATH_KEYWORDS = (
    "/artifacts/",
    "/brandkit/",
    "/branding/",
    "/campaigns/",
    "/deliverables/",
    "/decks/",
    "/exports/",
    "/graphics/",
    "/images/",
    "/outputs/",
    "/presentations/",
    "/reports/",
    "/release/",
    "/screenshots/",
)
OUTPUT_NAME_KEYWORDS = (
    "battlecard",
    "brief",
    "campaign",
    "deck",
    "draft",
    "export",
    "guide",
    "handoff",
    "image",
    "newsletter",
    "one-pager",
    "playbook",
    "prompt",
    "report",
    "summary",
    "webinar",
)
OUTPUT_EXCLUDE_KEYWORDS = (
    "/.codex/",
    "/.claude/",
    "/.git/",
    "/.next/",
    "/.session-history/",
    "/__pycache__/",
    "/node_modules/",
    "/html/assets/",
    "/qa/",
    "/sessions/",
    "/tool-results/",
    "/transcripts/",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
)
STOPWORDS = {
    "a",
    "about",
    "add",
    "and",
    "are",
    "build",
    "can",
    "check",
    "code",
    "compare",
    "create",
    "draft",
    "find",
    "fix",
    "for",
    "from",
    "help",
    "how",
    "i",
    "in",
    "install",
    "into",
    "locate",
    "make",
    "me",
    "my",
    "new",
    "of",
    "on",
    "open",
    "prepare",
    "project",
    "review",
    "rewrite",
    "run",
    "set",
    "show",
    "the",
    "this",
    "to",
    "update",
    "use",
    "what",
    "where",
    "with",
    "write",
}

# Optional manual per-session project overrides. Keyed by full session id (the
# UUID from the JSONL transcript, not the short id used in filenames). Keep this
# empty by default for a portable public package.
SESSION_OVERRIDES: dict[str, str] = {}


KEYWORD_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("CRM / Data Hygiene", ("crm", "dedupe", "deduplication", "duplicate contact", "duplicate company", "data hygiene")),
    ("Data Analysis", ("analysis", "analytics", "csv", "spreadsheet", "data export", "report")),
    ("Design / Graphics", ("design", "graphic", "branding", "image", "screenshot", "figma", "canva")),
    ("Documentation", ("documentation", "docs", "readme", "guide", "manual", "how-to")),
    ("GitHub / CI", ("github", "pull request", "pr review", "ci", "github actions")),
    ("Newsletter / Content", ("newsletter", "draft", "copy", "editorial", "article", "blog post")),
    ("LinkedIn / Social", ("linkedin", "social post", "carousel", "profile")),
    ("Outbound / Sales", ("outbound", "prospecting", "sales", "campaign", "lead list", "audience")),
    ("Presentations", ("presentation", "slide deck", "pptx", "deck slides", "convert html to pptx")),
    ("Plugins / Skills", ("claude plugin", "codex plugin", "skill", "plugin conversion", "plugin compatibility")),
    ("Session History Tool", ("session history", "conversation history", "jsonl transcript")),
    ("Session Relay", ("session-relay", "session relay")),
    ("Slack Messages", ("slack follow-up", "slack repo update", "slack send schedule", "scheduled slack", "slack message", "delete all scheduled slack", "follow-up message")),
    ("Notion Docs", ("notion",)),
    ("MCP vs CLI Article", ("mcp vs cli",)),
    ("Vector Ingest", ("vector ingest",)),
    ("Web App Development", ("next.js", "react", "frontend", "web app", "localhost", "vercel")),
]


@dataclass
class Session:
    source: str
    source_path: Path
    session_id: str
    project_path: str
    project_name: str
    project_slug: str
    thread_name: str
    thread_slug: str
    title: str
    started_at: str
    updated_at: str
    user_prompts: list[str] = field(default_factory=list)
    assistant_outputs: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    session_md: str = ""
    transcript_copy: str = ""


@dataclass
class OutputFile:
    path: str
    kind: str
    latest_at: str
    session_count: int
    session_title: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Index and browse Claude Code/Codex session history.")
    parser.add_argument(
        "command",
        nargs="?",
        default="menu",
        help="menu, build, project, thread, find/search, open, or a project query",
    )
    parser.add_argument("query", nargs="*", help="Project or search query.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Generated library directory.")
    parser.add_argument("--codex-root", default=str(CODEX_ROOT), help="Codex config directory containing sessions.")
    parser.add_argument("--claude-root", default=str(CLAUDE_ROOT), help="Claude config directory containing projects.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum rows to print.")
    parser.add_argument("--no-clean", action="store_true", help="Do not delete generated project files first.")
    args = parser.parse_args()

    command = args.command.lower()
    query = " ".join(args.query).strip()

    if command in {"search"}:
        command = "find"

    if command not in {"menu", "build", "project", "thread", "find", "open"}:
        query = " ".join([args.command, *args.query]).strip()
        command = "project"

    output = Path(args.output).expanduser()
    sessions = build_library(
        output,
        clean=not args.no_clean,
        codex_root=Path(args.codex_root).expanduser(),
        claude_root=Path(args.claude_root).expanduser(),
    )

    if command == "build":
        print(f"Built {len(sessions)} sessions in {output}")
        print(output / "session-history.md")
        return 0
    if command == "menu":
        print_menu(output, sessions, limit=args.limit)
        return 0
    if command == "project":
        print_project(output, sessions, query=query, limit=args.limit)
        return 0
    if command == "thread":
        print_thread(output, sessions, query=query, limit=args.limit)
        return 0
    if command == "find":
        if not query:
            print("Provide a search query, for example: session_history.py find hubspot dedupe", file=sys.stderr)
            return 2
        print_search(output, sessions, query=query, limit=args.limit)
        return 0
    if command == "open":
        if not query:
            print("Provide a project name or slug to open.", file=sys.stderr)
            return 2
        return open_project(output, sessions, query=query)
    return 0


def build_library(
    output: Path,
    clean: bool = True,
    codex_root: Path = CODEX_ROOT,
    claude_root: Path = CLAUDE_ROOT,
) -> list[Session]:
    output.mkdir(parents=True, exist_ok=True)
    with build_lock(output):
        projects_dir = output / "projects"
        if clean and projects_dir.exists():
            shutil.rmtree(projects_dir, ignore_errors=True)
        projects_dir.mkdir(parents=True, exist_ok=True)

        codex_titles = load_codex_titles(codex_root)
        sessions: list[Session] = []

        for path in discover_codex_jsonl(codex_root):
            session = parse_codex_session(path, codex_titles)
            if session:
                sessions.append(session)

        for path in discover_claude_jsonl(claude_root):
            session = parse_claude_session(path)
            if session:
                sessions.append(session)

        sessions.sort(key=lambda item: item.updated_at or item.started_at, reverse=True)

        for session in sessions:
            write_session(output, session)

        write_index(output, sessions)
        write_menu(output, sessions)
        write_artifact_hubs(output, sessions)
        return sessions


@contextmanager
def build_lock(output: Path):
    lock_path = output / ".build.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        try:
            import fcntl

            fcntl.flock(lock_file, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        try:
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(lock_file, fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass


def discover_codex_jsonl(codex_root: Path = CODEX_ROOT) -> Iterable[Path]:
    roots = [codex_root / "sessions", codex_root / "archived_sessions"]
    for root in roots:
        if root.exists():
            yield from sorted(root.rglob("*.jsonl"))


def discover_claude_jsonl(claude_root: Path = CLAUDE_ROOT) -> Iterable[Path]:
    root = claude_root / "projects"
    if root.exists():
        yield from sorted(root.rglob("*.jsonl"))


def load_codex_titles(codex_root: Path = CODEX_ROOT) -> dict[str, str]:
    index = codex_root / "session_index.jsonl"
    titles: dict[str, str] = {}
    if not index.exists():
        return titles
    for obj in read_jsonl(index):
        session_id = str(obj.get("id") or "")
        title = clean_inline(str(obj.get("thread_name") or ""))
        if session_id and title:
            titles[session_id] = title
    return titles


def parse_codex_session(path: Path, title_index: dict[str, str]) -> Session | None:
    records = list(read_jsonl(path))
    if not records:
        return None

    session_id = ""
    project_path = ""
    timestamps: list[str] = []
    user_prompts: list[str] = []
    assistant_outputs: list[str] = []
    tool_names: list[str] = []
    file_paths: list[str] = []

    for obj in records:
        timestamp = obj.get("timestamp")
        if isinstance(timestamp, str):
            timestamps.append(timestamp)

        obj_type = obj.get("type")
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}

        if obj_type == "session_meta":
            meta = payload
            session_id = session_id or str(meta.get("id") or "")
            project_path = project_path or str(meta.get("cwd") or "")
            meta_ts = meta.get("timestamp")
            if isinstance(meta_ts, str):
                timestamps.append(meta_ts)

        if obj_type == "response_item":
            role = payload.get("role")
            ptype = payload.get("type")
            content = payload.get("content")
            if role == "user":
                user_prompts.extend(extract_content_text(content, wanted={"input_text", "text"}))
            elif role == "assistant":
                assistant_outputs.extend(extract_content_text(content, wanted={"output_text", "text"}))
            if ptype in {"function_call", "tool_search_call"}:
                name = str(payload.get("name") or ptype)
                tool_names.append(name)
                file_paths.extend(extract_paths(json.dumps(payload, ensure_ascii=False)))

        if obj_type == "event_msg":
            ptype = payload.get("type")
            if ptype == "user_message":
                msg = payload.get("message")
                if isinstance(msg, str):
                    user_prompts.append(msg)
            elif ptype == "agent_message":
                msg = payload.get("message")
                if isinstance(msg, str):
                    assistant_outputs.append(msg)

    session_id = session_id or path.stem
    project_path = project_path or "Unknown Codex Project"
    user_prompts = clean_prompt_list(user_prompts)
    assistant_outputs = clean_prompt_list(assistant_outputs)
    tool_names = unique(tool_names)
    file_paths = unique(file_paths + extract_paths("\n".join(user_prompts + assistant_outputs)))

    title = title_index.get(session_id) or title_from_prompts(user_prompts) or path.stem
    project_name, project_key = infer_project_identity(
        workspace_path=project_path,
        title=title,
        user_prompts=user_prompts,
        assistant_outputs=assistant_outputs,
        file_paths=file_paths,
    )
    override = SESSION_OVERRIDES.get(session_id)
    if override:
        project_name, project_key = override, f"override:{override}"
    project_slug = make_project_slug(project_name, project_name.lower())
    thread_name = infer_thread_identity(project_name, title, user_prompts, assistant_outputs, file_paths)
    thread_slug = make_slug(thread_name)
    started_at = normalize_time(min(timestamps) if timestamps else mtime_iso(path))
    updated_at = normalize_time(max(timestamps) if timestamps else mtime_iso(path))

    return Session(
        source="codex",
        source_path=path,
        session_id=session_id,
        project_path=project_path,
        project_name=project_name,
        project_slug=project_slug,
        thread_name=thread_name,
        thread_slug=thread_slug,
        title=title,
        started_at=started_at,
        updated_at=updated_at,
        user_prompts=user_prompts,
        assistant_outputs=assistant_outputs,
        tool_names=tool_names,
        file_paths=file_paths,
    )


def parse_claude_session(path: Path) -> Session | None:
    records = list(read_jsonl(path))
    if not records:
        return None

    session_id = ""
    project_path = ""
    title = ""
    timestamps: list[str] = []
    user_prompts: list[str] = []
    assistant_outputs: list[str] = []
    tool_names: list[str] = []
    file_paths: list[str] = []

    for obj in records:
        timestamp = obj.get("timestamp")
        if isinstance(timestamp, str):
            timestamps.append(timestamp)

        session_id = session_id or str(obj.get("sessionId") or "")
        project_path = project_path or str(obj.get("cwd") or "")
        if obj.get("type") == "ai-title":
            title = clean_inline(str(obj.get("aiTitle") or ""))

        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        role = message.get("role")
        content = message.get("content")
        if role == "user":
            user_prompts.extend(extract_claude_text(content, include_tool_results=False))
        elif role == "assistant":
            assistant_outputs.extend(extract_claude_text(content, include_tool_results=False))
            tool_names.extend(extract_claude_tools(content))
            file_paths.extend(extract_paths(json.dumps(content, ensure_ascii=False)))

    session_id = session_id or path.stem
    project_path = project_path or decode_claude_project_path(path.parent.name)
    user_prompts = clean_prompt_list(user_prompts)
    assistant_outputs = clean_prompt_list(assistant_outputs)
    tool_names = unique(tool_names)
    file_paths = unique(file_paths + extract_paths("\n".join(user_prompts + assistant_outputs)))
    title = title or title_from_prompts(user_prompts) or path.stem
    project_name, project_key = infer_project_identity(
        workspace_path=project_path,
        title=title,
        user_prompts=user_prompts,
        assistant_outputs=assistant_outputs,
        file_paths=file_paths,
    )
    override = SESSION_OVERRIDES.get(session_id)
    if override:
        project_name, project_key = override, f"override:{override}"
    project_slug = make_project_slug(project_name, project_name.lower())
    thread_name = infer_thread_identity(project_name, title, user_prompts, assistant_outputs, file_paths)
    thread_slug = make_slug(thread_name)
    started_at = normalize_time(min(timestamps) if timestamps else mtime_iso(path))
    updated_at = normalize_time(max(timestamps) if timestamps else mtime_iso(path))

    return Session(
        source="claude",
        source_path=path,
        session_id=session_id,
        project_path=project_path,
        project_name=project_name,
        project_slug=project_slug,
        thread_name=thread_name,
        thread_slug=thread_slug,
        title=title,
        started_at=started_at,
        updated_at=updated_at,
        user_prompts=user_prompts,
        assistant_outputs=assistant_outputs,
        tool_names=tool_names,
        file_paths=file_paths,
    )


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except OSError:
        return


def extract_content_text(content: Any, wanted: set[str]) -> list[str]:
    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type in wanted and isinstance(item.get("text"), str):
                    texts.append(item["text"])
    return texts


def extract_claude_text(content: Any, include_tool_results: bool) -> list[str]:
    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "text" and isinstance(item.get("text"), str):
                    texts.append(item["text"])
                elif include_tool_results and item_type == "tool_result":
                    texts.extend(extract_claude_text(item.get("content"), include_tool_results=True))
    return texts


def extract_claude_tools(content: Any) -> list[str]:
    names: list[str] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                name = item.get("name")
                if isinstance(name, str):
                    names.append(name)
    return names


def clean_prompt_list(texts: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for text in texts:
        text = clean_text(text)
        if not text or is_noise_text(text):
            continue
        key = text[:500]
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def clean_text(text: str) -> str:
    text = re.sub(r"<local-command-caveat>.*?</local-command-caveat>", "", text, flags=re.S)
    text = re.sub(r"<permissions instructions>.*?</permissions instructions>", "", text, flags=re.S)
    text = re.sub(r"<app-context>.*?</app-context>", "", text, flags=re.S)
    text = re.sub(r"<skills_instructions>.*?</skills_instructions>", "", text, flags=re.S)
    text = re.sub(r"<plugins_instructions>.*?</plugins_instructions>", "", text, flags=re.S)
    text = re.sub(r"<environment_context>\s*", "", text)
    text = re.sub(r"\s*</environment_context>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_noise_text(text: str) -> bool:
    if not text:
        return True
    noise_markers = [
        "<local-command-stdout>",
        "<command-name>",
        "<command-message>",
        "<command-args>",
        "<cwd>",
        "<shell>",
        "<current_date>",
        "<timezone>",
        "Filesystem sandboxing defines",
        "You are Codex, a coding agent",
        "# Collaboration Mode:",
        "# AGENTS.md instructions",
        "<INSTRUCTIONS>",
        "## Skills A skill",
    ]
    if any(marker in text for marker in noise_markers):
        return True
    return len(text) > 30000


def title_from_prompts(prompts: list[str]) -> str:
    for prompt in prompts:
        first_line = clean_inline(prompt.splitlines()[0] if prompt.splitlines() else prompt)
        first_line = re.sub(r"^(please|can you|could you|help me)\s+", "", first_line, flags=re.I)
        if first_line:
            return first_line[:90]
    return ""


def project_name_from_path(project_path: str) -> str:
    project_path = project_path.rstrip("/")
    if not project_path:
        return "Unknown Project"
    name = Path(project_path).name
    return name or project_path


def infer_project_identity(
    workspace_path: str,
    title: str,
    user_prompts: list[str],
    assistant_outputs: list[str],
    file_paths: list[str],
) -> tuple[str, str]:
    """Infer the real workstream, not just the shell cwd."""
    workspace_name = project_name_from_path(workspace_path)
    evidence = "\n".join(
        [
            title,
            "\n".join(user_prompts[:8]),
            "\n".join(assistant_outputs[-4:]),
            "\n".join(file_paths[:80]),
            workspace_path,
        ]
    )
    intent_evidence = "\n".join([title, "\n".join(user_prompts[:8])])

    explicit = explicit_project_name(intent_evidence)
    if explicit:
        return explicit, f"explicit:{explicit}"

    keyword_candidate = project_from_keywords(title) or project_from_keywords(intent_evidence)
    if keyword_candidate:
        return keyword_candidate, f"keyword:{keyword_candidate}"

    path_candidate = project_from_paths(file_paths + [workspace_path])
    if path_candidate:
        return path_candidate, f"path:{path_candidate}"

    if workspace_name not in GENERIC_WORKSPACE_NAMES:
        return workspace_name, f"workspace:{workspace_path}"

    topic = project_from_title(title) or "Miscellaneous Sessions"
    return topic, f"topic:{topic}"


def explicit_project_name(text: str) -> str:
    patterns = [
        r"project\s+name\s*[:=-]\s*([A-Za-z0-9][A-Za-z0-9 _./&+'-]{1,80})",
        r"project\s+called\s+([A-Za-z0-9][A-Za-z0-9 _./&+'-]{1,80})",
        r"using\s+/session-relay\s*\(\s*project\s+name\s*:\s*([^)]+)\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            value = match.group(1)
            value = re.split(r"[\n\r).,;]", value, maxsplit=1)[0]
            value = clean_project_label(value)
            if value:
                return value
    return ""


def project_from_paths(paths: list[str]) -> str:
    candidates: list[str] = []
    for raw_path in paths:
        path = clean_pathish(raw_path)
        if not path:
            continue

        candidates.extend(project_candidates_from_path(path))

    counts: dict[str, int] = {}
    for candidate in candidates:
        label = clean_project_label(candidate)
        label = normalize_project_label(label)
        if not label or label in GENERIC_WORKSPACE_NAMES:
            continue
        if looks_like_artifact_label(label):
            continue
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (item[1], len(item[0])), reverse=True)[0][0]


def project_candidates_from_path(path: str) -> list[str]:
    try:
        parsed = Path(path).expanduser()
    except (OSError, ValueError):
        return []
    if not parsed.is_absolute():
        return []

    parts = [part for part in parsed.parts if part and part not in {"/", ".", ".."}]
    if not parts:
        return []

    # Drop platform/user prefixes and common container folders so that
    # /Users/name/Documents/my-app/... resolves to my-app.
    if len(parts) >= 2 and parts[0] in {"Users", "home"}:
        parts = parts[2:]
    while parts and (parts[0] in GENERIC_WORKSPACE_NAMES or parts[0].startswith(".")):
        parts = parts[1:]

    if not parts:
        return []

    if len(parts) >= 2 and parts[0].lower() in {
        "artifacts",
        "branding",
        "campaigns",
        "deliverables",
        "decks",
        "exports",
        "outputs",
        "presentations",
        "reports",
    }:
        return [parts[1]]

    first = parts[0]
    if looks_like_file_name(first):
        return []
    if first.lower() in {"tmp", "temp", "cache", "sessions", "transcripts"}:
        return []
    return [first]
    return []


def project_from_keywords(text: str) -> str:
    lowered = text.lower()
    for label, needles in KEYWORD_GROUPS:
        if any(needle in lowered for needle in needles):
            return label
    return ""


def project_from_title(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    useful = [word for word in words if word not in STOPWORDS and len(word) > 2]
    if not useful:
        return ""
    label = " ".join(word.capitalize() for word in useful[:4])
    if looks_like_artifact_label(label):
        return ""
    return label


def infer_thread_identity(
    project_name: str,
    title: str,
    user_prompts: list[str],
    assistant_outputs: list[str],
    file_paths: list[str],
) -> str:
    text = "\n".join([title, "\n".join(user_prompts[:6]), "\n".join(file_paths[:40])])

    explicit = explicit_project_name(text)
    if explicit:
        return explicit

    notion_title = notion_slug_label(text)
    if notion_title:
        return normalize_thread_label(notion_title)

    path_thread = thread_from_paths(file_paths)
    if path_thread:
        return path_thread

    if any(needle in project_name.lower() for needle in ("newsletter", "linkedin", "content", "social")):
        title_thread = thread_from_title(title)
        return title_thread or project_name

    return project_name


def notion_slug_label(text: str) -> str:
    match = re.search(r"notion\.so/[^/\s]+/([A-Za-z0-9][A-Za-z0-9-]+)-[a-f0-9]{16,}", text)
    if not match:
        match = re.search(r"notion\.so/([A-Za-z0-9][A-Za-z0-9-]+)-[a-f0-9]{16,}", text)
    if not match:
        return ""
    slug = match.group(1)
    slug = re.sub(r"-v\d+.*$", "", slug, flags=re.I)
    slug = re.sub(r"-notes-addressed.*$", "", slug, flags=re.I)
    return clean_project_label(slug)


def thread_from_paths(paths: list[str]) -> str:
    for raw_path in paths:
        path = clean_pathish(raw_path)
        label = thread_label_from_path(path)
        if label:
            return label
    return ""


def thread_label_from_path(path: str) -> str:
    parts = [part for part in Path(path).parts if part and part not in {"/", ".", ".."}]
    for marker in (
        "artifacts",
        "branding",
        "campaigns",
        "deliverables",
        "decks",
        "exports",
        "graphics",
        "outputs",
        "presentations",
        "reports",
    ):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return clean_project_label(parts[index + 1])
    return ""


def thread_from_title(title: str) -> str:
    text = clean_project_label(title)
    text = re.sub(r"^(Review|Update|Refine|Find|Create|Build|Add|Assess|Locate)\s+", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or looks_like_artifact_label(text):
        return ""
    return text[:80]


def normalize_thread_label(label: str) -> str:
    return label


def clean_pathish(path: str) -> str:
    path = path.strip().strip("`'\"")
    path = re.split(r"[\n\r\t]", path, maxsplit=1)[0]
    path = re.split(r"\s+-{1,2}[A-Za-z0-9]", path, maxsplit=1)[0]
    return path.rstrip(".,);]}'\"")


def clean_project_label(value: str) -> str:
    value = value.strip().strip("`'\"")
    value = re.sub(r"[_-]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" ./")
    if not value:
        return ""
    acronyms = {"crm", "gtm", "cc", "aeo", "b2b", "smb", "pptx", "ai"}
    words = []
    for word in value.split(" "):
        if word.lower() in acronyms:
            words.append(word.upper())
        elif "." in word:
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)


def normalize_project_label(label: str) -> str:
    lowered = label.lower()
    if any(needle in lowered for needle in ("crm dedupe", "crm dedup", "dedupe", "deduplication", "contact review queue", "company review queue")):
        return "CRM / Data Hygiene"
    return label


def looks_like_artifact_label(label: str) -> bool:
    lowered = label.lower()
    if lowered in {item.lower() for item in GENERIC_WORKSPACE_NAMES}:
        return True
    if re.fullmatch(r"[a-f0-9]{6,}( [a-f0-9]{4,}){1,4}", lowered):
        return True
    if any(lowered.endswith(ext) for ext in (".csv", ".json", ".jsonl", ".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".html")):
        return True
    shell_words = {"type", "name", "maxdepth", "include", "depth"}
    return len(set(lowered.split()) & shell_words) >= 2


def looks_like_file_name(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.endswith(ext) for ext in (".csv", ".json", ".jsonl", ".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".html"))


def decode_claude_project_path(folder_name: str) -> str:
    if folder_name.startswith("-"):
        return "/" + folder_name.strip("-").replace("-", "/")
    return folder_name.replace("-", "/")


def make_project_slug(project_name: str, project_path: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-") or "unknown-project"
    digest = hashlib.sha1(project_path.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


def make_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "misc"


def write_session(output: Path, session: Session) -> None:
    project_dir = output / "projects" / session.project_slug
    sessions_dir = project_dir / "sessions"
    transcripts_dir = project_dir / "transcripts"
    thread_dir = project_dir / "threads" / session.thread_slug
    sessions_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    (thread_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (thread_dir / "transcripts").mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r"[^a-z0-9]+", "-", session.title.lower()).strip("-")[:70] or "session"
    date = date_part(session.started_at)
    path_id = hashlib.sha1(str(session.source_path).encode("utf-8")).hexdigest()[:8]
    short_id = f"{session.session_id[:8]}-{path_id}" if session.session_id else path_id
    transcript_name = f"{session.source}-{short_id}.jsonl"
    md_name = f"{date}--{session.source}--{safe_title}--{short_id}.md"

    transcript_copy = transcripts_dir / transcript_name
    try:
        shutil.copy2(session.source_path, transcript_copy)
        shutil.copy2(session.source_path, thread_dir / "transcripts" / transcript_name)
    except OSError:
        pass

    session.transcript_copy = str(transcript_copy)
    session.session_md = str(sessions_dir / md_name)
    rendered = render_session_markdown(session)
    Path(session.session_md).write_text(rendered, encoding="utf-8")
    (thread_dir / "sessions" / md_name).write_text(rendered, encoding="utf-8")


def render_session_markdown(session: Session) -> str:
    prompts = "\n".join(f"- {clip(one_line(item), 240)}" for item in session.user_prompts[:8]) or "- No user prompt text extracted."
    tools = ", ".join(session.tool_names[:20]) if session.tool_names else "No tool calls extracted."
    files = "\n".join(f"- `{path}`" for path in session.file_paths[:25]) or "- No file paths extracted."
    summary = make_summary(session)
    final_output = clip(session.assistant_outputs[-1], MAX_FINAL_OUTPUT) if session.assistant_outputs else "No assistant output extracted."

    return "\n".join(
        [
            f"# {session.title}",
            "",
            f"- Date: {display_time(session.started_at)}",
            f"- Last updated: {display_time(session.updated_at)}",
            f"- Source: {session.source}",
            f"- Inferred project: {session.project_name}",
            f"- Thread: {session.thread_name}",
            f"- Workspace path: `{session.project_path}`",
            f"- Session id: `{session.session_id}`",
            f"- Original transcript: `{session.source_path}`",
            f"- Copied transcript: `{session.transcript_copy}`",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## User Prompts",
            "",
            prompts,
            "",
            "## What Got Done",
            "",
            make_done_list(session),
            "",
            "## Final Output",
            "",
            final_output,
            "",
            "## Tool And File Signal",
            "",
            f"Tools: {tools}",
            "",
            "Files:",
            "",
            files,
            "",
        ]
    )


def make_summary(session: Session) -> str:
    prompt = clip(one_line(session.user_prompts[0]), 280) if session.user_prompts else ""
    final = clip(one_line(session.assistant_outputs[-1]), 360) if session.assistant_outputs else ""
    if prompt and final:
        return f"Started from: {prompt}\n\nEnded with: {final}"
    if prompt:
        return f"Started from: {prompt}"
    if final:
        return f"Ended with: {final}"
    return "No conversational text was extracted from this transcript."


def make_done_list(session: Session) -> str:
    outputs = [one_line(item) for item in session.assistant_outputs[-4:]]
    outputs = [clip(item, 260) for item in outputs if item]
    if outputs:
        return "\n".join(f"- {item}" for item in outputs)
    if session.tool_names:
        return "- Tool activity was detected: " + ", ".join(session.tool_names[:12])
    return "- No completion details extracted."


def collect_project_outputs(project_sessions: list[Session], limit: int = OUTPUT_TABLE_LIMIT) -> list[OutputFile]:
    by_path: dict[str, dict[str, Any]] = {}
    for session in project_sessions:
        for raw_path in session.file_paths:
            path = clean_pathish(raw_path)
            if not is_important_output_path(path):
                continue
            record = by_path.setdefault(
                path,
                {
                    "path": path,
                    "kind": output_kind(path),
                    "latest_at": session.updated_at,
                    "session_ids": set(),
                    "session_title": session.title,
                    "score": output_score(path),
                },
            )
            record["session_ids"].add(session.session_id)
            if session.updated_at > record["latest_at"]:
                record["latest_at"] = session.updated_at
                record["session_title"] = session.title

    outputs = [
        OutputFile(
            path=record["path"],
            kind=record["kind"],
            latest_at=record["latest_at"],
            session_count=len(record["session_ids"]),
            session_title=record["session_title"],
        )
        for record in sorted(by_path.values(), key=lambda item: (item["score"], item["latest_at"]), reverse=True)
    ]
    return outputs[:limit]


def render_output_files_table(
    outputs: list[OutputFile],
    base_dir: Path | None = None,
    start_index: int = 1,
) -> list[str]:
    rows = ["| # | File | Path | Kind | Last Seen | Related Session |", "| --- | --- | --- | --- | --- | --- |"]
    if not outputs:
        rows.append("| - | No high-signal output files detected | - | - | - | - |")
        return rows
    for index, output_file in enumerate(outputs, start=start_index):
        file_cell = output_file_label(output_file.path, base_dir)
        path_cell = f"`{md_cell(output_file.path)}`"
        rows.append(
            f"| {index} | {file_cell} | {path_cell} | {md_cell(output_file.kind)} | "
            f"{md_cell(display_date(output_file.latest_at))} | {md_cell(clip(output_file.session_title, 90))} |"
        )
    return rows


def output_file_label(path: str, base_dir: Path | None = None) -> str:
    label = Path(path).name or path
    if base_dir:
        try:
            target = relpath(path, base_dir)
        except ValueError:
            target = path
        return f"[{md_cell(label)}]({markdown_link_target(target)})"
    return f"[{md_cell(label)}]({markdown_link_target(path)})"


def is_important_output_path(path: str) -> bool:
    try:
        parsed = Path(path).expanduser()
    except (OSError, ValueError):
        return False
    if not parsed.is_absolute():
        return False
    lowered = path.lower()
    if any(needle in lowered for needle in OUTPUT_EXCLUDE_KEYWORDS):
        return False
    suffix = Path(path).suffix.lower()
    if suffix not in HIGH_SIGNAL_OUTPUT_EXTENSIONS:
        return False
    filename = Path(path).name.lower()
    if suffix in ALWAYS_OUTPUT_EXTENSIONS:
        return True
    if "readme.md" == filename and any(needle in lowered for needle in OUTPUT_PATH_KEYWORDS):
        return True
    return any(needle in lowered for needle in OUTPUT_PATH_KEYWORDS) or any(needle in filename for needle in OUTPUT_NAME_KEYWORDS)


def output_score(path: str) -> int:
    lowered = path.lower()
    suffix = Path(path).suffix.lower()
    score = 0
    if suffix in {".pdf", ".pptx", ".docx", ".xlsx"}:
        score += 8
    elif suffix in {".csv", ".tsv", ".html", ".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        score += 6
    elif suffix in {".md", ".json"}:
        score += 3
    score += sum(3 for needle in OUTPUT_PATH_KEYWORDS if needle in lowered)
    score += sum(2 for needle in OUTPUT_NAME_KEYWORDS if needle in lowered)
    if any(needle in lowered for needle in ("final", "clean", "full", "ranked", "signal_scan")):
        score += 6
    if any(needle in lowered for needle in ("draft", "sample", "page1", "page2", "page3", "v2", "v3")):
        score -= 2
    return score


def output_kind(path: str) -> str:
    lowered = path.lower()
    suffix = Path(path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return "Image / graphic"
    if suffix in {".pptx"} or "deck" in lowered or "presentation" in lowered:
        return "Deck / presentation"
    if suffix in {".pdf", ".docx", ".md"}:
        return "Document / brief"
    if suffix in {".csv", ".tsv", ".xlsx"}:
        return "Data export"
    if suffix == ".html":
        return "HTML output"
    if suffix == ".json":
        return "Data artifact"
    return "Output"


def write_project_readmes(output: Path, sessions: list[Session]) -> None:
    for project_slug, project_sessions in group_by_project(sessions).items():
        project_sessions.sort(key=lambda item: item.updated_at, reverse=True)
        first = project_sessions[0]
        project_dir = output / "projects" / project_slug
        write_thread_readmes(project_dir, project_sessions)
        thread_rows = ["| # | Last Conversation | Thread | Sessions |", "| --- | --- | --- | --- |"]
        thread_rows.append(f"| 0 | {md_cell(display_date(first.updated_at))} | [Back to Project Menu](../../session-history.md) | {len(group_by_project(sessions))} projects |")
        for thread_slug, thread_sessions in group_by_thread(project_sessions).items():
            thread_sessions.sort(key=lambda item: item.updated_at, reverse=True)
            thread_first = thread_sessions[0]
            thread_rows.append(
                f"| {len(thread_rows) - 2} | {md_cell(display_date(thread_first.updated_at))} | "
                f"[{md_cell(thread_first.thread_name)}](threads/{thread_slug}/README.md) | "
                f"{len(thread_sessions)} |"
            )
        next_index = len(thread_rows) - 2
        output_files = collect_project_outputs(project_sessions)
        output_rows = render_output_files_table(output_files, project_dir, start_index=next_index)
        next_index += len(output_files)
        rows = ["| # | Date | Source | Conversation | Summary | Session File |", "| --- | --- | --- | --- | --- | --- |"]
        for index, session in enumerate(project_sessions, start=next_index):
            session_path = relpath(session.session_md, project_dir)
            rows.append(
                f"| {index} | {md_cell(display_date(session.updated_at))} | {md_cell(session.source)} | "
                f"[{md_cell(session.title)}]({session_path}) | "
                f"{md_cell(clip(one_line(make_summary(session)), 180))} | "
                f"`{md_cell(session_path)}` |"
            )
        content = "\n".join(
            [
                f"# {first.project_name}",
                "",
                f"- Workspace path: `{first.project_path}`",
                f"- Last conversation: {display_time(first.updated_at)}",
                f"- Sessions: {len(project_sessions)}",
                "",
                "## Threads",
                "",
                *thread_rows,
                "",
                "## Important Output Files",
                "",
                *output_rows,
                "",
                "## Conversations",
                "",
                *rows,
                "",
            ]
        )
        (project_dir / "README.md").write_text(content, encoding="utf-8")


def write_thread_readmes(project_dir: Path, sessions: list[Session]) -> None:
    for thread_slug, thread_sessions in group_by_thread(sessions).items():
        thread_sessions.sort(key=lambda item: item.updated_at, reverse=True)
        first = thread_sessions[0]
        thread_dir = project_dir / "threads" / thread_slug
        thread_dir.mkdir(parents=True, exist_ok=True)
        output_files = collect_project_outputs(thread_sessions)
        output_rows = render_output_files_table(output_files, thread_dir, start_index=1)
        conversation_start = 1 + len(output_files)
        rows = ["| # | Date | Source | Conversation | Summary | Session File |", "| --- | --- | --- | --- | --- | --- |"]
        rows.append(f"| 0 | {md_cell(display_date(first.updated_at))} | back | [Back to {md_cell(first.project_name)}](../../README.md) | Parent project | - |")
        for index, session in enumerate(thread_sessions, start=conversation_start):
            copied_session = thread_dir / "sessions" / Path(session.session_md).name
            session_path = relpath(copied_session, thread_dir)
            rows.append(
                f"| {index} | {md_cell(display_date(session.updated_at))} | {md_cell(session.source)} | "
                f"[{md_cell(session.title)}]({session_path}) | "
                f"{md_cell(clip(one_line(make_summary(session)), 180))} | "
                f"`{md_cell(session_path)}` |"
            )
        content = "\n".join(
            [
                f"# {first.thread_name}",
                "",
                f"- Parent workstream: {first.project_name}",
                f"- Last conversation: {display_time(first.updated_at)}",
                f"- Sessions: {len(thread_sessions)}",
                "",
                "## Important Output Files",
                "",
                *output_rows,
                "",
                "## Conversations",
                "",
                *rows,
                "",
            ]
        )
        (thread_dir / "README.md").write_text(content, encoding="utf-8")


def write_menu(output: Path, sessions: list[Session]) -> None:
    write_project_readmes(output, sessions)
    projects = ordered_projects(sessions)

    lines = [
        "# Session History",
        "",
        f"Generated: {display_time(datetime.now(timezone.utc).isoformat())}",
        f"Sessions indexed: {len(sessions)}",
        f"Projects indexed: {len(projects)}",
        "",
        "## Projects",
        "",
        "| # | Last Conversation | Project | Sessions | Workspace |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, (_updated, project_slug, first, count) in enumerate(projects, start=1):
        readme = output / "projects" / project_slug / "README.md"
        lines.append(
            f"| {index} | {md_cell(display_date(first.updated_at))} | "
            f"[{md_cell(first.project_name)}]({relpath(readme, output)}) | "
            f"{count} | `{md_cell(first.project_path)}` |"
        )
    lines.append("")
    (output / "session-history.md").write_text("\n".join(lines), encoding="utf-8")


def write_artifact_hubs(output: Path, sessions: list[Session]) -> None:
    artifacts_dir = output / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[Session]] = {}
    for session in sessions:
        if session.thread_name and session.thread_name != session.project_name:
            grouped.setdefault(session.thread_slug, []).append(session)

    index_rows = []
    for thread_slug, thread_sessions in grouped.items():
        thread_sessions.sort(key=lambda item: item.updated_at, reverse=True)
        first = thread_sessions[0]
        artifact_dir = artifacts_dir / thread_slug
        artifact_dir.mkdir(parents=True, exist_ok=True)
        rows = ["| # | Date | Source | Workstream | Conversation |", "| --- | --- | --- | --- | --- |"]
        rows.append("| 0 | - | back | [Back to Artifacts Menu](../README.md) | Parent artifact menu |")
        for session in thread_sessions:
            rows.append(
                f"| {len(rows) - 2} | {md_cell(display_date(session.updated_at))} | {md_cell(session.source)} | "
                f"{md_cell(session.project_name)} | "
                f"[{md_cell(session.title)}]({relpath(session.session_md, artifact_dir)}) |"
            )
        content = "\n".join(
            [
                f"# {first.thread_name}",
                "",
                f"- Last conversation: {display_time(first.updated_at)}",
                f"- Sessions: {len(thread_sessions)}",
                f"- Workstreams: {', '.join(sorted({s.project_name for s in thread_sessions}))}",
                "",
                "## Conversations",
                "",
                *rows,
                "",
            ]
        )
        (artifact_dir / "README.md").write_text(content, encoding="utf-8")
        index_rows.append(
            f"| {len(index_rows) + 1} | {md_cell(display_date(first.updated_at))} | [{md_cell(first.thread_name)}]({thread_slug}/README.md) | "
            f"{len(thread_sessions)} | {len({s.project_name for s in thread_sessions})} |"
        )

    index_rows.sort(reverse=True)
    (artifacts_dir / "README.md").write_text(
        "\n".join(
            [
                "# Session History Artifacts",
                "",
                "| # | Last Conversation | Artifact / Thread | Sessions | Workstreams |",
                "| --- | --- | --- | --- | --- |",
                *index_rows,
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_index(output: Path, sessions: list[Session]) -> None:
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output": str(output),
        "sessions": [
            {
                "source": s.source,
                "source_path": str(s.source_path),
                "session_id": s.session_id,
                "project_path": s.project_path,
                "project_name": s.project_name,
                "project_slug": s.project_slug,
                "thread_name": s.thread_name,
                "thread_slug": s.thread_slug,
                "title": s.title,
                "started_at": s.started_at,
                "updated_at": s.updated_at,
                "summary": make_summary(s),
                "session_md": s.session_md,
                "transcript_copy": s.transcript_copy,
                "tool_names": s.tool_names,
                "file_paths": s.file_paths,
            }
            for s in sessions
        ],
    }
    (output / "index.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def group_by_project(sessions: list[Session]) -> dict[str, list[Session]]:
    grouped: dict[str, list[Session]] = {}
    for session in sessions:
        grouped.setdefault(session.project_slug, []).append(session)
    return grouped


def group_by_thread(sessions: list[Session]) -> dict[str, list[Session]]:
    grouped: dict[str, list[Session]] = {}
    for session in sessions:
        grouped.setdefault(session.thread_slug, []).append(session)
    return grouped


def ordered_projects(sessions: list[Session]) -> list[tuple[str, str, Session, int]]:
    projects = []
    for project_slug, project_sessions in group_by_project(sessions).items():
        project_sessions.sort(key=lambda item: item.updated_at, reverse=True)
        first = project_sessions[0]
        projects.append((first.updated_at, project_slug, first, len(project_sessions)))
    projects.sort(reverse=True)
    return projects


def print_menu(output: Path, sessions: list[Session], limit: int) -> None:
    projects = ordered_projects(sessions)

    print(f"Session history: {output / 'session-history.md'}")
    print(f"Indexed {len(sessions)} sessions across {len(projects)} projects.")
    print("")
    print("| # | Project | Last Conversation | Sessions | Slug | Workspace | Open Command |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for index, (_updated, project_slug, first, count) in enumerate(projects[:limit], start=1):
        print(
            f"| {index} | {md_cell(first.project_name)} | {md_cell(display_date(first.updated_at))} | "
            f"{count} | `{md_cell(project_slug)}` | `{md_cell(first.project_path)}` | "
            f"`python3 {md_cell(str(SCRIPT_PATH))} project {index}` |"
        )


def print_project(output: Path, sessions: list[Session], query: str, limit: int) -> None:
    if query.strip() == "0":
        print_menu(output, sessions, limit=limit)
        return
    matches = match_projects(sessions, query)
    if not matches:
        print(f"No project matched: {query}", file=sys.stderr)
        print_menu(output, sessions, limit=10)
        return
    if len(matches) > 1:
        print(f"Multiple projects matched {query!r}:")
        print("")
        print("| Project | Sessions | Last Conversation | Slug |")
        print("| --- | --- | --- | --- |")
        for project_slug, first, count in matches[:10]:
            print(f"| {md_cell(first.project_name)} | {count} | {md_cell(display_date(first.updated_at))} | `{md_cell(project_slug)}` |")
        return

    project_slug, first, _count = matches[0]
    project_sessions = [s for s in sessions if s.project_slug == project_slug]
    project_sessions.sort(key=lambda item: item.updated_at, reverse=True)
    readme = output / "projects" / project_slug / "README.md"
    print(f"Project history: {readme}")
    print(f"{first.project_name} - {len(project_sessions)} sessions - last {display_date(first.updated_at)}")
    print(f"Workspace path: {first.project_path}")
    print("")
    thread_groups = group_by_thread(project_sessions)
    sorted_threads = sorted(
        thread_groups.items(),
        key=lambda item: item[1][0].updated_at if item[1] else "",
        reverse=True,
    )
    print("| # | Thread / Subfolder | Last Conversation | Sessions | Open Command |")
    print("| --- | --- | --- | --- | --- |")
    print(f"| 0 | Back to Project Menu | {md_cell(display_date(first.updated_at))} | {len(group_by_project(sessions))} projects | `python3 {md_cell(str(SCRIPT_PATH))} menu` |")
    for thread_index, (thread_slug, thread_sessions) in enumerate(sorted_threads, start=1):
        thread_sessions.sort(key=lambda item: item.updated_at, reverse=True)
        thread_first = thread_sessions[0]
        print(
            f"| {thread_index} | {md_cell(thread_first.thread_name)} | {md_cell(display_date(thread_first.updated_at))} | "
            f"{len(thread_sessions)} | `python3 {md_cell(str(SCRIPT_PATH))} thread {md_cell(project_slug)} {thread_index}` |"
        )
    print("")
    next_index = len(sorted_threads) + 1
    output_files = collect_project_outputs(project_sessions)
    print("Important output files:")
    for line in render_output_files_table(output_files, start_index=next_index):
        print(line)
    print("")
    conversation_start = next_index + len(output_files)
    print("| # | Date | Source | Conversation | Summary | Session File |")
    print("| --- | --- | --- | --- | --- | --- |")
    for index, session in enumerate(project_sessions[:limit], start=conversation_start):
        print(
            f"| {index} | {md_cell(display_date(session.updated_at))} | {md_cell(session.source)} | "
            f"{md_cell(session.title)} | {md_cell(clip(one_line(make_summary(session)), 220))} | "
            f"`{md_cell(session.session_md)}` |"
        )


def print_thread(output: Path, sessions: list[Session], query: str, limit: int) -> None:
    project_query, thread_query = split_thread_query(query)
    if not project_query:
        print("Provide a project row/slug plus a thread row, for example: session_history.py thread 13 2", file=sys.stderr)
        print_menu(output, sessions, limit=10)
        return
    if thread_query == "0":
        print_project(output, sessions, query=project_query, limit=limit)
        return

    project_matches = match_projects(sessions, project_query)
    if not project_matches:
        print(f"No project matched: {project_query}", file=sys.stderr)
        print_menu(output, sessions, limit=10)
        return
    if len(project_matches) > 1:
        print(f"Multiple projects matched {project_query!r}:")
        print("")
        print("| # | Project | Sessions | Last Conversation | Slug |")
        print("| --- | --- | --- | --- | --- |")
        for index, (project_slug, first, count) in enumerate(project_matches[:10], start=1):
            print(f"| {index} | {md_cell(first.project_name)} | {count} | {md_cell(display_date(first.updated_at))} | `{md_cell(project_slug)}` |")
        return

    project_slug, first, _count = project_matches[0]
    project_sessions = [s for s in sessions if s.project_slug == project_slug]
    thread_groups = group_by_thread(project_sessions)
    sorted_threads = sorted(
        thread_groups.items(),
        key=lambda item: item[1][0].updated_at if item[1] else "",
        reverse=True,
    )
    if not thread_query:
        print_project(output, sessions, query=project_slug, limit=limit)
        return

    thread_sessions = resolve_thread(sorted_threads, thread_query)
    if not thread_sessions:
        print(f"No thread matched: {thread_query}", file=sys.stderr)
        print_project(output, sessions, query=project_slug, limit=limit)
        return
    thread_sessions.sort(key=lambda item: item.updated_at, reverse=True)
    thread_first = thread_sessions[0]
    thread_readme = output / "projects" / project_slug / "threads" / thread_first.thread_slug / "README.md"
    print(f"Thread history: {thread_readme}")
    print(f"{thread_first.thread_name} - {len(thread_sessions)} sessions - last {display_date(thread_first.updated_at)}")
    print(f"Parent project: {first.project_name}")
    print("")
    output_files = collect_project_outputs(thread_sessions)
    print("Important output files:")
    for line in render_output_files_table(output_files, start_index=1):
        print(line)
    print("")
    conversation_start = 1 + len(output_files)
    print("| # | Date | Source | Conversation | Summary | Session File |")
    print("| --- | --- | --- | --- | --- | --- |")
    print(f"| 0 | {md_cell(display_date(first.updated_at))} | back | Back to {md_cell(first.project_name)} | Parent project | `python3 {md_cell(str(SCRIPT_PATH))} project {md_cell(project_slug)}` |")
    for index, session in enumerate(thread_sessions[:limit], start=conversation_start):
        print(
            f"| {index} | {md_cell(display_date(session.updated_at))} | {md_cell(session.source)} | "
            f"{md_cell(session.title)} | {md_cell(clip(one_line(make_summary(session)), 220))} | "
            f"`{md_cell(session.session_md)}` |"
        )


def print_search(output: Path, sessions: list[Session], query: str, limit: int) -> None:
    terms = [term.lower() for term in query.split() if term.strip()]
    scored: list[tuple[int, Session]] = []
    for session in sessions:
        haystack = "\n".join(
            [
                session.project_name,
                session.project_path,
                session.title,
                make_summary(session),
                "\n".join(session.user_prompts[:5]),
                "\n".join(session.assistant_outputs[-3:]),
                "\n".join(session.file_paths),
            ]
        ).lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            scored.append((score, session))
    scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)

    print(f"Search results for {query!r} in {output / 'session-history.md'}")
    print("")
    if scored:
        print("| # | Date | Project | Source | Conversation | Summary | Session File |")
        print("| --- | --- | --- | --- | --- | --- | --- |")
    for index, (_score, session) in enumerate(scored[:limit], start=1):
        print(
            f"| {index} | {md_cell(display_date(session.updated_at))} | {md_cell(session.project_name)} | "
            f"{md_cell(session.source)} | {md_cell(session.title)} | "
            f"{md_cell(clip(one_line(make_summary(session)), 220))} | `{md_cell(session.session_md)}` |"
        )
    if not scored:
        print("No matching sessions.")


def open_project(output: Path, sessions: list[Session], query: str) -> int:
    matches = match_projects(sessions, query)
    if not matches:
        print(f"No project matched: {query}", file=sys.stderr)
        return 1
    if len(matches) > 1:
        print(f"Multiple projects matched {query!r}:")
        print("")
        print("| Project | Sessions | Last Conversation | Slug |")
        print("| --- | --- | --- | --- |")
        for project_slug, first, count in matches[:10]:
            print(f"| {md_cell(first.project_name)} | {count} | {md_cell(display_date(first.updated_at))} | `{md_cell(project_slug)}` |")
        return 2
    project_slug, _first, _count = matches[0]
    readme = output / "projects" / project_slug / "README.md"
    if sys.platform == "darwin":
        subprocess.run(["open", str(readme)], check=False)
    print(readme)
    return 0


def match_projects(sessions: list[Session], query: str) -> list[tuple[str, Session, int]]:
    query = query.lower().strip()
    if query.isdigit():
        index = int(query)
        projects = ordered_projects(sessions)
        if 1 <= index <= len(projects):
            _updated, project_slug, first, count = projects[index - 1]
            return [(project_slug, first, count)]
        return []
    projects = []
    for project_slug, project_sessions in group_by_project(sessions).items():
        project_sessions.sort(key=lambda item: item.updated_at, reverse=True)
        first = project_sessions[0]
        haystacks = [project_slug.lower(), first.project_name.lower(), first.project_path.lower()]
        if not query or any(query in item for item in haystacks):
            projects.append((project_slug, first, len(project_sessions)))
    projects.sort(key=lambda item: item[1].updated_at, reverse=True)
    return projects


def split_thread_query(query: str) -> tuple[str, str]:
    query = query.strip()
    if not query:
        return "", ""
    if " " not in query:
        return query, ""
    project_query, thread_query = query.rsplit(" ", 1)
    return project_query.strip(), thread_query.strip()


def resolve_thread(sorted_threads: list[tuple[str, list[Session]]], query: str) -> list[Session]:
    query = query.lower().strip()
    if query.isdigit():
        index = int(query)
        if 1 <= index <= len(sorted_threads):
            return sorted_threads[index - 1][1]
        return []
    for thread_slug, thread_sessions in sorted_threads:
        first = thread_sessions[0]
        haystacks = [thread_slug.lower(), first.thread_name.lower()]
        if any(query in item for item in haystacks):
            return thread_sessions
    return []


def unique(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = str(item).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def extract_paths(text: str) -> list[str]:
    pattern = r"((?:/Users|/home)/[A-Za-z0-9._-]+/[A-Za-z0-9_./ +'()@:-]+)"
    paths = []
    for match in re.findall(pattern, text):
        for path in re.split(r"\s+['\"]?(?=(?:/Users|/home)/)", match):
            paths.append(path.rstrip(".,);]}'\""))
    return unique(paths)


def mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def normalize_time(value: str) -> str:
    value = value.strip()
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        if value.endswith("Z"):
            dt = datetime.fromisoformat(value[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return value


def display_time(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    except ValueError:
        return value


def display_date(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone().strftime("%Y-%m-%d")
    except ValueError:
        return value[:10]


def date_part(value: str) -> str:
    return display_date(value)


def clean_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def one_line(text: str) -> str:
    return clean_inline(text.replace("\n", " "))


def clip(text: str, limit: int = MAX_TEXT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def relpath(path: str | Path, start: str | Path) -> str:
    return os.path.relpath(str(path), str(start))


def md_cell(value: object) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|").strip()


def markdown_link_target(value: str) -> str:
    value = value.strip()
    if any(char.isspace() for char in value):
        return f"<{value}>"
    return value


if __name__ == "__main__":
    raise SystemExit(main())
