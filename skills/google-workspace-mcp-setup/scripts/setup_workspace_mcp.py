#!/usr/bin/env python3
"""Configures Google Workspace Managed MCP servers for Antigravity.

Uses implicit Application Default Credentials (`"authProviderType": "google_credentials"`)
and per-project IAM (`roles/mcp.toolUser` + `X-Goog-User-Project`) so multiple users in an
organization can share a secret-free `mcp_config.json` while keeping their Gemini Enterprise
Standard/Plus AI-Assisted Dev Tools seat quota intact.
"""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from harness_registry import (  # noqa: E402
    ORDERED_SERVICES,
    WORKSPACE_SERVICES,
    AccessMode,
    WorkspaceServiceSpec,
    aggregate_adc_scopes,
    build_google_credentials_entry,
    decode_config_payload,
    prompt_for_services,
    resolve_antigravity_config_path,
    resolve_selected_services,
)


def run_cmd(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Executes a subprocess command and returns the completed process."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True, encoding="utf-8", capture_output=True)
    if check and result.returncode != 0:
        print(f"Command failed ({result.returncode}): {result.stderr.strip()}", file=sys.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def get_gcloud_account() -> str | None:
    """Returns the active gcloud account email if configured."""
    res = subprocess.run(
        ["gcloud", "config", "get-value", "account"],
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    account = res.stdout.strip()
    if res.returncode == 0 and account and account != "(unset)":
        return account
    return None


def prompt_for_scope() -> str:
    """Interactively prompts the user for local or global installation scope if not specified."""
    if not sys.stdin.isatty():
        print(
            "Error: Neither --local nor --global specified, and stdin is not interactive.\n"
            "Please specify --local (workspace-scoped) or --global (user-scoped).",
            file=sys.stderr,
        )
        sys.exit(2)

    print("\nSelect installation target scope for Google Workspace MCP configuration:")
    print("  [1] local  - Workspace-scoped (.agents/mcp_config.json, safe to commit to git)")
    print("  [2] global - User-scoped (~/.gemini/config/mcp_config.json)")
    while True:
        try:
            choice = input("Enter choice [1/local, 2/global] (default: 1): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            sys.exit(1)
        if not choice or choice in ("1", "local", "l"):
            return "local"
        if choice in ("2", "global", "g"):
            return "global"
        print("Invalid selection. Please enter '1' for local or '2' for global.")


def build_mcp_servers_map(
    specs: list[WorkspaceServiceSpec],
    *,
    project_id: str,
) -> dict[str, dict[str, Any]]:
    """Builds the Antigravity mcpServers dictionary for the selected services."""
    servers: dict[str, dict[str, Any]] = {}
    for spec in specs:
        servers[spec.mcp_key] = build_google_credentials_entry(
            spec,
            project_id=project_id,
        )
    return servers


def compute_updated_config(
    existing_text: str | None,
    new_servers: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """Merges new_servers into existing JSON config text and returns (old_text, new_text)."""
    old_text = existing_text or ""
    data: dict[str, Any] = {}
    if old_text.strip():
        try:
            parsed = json.loads(old_text)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError as exc:
            raise ValueError(f"Existing config file contains invalid JSON: {exc}") from exc

    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    data["mcpServers"].update(new_servers)
    new_text = json.dumps(data, indent=2) + "\n"
    return old_text, new_text


def format_unified_diff(old_text: str, new_text: str, target_path: Path) -> str:
    """Generates a unified diff string for previewing changes."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{target_path}",
        tofile=f"b/{target_path}",
    )
    return "".join(diff)


def run_admin_bootstrap(
    project_id: str,
    specs: list[WorkspaceServiceSpec],
    *,
    principal: str | None,
    dry_run: bool,
) -> None:
    """Enables Workspace MCP services and binds roles/mcp.toolUser on the project."""
    service_names = [s.service_name for s in specs]
    enable_api_cmd = ["gcloud", "services", "enable", *service_names, f"--project={project_id}"]

    if dry_run:
        print(f"[Dry-Run] Would enable APIs: {' '.join(enable_api_cmd)}")
    else:
        run_cmd(enable_api_cmd, check=True)

    member = principal
    if not member:
        acct = get_gcloud_account()
        if acct:
            member = f"user:{acct}"

    if member:
        if ":" not in member:
            member = f"user:{member}"
        for role in ("roles/mcp.toolUser", "roles/serviceusage.serviceUsageConsumer"):
            iam_cmd = [
                "gcloud",
                "projects",
                "add-iam-policy-binding",
                project_id,
                f"--member={member}",
                f"--role={role}",
                "--condition=None",
            ]
            if dry_run:
                print(f"[Dry-Run] Would grant IAM role: {' '.join(iam_cmd)}")
            else:
                run_cmd(iam_cmd, check=False)


def run_adc_login(
    project_id: str,
    specs: list[WorkspaceServiceSpec],
    mode: AccessMode,
    *,
    dry_run: bool,
) -> None:
    """Runs gcloud auth application-default login with required Workspace OAuth scopes."""
    scopes_csv = ",".join(aggregate_adc_scopes(specs, mode))
    login_cmd = [
        "gcloud",
        "auth",
        "application-default",
        "login",
        f"--scopes={scopes_csv}",
    ]
    quota_cmd = [
        "gcloud",
        "auth",
        "application-default",
        "set-quota-project",
        project_id,
    ]
    if dry_run:
        print(f"[Dry-Run] Would authenticate ADC: {' '.join(login_cmd)}")
        print(f"[Dry-Run] Would set ADC quota project: {' '.join(quota_cmd)}")
    else:
        print("\nOpening Google authentication in your browser...")
        res = subprocess.run(login_cmd)
        if res.returncode == 0:
            subprocess.run(quota_cmd, check=False)
            print("✅ Application Default Credentials authenticated and quota project set.")
        else:
            print("⚠️ Application Default Credentials login was not completed.", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure Google Workspace Managed MCP servers for Antigravity with IAM and implicit ADC."
    )
    parser.add_argument(
        "project_id",
        nargs="?",
        default=None,
        help="Google Cloud Project ID used for MCP billing/quota and IAM (optional if --payload is provided).",
    )
    parser.add_argument(
        "--payload",
        default=None,
        help="Base64-encoded configuration payload generated by google-workspace-mcp-admin.",
    )

    scope_group = parser.add_mutually_exclusive_group(required=False)
    scope_group.add_argument(
        "--local",
        action="store_true",
        help="Write workspace-scoped config (.agents/mcp_config.json) safe to commit to git.",
    )
    scope_group.add_argument(
        "--global",
        action="store_true",
        dest="global_config",
        help="Write user-scoped global config (~/.gemini/config/mcp_config.json).",
    )

    parser.add_argument(
        "--services",
        default=None,
        help=(
            "Comma-separated Workspace services to configure "
            "(e.g. 'drive,gmail' or 'all'). "
            "Must not exceed services permitted by administrator. "
            "If omitted, prompts interactively or defaults to all permitted."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=[m.value for m in AccessMode],
        default=None,
        help="OAuth scope access mode for ADC login: 'readonly' (default) or 'readwrite'.",
    )
    parser.add_argument(
        "--admin-bootstrap",
        action="store_true",
        help="Admin step: enable *mcp.googleapis.com APIs and bind roles/mcp.toolUser on the project.",
    )
    parser.add_argument(
        "--principal",
        help=(
            "IAM principal to grant roles/mcp.toolUser during --admin-bootstrap "
            "(e.g. 'group:devs@example.com' or 'user:alice@example.com')."
        ),
    )
    parser.add_argument(
        "--adc-login",
        action="store_true",
        help="Run 'gcloud auth application-default login' with the required Workspace OAuth scopes.",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Target workspace directory when using --local (defaults to current working directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview planned commands and unified config diffs without modifying disk or GCP.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    payload_data: dict[str, Any] | None = None
    if args.payload:
        try:
            payload_data = decode_config_payload(args.payload)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    # Resolve project_id
    project_id = args.project_id
    if payload_data:
        payload_project = payload_data["project_id"]
        if project_id and project_id != payload_project:
            print(
                f"Error: Specified project_id '{project_id}' does not match payload project_id '{payload_project}'.",
                file=sys.stderr,
            )
            return 2
        project_id = payload_project
    elif not project_id:
        print("Error: Either project_id or --payload must be provided.", file=sys.stderr)
        return 2

    # Resolve mode: CLI flag overrides payload; payload overrides default
    if args.mode:
        mode = AccessMode(args.mode)
    elif payload_data and "mode" in payload_data:
        mode = AccessMode(payload_data["mode"])
    else:
        mode = AccessMode.READONLY

    # Confirm admin settings if payload was provided
    allowed_slugs = payload_data["allowed_services"] if payload_data else None
    if payload_data:
        service_names = ", ".join(WORKSPACE_SERVICES[s].slug for s in allowed_slugs)
        print("\n📋 Administrator Configuration Received:")
        print(f"   GCP Project:      {project_id}")
        print(f"   Allowed Services: {service_names}")
        print(f"   Default Mode:     {mode.value}")

    # Resolve services & enforce administrator boundaries
    services_arg = args.services
    if services_arg is not None:
        try:
            requested_specs = resolve_selected_services(services_arg)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

        if allowed_slugs is not None:
            allowed_set = set(allowed_slugs)
            forbidden = [s.slug for s in requested_specs if s.slug not in allowed_set]
            if forbidden:
                forbidden_str = ", ".join(repr(s) for s in forbidden)
                allowed_str = ", ".join(allowed_slugs)
                print(
                    f"Error: Service(s) {forbidden_str} cannot be configured because your administrator has not enabled them for project '{project_id}'.\n"
                    f"Permitted services: {allowed_str}",
                    file=sys.stderr,
                )
                return 2
        specs = requested_specs
    else:
        if sys.stdin.isatty():
            prompt_title = (
                "Select services to configure (you may deselect any you do not need):"
                if allowed_slugs is not None
                else "Select Google Workspace services to configure:"
            )
            selected_str = prompt_for_services(allowed_slugs=allowed_slugs, title=prompt_title)
            specs = resolve_selected_services(selected_str)
        else:
            if allowed_slugs is not None:
                specs = [WORKSPACE_SERVICES[s] for s in allowed_slugs]
            else:
                specs = resolve_selected_services("default")

    if args.local:
        scope = "local"
    elif args.global_config:
        scope = "global"
    else:
        scope = prompt_for_scope()

    if args.admin_bootstrap:
        run_admin_bootstrap(
            project_id,
            specs,
            principal=args.principal,
            dry_run=args.dry_run,
        )

    if args.adc_login:
        run_adc_login(project_id, specs, mode, dry_run=args.dry_run)

    target_path = resolve_antigravity_config_path(scope, workspace_root=args.workspace_root)
    new_servers = build_mcp_servers_map(
        specs,
        project_id=project_id,
    )

    existing_text = target_path.read_text(encoding="utf-8") if target_path.exists() else None
    old_text, new_text = compute_updated_config(existing_text, new_servers)
    diff = format_unified_diff(old_text, new_text, target_path)

    if args.dry_run:
        print(f"\n[Dry-Run] Planned changes for {target_path}:")
        print(diff if diff else "  (no changes — already up to date)")
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_text, encoding="utf-8")
        print(f"Updated {target_path} ({len(new_servers)} Workspace MCP servers configured).")

    print("\n======================================================================")
    print(f"Workspace MCP Configuration Complete (project: {project_id}, mode: {mode.value})")
    print(f"Services: {', '.join(s.slug for s in specs)}")
    print("======================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
