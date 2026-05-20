#!/usr/bin/env python3
"""Validate commit subjects used by release automation."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys


CONVENTIONAL_RE = re.compile(r"^[a-z]+(?:\([^)]+\))?!?: .+")


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def commit_range(from_ref: str) -> str:
    return f"{from_ref}..HEAD" if from_ref else "HEAD"


def commit_subjects(range_arg: str) -> list[tuple[str, str]]:
    output = run_git(["log", "--no-merges", "--format=%H%x00%s", range_arg])
    subjects: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        sha, _, subject = line.partition("\x00")
        subjects.append((sha, subject))
    return subjects


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-ref", default="")
    parser.add_argument("--range", dest="range_arg", default="")
    args = parser.parse_args()

    range_arg = args.range_arg or commit_range(args.from_ref)
    invalid = [(sha, subject) for sha, subject in commit_subjects(range_arg) if not CONVENTIONAL_RE.match(subject)]
    if invalid:
        print("Commit subjects must use Conventional Commits: type(scope)!: subject")
        for sha, subject in invalid:
            print(f"- {sha[:12]} {subject}")
        return 1

    print(f"Validated Conventional Commit subjects in {range_arg}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
