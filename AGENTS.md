# AGENTS.md

## Scope

These instructions apply to the custom Dalamud feed repository.

## Feed Rules

- Do not manually edit generated `pluginmaster.json` unless fixing generation.
- Update `repos.txt` when adding a plugin repository.
- Do not remove plugin entries without explicit instruction.
- The feed must remain valid JSON.
- Download URLs must be public and reachable without authentication.
- Do not use GitHub Actions artifacts as download URLs.
- PR preview updates may only touch testing fields:
  - `TestingAssemblyVersion`
  - `TestingChangelog`
  - `TestingDalamudApiLevel`
  - `DownloadLinkTesting`
- Stable field updates may only come from the manual stable release workflow.
- Stable release updates may touch:
  - `AssemblyVersion`
  - `DownloadLinkInstall`
  - `DownloadLinkUpdate`
  - stable changelog/release metadata

