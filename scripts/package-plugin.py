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
from pathlib import PurePosixPath


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
    return None


def find_build_output_dir(project: Path, configuration: str, internal_name: str) -> Path:
    project_dir = project.parent
    candidates = [
        project_dir / "bin" / configuration,
        project_dir / "bin" / "x64" / configuration,
    ]
    for candidate in candidates:
        if (candidate / f"{internal_name}.dll").exists() and (candidate / f"{internal_name}.json").exists():
            return candidate

    raise SystemExit(f"Build output was not found for {internal_name} {configuration}")


def manifest_from_zip(zip_path: Path, internal_name: str) -> dict[str, object] | None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        for name in archive.namelist():
            if Path(name).name == f"{internal_name}.json":
                return json.loads(archive.read(name).decode("utf-8"))
    return None


def package_cache_dir() -> Path:
    return Path(os.environ.get("NUGET_PACKAGES", Path.home() / ".nuget" / "packages"))


def dependency_asset_source(library_name: str, asset: str) -> Path | None:
    if "/" not in library_name:
        return None

    package_id, version = library_name.split("/", 1)
    candidate = package_cache_dir() / package_id.lower() / version / PurePosixPath(asset)
    return candidate if candidate.exists() else None


def build_output_zip(project: Path, configuration: str, internal_name: str, zip_output: Path) -> None:
    build_output = find_build_output_dir(project, configuration, internal_name)
    deps_path = build_output / f"{internal_name}.deps.json"
    added: set[str] = set()
    with zipfile.ZipFile(zip_output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(build_output.rglob("*")):
            if not path.is_file() or path.name == "latest.zip":
                continue

            archive_name = path.relative_to(build_output).as_posix()
            archive.write(path, archive_name)
            added.add(archive_name)

        if not deps_path.exists():
            return

        deps = json.loads(deps_path.read_text(encoding="utf-8"))
        for target in deps.get("targets", {}).values():
            for library_name, library in target.items():
                for section in ("runtime", "runtimeTargets"):
                    for asset in library.get(section, {}):
                        archive_name = asset if asset.startswith("runtimes/") else PurePosixPath(asset).name
                        if archive_name in added:
                            continue

                        source = dependency_asset_source(library_name, asset)
                        if source is None:
                            continue

                        archive.write(source, archive_name)
                        added.add(archive_name)


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
            build_args.append(f"-p:AssemblyVersion={args.version}")
            build_args.append(f"-p:FileVersion={args.version}")
            build_args.append(f"-p:InformationalVersion={args.version}")
        run(build_args)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_output = output_dir / f"{internal_name}.zip"
    json_output = output_dir / f"{internal_name}.json"

    packager_zip = find_packager_zip(project, args.configuration, internal_name)
    if packager_zip is None:
        build_output_zip(project, args.configuration, internal_name, zip_output)
    else:
        shutil.copyfile(packager_zip, zip_output)

    built_manifest = manifest_from_zip(zip_output, internal_name) or source_manifest
    if args.version and str(built_manifest.get("AssemblyVersion", "")) != args.version:
        raise SystemExit(
            f"Built manifest AssemblyVersion {built_manifest.get('AssemblyVersion')} "
            f"does not match expected {args.version}"
        )

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
