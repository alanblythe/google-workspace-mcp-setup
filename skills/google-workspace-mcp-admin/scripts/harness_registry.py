from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class AccessMode(str, Enum):
    """OAuth scope access mode for Google Workspace MCP tools."""

    READONLY = "readonly"
    READWRITE = "readwrite"


@dataclass(frozen=True)
class WorkspaceServiceSpec:
    """Specification for a 1P Google Workspace Managed MCP service."""

    slug: str
    mcp_key: str
    service_name: str
    endpoint_url: str
    readonly_scopes: tuple[str, ...]
    readwrite_scopes: tuple[str, ...]

    def scopes_for(self, mode: AccessMode) -> list[str]:
        base = ["https://www.googleapis.com/auth/cloud-platform"]
        extra = (
            self.readonly_scopes
            if mode == AccessMode.READONLY
            else self.readwrite_scopes
        )
        return base + list(extra)


WORKSPACE_SERVICES: dict[str, WorkspaceServiceSpec] = {
    "drive": WorkspaceServiceSpec(
        slug="drive",
        mcp_key="google-workspace-drive",
        service_name="drivemcp.googleapis.com",
        endpoint_url="https://drivemcp.googleapis.com/mcp/v1",
        readonly_scopes=("https://www.googleapis.com/auth/drive.readonly",),
        readwrite_scopes=("https://www.googleapis.com/auth/drive",),
    ),
    "gmail": WorkspaceServiceSpec(
        slug="gmail",
        mcp_key="google-workspace-gmail",
        service_name="gmailmcp.googleapis.com",
        endpoint_url="https://gmailmcp.googleapis.com/mcp/v1",
        readonly_scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        readwrite_scopes=("https://www.googleapis.com/auth/gmail.modify",),
    ),
    "calendar": WorkspaceServiceSpec(
        slug="calendar",
        mcp_key="google-workspace-calendar",
        service_name="calendarmcp.googleapis.com",
        endpoint_url="https://calendarmcp.googleapis.com/mcp/v1",
        readonly_scopes=("https://www.googleapis.com/auth/calendar.readonly",),
        readwrite_scopes=("https://www.googleapis.com/auth/calendar",),
    ),
    "docs": WorkspaceServiceSpec(
        slug="docs",
        mcp_key="google-workspace-docs",
        service_name="docsmcp.googleapis.com",
        endpoint_url="https://docsmcp.googleapis.com/mcp/v1",
        readonly_scopes=("https://www.googleapis.com/auth/documents.readonly",),
        readwrite_scopes=("https://www.googleapis.com/auth/documents",),
    ),
    "sheets": WorkspaceServiceSpec(
        slug="sheets",
        mcp_key="google-workspace-sheets",
        service_name="sheetsmcp.googleapis.com",
        endpoint_url="https://sheetsmcp.googleapis.com/mcp/v1",
        readonly_scopes=("https://www.googleapis.com/auth/spreadsheets.readonly",),
        readwrite_scopes=("https://www.googleapis.com/auth/spreadsheets",),
    ),
    "slides": WorkspaceServiceSpec(
        slug="slides",
        mcp_key="google-workspace-slides",
        service_name="slidesmcp.googleapis.com",
        endpoint_url="https://slidesmcp.googleapis.com/mcp/v1",
        readonly_scopes=("https://www.googleapis.com/auth/presentations.readonly",),
        readwrite_scopes=("https://www.googleapis.com/auth/presentations",),
    ),
    "chat": WorkspaceServiceSpec(
        slug="chat",
        mcp_key="google-workspace-chat",
        service_name="chatmcp.googleapis.com",
        endpoint_url="https://chatmcp.googleapis.com/mcp/v1",
        readonly_scopes=("https://www.googleapis.com/auth/chat.messages.readonly",),
        readwrite_scopes=("https://www.googleapis.com/auth/chat.messages",),
    ),
}

ORDERED_SERVICES: list[tuple[str, str, str]] = [
    ("drive", "Google Drive", "Files, folders, search, export"),
    ("gmail", "Gmail", "Messages, threads, labels, drafts"),
    ("calendar", "Google Calendar", "Events, schedules, meetings"),
    ("docs", "Google Docs", "Document creation and formatting"),
    ("sheets", "Google Sheets", "Spreadsheets, workbooks, grid data"),
    ("slides", "Google Slides", "Presentations, slides, layouts"),
    ("chat", "Google Chat", "Chat spaces, direct messages"),
]

DEFAULT_SERVICE_SLUGS: tuple[str, ...] = (
    "drive",
    "gmail",
    "calendar",
    "docs",
    "sheets",
    "slides",
)

WORKSPACE_PLUGIN_NAME = "google-workspace-mcp-setup"
WORKSPACE_PLUGIN_DIR_REL_PATH = f".agents/plugins/{WORKSPACE_PLUGIN_NAME}"
ANTIGRAVITY_LOCAL_REL_PATH = f"{WORKSPACE_PLUGIN_DIR_REL_PATH}/mcp_config.json"
ANTIGRAVITY_LOCAL_PLUGIN_MANIFEST_REL_PATH = f"{WORKSPACE_PLUGIN_DIR_REL_PATH}/plugin.json"
ANTIGRAVITY_GLOBAL_REL_PATH = "config/mcp_config.json"
ANTIGRAVITY_MCP_LIST_CMD: tuple[str, ...] = ("agy", "mcp", "list")


def build_workspace_plugin_manifest() -> dict[str, Any]:
    """Generates the workspace plugin.json marker required for Antigravity discovery."""
    return {
        "name": WORKSPACE_PLUGIN_NAME,
        "description": "Google Workspace Managed MCP integration",
        "version": "1.0.0",
    }


def probe_running_agy_gemini_dir(home: Path) -> Path | None:
    """Probes running processes to check if agy was launched with --gemini_dir."""
    try:
        proc = subprocess.run(
            ["ps", "-eo", "args"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        for line in proc.stdout.splitlines():
            if "agy" in line and "--gemini_dir" in line:
                match = re.search(r"--gemini_dir[=\s]([^\s]+)", line)
                if match:
                    raw_path = match.group(1).strip("'\"")
                    p = Path(raw_path).expanduser()
                    return p.resolve() if p.is_absolute() else (home / p).resolve()
    except Exception:
        return None
    return None


def resolve_antigravity_gemini_dir(
    *,
    gemini_dir_arg: Path | str | None = None,
    home_dir: Path | None = None,
) -> Path:
    """Discovers the active Antigravity root directory (--gemini_dir).

    Discovery precedence:
    1. Explicit CLI / function argument (`--gemini-dir`)
    2. Environment variables (`ANTIGRAVITY_GEMINI_DIR`, `GEMINI_DIR`)
    3. Active running process inspection (`agy --gemini_dir=...`)
    4. Filesystem probe (`~/.antigravity` if existing config, else `~/.gemini`)
    5. Default fallback (`~/.gemini`)
    """
    if gemini_dir_arg:
        p = Path(gemini_dir_arg).expanduser()
        return p.resolve() if p.is_absolute() else (home_dir or Path.home()).resolve() / p

    for env_var in ("ANTIGRAVITY_GEMINI_DIR", "GEMINI_DIR"):
        val = os.environ.get(env_var)
        if val and val.strip():
            p = Path(val.strip()).expanduser()
            return p.resolve() if p.is_absolute() else (home_dir or Path.home()).resolve() / p

    home = (home_dir or Path.home()).resolve()

    proc_dir = probe_running_agy_gemini_dir(home)
    if proc_dir:
        return proc_dir

    if (home / ".antigravity" / "config").exists():
        return home / ".antigravity"
    if (home / ".gemini" / "config").exists():
        return home / ".gemini"

    return home / ".gemini"


def build_google_credentials_entry(
    spec: WorkspaceServiceSpec,
    *,
    project_id: str,
) -> dict[str, Any]:
    """Builds an Antigravity mcp_config.json server entry using google_credentials.

    Conforms strictly to https://antigravity.google/schemas/mcp_config.json
    (additionalProperties: false). OAuth scopes are requested during
    `gcloud auth application-default login --scopes=...` and stored in the user's
    local ADC token rather than inside mcp_config.json.
    """
    return {
        "serverUrl": spec.endpoint_url,
        "authProviderType": "google_credentials",
        "headers": {
            "X-Goog-User-Project": project_id,
        },
    }


def resolve_antigravity_config_path(
    scope: str,
    *,
    workspace_root: Path | None = None,
    gemini_dir: Path | str | None = None,
    home_dir: Path | None = None,
) -> Path:
    """Resolves the target Antigravity mcp_config.json path for 'local' or 'global' scope."""
    if scope == "local":
        root = workspace_root or Path.cwd()
        return root / ANTIGRAVITY_LOCAL_REL_PATH
    if scope == "global":
        active_gemini_dir = resolve_antigravity_gemini_dir(
            gemini_dir_arg=gemini_dir,
            home_dir=home_dir,
        )
        return active_gemini_dir / ANTIGRAVITY_GLOBAL_REL_PATH
    raise ValueError(f"Unsupported scope: {scope}")


def resolve_selected_services(services_arg: str | None) -> list[WorkspaceServiceSpec]:
    """Resolves a comma-separated service list (or 'all'/'default') into specs."""
    if not services_arg or services_arg.strip().lower() == "default":
        return [WORKSPACE_SERVICES[s] for s in DEFAULT_SERVICE_SLUGS]
    if services_arg.strip().lower() == "all":
        return list(WORKSPACE_SERVICES.values())

    selected: list[WorkspaceServiceSpec] = []
    seen: set[str] = set()
    for raw in services_arg.split(","):
        slug = raw.strip().lower()
        if not slug or slug in seen:
            continue
        if slug not in WORKSPACE_SERVICES:
            valid = ", ".join(sorted(WORKSPACE_SERVICES.keys()))
            raise ValueError(f"Unknown Workspace service '{slug}'. Valid options: {valid}, all")
        selected.append(WORKSPACE_SERVICES[slug])
        seen.add(slug)
    if not selected:
        raise ValueError("At least one Workspace service must be selected.")
    return selected


def aggregate_adc_scopes(
    specs: list[WorkspaceServiceSpec],
    mode: AccessMode,
) -> list[str]:
    """Computes the deduplicated list of OAuth scopes needed for gcloud ADC login."""
    scopes: list[str] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/cloud-platform",
    ]
    for spec in specs:
        for scope in spec.scopes_for(mode):
            if scope not in scopes:
                scopes.append(scope)
    return scopes


def encode_config_payload(
    project_id: str,
    allowed_services: list[str],
    mode: AccessMode = AccessMode.READONLY,
) -> str:
    """Serializes project configuration and allowed services to a base64-encoded string."""
    if not project_id or not project_id.strip():
        raise ValueError("project_id must not be empty.")
    if not allowed_services:
        raise ValueError("allowed_services must contain at least one service.")

    valid_slugs = set(WORKSPACE_SERVICES.keys())
    cleaned_services: list[str] = []
    for slug in allowed_services:
        clean_slug = slug.strip().lower()
        if clean_slug not in valid_slugs:
            raise ValueError(f"Unknown service '{slug}' in allowed_services.")
        if clean_slug not in cleaned_services:
            cleaned_services.append(clean_slug)

    payload_data = {
        "version": "1.0",
        "project_id": project_id.strip(),
        "allowed_services": cleaned_services,
        "mode": mode.value if isinstance(mode, AccessMode) else str(mode),
    }
    raw_json = json.dumps(payload_data, separators=(",", ":"))
    return base64.b64encode(raw_json.encode("utf-8")).decode("utf-8")


def decode_config_payload(payload_str: str) -> dict[str, Any]:
    """Decodes and validates a base64 configuration payload."""
    if not payload_str or not payload_str.strip():
        raise ValueError("Payload string cannot be empty.")
    try:
        raw_json = base64.b64decode(payload_str.strip().encode("utf-8")).decode("utf-8")
        data = json.loads(raw_json)
    except Exception as exc:
        raise ValueError(f"Invalid or corrupted base64 configuration payload: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Decoded payload must be a JSON object.")

    project_id = data.get("project_id")
    if not project_id or not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("Payload missing valid 'project_id'.")

    allowed_services = data.get("allowed_services")
    if not isinstance(allowed_services, list) or not allowed_services:
        raise ValueError("Payload missing valid 'allowed_services' list.")

    valid_slugs = set(WORKSPACE_SERVICES.keys())
    for s in allowed_services:
        if not isinstance(s, str) or s.lower() not in valid_slugs:
            raise ValueError(f"Payload contains unrecognized service '{s}'.")

    mode_val = data.get("mode", AccessMode.READONLY.value)
    if mode_val not in [m.value for m in AccessMode]:
        raise ValueError(f"Payload contains invalid mode '{mode_val}'.")

    return {
        "version": data.get("version", "1.0"),
        "project_id": project_id.strip(),
        "allowed_services": [s.lower() for s in allowed_services],
        "mode": mode_val,
    }


def prompt_for_services(
    *,
    allowed_slugs: list[str] | None = None,
    title: str = "Select Google Workspace services to configure:",
) -> str:
    """Interactively prompts the user to select which Google Workspace services to configure.

    If allowed_slugs is provided, only those services are shown as selectable options.
    Returns a comma-separated string of selected service slugs.
    """
    if not sys.stdin.isatty():
        if allowed_slugs is not None:
            return ",".join(allowed_slugs)
        return "default"

    if allowed_slugs is not None:
        allowed_set = set(allowed_slugs)
        available = [item for item in ORDERED_SERVICES if item[0] in allowed_set]
    else:
        available = ORDERED_SERVICES

    print(f"\n{title}")
    for idx, (slug, name, desc) in enumerate(available, 1):
        print(f"  [{idx}] {name:<17} ({slug:<8}) - {desc}")

    if allowed_slugs is not None:
        print(f"  [A] All permitted services (1-{len(available)})")
    else:
        print("  [A] All services      (1-7: includes Chat)")
        print("  [D] Default core      (1-6: Drive, Gmail, Calendar, Docs, Sheets, Slides)")

    num_to_slug = {str(idx): slug for idx, (slug, _, _) in enumerate(available, 1)}
    valid_slugs = set(num_to_slug.values())

    default_prompt_hint = "A" if allowed_slugs is not None else "D"
    while True:
        try:
            choice = (
                input(f"\nEnter selections [e.g. 1,2,5 or 'all'] (default: {default_prompt_hint}): ")
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            print("\nSelection cancelled.")
            sys.exit(1)

        if not choice:
            if allowed_slugs is not None:
                return ",".join(s for s, _, _ in available)
            return "default"

        if choice in ("d", "default"):
            if allowed_slugs is not None:
                return ",".join(s for s, _, _ in available)
            return "default"

        if choice in ("a", "all"):
            if allowed_slugs is not None:
                return ",".join(s for s, _, _ in available)
            return "all"

        tokens = [t.strip().strip(",") for t in choice.replace(",", " ").split() if t.strip()]
        selected_slugs: list[str] = []
        invalid: list[str] = []

        for token in tokens:
            if token in num_to_slug:
                selected_slugs.append(num_to_slug[token])
            elif token in valid_slugs:
                selected_slugs.append(token)
            else:
                invalid.append(token)

        if invalid:
            print(
                f"Invalid option(s): {', '.join(invalid)}. Please enter valid numbers (1-{len(available)}), service names, or 'all'."
            )
            continue

        if not selected_slugs:
            print("No services selected. Please select at least one service.")
            continue

        deduped = [slug for slug, _, _ in available if slug in set(selected_slugs)]
        return ",".join(deduped)
