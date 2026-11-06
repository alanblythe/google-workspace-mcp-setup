---
name: google-workspace-mcp-setup
description: Developer skill to configure Google Workspace Managed MCP servers (Drive, Gmail, Calendar, Docs, Sheets, Slides, Chat) for Antigravity in a repository or user environment using implicit Application Default Credentials (google_credentials) and IAM while preserving Gemini Enterprise Standard/Plus seat quota. Supports administrator base64 configuration payloads with boundary enforcement and user deselection. Use when an engineer wants to configure Workspace MCP in their repository (.agents/plugins/google-workspace-mcp-setup/) or global config, authenticate local ADC with Workspace scopes, and verify MCP connectivity without needing GCP admin rights.
license: Apache-2.0
compatibility: Python 3.11+, gcloud CLI, Antigravity (agy)
metadata:
  author: Alan Blythe
  version: "1.1.0"
  category: GoogleWorkspace
---

# Google Workspace MCP Setup (`google-workspace-mcp-setup`)

Configures Google's 1P Managed **Google Workspace MCP servers** (`drivemcp`, `gmailmcp`, `calendarmcp`, `docsmcp`, `sheetsmcp`, `slidesmcp`, `chatmcp`) for **Antigravity** (`agy`, Antigravity IDE, and Antigravity Desktop App) using **implicit Application Default Credentials (`"authProviderType": "google_credentials"`)** and **Google Cloud IAM (`roles/mcp.toolUser`)**.

> [!NOTE]
> **Developer Skill**: This skill is designed to make setup completely effortless for engineers with zero GCP administrative privileges. If the Google Cloud Project has not yet been bootstrapped (APIs enabled and IAM roles granted), ask your GCP project owner to run `google-workspace-mcp-admin`.

## Why Implicit ADC + IAM (Instead of Shared OAuth Client Secrets)

1. **Zero Shared OAuth Secrets**: Standard OAuth client flows require creating a Web Application OAuth 2.0 Client ID/Secret in Google Auth Platform and distributing the secret across every developer's `mcp_config.json`. With `"authProviderType": "google_credentials"`, the configuration is **100% secret-free** and safe to commit directly to git as a workspace plugin (`.agents/plugins/google-workspace-mcp-setup/mcp_config.json` + `plugin.json`).
2. **Gemini Enterprise Quota Coexistence**:
   - **Antigravity Harness Login (`~/.gemini/`)**: Remains authenticated via the developer's standard Gemini Enterprise ("Use business account") login, drawing LLM turns from their **Gemini Enterprise Standard/Plus pooled seat quota**.
   - **MCP Tool Auth (`~/.config/gcloud/application_default_credentials.json`)**: Antigravity reads local ADC implicitly *only* when making outbound HTTP tool calls to `https://*mcp.googleapis.com/mcp/v1`. Do **not** set `AGY_ADC_AUTH=true` (which would switch LLM inference to Vertex AI PAYG).
3. **Dual-Layer Per-User Security**:
   - **Gate 1 (GCP IAM)**: Verifies the calling user has `roles/mcp.toolUser` (`mcp.tools.call`) on the quota project specified in `X-Goog-User-Project`.
   - **Gate 2 (Workspace ACLs)**: Executes every Workspace tool call strictly under that individual developer's Workspace identity and file/email ACLs.

---

## One-Step Execution Workflow

Resolve the skill root dynamically relative to this `SKILL.md` file (`<skill-dir>`).

When an engineer receives an onboarding prompt from their administrator or asks to set up Workspace MCP:

### Mode A: Turnkey Setup with Admin Payload (Recommended)

When provided with a base64 configuration payload from `google-workspace-mcp-admin`:

```bash
python3 <skill-dir>/scripts/setup_workspace_mcp.py --payload <BASE64_PAYLOAD> --local --adc-login
```

This single command automatically:
1. **Decodes & Confirms Payload**: Displays the administrator's configured GCP project ID, access mode, and permitted services.
2. **Deselection & Boundary Enforcement**:
   - In an interactive terminal, presents the developer with a numbered picker showing *only* the admin-permitted services. The developer can accept all or deselect any tools they don't need (e.g. entering `1,3` to install only Drive and Docs).
   - If a developer attempts to install services outside the administrator's configuration (via `--services`), the script strictly rejects the request and lists only permitted services.
3. **Writes Secret-Free Config**: Generates `.agents/plugins/google-workspace-mcp-setup/mcp_config.json` and `plugin.json` containing only the selected services with `"authProviderType": "google_credentials"` and `"X-Goog-User-Project"`.
4. **Authenticates ADC**: Opens your browser for a quick 1-click Google authorization requesting only the OAuth scopes needed for your selected tools, and sets the ADC quota project.

---

### Mode B: Direct Setup with Project ID

For solo developers or admins configuring directly without a payload:

```bash
python3 <skill-dir>/scripts/setup_workspace_mcp.py <PROJECT_ID> --local --adc-login
```

You can pass `--services` (e.g. `--services drive,gmail,docs` or `--services all`) or pick interactively from all 7 available services.

---

### Manual ADC Login Fallback
If the developer prefers to run `gcloud auth application-default login` manually in their terminal rather than using `--adc-login`, the agent **MUST** present the command in a strict fenced code block (` ```bash `) with backslash line continuations:

```bash
gcloud auth application-default login \
  --scopes="openid,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive.readonly,https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/calendar.readonly,https://www.googleapis.com/auth/documents.readonly,https://www.googleapis.com/auth/spreadsheets.readonly,https://www.googleapis.com/auth/presentations.readonly"
gcloud auth application-default set-quota-project <PROJECT_ID>
```

> [!WARNING]
> Never print the `gcloud ... --scopes=...` command as unfenced prose or in bullet points. Antigravity CLI and terminal markdown renderers will mistakenly detect the comma-separated `https://` scope URIs and auto-linkify them across line breaks into broken, unclickable URLs. Always use fenced code blocks.

---

### Step 2: Verify Setup & Gemini Enterprise Quota Coexistence

Run the verification script to confirm everything is green:

```bash
python3 <skill-dir>/scripts/verify_workspace_mcp.py
```

This confirms:
- `AGY_ADC_AUTH` is **unset** (preserving Gemini Enterprise seat quota).
- ADC identity and scopes are valid for the selected services.
- Workspace MCP servers are configured and ready.

> [!NOTE]
> If a 403 Forbidden or API Not Enabled error occurs during verification or tool calls, the GCP project owner has not yet enabled the APIs or granted `roles/mcp.toolUser`. Refer them to the `google-workspace-mcp-admin` skill.
