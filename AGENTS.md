# AGENTS.md

## Scope

These instructions apply to the custom Dalamud feed repository.

## Agent Instruction Standards

- Treat this file as the durable repository instruction source for coding agents.
- Keep instructions concrete and verifiable. Prefer exact commands, paths, ownership boundaries, and review expectations over broad preferences.
- Keep user-facing repository usage in `README.md`; keep build, release, automation, and agent workflow rules in `AGENTS.md`.
- Do not add task-specific notes, transient plans, or duplicate large instruction blocks here.
- Do not use alternate instruction filenames unless Codex has been explicitly configured to discover them.

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
- Full testing release notes belong on the GitHub prerelease page, not in `pluginmaster.json` changelog fields.
- Stable field updates may only come from the manual stable release workflow.
- Stable release updates may touch:
  - `AssemblyVersion`
  - `DownloadLinkInstall`
  - `DownloadLinkUpdate`
- Full stable release notes belong on the GitHub Release page, not in `pluginmaster.json` changelog fields.

## Shared Automation

- Reusable plugin workflows live in `.github/workflows/`.
- Helper scripts live in `scripts/` and are shared by `XelsTweaks` and `XelsCombatAI`.
- Testing publication uses a mutable prerelease tagged `testing`; do not restore `pr-*` release tags to feed generation.
- Stable releases use immutable `vX.Y.Z` tags.

## Commit Message Standards

Use Conventional Commits for all agent-authored commits. The release automation validates non-merge commit subjects on pushes to `main` and before publishing testing or stable builds.

- Use `fix:` or `perf:` for patch-level user-facing changes.
- Use `feat:` for minor user-facing additions.
- Use `type!:` or a `BREAKING CHANGE:` footer for major changes.
- Use `docs:`, `style:`, `refactor:`, `test:`, `build:`, `ci:`, or `chore:` for changes that should not create a user-facing stable bump unless breaking.
- Do not prefix commit subjects with `[codex]`.
- Keep the subject concise, imperative, and clear about the user or automation impact.

Examples:

- `fix: keep testing versions monotonic`
- `feat: add manual testing publish workflow`
- `ci: validate release commit messages`
- `docs: clarify custom feed release process`
- `chore: update pluginmaster`
