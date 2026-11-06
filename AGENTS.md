# Repository Agent Guidelines (`AGENTS.md`)

This repository provides the `google-workspace-mcp-setup` AAIF skill, Antigravity plugin (`plugin.json`), and Python CLI for configuring Google Workspace Managed MCP servers in Antigravity using implicit Application Default Credentials (`"authProviderType": "google_credentials"`) and Google Cloud IAM (`roles/mcp.toolUser`).

## Engineering Standards

- **Antigravity & AAIF Compliance**:
  - Canonical instructions live in root `AGENTS.md` (with `GEMINI.md` symlinked to `AGENTS.md`).
  - Canonical skill definitions live in `skills/google-workspace-mcp-setup/SKILL.md` (developer skill) and `skills/google-workspace-mcp-admin/SKILL.md` (admin skill), both self-contained for `npx skills` discovery (`-s <skill-name>`) and exposed under `.agents/skills/`.
  - Root `plugin.json` adheres to the Antigravity plugin specification.
  - Antigravity MCP configurations are written strictly to `.agents/plugins/google-workspace-mcp-setup/mcp_config.json` (`--local`) or `~/.antigravity/config/mcp_config.json` / `~/.gemini/config/mcp_config.json` (`--global`), conforming to `https://antigravity.google/schemas/mcp_config.json`.
- **Language & Runtime**: Pure Python 3.11+ standard library (`from __future__ import annotations`, `dataclasses`, `pathlib`, `unittest`). Zero external PyPI dependencies.
- **Portability & Security**:
  - Never hardcode usernames, corporate domains, or user-specific home paths; always resolve dynamically via `Path.home()` and `os.environ.get("USER")`.
  - Never write OAuth Client Secrets to `mcp_config.json`. Always use `"authProviderType": "google_credentials"` and `"X-Goog-User-Project"`.
- **Testing & Idempotency**:
  - Run unit tests via `python3 -m unittest discover -s tests -v`.
  - All configuration updates must be strictly idempotent: running the setup script twice with the same arguments produces zero diff on the second run.
