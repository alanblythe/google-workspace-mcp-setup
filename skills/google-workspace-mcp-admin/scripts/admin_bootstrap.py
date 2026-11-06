#!/usr/bin/env python3
"""Bootstraps a Google Cloud project for Google Workspace Managed MCP servers.

Intended for GCP Project Owners / IAM Administrators.
Enables remote MCP APIs (*mcp.googleapis.com), binds roles/mcp.toolUser to team
members or Google Groups, generates a base64 JSON configuration payload, and
outputs two copy-pasteable Developer Onboarding Prompts (1: install skill,
2: use skill with payload).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from harness_registry import (  # noqa: E402
    AccessMode,
    WorkspaceServiceSpec,
    encode_config_payload,
    prompt_for_services,
    resolve_selected_services,
)

GITHUB_REPO_URL = "https://github.com/alanblythe/google-workspace-mcp-setup"


def run_cmd(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Executes a command and checks result."""
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


def check_prerequisites() -> int:
    """Verifies environment prerequisites (Python 3.11+, gcloud CLI, active gcloud auth).

    Returns 0 if all prerequisites pass, non-zero if critical tools are missing.
    """
    print("\n" + "=" * 72)
    print("🔍 Google Workspace MCP Admin: Prerequisites Check")
    print("=" * 72)

    has_errors = False

    # 1. Python version check
    py_ver = sys.version_info
    py_str = f"v{py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    if py_ver >= (3, 11):
        print(f"[✓] Python: 3.11+ detected ({py_str})")
    else:
        print(f"[✗] Python: Incompatible version {py_str}. Python 3.11+ is required.")
        has_errors = True

    # 2. gcloud CLI presence
    gcloud_path = shutil.which("gcloud")
    if gcloud_path:
        res = subprocess.run(
            ["gcloud", "--version"],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        version_line = res.stdout.strip().splitlines()[0] if res.stdout else "version unknown"
        print(f"[✓] gcloud CLI: {gcloud_path} ({version_line})")

        # 3. gcloud active account
        account = get_gcloud_account()
        if account:
            print(f"[✓] gcloud account: {account} (active)")
        else:
            print("[!] gcloud account: No active account configured.")
            print("    Please authenticate with: gcloud auth login")
            has_errors = True
    else:
        print("[✗] gcloud CLI: Not found in PATH.")
        print("    Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install")
        has_errors = True

    print("=" * 72)
    if has_errors:
        print("❌ One or more prerequisites require attention before continuing.\n")
        return 1

    print("✨ All prerequisites verified! You are ready to bootstrap GCP projects.\n")
    return 0


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
                run_cmd(iam_cmd, check=True)


def format_install_skill_prompt() -> str:
    """Builds Prompt 1: instructs the client user to install the developer skill."""
    return (
        f"Install the google-workspace-mcp-setup skill: "
        f"npx skills add {GITHUB_REPO_URL} -s google-workspace-mcp-setup -a antigravity"
    )


def format_configure_skill_prompt(payload: str) -> str:
    """Builds Prompt 2: starts with using the skill with the base64 JSON payload."""
    return (
        f"Use the google-workspace-mcp-setup skill with payload {payload} "
        "to configure Google Workspace MCP."
    )


def format_developer_prompts(payload: str) -> tuple[str, str]:
    """Returns (install_prompt, configure_prompt) for client user onboarding."""
    return format_install_skill_prompt(), format_configure_skill_prompt(payload)


def print_developer_handoff_box(
    project_id: str,
    payload: str,
    specs: list[WorkspaceServiceSpec],
    mode: AccessMode = AccessMode.READONLY,
) -> None:
    """Prints the final formatted developer onboarding instructions with two prompts."""
    install_prompt, configure_prompt = format_developer_prompts(payload)
    service_names = ", ".join(s.slug for s in specs)

    print("\n" + "=" * 72)
    print("📢 ADMIN BOOTSTRAP COMPLETE — DEVELOPER ONBOARDING HAND-OFF")
    print("=" * 72)
    print("Share the following two prompts with your development team (via Slack,")
    print("Chat, PR description, or your team's onboarding wiki):\n")
    print("------------------------------------------------------------------------")
    print(f"Hey team! Google Workspace MCP has been bootstrapped for our project ({project_id}).")
    print(f"Enabled services ({len(specs)}): {service_names} (default mode: {mode.value})\n")
    print("Prompt 1 — Install the Google Workspace MCP setup skill:")
    print(f'  "{install_prompt}"\n')
    print("Prompt 2 — Configure Google Workspace MCP with the base64 JSON payload:")
    print(f'  "{configure_prompt}"')
    print("  (Note: The skill will ask you whether to install locally in this repo or globally for your user)\n")
    print("------------------------------------------------------------------------")
    print("=" * 72)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap Google Cloud project for Google Workspace Managed MCP servers (Admin)."
    )
    parser.add_argument(
        "project_id",
        nargs="?",
        default=None,
        help="Google Cloud Project ID to bootstrap for Workspace MCP (optional when using --check-prereqs).",
    )
    parser.add_argument(
        "--check-prereqs",
        action="store_true",
        help="Verify environment prerequisites (Python 3.11+, gcloud CLI, active gcloud auth) and exit.",
    )
    parser.add_argument(
        "--principal",
        help=(
            "IAM principal to grant roles/mcp.toolUser (e.g. 'group:devs@example.com' or 'user:alice@example.com'). "
            "Defaults to active gcloud account."
        ),
    )
    parser.add_argument(
        "--services",
        default=None,
        help="Comma-separated Workspace services to enable (default: interactive selector or core 6).",
    )
    parser.add_argument(
        "--mode",
        choices=[m.value for m in AccessMode],
        default=AccessMode.READONLY.value,
        help="Access mode to specify in developer instructions: 'readonly' (default) or 'readwrite'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview planned gcloud commands and hand-off prompt without modifying GCP.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.check_prereqs:
        return check_prerequisites()

    if not args.project_id:
        print("Error: Project ID is required unless running with --check-prereqs.", file=sys.stderr)
        print("Usage: python3 admin_bootstrap.py <PROJECT_ID> [options]", file=sys.stderr)
        print("   or: python3 admin_bootstrap.py --check-prereqs", file=sys.stderr)
        return 2

    services_arg = args.services
    if services_arg is None:
        if sys.stdin.isatty():
            services_arg = prompt_for_services(
                title="Select Google Workspace services to enable on GCP project:"
            )
        else:
            services_arg = "default"

    try:
        specs = resolve_selected_services(services_arg)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    mode = AccessMode(args.mode)
    payload = encode_config_payload(args.project_id, [s.slug for s in specs], mode)

    print(f"Bootstrapping GCP project '{args.project_id}' for Google Workspace MCP...")
    run_admin_bootstrap(
        args.project_id,
        specs,
        principal=args.principal,
        dry_run=args.dry_run,
    )

    print_developer_handoff_box(args.project_id, payload, specs, mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
