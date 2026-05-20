#!/usr/bin/env python3
"""Generate grouped release notes from Conventional Commits and PR metadata."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


HEADER_RE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]+\))?(?P<breaking>!)?: (?P<subject>.+)")
GROUPS = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "docs": "Technical/Internal",
    "style": "Technical/Internal",
    "test": "Technical/Internal",
    "build": "Technical/Internal",
    "ci": "Technical/Internal",
    "chore": "Technical/Internal",
}
ORDER = ["Added", "Changed", "Fixed", "Removed", "Technical/Internal"]


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def git_log_messages(from_ref: str | None) -> list[str]:
    range_arg = "HEAD" if not from_ref else f"{from_ref}..HEAD"
    output = run_git(["log", "--format=%B%x1e", range_arg])
    return [part.strip() for part in output.split("\x1e") if part.strip()]


def extract_user_notes(pr_body: str) -> list[str]:
    if not pr_body:
        return []

    lines = pr_body.splitlines()
    capture = False
    notes: list[str] = []
    for line in lines:
        stripped = line.strip()
        normalized = stripped.lower()
        if normalized in {
            "## release notes",
            "## player release notes",
            "## player-facing release notes",
            "## user-facing release notes",
        }:
            capture = True
            continue
        if capture and stripped.startswith("## "):
            break
        if capture and stripped and not stripped.startswith("<!--"):
            notes.append(stripped.lstrip("- ").strip())

    return [note for note in notes if note and note.lower() not in {"none", "n/a"}]


def summarize_commit(message: str) -> tuple[str, str] | None:
    first_line = message.splitlines()[0] if message.splitlines() else ""
    match = HEADER_RE.match(first_line)
    if not match:
        return None

    commit_type = match.group("type")
    subject = match.group("subject").strip()
    group = "Changed" if match.group("breaking") or "BREAKING CHANGE:" in message else GROUPS.get(commit_type, "Technical/Internal")
    if subject.lower().startswith(("update ", "change ", "fix ", "add ")):
        text = subject[0].upper() + subject[1:]
    else:
        text = subject[0].upper() + subject[1:] if subject else subject
    return group, text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-ref", default="")
    parser.add_argument("--pr-body", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    grouped: dict[str, list[str]] = {group: [] for group in ORDER}
    user_notes = extract_user_notes(args.pr_body)
    if user_notes:
        grouped["Changed"].extend(user_notes)

    for message in git_log_messages(args.from_ref or None):
        summarized = summarize_commit(message)
        if summarized is None:
            continue
        group, text = summarized
        if text not in grouped[group]:
            grouped[group].append(text)

    lines: list[str] = []
    for group in ORDER:
        items = grouped[group]
        if not items:
            continue
        lines.append(f"## {group}")
        lines.extend(f"- {item}" for item in items)
        lines.append("")

    if not lines:
        lines = ["## Changed", "- Maintenance release.", ""]

    Path(args.output).write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(Path(args.output).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
