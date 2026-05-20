#!/usr/bin/env python3
"""Mode-gated updater for Xels Dalamud pluginmaster entries."""

from __future__ import annotations

import argparse
import copy
import json
import os
import time
from pathlib import Path


STABLE_FIELDS = {
    "AssemblyVersion",
    "DownloadLinkInstall",
    "DownloadLinkUpdate",
    "LastUpdate",
}
TESTING_FIELDS = {
    "TestingAssemblyVersion",
    "TestingDalamudApiLevel",
    "DownloadLinkTesting",
}


def version_key(value: object) -> tuple[int, int, int, int]:
    parts = str(value or "0.0.0.0").split(".")
    numbers = [int(part) for part in parts if part.isdigit()]
    while len(numbers) < 4:
        numbers.append(0)
    return tuple(numbers[:4])


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def base_entry(manifest: dict[str, object], repo_url: str) -> dict[str, object]:
    return {
        "Author": manifest.get("Author", ""),
        "Name": manifest["Name"],
        "InternalName": manifest["InternalName"],
        "AssemblyVersion": manifest["AssemblyVersion"],
        "Description": manifest.get("Description", ""),
        "ApplicableVersion": manifest.get("ApplicableVersion", "any"),
        "DalamudApiLevel": int(manifest.get("DalamudApiLevel", 0)),
        "LoadRequiredState": int(manifest.get("LoadRequiredState", 0)),
        "LoadSync": bool(manifest.get("LoadSync", False)),
        "CanUnloadAsync": bool(manifest.get("CanUnloadAsync", False)),
        "LoadPriority": int(manifest.get("LoadPriority", 0)),
        "IsHide": bool(manifest.get("IsHide", False)),
        "IsTestingExclusive": bool(manifest.get("IsTestingExclusive", False)),
        "Punchline": manifest.get("Punchline", ""),
        "AcceptsFeedback": bool(manifest.get("AcceptsFeedback", True)),
        "DownloadCount": 0,
        "LastUpdate": int(time.time()),
        "DownloadLinkInstall": "",
        "DownloadLinkUpdate": "",
        "DownloadLinkTesting": "",
        "RepoUrl": repo_url,
    }


def merge_metadata(entry: dict[str, object], manifest: dict[str, object], repo_url: str) -> None:
    for key in [
        "Author",
        "Name",
        "Description",
        "ApplicableVersion",
        "DalamudApiLevel",
        "LoadRequiredState",
        "LoadSync",
        "CanUnloadAsync",
        "LoadPriority",
        "IsHide",
        "IsTestingExclusive",
        "Punchline",
        "AcceptsFeedback",
        "IconUrl",
        "Tags",
        "CategoryTags",
        "ImageUrls",
        "MinimumDalamudVersion",
    ]:
        if key in manifest:
            entry[key] = manifest[key]
    entry["RepoUrl"] = repo_url


def stable_snapshot(entry: dict[str, object]) -> dict[str, object]:
    return {key: entry.get(key) for key in STABLE_FIELDS}


def testing_snapshot(entry: dict[str, object]) -> dict[str, object]:
    return {key: entry.get(key) for key in TESTING_FIELDS}


def same_version_base(left: object, right: object) -> bool:
    return version_key(left)[:3] == version_key(right)[:3]


def write_github_output(status: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"feed_status={status}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed-repo-dir", required=True)
    parser.add_argument("--mode", choices=["testing", "stable"], required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--assembly-version", required=True)
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--clear-testing", action="store_true")
    args = parser.parse_args()

    feed_path = Path(args.feed_repo_dir) / "pluginmaster.json"
    manifest = load_json(Path(args.manifest))
    if not isinstance(manifest, dict):
        raise SystemExit("Manifest must be a JSON object")

    internal_name = str(manifest["InternalName"])
    data = load_json(feed_path)
    if not isinstance(data, list):
        raise SystemExit("pluginmaster.json must be a JSON array")

    original_data = copy.deepcopy(data)
    index = next((i for i, entry in enumerate(data) if entry.get("InternalName") == internal_name), None)

    if args.mode == "testing" and index is None:
        status = f"skipped: no stable feed entry exists for {internal_name}"
        print(status)
        write_github_output(status)
        return 0

    if index is None:
        entry = base_entry(manifest, args.repo_url)
        data.append(entry)
    else:
        entry = data[index]

    before = copy.deepcopy(entry)
    merge_metadata(entry, manifest, args.repo_url)

    if args.mode == "testing":
        stable_before = stable_snapshot(before)
        entry["TestingAssemblyVersion"] = args.assembly_version
        entry["TestingDalamudApiLevel"] = int(manifest.get("DalamudApiLevel", 0))
        entry["DownloadLinkTesting"] = args.download_url
        if stable_snapshot(entry) != stable_before:
            raise SystemExit("testing mode attempted to modify stable feed fields")
    else:
        testing_before = testing_snapshot(before)
        entry["AssemblyVersion"] = args.assembly_version
        entry["DownloadLinkInstall"] = args.download_url
        entry["DownloadLinkUpdate"] = args.download_url
        entry["LastUpdate"] = int(time.time())
        if args.clear_testing:
            testing_version = entry.get("TestingAssemblyVersion")
            if testing_version and (
                same_version_base(testing_version, args.assembly_version)
                or version_key(testing_version) <= version_key(args.assembly_version)
            ):
                for key in TESTING_FIELDS:
                    entry.pop(key, None)
        elif testing_snapshot(entry) != testing_before:
            raise SystemExit("stable mode modified testing feed fields without --clear-testing")

    data.sort(key=lambda item: str(item.get("InternalName", "")))
    write_json(feed_path, data)
    status = "updated" if data != original_data else "no changes"
    write_github_output(status)
    print(f"{status}: {internal_name} in {args.mode} mode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
