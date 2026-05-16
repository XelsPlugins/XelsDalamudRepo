#!/usr/bin/env python3
"""Rebuild pluginmaster.json from public GitHub release assets."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STABLE_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:\.(?P<build>\d+))?$")
PREVIEW_TAG_RE = re.compile(r"^pr-(?P<number>\d+)$")


@dataclass(frozen=True)
class ReleaseInfo:
    repo: str
    tag: str
    prerelease: bool
    draft: bool
    body: str
    assets: list[dict[str, Any]]


def gh_json(args: list[str]) -> Any:
    result = subprocess.run(["gh", *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def read_repos(path: Path) -> list[str]:
    repos: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped:
            repos.append(stripped)
    return repos


def release_version_key(tag: str) -> tuple[int, int, int, int]:
    match = STABLE_TAG_RE.match(tag)
    if not match:
        return (-1, -1, -1, -1)
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        int(match.group("build") or 0),
    )


def assembly_version_key(value: object) -> tuple[int, int, int, int]:
    numbers = [int(part) for part in str(value).split(".") if part.isdigit()]
    while len(numbers) < 4:
        numbers.append(0)
    return tuple(numbers[:4])


def load_releases(repo: str) -> list[ReleaseInfo]:
    raw = gh_json(["api", f"repos/{repo}/releases", "--paginate"])
    releases = []
    for item in raw:
        releases.append(
            ReleaseInfo(
                repo=repo,
                tag=item["tag_name"],
                prerelease=bool(item.get("prerelease")),
                draft=bool(item.get("draft")),
                body=item.get("body") or "",
                assets=item.get("assets") or [],
            )
        )
    return releases


def download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response:
        destination.write_bytes(response.read())


def manifest_from_assets(release: ReleaseInfo) -> tuple[dict[str, Any], str]:
    json_assets = [asset for asset in release.assets if asset.get("name", "").endswith(".json")]
    zip_assets = [asset for asset in release.assets if asset.get("name", "").endswith(".zip")]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for asset in json_assets:
            destination = tmp_path / asset["name"]
            download(asset["browser_download_url"], destination)
            manifest = json.loads(destination.read_text(encoding="utf-8"))
            if "InternalName" in manifest:
                zip_url = next((zip_asset["browser_download_url"] for zip_asset in zip_assets), "")
                return manifest, zip_url

        for asset in zip_assets:
            destination = tmp_path / asset["name"]
            download(asset["browser_download_url"], destination)
            with zipfile.ZipFile(destination, "r") as archive:
                for name in archive.namelist():
                    if name.endswith(".json"):
                        manifest = json.loads(archive.read(name).decode("utf-8"))
                        if "InternalName" in manifest:
                            return manifest, asset["browser_download_url"]

    raise RuntimeError(f"No manifest/zip assets found for {release.repo} {release.tag}")


def base_entry(manifest: dict[str, Any], repo: str, download_url: str, changelog: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
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
        "LastUpdate": 0,
        "DownloadLinkInstall": download_url,
        "DownloadLinkUpdate": download_url,
        "DownloadLinkTesting": "",
        "RepoUrl": f"https://github.com/{repo}",
    }

    for key in ["IconUrl", "Tags", "CategoryTags", "ImageUrls", "MinimumDalamudVersion"]:
        if key in manifest:
            entry[key] = manifest[key]
    if changelog:
        entry["Changelog"] = changelog
    return entry


def add_testing(entry: dict[str, Any], release: ReleaseInfo) -> None:
    manifest, download_url = manifest_from_assets(release)
    stable_version = assembly_version_key(entry["AssemblyVersion"])
    testing_version = assembly_version_key(manifest["AssemblyVersion"])
    if testing_version <= stable_version:
        return

    entry["TestingAssemblyVersion"] = str(manifest["AssemblyVersion"])
    entry["TestingChangelog"] = release.body
    entry["TestingDalamudApiLevel"] = int(manifest.get("DalamudApiLevel", entry.get("DalamudApiLevel", 0)))
    entry["DownloadLinkTesting"] = download_url


def build_entries(repo: str) -> list[dict[str, Any]]:
    releases = [release for release in load_releases(repo) if not release.draft]
    stable_releases = [
        release for release in releases
        if not release.prerelease and STABLE_TAG_RE.match(release.tag)
    ]
    if not stable_releases:
        print(f"warning: {repo} has no stable release; skipping feed entry", file=sys.stderr)
        return []

    stable = max(stable_releases, key=lambda release: release_version_key(release.tag))
    manifest, download_url = manifest_from_assets(stable)
    entry = base_entry(manifest, repo, download_url, stable.body)

    previews = [
        release for release in releases
        if release.prerelease and PREVIEW_TAG_RE.match(release.tag)
    ]
    previews.sort(key=lambda release: int(PREVIEW_TAG_RE.match(release.tag).group("number")), reverse=True)
    for preview in previews:
        try:
            before = dict(entry)
            add_testing(entry, preview)
            if entry != before:
                break
        except Exception as exc:  # noqa: BLE001 - defensive feed generation
            print(f"warning: failed to read preview {repo} {preview.tag}: {exc}", file=sys.stderr)

    return [entry]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repos", default="repos.txt")
    parser.add_argument("--output", default="pluginmaster.json")
    args = parser.parse_args()

    repos = read_repos(Path(args.repos))
    entries: list[dict[str, Any]] = []
    failed = 0
    for repo in repos:
        try:
            entries.extend(build_entries(repo))
        except Exception as exc:  # noqa: BLE001 - continue broken plugin repos
            failed += 1
            print(f"warning: failed to update {repo}: {exc}", file=sys.stderr)

    if repos and failed == len(repos):
        raise SystemExit("all plugin repositories failed")

    entries.sort(key=lambda item: str(item.get("InternalName", "")))
    output = Path(args.output)
    output.write_text(json.dumps(entries, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    json.loads(output.read_text(encoding="utf-8"))
    print(f"Wrote {output} with {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
