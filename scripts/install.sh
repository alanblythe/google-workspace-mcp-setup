#!/usr/bin/env bash
# Symlinks google-workspace-mcp-setup and google-workspace-mcp-admin into ~/.gemini/config/skills/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="${HOME}/.gemini/config/skills"

mkdir -p "${TARGET_DIR}"
ln -sfn "${REPO_DIR}/skills/google-workspace-mcp-setup" "${TARGET_DIR}/google-workspace-mcp-setup"
ln -sfn "${REPO_DIR}/skills/google-workspace-mcp-admin" "${TARGET_DIR}/google-workspace-mcp-admin"

echo "Installed google-workspace-mcp-setup skill -> ${TARGET_DIR}/google-workspace-mcp-setup"
echo "Installed google-workspace-mcp-admin skill -> ${TARGET_DIR}/google-workspace-mcp-admin"
