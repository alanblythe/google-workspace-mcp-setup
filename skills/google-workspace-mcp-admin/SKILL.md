---
name: google-workspace-mcp-admin
description: Admin skill to bootstrap a Google Cloud project for Google Workspace Managed MCP servers (selects services to enable, activates *mcp.googleapis.com endpoints, binds roles/mcp.toolUser to developers/groups, and outputs two developer prompts: one to install the skill and a second starting with using the skill with the base64 JSON config payload). Use when a GCP project owner or cloud administrator wants to prepare a GCP project for Workspace MCP before developers use it.
license: Apache-2.0
compatibility: Python 3.11+, gcloud CLI, Antigravity (agy)
metadata:
  author: Alan Blythe
  version: "1.1.0"
  category: GoogleWorkspace
---

# Google Workspace MCP Project Admin (`google-workspace-mcp-admin`)

Prepares a Google Cloud Project for **Google Workspace Managed MCP servers** (`drivemcp`, `gmailmcp`, `calendarmcp`, `docsmcp`, `sheetsmcp`, `slidesmcp`, `chatmcp`), encodes an administrator-approved configuration payload (base64 JSON), and generates **two copy-pasteable Developer Onboarding Prompts** for client users.

> [!IMPORTANT]
> **This skill is for Cloud Administrators and Project Owners only.**
> Regular developers do not need and should not run this skill. Once the admin bootstraps the GCP project, developers only run the developer skill (`google-workspace-mcp-setup`).

---

## Execution Workflow

Resolve the skill root dynamically relative to this `SKILL.md` file (`<skill-dir>`).

### Step 1: Confirm Required Inputs with Admin

Before running, confirm:
1. **`PROJECT_ID`**: The Google Cloud Project ID enrolled in the Google Workspace Developer Preview.
2. **`--principal`**: The IAM principal to grant `roles/mcp.toolUser` (e.g. `group:engineering@yourdomain.com` for an entire team, or `user:alice@yourdomain.com`).
3. **`--mode`**: Default access mode for developers (`readonly` recommended, or `readwrite`).
4. **`--services`**: Comma-separated services (e.g. `drive,gmail,calendar,docs,sheets,slides`) or omit to select interactively via the built-in multi-choice selector.

---

### Step 2: Preview Planned Changes (Dry-Run First)

Always run a dry-run first to review the planned `gcloud` commands and preview the generated developer hand-off prompts:

```bash
python3 <skill-dir>/scripts/admin_bootstrap.py <PROJECT_ID> \
  --principal "group:engineering@yourdomain.com" \
  --dry-run
```

---

### Step 3: Execute Admin Bootstrap

Run the bootstrap script to enable chosen APIs, bind IAM roles, and encode the base64 configuration payload:

```bash
python3 <skill-dir>/scripts/admin_bootstrap.py <PROJECT_ID> \
  --principal "group:engineering@yourdomain.com"
```

This:
1. Presents an interactive service picker (if `--services` is omitted) to choose which Workspace MCPs to enable.
2. Enables only the selected `*mcp.googleapis.com` APIs on `<PROJECT_ID>`.
3. Binds `roles/mcp.toolUser` and `roles/serviceusage.serviceUsageConsumer` on `<PROJECT_ID>`.
4. Serializes the configuration into a compact base64 JSON payload:
   ```json
   {
     "version": "1.0",
     "project_id": "<PROJECT_ID>",
     "allowed_services": ["drive", "gmail", "docs"],
     "mode": "readonly"
   }
   ```
5. Outputs two developer onboarding prompts: one to install the developer skill and a second starting with using the skill with the base64 JSON payload.

---

### Step 4: Present the Two Client Prompts in Your Final Message

In your **final message** to the administrator after running the skill, you **MUST** present **two separate, copy-pasteable prompts** for the administrator to share with client users (in Slack, Google Chat, PR description, or onboarding wiki):

1. **Prompt 1 — Install the Skill**: Instructs the client user to install the `google-workspace-mcp-setup` skill:
   ```text
   Install the google-workspace-mcp-setup skill from https://github.com/alanblythe/google-workspace-mcp-setup.
   ```

2. **Prompt 2 — Use the Skill with the Base64 JSON Payload**: Starts with using the `google-workspace-mcp-setup` skill with the generated base64 JSON payload:
   ```text
   Use the google-workspace-mcp-setup skill with payload <BASE64_PAYLOAD> to configure Google Workspace MCP.
   ```

When a client user runs these two prompts in Antigravity:
1. **Prompt 1** installs the developer skill (`google-workspace-mcp-setup`). The skill can be installed locally into the repository (`.agents/skills/google-workspace-mcp-setup/`) or globally for the user (`~/.antigravity/skills/` or `~/.gemini/skills/`).
2. **Prompt 2** activates `google-workspace-mcp-setup`, decodes the base64 JSON payload, and **asks the developer whether they want to configure local or global scope**:
   - **Local**: Generates `.agents/plugins/google-workspace-mcp-setup/` workspace plugin in the repository (safe to commit to git).
   - **Global**: Generates `<gemini_dir>/config/mcp_config.json` (`~/.antigravity` or `~/.gemini`) for user-wide access across all repositories.
3. The developer can confirm all permitted tools or deselect any tools they do not need (they cannot install services the administrator did not enable).
4. Antigravity writes the secret-free configuration, guides the developer through their 1-click local browser ADC login with least-privilege scopes, and verifies tool connectivity.
