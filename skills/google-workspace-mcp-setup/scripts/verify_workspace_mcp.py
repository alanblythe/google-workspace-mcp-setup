#!/usr/bin/env python3
"""Verifies Google Workspace MCP setup for Antigravity, ADC scopes, and Gemini Enterprise quota coexistence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from harness_registry import (  # noqa: E402
    ANTIGRAVITY_MCP_LIST_CMD,
    WORKSPACE_SERVICES,
    AccessMode,
    resolve_antigravity_config_path,
)

KEY_TO_SPEC = {spec.mcp_key: spec for spec in WORKSPACE_SERVICES.values()}


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, encoding="utf-8", capture_output=True)


def get_gcloud_identity() -> str:
    res = run_cmd(["gcloud", "config", "get-value", "account"])
    out = res.stdout.strip()
    return out if res.returncode == 0 and out and out != "(unset)" else "Unknown"


def get_adc_token_info() -> dict[str, Any]:
    """Fetches tokeninfo for the active Application Default Credentials token."""
    res = run_cmd(["gcloud", "auth", "application-default", "print-access-token"])
    token = res.stdout.strip()
    if res.returncode != 0 or not token:
        return {}
    url = f"https://oauth2.googleapis.com/tokeninfo?access_token={token}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def check_ge_quota_coexistence() -> tuple[bool, str]:
    """Checks that AGY_ADC_AUTH is not set so Gemini Enterprise seat quota remains active."""
    adc_auth = os.environ.get("AGY_ADC_AUTH", "").strip().lower()
    if adc_auth in ("1", "true", "yes"):
        return (
            False,
            "AGY_ADC_AUTH=true is set in environment; this forces Vertex AI PAYG instead of "
            "Gemini Enterprise seat quota. Unset AGY_ADC_AUTH to use Gemini Enterprise quota.",
        )
    return (
        True,
        "AGY_ADC_AUTH is unset (Antigravity harness uses Gemini Enterprise seat quota while "
        "MCP servers use ADC implicitly via google_credentials).",
    )


def find_configured_workspace_servers(workspace_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Scans Antigravity global and local mcp_config.json files for google-workspace-* entries."""
    found: dict[str, dict[str, Any]] = {}
    for scope in ("global", "local"):
        path = resolve_antigravity_config_path(scope, workspace_root=workspace_root)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            continue
        for key, val in servers.items():
            if key in KEY_TO_SPEC and isinstance(val, dict):
                found[key] = val
    return found


def verify_setup(
    *,
    mode: AccessMode = AccessMode.READONLY,
    workspace_root: Path | None = None,
) -> int:
    print("=== Antigravity Google Workspace MCP Verification ===\n")

    coexists, msg = check_ge_quota_coexistence()
    status_icon = "✅" if coexists else "❌"
    print(f"[1/4] Gemini Enterprise Quota Coexistence: {status_icon} {msg}")

    gcloud_id = get_gcloud_identity()
    token_info = get_adc_token_info()
    adc_email = str(token_info.get("email", "Unknown (ADC not configured)"))
    adc_scopes = set(str(token_info.get("scope", "")).split())

    print("\n[2/4] Identity Consistency:")
    print(f"  gcloud CLI account: {gcloud_id}")
    print(f"  ADC token account:  {adc_email}")
    identity_ok = gcloud_id != "Unknown" and gcloud_id == adc_email
    if identity_ok:
        print("  ✅ gcloud and ADC identities match.")
    else:
        print("  ⚠️ Identity mismatch or ADC not logged in.")

    configured = find_configured_workspace_servers(workspace_root=workspace_root)
    print(f"\n[3/4] Configured Workspace MCP Servers ({len(configured)} found):")
    if not configured:
        print("  ❌ No google-workspace-* servers found in .agents/plugins/google-workspace-mcp-setup/mcp_config.json or global mcp_config.json.")
        return 1

    missing_scopes: list[str] = []
    for key, entry in sorted(configured.items()):
        auth_type = entry.get("authProviderType")
        project = entry.get("headers", {}).get("X-Goog-User-Project") or entry.get("headers", {}).get(
            "x-goog-user-project"
        )
        print(f"  • {key}: authProviderType={auth_type}, project={project}")
        spec = KEY_TO_SPEC[key]
        if adc_scopes:
            ro_scopes = set(spec.scopes_for(AccessMode.READONLY))
            rw_scopes = set(spec.scopes_for(AccessMode.READWRITE))
            required = ro_scopes if mode == AccessMode.READONLY else rw_scopes
            for s in required:
                # A readwrite scope in the token also satisfies readonly mode
                if s not in adc_scopes and not (mode == AccessMode.READONLY and rw_scopes.issubset(adc_scopes)):
                    if s not in missing_scopes:
                        missing_scopes.append(s)

    if missing_scopes:
        print(f"\n  ⚠️ Active ADC token is missing OAuth scopes: {', '.join(missing_scopes)}")
        print("  💡 Re-run setup_workspace_mcp.py with --adc-login to refresh ADC scopes.")
    elif adc_scopes:
        print("  ✅ Active ADC token includes all required Workspace OAuth scopes.")

    print("\n[4/4] Antigravity MCP Registration:")
    res = run_cmd(list(ANTIGRAVITY_MCP_LIST_CMD))
    output = (res.stdout + res.stderr).strip()
    if res.returncode != 0:
        print(f"  ⚠️ Could not run {' '.join(ANTIGRAVITY_MCP_LIST_CMD)} (exit {res.returncode}).")
    else:
        for key in sorted(configured.keys()):
            if key in output:
                print(f"  ✅ {key} registered in Antigravity")
            else:
                print(f"  ⚠️ {key} not listed in Antigravity output")

    return 0 if coexists and bool(configured) else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Antigravity Google Workspace MCP configuration and ADC."
    )
    parser.add_argument(
        "--mode",
        choices=[m.value for m in AccessMode],
        default=AccessMode.READONLY.value,
        help="Expected OAuth scope mode ('readonly' or 'readwrite'). Default: readonly.",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Optional workspace directory to inspect.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    parsed = parse_args()
    sys.exit(
        verify_setup(
            mode=AccessMode(parsed.mode),
            workspace_root=parsed.workspace_root,
        )
    )
