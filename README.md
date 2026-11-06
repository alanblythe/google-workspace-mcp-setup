# Google Workspace MCP Setup

> [!IMPORTANT]  
> This project is not provided by Google and does not come with any support or warranties. While the author is an employee at Google, this is a personal project and not an officially supported Google product. This project serves as a utility and reference implementation for configuring Google Workspace Managed MCP servers with Antigravity using IAM and Application Default Credentials.  
> Though functional, you may wish to adapt the configuration and scripts to suit your organization's specific development environments.  

> [!IMPORTANT]  
> Accurate as of 11/4/2026  

**What this is**  
An AAIF-compliant agent skill and Antigravity plugin that configures Google's 1P Managed Google Workspace MCP servers (`drivemcp`, `gmailmcp`, `calendarmcp`, `docsmcp`, `sheetsmcp`, `slidesmcp`, `chatmcp`) for **Antigravity** (`agy`, Antigravity IDE, and Antigravity Desktop App) using implicit Application Default Credentials (`"authProviderType": "google_credentials"`) and Google Cloud IAM (`roles/mcp.toolUser`).

**Why this exists**  
- standard 3-legged OAuth MCP setups require creating a Web Application OAuth Client ID/Secret in Google Auth Platform and distributing the client secret across every developer's `mcp_config.json`.
- setting `AGY_ADC_AUTH=true` globally in Antigravity switches LLM inference away from a developer's Gemini Enterprise seat license onto Vertex AI PAYG billing.
- this tool configures per-server `"authProviderType": "google_credentials"` in Antigravity's `mcp_config.json` so developers stay logged into Antigravity with their **Gemini Enterprise Standard/Plus seat quota** while MCP tool calls implicitly use local ADC (`~/.config/gcloud/application_default_credentials.json`) and project-level IAM (`X-Goog-User-Project`).

**What this is not**  
- not an official Google, Google Workspace, or Antigravity product.
- not a local Node.js or Python MCP wrapper — it connects directly to Google's managed remote endpoints (`https://*mcp.googleapis.com/mcp/v1`).
- does not bypass Google Workspace ACLs or require Domain-Wide Delegation (DWD); every tool call runs strictly under the individual developer's authenticated Workspace identity.

**How it works**  
- **Admin bootstrap (`--admin-bootstrap`)**: enables the `*mcp.googleapis.com` APIs on a shared GCP quota project and binds `roles/mcp.toolUser` + `roles/serviceusage.serviceUsageConsumer` to a user or team Google Group.
- **Secret-free Antigravity config generation (`--local` or `--global`)**: writes `.agents/plugins/google-workspace-mcp-setup/mcp_config.json` (workspace plugin) or `~/.antigravity/config/mcp_config.json` / `~/.gemini/config/mcp_config.json` (user-global) conforming strictly to `https://antigravity.google/schemas/mcp_config.json` with `"serverUrl"`, `"authProviderType": "google_credentials"`, and `"X-Goog-User-Project"`.
- **Per-user ADC login (`--adc-login`)**: runs `gcloud auth application-default login --scopes=...` with least-privilege `.readonly` (or `readwrite`) OAuth scopes so each developer authorizes their own local ADC token once without touching their Gemini Enterprise session in `~/.gemini/`.

---

## Quickstart

### 1. Install as an Antigravity Skill or Plugin

```bash
# Install the developer skill (google-workspace-mcp-setup) via npx skills
npx skills add https://github.com/alanblythe/google-workspace-mcp-setup -s google-workspace-mcp-setup -a antigravity

# Install the admin skill (google-workspace-mcp-admin) via npx skills
npx skills add https://github.com/alanblythe/google-workspace-mcp-setup -s google-workspace-mcp-admin -a antigravity

# Or choose interactively between both skills
npx skills add https://github.com/alanblythe/google-workspace-mcp-setup -a antigravity

# Or install as an Antigravity plugin
agy plugin install ./google-workspace-mcp-setup

# Or symlink locally into ~/.gemini/config/skills/
./scripts/install.sh
```

### 2. Team Setup Flow (1 Admin + N Developers)

#### Cohort A — Cloud Administrator (Once per GCP Project)

The administrator installs and runs the **`google-workspace-mcp-admin`** skill (or script) to choose which Workspace MCPs to enable, activate the GCP APIs, grant `roles/mcp.toolUser` to the team, and generate a tamper-evident base64 configuration payload:

1. **Install the admin skill**:
   > *"Install the google-workspace-mcp-admin skill: `npx skills add https://github.com/alanblythe/google-workspace-mcp-setup -s google-workspace-mcp-admin -a antigravity`"*

2. **Bootstrap the GCP project** (via prompt or CLI):
   > *"Use the google-workspace-mcp-admin skill to bootstrap GCP project `YOUR_PROJECT_ID` for principal `group:developers@yourdomain.com`."*

```bash
# Or run directly from a repository checkout:
python3 skills/google-workspace-mcp-admin/scripts/admin_bootstrap.py YOUR_PROJECT_ID \
  --principal "group:developers@yourdomain.com"
```

The script interactively presents the Workspace service selector (or accepts `--services`), enables only those APIs, and prints **two copy-pasteable Developer Onboarding Prompts** (one to install the developer skill via `-s google-workspace-mcp-setup`, and a second to run the skill with the base64 JSON configuration payload):

```text
Prompt 1 (Install the skill):
Install the google-workspace-mcp-setup skill: npx skills add https://github.com/alanblythe/google-workspace-mcp-setup -s google-workspace-mcp-setup -a antigravity

Prompt 2 (Configure with payload):
Use the google-workspace-mcp-setup skill with payload <BASE64_PAYLOAD> to configure Google Workspace MCP.
```

#### Cohort B — Developers (Zero GCP Admin Privileges Needed)

Each developer runs the two prompts in Antigravity:

1. **Install the developer skill**:
   > *"Install the google-workspace-mcp-setup skill: `npx skills add https://github.com/alanblythe/google-workspace-mcp-setup -s google-workspace-mcp-setup -a antigravity`"*

2. **Configure using the skill and base64 JSON payload**:
   > *"Use the google-workspace-mcp-setup skill with payload `<BASE64_PAYLOAD>` to configure Google Workspace MCP."*

Antigravity installs the **`google-workspace-mcp-setup`** skill first (locally in `.agents/skills/` or globally in `~/.antigravity/skills/` or `~/.gemini/skills/`). In the second step, the skill:
- Decodes the payload and confirms the administrator's configuration.
- **Asks the developer whether to install in local or global scope**:
  - **Local (`--local`)**: Workspace plugin (`.agents/plugins/google-workspace-mcp-setup/`, safe to commit to git).
  - **Global (`--global`)**: User configuration (`~/.antigravity/config/mcp_config.json` or `~/.gemini/config/mcp_config.json`).
- Lets the developer accept all permitted services or deselect any they don't need (strictly preventing installation of unpermitted services).
- Guides the developer through their 1-click local browser ADC login, and verifies connectivity:

```bash
# Manual developer run with payload (local workspace plugin):
python3 skills/google-workspace-mcp-setup/scripts/setup_workspace_mcp.py --payload <BASE64_PAYLOAD> --local --adc-login

# Manual developer run with payload (global user configuration):
python3 skills/google-workspace-mcp-setup/scripts/setup_workspace_mcp.py --payload <BASE64_PAYLOAD> --global --adc-login

python3 skills/google-workspace-mcp-setup/scripts/verify_workspace_mcp.py
```

---

## Skills Included

| Skill | Audience | Location | Purpose |
| :--- | :--- | :--- | :--- |
| **`google-workspace-mcp-admin`** | Cloud Admin / Project Owner | `skills/google-workspace-mcp-admin/` | Enables `*mcp.googleapis.com` endpoints, grants `roles/mcp.toolUser` to team members or Google Groups, and generates the two developer onboarding prompts. |
| **`google-workspace-mcp-setup`** | Developer / Team Member | `skills/google-workspace-mcp-setup/` | Configures repository `.agents/plugins/google-workspace-mcp-setup/`, guides per-user ADC authentication, and runs quota coexistence verification. |

---

## CLI Reference (`setup_workspace_mcp.py`)

* `project_id`: GCP Project ID used for `X-Goog-User-Project` quota and `roles/mcp.toolUser` IAM evaluation (optional when `--payload` is provided).
* `--payload <BASE64>`: Administrator-generated base64 configuration payload containing GCP project ID, allowed services, and access mode.
* `--local`: Write workspace plugin config (`.agents/plugins/google-workspace-mcp-setup/mcp_config.json` + `plugin.json`) safe to commit to git.
* `--global`: Write user-scoped global config (`~/.antigravity/config/mcp_config.json` or `~/.gemini/config/mcp_config.json`).
* `--gemini-dir`: Custom Antigravity root directory (defaults to auto-discovering `~/.antigravity` or `~/.gemini`).
* `--services`: Comma-separated list (`drive,gmail,calendar,docs,sheets,slides,chat` or `all`). When `--payload` is present, services cannot exceed the administrator's permitted set. If omitted, prompts interactively with deselection or defaults to all permitted.
* `--mode {readonly,readwrite}`: OAuth scope profile for ADC login (`readonly` by default for least privilege).
* `--admin-bootstrap`: Enable `*mcp.googleapis.com` APIs and grant `roles/mcp.toolUser`.
* `--principal <member>`: IAM member for `--admin-bootstrap` (e.g., `group:eng@yourdomain.com`).
* `--adc-login`: Execute `gcloud auth application-default login` with the aggregated OAuth scopes.
* `--dry-run`: Preview planned `gcloud` commands and unified config diffs (`diff -u`) without touching disk.

---

## Testing

```bash
python3 -m unittest discover -s tests -v
```

---

## Repository Layout

```
.
├── AGENTS.md                                  # Canonical AAIF agent instructions (GEMINI.md symlinked)
├── LICENSE                                    # Apache License, Version 2.0
├── README.md                                  # Quickstart, architecture, and CLI reference
├── plugin.json                                # Antigravity plugin manifest
├── .agents/skills/
│   ├── google-workspace-mcp-setup             # AAIF developer skill symlink
│   └── google-workspace-mcp-admin             # AAIF admin skill symlink
├── .gemini/settings.json                      # Pre-seeded read-only git inspection permissions
├── scripts/
│   └── install.sh                             # Local skill installer for ~/.gemini/config/skills/
├── skills/
│   ├── google-workspace-mcp-admin/
│   │   ├── SKILL.md                           # Admin skill specification & workflow
│   │   └── scripts/
│   │       ├── admin_bootstrap.py             # GCP API activator, IAM binder, and onboarding payload encoder
│   │       └── harness_registry.py            # Shared registry & payload codecs (self-contained)
│   └── google-workspace-mcp-setup/
│       ├── SKILL.md                           # Developer skill specification & workflow
│       └── scripts/
│           ├── harness_registry.py            # Managed Workspace MCP endpoints, OAuth scopes, and payload codecs
│           ├── setup_workspace_mcp.py         # Config generator, boundary enforcer, and ADC login runner
│           └── verify_workspace_mcp.py        # Gemini Enterprise seat quota coexistence & ADC token scope verifier
└── tests/
    └── test_workspace_mcp.py                  # Hermetic unit test suite
```

---

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
