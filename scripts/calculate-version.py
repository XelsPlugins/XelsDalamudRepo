#!/usr/bin/env python3
"""Calculate Xels Dalamud plugin release and testing versions."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


SEMVER_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
TESTING_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)-testing\.(?P<build>\d+)$")
LEGACY_STABLE_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)\.(?P<build>\d+)$")
HEADER_RE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]+\))?(?P<breaking>!)?: .+")

NO_BUMP_TYPES = {"docs", "style", "refactor", "test", "build", "ci", "chore"}
PATCH_TYPES = {"fix", "perf"}
MINOR_TYPES = {"feat"}
BUMP_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}
ZERO_VERSION = (0, 0, 0, 0)


@dataclass(frozen=True)
class StableTag:
    tag: str
    version: tuple[int, int, int]
    legacy_build: int


@dataclass(frozen=True)
class TestingTag:
    tag: str
    version: tuple[int, int, int]
    build: int


def run_git(args: list[str], check: bool = True) -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def run_gh(args: list[str], check: bool = True) -> str:
    result = subprocess.run(["gh", *args], text=True, capture_output=True, check=False)
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


def parse_testing_tag(tag: str) -> TestingTag | None:
    match = TESTING_TAG_RE.match(tag)
    if not match:
        return None

    return TestingTag(
        tag=tag,
        version=(int(match.group("major")), int(match.group("minor")), int(match.group("patch"))),
        build=int(match.group("build")),
    )


def latest_testing_tag() -> TestingTag | None:
    tags = []
    for raw in run_git(["tag", "--list", "v*-testing.*"], check=False).splitlines():
        parsed = parse_testing_tag(raw.strip())
        if parsed is not None:
            tags.append(parsed)

    return max(tags, key=lambda item: (*item.version, item.build)) if tags else None


def tag_exists(tag: str) -> bool:
    return bool(run_git(["rev-parse", "--verify", f"refs/tags/{tag}"], check=False))


def git_log_messages(from_ref: str | None, oldest_first: bool = False) -> list[str]:
    range_arg = "HEAD"
    if from_ref:
        range_arg = f"{from_ref}..HEAD"

    output = run_git(["log", "--format=%B%x1e", range_arg], check=False)
    messages = [part.strip() for part in output.split("\x1e") if part.strip()]
    if oldest_first:
        messages.reverse()
    return messages


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


def additive_bump(version: tuple[int, int, int], messages: list[str], override: str) -> tuple[tuple[int, int, int], str]:
    if override != "auto":
        return apply_bump(version, override), override

    major, minor, patch = version
    major_bumps = 0
    minor_bumps = 0
    patch_bumps = 0
    highest_bump = "none"
    for message in messages:
        bump = bump_for_message(message)
        if BUMP_RANK[bump] > BUMP_RANK[highest_bump]:
            highest_bump = bump
        if bump == "major":
            major_bumps += 1
        elif bump == "minor":
            minor_bumps += 1
        elif bump == "patch":
            patch_bumps += 1

    if major_bumps:
        return (major + major_bumps, minor_bumps, patch_bumps), highest_bump
    if minor_bumps:
        return (major, minor + minor_bumps, patch_bumps), highest_bump
    if patch_bumps:
        return (major, minor, patch + patch_bumps), highest_bump

    return version, highest_bump


def apply_bump(version: tuple[int, int, int], bump: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if bump == "major":
        return major + 1, 0, 0
    if bump == "minor":
        return major, minor + 1, 0
    if bump == "patch":
        return major, minor, patch + 1
    return version


def version_key(value: object) -> tuple[int, int, int, int]:
    parts = str(value or "0.0.0.0").split(".")
    numbers = [int(part) for part in parts if part.isdigit()]
    while len(numbers) < 4:
        numbers.append(0)
    return tuple(numbers[:4])


def version_base(value: tuple[int, int, int, int]) -> tuple[int, int, int]:
    return value[:3]


def feed_versions(feed_path: Path | None, internal_name: str) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    if feed_path is None:
        return ZERO_VERSION, ZERO_VERSION
    if not internal_name:
        raise SystemExit("--internal-name is required when --feed is provided")
    if not feed_path.exists():
        raise SystemExit(f"Feed file does not exist: {feed_path}")

    data = json.loads(feed_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("Feed file must contain a JSON array")

    entry = next((item for item in data if isinstance(item, dict) and item.get("InternalName") == internal_name), None)
    if entry is None:
        return ZERO_VERSION, ZERO_VERSION

    return version_key(entry.get("AssemblyVersion")), version_key(entry.get("TestingAssemblyVersion"))


def download_json_asset(url: str) -> dict[str, object] | None:
    with tempfile.TemporaryDirectory() as tmp:
        destination = Path(tmp) / "manifest.json"
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                destination.write_bytes(response.read())
            data = json.loads(destination.read_text(encoding="utf-8"))
        except Exception:
            return None

    return data if isinstance(data, dict) else None


def historical_release_version(repo: str, internal_name: str) -> tuple[int, int, int, int]:
    if not repo or not internal_name:
        return ZERO_VERSION

    raw = run_gh(["api", f"repos/{repo}/releases", "--paginate"], check=False)
    if not raw:
        return ZERO_VERSION

    try:
        releases = json.loads(raw)
    except json.JSONDecodeError:
        return ZERO_VERSION

    highest = ZERO_VERSION
    for release in releases:
        if not isinstance(release, dict):
            continue

        for asset in release.get("assets") or []:
            if not isinstance(asset, dict) or asset.get("name") != f"{internal_name}.json":
                continue

            manifest = download_json_asset(str(asset.get("browser_download_url") or ""))
            if manifest is None or manifest.get("InternalName") != internal_name:
                continue

            highest = max(highest, version_key(manifest.get("AssemblyVersion")))
            break

    return highest


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
    parser.add_argument("--feed", default="")
    parser.add_argument("--internal-name", default="")
    parser.add_argument("--repo", default="")
    args = parser.parse_args()

    stable = latest_stable_tag()
    messages = git_log_messages(stable.tag or None, oldest_first=True)

    next_version, bump = additive_bump(stable.version, messages, args.release_type)

    should_release = args.mode == "testing" or bump != "none" or args.release_type != "auto"
    build = int(args.run_number or "0")
    if args.mode == "testing":
        feed_stable, feed_testing = feed_versions(Path(args.feed) if args.feed else None, args.internal_name)
        historical_testing = historical_release_version(args.repo, args.internal_name)
        latest_testing = latest_testing_tag()
        latest_testing_version = latest_testing.version if latest_testing is not None else (0, 0, 0)
        testing_base = max(
            next_version,
            version_base(feed_stable),
            version_base(feed_testing),
            version_base(historical_testing),
            latest_testing_version,
        )
        testing_build_candidates = [build, feed_testing[3] + 1, historical_testing[3] + 1, 1]
        if latest_testing is not None and latest_testing.version == testing_base:
            testing_build_candidates.append(latest_testing.build + 1)
        testing_build = max(testing_build_candidates)
        assembly_version = f"{testing_base[0]}.{testing_base[1]}.{testing_base[2]}.{testing_build}"
        tag = f"v{testing_base[0]}.{testing_base[1]}.{testing_base[2]}-testing.{testing_build}"
        notes_from_ref = latest_testing.tag if latest_testing is not None else ("testing" if tag_exists("testing") else stable.tag)
    else:
        assembly_version = f"{next_version[0]}.{next_version[1]}.{next_version[2]}.0"
        tag = f"v{next_version[0]}.{next_version[1]}.{next_version[2]}"
        notes_from_ref = stable.tag

    values: dict[str, object] = {
        "current_version": ".".join(str(part) for part in stable.version),
        "current_tag": stable.tag,
        "bump": bump,
        "next_version": ".".join(str(part) for part in next_version),
        "assembly_version": assembly_version,
        "tag": tag,
        "notes_from_ref": notes_from_ref,
        "should_release": str(should_release).lower(),
    }

    write_github_output(values)
    print(json.dumps(values, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
