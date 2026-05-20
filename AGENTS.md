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
- Manual testing updates may only touch testing fields:
  - `TestingAssemblyVersion`
  - `TestingDalamudApiLevel`
  - `DownloadLinkTesting`
- Full testing release notes belong on the GitHub prerelease page, not in `pluginmaster.json`.
- Stable field updates may only come from the manual stable release workflow.
- Stable release updates may touch:
  - `AssemblyVersion`
  - `DownloadLinkInstall`
  - `DownloadLinkUpdate`
- Full stable release notes belong on the GitHub Release page, not in `pluginmaster.json`.

## Shared Automation

- Reusable plugin workflows live in `.github/workflows/`.
- Helper scripts live in `scripts/` and are shared by `XelsTweaks` and `XelsCombatAI`.
- Testing publication uses a mutable prerelease tagged `testing`; do not restore `pr-*` release tags to feed generation.
- Stable releases use immutable `vX.Y.Z` tags.
