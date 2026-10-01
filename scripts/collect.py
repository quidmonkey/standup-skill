#!/usr/bin/env python3
"""Collect a per-project digest of recent Claude Code sessions for a standup update.

Reads ~/.claude/projects/*/*.jsonl transcripts, keeps records inside the time
window, groups sessions by working directory, and prints Markdown to stdout. Directories
at or under the current working directory are listed first.
"""

import argparse
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SKIP_COMMANDS = {
    "/clear",
    "/standup",
    "/standup-skill",
    "/compact",
    "/exit",
    "/resume",
    "/model",
    "/config",
}
MAX_PROMPT_CHARS = 400
MAX_PROMPTS = 20
MAX_FINAL_CHARS = 600


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--hours", type=float, default=24, help="look back N hours (default 24)"
    )
    p.add_argument("--since", help="ISO date/time to start from; overrides --hours")
    p.add_argument(
        "--include-automated",
        action="store_true",
        help="include non-interactive (sdk/-p) sessions",
    )
    return p.parse_args()


def cutoff_from(args):
    if args.since:
        dt = datetime.fromisoformat(args.since)
        return dt if dt.tzinfo else dt.astimezone()
    return datetime.now(timezone.utc) - timedelta(hours=args.hours)


def parse_ts(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def read_records(path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def truncate(text, limit):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def clean_prompt(text):
    """Return a readable prompt, or None if it is noise (slash-command plumbing, hook output)."""
    if text.startswith(("<local-command", "<bash-stdout", "<bash-stderr", "Caveat:")):
        return None
    text = re.sub(
        r"<pasted_content[^>]*>.*?</pasted_content[^>]*>",
        "[pasted content]",
        text,
        flags=re.DOTALL,
    )
    shell = re.match(r"<bash-input>(.*?)</bash-input>", text, re.DOTALL)
    if shell:
        return "! " + shell.group(1).strip()
    cmd = re.search(r"<command-name>(.*?)</command-name>", text)
    if cmd:
        name = cmd.group(1).strip()
        if name in SKIP_COMMANDS:
            return None
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.DOTALL)
        return f"{name} {args.group(1).strip() if args else ''}".strip()
    return text.strip() or None


def human_prompt(rec):
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
        return None
    origin = rec.get("origin") or {}
    if origin and origin.get("kind") != "human":
        return None
    content = rec.get("message", {}).get("content")
    if isinstance(content, list):
        if any(c.get("type") == "tool_result" for c in content if isinstance(c, dict)):
            return None
        content = "\n".join(
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        )
    return clean_prompt(content) if isinstance(content, str) else None


def summarize_tool_use(block, session):
    name, inp = block.get("name"), block.get("input") or {}
    if name in EDIT_TOOLS and inp.get("file_path"):
        session["files"].add(inp["file_path"])
    elif name == "Bash":
        cmd = inp.get("command", "")
        if "git commit" in cmd:
            msg = re.search(
                r"""git commit\b[^;&|\n]*?-\w*m\s+(?:"\$\(cat <<'?EOF'?\n)?["']?([^"'\n]+)""",
                cmd,
            )
            if msg:
                session["commits"].append(msg.group(1).strip())
        if "gh pr create" in cmd:
            title = re.search(r"""--title\s+["']([^"']+)""", cmd)
            session["prs"].append(title.group(1) if title else "PR created")


def parse_session(path, cutoff, include_automated):
    s = {
        "id": path.stem,
        "title": None,
        "prompts": [],
        "files": set(),
        "commits": [],
        "prs": [],
        "cwds": defaultdict(int),
        "branches": set(),
        "first": None,
        "last": None,
        "final": None,
        "automated": False,
    }
    for rec in read_records(path):
        if rec.get("type") == "ai-title":
            s["title"] = rec.get("aiTitle")
            continue
        if rec.get("entrypoint", "").startswith("sdk"):
            s["automated"] = True
        ts = parse_ts(rec.get("timestamp"))
        if ts is None or ts < cutoff or rec.get("isSidechain"):
            continue
        if rec.get("cwd"):
            s["cwds"][rec["cwd"]] += 1
        if rec.get("gitBranch") and rec["gitBranch"] != "HEAD":
            s["branches"].add(rec["gitBranch"])
        prompt = human_prompt(rec)
        if prompt:
            s["prompts"].append(truncate(prompt, MAX_PROMPT_CHARS))
            s["first"] = s["first"] or ts
        if rec.get("type") == "assistant":
            for block in rec.get("message", {}).get("content") or []:
                if block.get("type") == "tool_use":
                    summarize_tool_use(block, s)
                elif block.get("type") == "text" and block.get("text", "").strip():
                    s["final"] = block["text"]
        s["last"] = ts
    if not s["prompts"] or (s["automated"] and not include_automated):
        return None
    return s


def git_commits(repo, cutoff):
    """Commits by the configured user in repo since cutoff, across all branches."""

    def git(*cmd):
        r = subprocess.run(
            ["git", "-C", repo, *cmd],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return r.stdout.strip() if r.returncode == 0 else ""

    email = git("config", "user.email")
    if not email:
        return []
    out = git(
        "log",
        "--all",
        f"--since={cutoff.isoformat()}",
        f"--author={email}",
        "--format=%h %s",
    )
    return out.splitlines()


def short_path(p):
    home = str(Path.home())
    return "~" + p[len(home) :] if p.startswith(home) else p


def is_current(cwd, current):
    return cwd == current or cwd.startswith(current.rstrip("/") + "/")


def render(projects, cutoff, current):
    lines = [
        f"# Claude Code activity since {cutoff.astimezone():%Y-%m-%d %H:%M %Z}",
        "",
    ]
    if not projects:
        lines.append("_No interactive sessions found in this window._")
    for cwd, sessions in sorted(
        projects.items(),
        key=lambda kv: (
            is_current(kv[0], current),
            max(s["last"] for s in kv[1]),
        ),
        reverse=True,
    ):
        marker = " (current project)" if is_current(cwd, current) else ""
        lines.append(f"## {short_path(cwd)}{marker}")
        if Path(cwd).is_dir():
            commits = git_commits(cwd, cutoff)
            if commits:
                lines.append("Git commits in window:")
                lines.extend(f"- {c}" for c in commits)
        lines.append("")
        for s in sorted(sessions, key=lambda s: s["first"]):
            local = s["first"].astimezone()
            branch = (
                f" [branch: {', '.join(sorted(s['branches']))}]"
                if s["branches"]
                else ""
            )
            lines.append(
                f"### {s['title'] or 'Untitled session'} ({local:%a %H:%M}){branch}"
            )
            prompts = s["prompts"]
            if len(prompts) > MAX_PROMPTS:
                half = MAX_PROMPTS // 2
                prompts = (
                    prompts[:half]
                    + [f"… {len(prompts) - MAX_PROMPTS} more prompts …"]
                    + prompts[-half:]
                )
            lines.append("User prompts:")
            lines.extend(f"- {p}" for p in prompts)
            if s["files"]:
                lines.append(
                    "Files edited: "
                    + ", ".join(sorted(short_path(f) for f in s["files"]))
                )
            if s["commits"]:
                lines.append("Commits made in session: " + "; ".join(s["commits"]))
            if s["prs"]:
                lines.append("PRs opened: " + "; ".join(s["prs"]))
            if s["final"]:
                lines.append(
                    "Last assistant message: " + truncate(s["final"], MAX_FINAL_CHARS)
                )
            lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()
    cutoff = cutoff_from(args)
    projects = defaultdict(list)
    for path in PROJECTS_DIR.glob("*/*.jsonl"):
        if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
            continue
        session = parse_session(path, cutoff, args.include_automated)
        if session:
            cwd = max(session["cwds"], key=session["cwds"].get)
            projects[cwd].append(session)
    print(render(projects, cutoff, str(Path.cwd())))


if __name__ == "__main__":
    main()
