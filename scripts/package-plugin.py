#!/usr/bin/env python3
"""Normalize DalamudPackager output into release assets."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path


def run(args: list[str]) -> None:
    result = subprocess.run(args, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def read_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_manifest(project: Path, internal_name: str | None) -> Path:
    project_dir = project.parent
    candidates = sorted(project_dir.glob("*.json"))
    if internal_name:
        preferred = project_dir / f"{internal_name}.json"
        if preferred.exists():
            return preferred

    for candidate in candidates:
        try:
            manifest = read_manifest(candidate)
        except json.JSONDecodeError:
            continue
        if "InternalName" in manifest:
            return candidate

    raise SystemExit(f"No Dalamud manifest JSON found beside {project}")


def find_packager_zip(project: Path, configuration: str, internal_name: str) -> Path | None:
    project_dir = project.parent
    candidates = [
        project_dir / "bin" / configuration / internal_name / "latest.zip",
        project_dir / "bin" / "x64" / configuration / internal_name / "latest.zip",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    found = sorted((project_dir / "bin").glob(f"**/{internal_name}/latest.zip"))
    return found[-1] if found else None


def manifest_from_zip(zip_path: Path, internal_name: str) -> dict[str, object] | None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        for name in archive.namelist():
            if Path(name).name == f"{internal_name}.json":
                return json.loads(archive.read(name).decode("utf-8"))
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--configuration", default="Release")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--internal-name", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()

    project = Path(args.project).resolve()
    if not project.exists():
        raise SystemExit(f"Project not found: {project}")

    source_manifest_path = find_manifest(project, args.internal_name or None)
    source_manifest = read_manifest(source_manifest_path)
    internal_name = args.internal_name or str(source_manifest["InternalName"])

    if not args.no_build:
        build_args = ["dotnet", "build", str(project), "-c", args.configuration, "-p:EnableWindowsTargeting=true"]
        if args.version:
            build_args.append(f"-p:Version={args.version}")
        run(build_args)

    packager_zip = find_packager_zip(project, args.configuration, internal_name)
    if packager_zip is None:
        raise SystemExit(f"DalamudPackager did not produce latest.zip for {internal_name}")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_output = output_dir / f"{internal_name}.zip"
    json_output = output_dir / f"{internal_name}.json"

    shutil.copyfile(packager_zip, zip_output)
    built_manifest = manifest_from_zip(packager_zip, internal_name) or source_manifest
    json_output.write_text(json.dumps(built_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"internal_name={internal_name}")
    print(f"zip={zip_output}")
    print(f"manifest={json_output}")

    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
            handle.write(f"internal_name={internal_name}\n")
            handle.write(f"zip={zip_output}\n")
            handle.write(f"manifest={json_output}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
