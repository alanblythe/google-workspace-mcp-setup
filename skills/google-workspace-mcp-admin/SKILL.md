---
name: google-workspace-mcp-admin
description: >-
  Admin skill to bootstrap a Google Cloud project for Google Workspace Managed MCP servers (checks prerequisite tools, prompts user to supply Project ID or list projects with gcloud, selects services to enable, activates *mcp.googleapis.com endpoints, binds roles/mcp.toolUser to developers/groups, and outputs two developer prompts: one to install the skill and a second starting with using the skill with the base64 JSON config payload). Use when a GCP project owner or cloud administrator wants to prepare a GCP project for Workspace MCP before developers use it.
license: Apache-2.0
compatibility: Python 3.11+, gcloud CLI, Antigravity (agy)
metadata:
  author: Alan Blythe
  version: "1.2.0"
  category: GoogleWorkspace
---

# Google Workspace MCP Project Admin (`google-workspace-mcp-admin`)

Prepares a Google Cloud Project for **Google Workspace Managed MCP servers** (`drivemcp`, `gmailmcp`, `calendarmcp`, `docsmcp`, `sheetsmcp`, `slidesmcp`, `chatmcp`), encodes an administrator-approved configuration payload (base64 JSON), and generates **two copy-pasteable Developer Onboarding Prompts** for client users.

> [!IMPORTANT]
> **This skill is for Cloud Administrators and Project Owners only.**
> Regular developers do not need and should not run this skill. Once the admin bootstraps the GCP project, developers only run the developer skill (`google-workspace-mcp-setup`).

> [!CAUTION]
> **CRITICAL OPERATIONAL RULES FOR THE AGENT:**
> 1. **STRICTLY NO UNPROMPTED RECONNAISSANCE**: Do NOT run `gcloud projects list`, search files, or browse directories on your own trying to guess a project ID.
> 2. **ALWAYS PAUSE AND ASK FIRST**: The very first thing you do MUST be to interactively ask the administrator the questions in Phase 1 and Phase 2.
> 3. **ONLY LIST PROJECTS IF REQUESTED**: Run `gcloud projects list` ONLY if the user explicitly asks you to list their projects.

---

## Execution Workflow

Resolve the skill root dynamically relative to this `SKILL.md` file (`<skill-dir>`).

### Phase 1: Environment Prerequisites (Ask Admin First)

Ask the administrator:
> *"Before we begin, would you like me to check that your environment has the required prerequisite tools (`gcloud` CLI installed, authenticated, and Python 3.11+)?"*

- If the user agrees, execute:
  ```bash
  python3 <skill-dir>/scripts/admin_bootstrap.py --check-prereqs
  ```
- If the user prefers to skip, proceed directly to Phase 2.

---

### Phase 2: Project ID Specification (Direct Entry vs. gcloud List)

Ask the administrator directly:
> *"How would you like to specify the Google Cloud Project ID to bootstrap for Google Workspace MCP?*
> *1. Provide the Project ID directly (e.g. `my-gcp-project`)*
> *2. Have me list your accessible GCP projects via `gcloud projects list` so you can choose from them"*

- **If Option 1 (or user provides ID)**: Use the provided `<PROJECT_ID>` and proceed to Phase 3.
- **If Option 2 (list projects requested)**: Execute:
  ```bash
  gcloud projects list --format="table(projectId,name,projectNumber)"
  ```
  Present the list to the administrator and ask them to select the `<PROJECT_ID>` to bootstrap.

---

### Phase 3: IAM Principal Specification

Ask the administrator:
> *"Which IAM principal should receive access to Workspace MCP tools (`roles/mcp.toolUser`)?*
> *- A Google Group for your team (strongly recommended, e.g. `group:engineering@yourdomain.com`)*
> *- An individual user (e.g. `user:alice@yourdomain.com`, defaults to your active gcloud account)"*

---

### Phase 4: Workspace Services & Access Mode

Confirm:
1. **Access Mode**: Default is `readonly` (strongly recommended for least-privilege security). Developers can read files, messages, and calendar entries without modification risk. Use `readwrite` only if editing capabilities are required.
2. **Services**: Default enables the core 6 services (`drive,gmail,calendar,docs,sheets,slides`). Ask if the administrator wants all core services or a specific subset (e.g. `drive,gmail`).

---

### Phase 5: Preview Planned Changes (Dry-Run First)

Always run a dry-run first to review the planned `gcloud` commands and preview the generated developer hand-off prompts:

```bash
python3 <skill-dir>/scripts/admin_bootstrap.py <PROJECT_ID> \
  --principal "group:engineering@yourdomain.com" \
  --dry-run
```

Show the dry-run output to the administrator and ask for confirmation to apply.

---

### Phase 6: Execute Admin Bootstrap & Deliver Hand-off Prompts

Upon confirmation, run the bootstrap script:

```bash
python3 <skill-dir>/scripts/admin_bootstrap.py <PROJECT_ID> \
  --principal "group:engineering@yourdomain.com"
```

This:
1. Enables only the selected `*mcp.googleapis.com` APIs on `<PROJECT_ID>`.
2. Binds `roles/mcp.toolUser` and `roles/serviceusage.serviceUsageConsumer` on `<PROJECT_ID>`.
3. Serializes the configuration into a compact base64 JSON payload:
   ```json
   {
     "version": "1.0",
     "project_id": "<PROJECT_ID>",
     "allowed_services": ["drive", "gmail", "docs"],
     "mode": "readonly"
   }
   ```
4. Outputs two developer onboarding prompts.

---

### Phase 7: Present the Two Client Prompts in Your Final Message

In your **final message** to the administrator after running the skill, you **MUST** present **two separate, copy-pasteable prompts** for the administrator to share with client users (in Slack, Google Chat, PR description, or onboarding wiki):

1. **Prompt 1 — Install the Skill**: Instructs the client user to install the `google-workspace-mcp-setup` skill using `-s google-workspace-mcp-setup`:
   ```text
   Install the google-workspace-mcp-setup skill: npx skills add https://github.com/alanblythe/google-workspace-mcp-setup -s google-workspace-mcp-setup -a antigravity
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
