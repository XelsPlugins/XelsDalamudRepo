#!/usr/bin/env python3
"""Calculate Xels Dalamud plugin release and testing versions."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SEMVER_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
LEGACY_STABLE_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)\.(?P<build>\d+)$")
HEADER_RE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]+\))?(?P<breaking>!)?: .+")

NO_BUMP_TYPES = {"docs", "style", "refactor", "test", "build", "ci", "chore"}
PATCH_TYPES = {"fix", "perf"}
MINOR_TYPES = {"feat"}
BUMP_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}


@dataclass(frozen=True)
class StableTag:
    tag: str
    version: tuple[int, int, int]
    legacy_build: int


def run_git(args: list[str], check: bool = True) -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def parse_stable_tag(tag: str) -> StableTag | None:
    match = SEMVER_TAG_RE.match(tag)
    if match:
        return StableTag(
            tag=tag,
            version=(int(match.group("major")), int(match.group("minor")), int(match.group("patch"))),
            legacy_build=0,
        )

    match = LEGACY_STABLE_TAG_RE.match(tag)
    if match:
        return StableTag(
            tag=tag,
            version=(int(match.group("major")), int(match.group("minor")), int(match.group("patch"))),
            legacy_build=int(match.group("build")),
        )

    return None


def latest_stable_tag() -> StableTag:
    tags = []
    for raw in run_git(["tag", "--list", "v*"], check=False).splitlines():
        parsed = parse_stable_tag(raw.strip())
        if parsed is not None:
            tags.append(parsed)

    if not tags:
        return StableTag(tag="", version=(0, 0, 0), legacy_build=0)

    return max(tags, key=lambda item: (*item.version, item.legacy_build))


def git_log_messages(from_ref: str | None) -> list[str]:
    range_arg = "HEAD"
    if from_ref:
        range_arg = f"{from_ref}..HEAD"

    output = run_git(["log", "--format=%B%x1e", range_arg], check=False)
    return [part.strip() for part in output.split("\x1e") if part.strip()]


def bump_for_message(message: str) -> str:
    first_line = message.splitlines()[0] if message.splitlines() else ""
    header = HEADER_RE.match(first_line)
    if not header:
        return "none"

    if header.group("breaking") or "BREAKING CHANGE:" in message:
        return "major"

    commit_type = header.group("type")
    if commit_type in MINOR_TYPES:
        return "minor"
    if commit_type in PATCH_TYPES:
        return "patch"
    if commit_type in NO_BUMP_TYPES:
        return "none"

    return "none"


def max_bump(messages: list[str], override: str) -> str:
    if override != "auto":
        return override

    bump = "none"
    for message in messages:
        candidate = bump_for_message(message)
        if BUMP_RANK[candidate] > BUMP_RANK[bump]:
            bump = candidate

    return bump


def apply_bump(version: tuple[int, int, int], bump: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if bump == "major":
        return major + 1, 0, 0
    if bump == "minor":
        return major, minor + 1, 0
    if bump == "patch":
        return major, minor, patch + 1
    return version


def write_github_output(values: dict[str, object]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return

    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["testing", "release"], required=True)
    parser.add_argument("--release-type", choices=["auto", "patch", "minor", "major"], default="auto")
    parser.add_argument("--run-number", default="0")
    args = parser.parse_args()

    stable = latest_stable_tag()
    messages = git_log_messages(stable.tag or None)

    bump = max_bump(messages, args.release_type)
    next_version = apply_bump(stable.version, bump)

    should_release = args.mode == "testing" or bump != "none" or args.release_type != "auto"
    build = int(args.run_number or "0")
    if args.mode == "testing":
        assembly_version = f"{next_version[0]}.{next_version[1]}.{next_version[2]}.{max(build, 1)}"
        tag = "testing"
    else:
        assembly_version = f"{next_version[0]}.{next_version[1]}.{next_version[2]}.0"
        tag = f"v{next_version[0]}.{next_version[1]}.{next_version[2]}"

    values: dict[str, object] = {
        "current_version": ".".join(str(part) for part in stable.version),
        "current_tag": stable.tag,
        "bump": bump,
        "next_version": ".".join(str(part) for part in next_version),
        "assembly_version": assembly_version,
        "tag": tag,
        "should_release": str(should_release).lower(),
    }

    write_github_output(values)
    print(json.dumps(values, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
