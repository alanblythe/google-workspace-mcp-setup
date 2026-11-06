from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "google-workspace-mcp-setup" / "scripts"
ADMIN_SCRIPTS_DIR = REPO_ROOT / "skills" / "google-workspace-mcp-admin" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(ADMIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(ADMIN_SCRIPTS_DIR))

import admin_bootstrap as admin_mod  # noqa: E402
import harness_registry as hr  # noqa: E402
import setup_workspace_mcp as setup_mod  # noqa: E402
import verify_workspace_mcp as verify_mod  # noqa: E402


class TestHarnessRegistry(unittest.TestCase):
    def test_resolve_selected_services_default_returns_core_six(self) -> None:
        specs = hr.resolve_selected_services("default")
        slugs = [s.slug for s in specs]
        self.assertEqual(slugs, ["drive", "gmail", "calendar", "docs", "sheets", "slides"])

    def test_resolve_selected_services_all_includes_chat(self) -> None:
        specs = hr.resolve_selected_services("all")
        slugs = [s.slug for s in specs]
        self.assertIn("chat", slugs)
        self.assertEqual(len(slugs), 7)

    def test_resolve_selected_services_subset_and_deduplication(self) -> None:
        specs = hr.resolve_selected_services("drive, gmail, drive")
        slugs = [s.slug for s in specs]
        self.assertEqual(slugs, ["drive", "gmail"])

    def test_resolve_selected_services_invalid_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            hr.resolve_selected_services("drive,nonexistent")

    def test_build_google_credentials_entry_conforms_to_antigravity_schema(self) -> None:
        drive_spec = hr.WORKSPACE_SERVICES["drive"]
        entry = hr.build_google_credentials_entry(
            drive_spec,
            project_id="my-org-proj",
        )
        self.assertEqual(
            set(entry.keys()),
            {"serverUrl", "authProviderType", "headers"},
        )
        self.assertEqual(entry["serverUrl"], "https://drivemcp.googleapis.com/mcp/v1")
        self.assertEqual(entry["authProviderType"], "google_credentials")
        self.assertEqual(entry["headers"]["X-Goog-User-Project"], "my-org-proj")
        self.assertNotIn("clientSecret", json.dumps(entry))

    def test_aggregate_adc_scopes_readonly_vs_readwrite(self) -> None:
        specs = hr.resolve_selected_services("drive,gmail")
        ro_scopes = hr.aggregate_adc_scopes(specs, hr.AccessMode.READONLY)
        self.assertIn("https://www.googleapis.com/auth/drive.readonly", ro_scopes)
        self.assertIn("https://www.googleapis.com/auth/gmail.readonly", ro_scopes)

        rw_scopes = hr.aggregate_adc_scopes(specs, hr.AccessMode.READWRITE)
        self.assertIn("https://www.googleapis.com/auth/drive", rw_scopes)
        self.assertIn("https://www.googleapis.com/auth/gmail.modify", rw_scopes)

    def test_encode_and_decode_config_payload_roundtrip(self) -> None:
        payload = hr.encode_config_payload(
            "test-project-123",
            ["drive", "gmail", "docs"],
            hr.AccessMode.READONLY,
        )
        self.assertIsInstance(payload, str)
        decoded = hr.decode_config_payload(payload)
        self.assertEqual(decoded["project_id"], "test-project-123")
        self.assertEqual(decoded["allowed_services"], ["drive", "gmail", "docs"])
        self.assertEqual(decoded["mode"], "readonly")
        self.assertEqual(decoded["version"], "1.0")

    def test_encode_config_payload_validations(self) -> None:
        with self.assertRaises(ValueError):
            hr.encode_config_payload("", ["drive"])
        with self.assertRaises(ValueError):
            hr.encode_config_payload("proj", [])
        with self.assertRaises(ValueError):
            hr.encode_config_payload("proj", ["unknown_service"])

    def test_decode_config_payload_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            hr.decode_config_payload("")
        with self.assertRaises(ValueError):
            hr.decode_config_payload("not-valid-base64!@#$")
        with self.assertRaises(ValueError):
            import base64
            hr.decode_config_payload(base64.b64encode(b"not json").decode("utf-8"))
        with self.assertRaises(ValueError):
            import base64
            hr.decode_config_payload(base64.b64encode(b'{"project_id": ""}').decode("utf-8"))

    @patch("sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="1, 3")
    def test_prompt_for_services_with_allowed_slugs_deselection(
        self, _mock_input: MagicMock, _mock_isatty: MagicMock
    ) -> None:
        # Given allowed slugs ["drive", "gmail", "docs"]
        # Options: 1: drive, 2: gmail, 3: docs
        # User selects 1, 3 -> returns "drive,docs"
        selected = hr.prompt_for_services(allowed_slugs=["drive", "gmail", "docs"])
        self.assertEqual(selected, "drive,docs")

    @patch("sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="")
    def test_prompt_for_services_with_allowed_slugs_default_enter(
        self, _mock_input: MagicMock, _mock_isatty: MagicMock
    ) -> None:
        selected = hr.prompt_for_services(allowed_slugs=["drive", "gmail"])
        self.assertEqual(selected, "drive,gmail")

    @patch("sys.stdin.isatty", return_value=False)
    def test_prompt_for_services_non_interactive_with_allowed_slugs(
        self, _mock_isatty: MagicMock
    ) -> None:
        selected = hr.prompt_for_services(allowed_slugs=["drive", "docs"])
        self.assertEqual(selected, "drive,docs")

    def test_resolve_antigravity_gemini_dir_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp) / "fake_home"
            fake_home.mkdir()

            # 1. Explicit arg wins
            custom_arg = fake_home / "custom_gemini"
            resolved = hr.resolve_antigravity_gemini_dir(gemini_dir_arg=custom_arg, home_dir=fake_home)
            self.assertEqual(resolved, custom_arg.resolve())

            # 2. Env var wins if arg is omitted
            with patch.dict(os.environ, {"ANTIGRAVITY_GEMINI_DIR": str(fake_home / "env_gemini")}):
                resolved = hr.resolve_antigravity_gemini_dir(home_dir=fake_home)
                self.assertEqual(resolved, (fake_home / "env_gemini").resolve())

            # 3. Filesystem probe: ~/.antigravity/config preferred if present
            antigravity_cfg = fake_home / ".antigravity" / "config"
            antigravity_cfg.mkdir(parents=True)
            with patch.dict(os.environ, {}, clear=True):
                # Ensure no env var interference
                for k in ("ANTIGRAVITY_GEMINI_DIR", "GEMINI_DIR"):
                    os.environ.pop(k, None)
                with patch("harness_registry.probe_running_agy_gemini_dir", return_value=None):
                    resolved = hr.resolve_antigravity_gemini_dir(home_dir=fake_home)
                    self.assertEqual(resolved, fake_home / ".antigravity")

                # 4. Fallback to ~/.gemini
                shutil.rmtree(fake_home / ".antigravity")
                with patch("harness_registry.probe_running_agy_gemini_dir", return_value=None):
                    resolved = hr.resolve_antigravity_gemini_dir(home_dir=fake_home)
                    self.assertEqual(resolved, fake_home / ".gemini")

    def test_global_setup_writes_to_gemini_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp)
            target = hr.resolve_antigravity_config_path(
                "global",
                gemini_dir=fake_home / ".custom_agy",
                home_dir=fake_home,
            )
            self.assertEqual(target, fake_home / ".custom_agy" / "config" / "mcp_config.json")


class TestSetupWorkspaceMcp(unittest.TestCase):
    def test_local_setup_writes_only_antigravity_agents_mcp_config_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws_root = Path(tmp)
            rc1 = setup_mod.main(
                [
                    "acme-mcp-quota",
                    "--local",
                    "--services",
                    "drive,gmail",
                    "--workspace-root",
                    str(ws_root),
                ]
            )
            self.assertEqual(rc1, 0)

            target_path = ws_root / ".agents" / "plugins" / "google-workspace-mcp-setup" / "mcp_config.json"
            plugin_path = ws_root / ".agents" / "plugins" / "google-workspace-mcp-setup" / "plugin.json"
            self.assertTrue(target_path.exists(), f"Expected {target_path} to be created")
            self.assertTrue(plugin_path.exists(), f"Expected {plugin_path} to be created")
            self.assertFalse((ws_root / ".agents" / "mcp_config.json").exists(), "Should not create bare .agents/mcp_config.json")
            self.assertFalse((ws_root / ".mcp.json").exists(), "Should not create .mcp.json")

            manifest_content = json.loads(plugin_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest_content.get("name"), "google-workspace-mcp-setup")

            content = json.loads(target_path.read_text(encoding="utf-8"))
            self.assertIn("google-workspace-drive", content["mcpServers"])
            self.assertIn("google-workspace-gmail", content["mcpServers"])
            drive_cfg = content["mcpServers"]["google-workspace-drive"]
            self.assertEqual(drive_cfg["authProviderType"], "google_credentials")
            self.assertEqual(drive_cfg["headers"]["X-Goog-User-Project"], "acme-mcp-quota")

            first_snapshot = target_path.read_text(encoding="utf-8")

            # Second run with identical flags must be strictly idempotent
            old_text, new_text = setup_mod.compute_updated_config(
                first_snapshot,
                setup_mod.build_mcp_servers_map(
                    hr.resolve_selected_services("drive,gmail"),
                    project_id="acme-mcp-quota",
                ),
            )
            diff = setup_mod.format_unified_diff(old_text, new_text, target_path)
            self.assertEqual(diff, "")

    def test_local_setup_cleans_up_legacy_bare_mcp_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws_root = Path(tmp)
            legacy_bare = ws_root / ".agents" / "mcp_config.json"
            legacy_bare.parent.mkdir(parents=True, exist_ok=True)
            legacy_bare.write_text('{"mcpServers": {}}', encoding="utf-8")
            self.assertTrue(legacy_bare.exists())

            rc = setup_mod.main(
                [
                    "acme-mcp-quota",
                    "--local",
                    "--services",
                    "drive",
                    "--workspace-root",
                    str(ws_root),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertFalse(legacy_bare.exists(), "Legacy bare config should be deleted")
            self.assertTrue(
                (ws_root / ".agents" / "plugins" / "google-workspace-mcp-setup" / "mcp_config.json").exists()
            )

    @patch("sys.stdin.isatty", return_value=False)
    def test_setup_with_payload_extracts_project_and_configures_servers(
        self, _mock_isatty: MagicMock
    ) -> None:
        payload = hr.encode_config_payload(
            "payload-project-123",
            ["drive", "gmail", "docs"],
            hr.AccessMode.READONLY,
        )
        with tempfile.TemporaryDirectory() as tmp:
            ws_root = Path(tmp)
            rc = setup_mod.main(
                [
                    "--payload",
                    payload,
                    "--local",
                    "--workspace-root",
                    str(ws_root),
                ]
            )
            self.assertEqual(rc, 0)

            target_path = ws_root / ".agents" / "plugins" / "google-workspace-mcp-setup" / "mcp_config.json"
            self.assertTrue(target_path.exists())
            content = json.loads(target_path.read_text(encoding="utf-8"))
            self.assertIn("google-workspace-drive", content["mcpServers"])
            self.assertIn("google-workspace-gmail", content["mcpServers"])
            self.assertIn("google-workspace-docs", content["mcpServers"])
            self.assertNotIn("google-workspace-calendar", content["mcpServers"])
            self.assertEqual(
                content["mcpServers"]["google-workspace-drive"]["headers"]["X-Goog-User-Project"],
                "payload-project-123",
            )

    @patch("sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="1, 2")
    def test_setup_with_payload_interactive_deselection(
        self, _mock_input: MagicMock, _mock_isatty: MagicMock
    ) -> None:
        payload = hr.encode_config_payload(
            "payload-project-123",
            ["drive", "gmail", "docs"],
            hr.AccessMode.READONLY,
        )
        with tempfile.TemporaryDirectory() as tmp:
            ws_root = Path(tmp)
            rc = setup_mod.main(
                [
                    "--payload",
                    payload,
                    "--local",
                    "--workspace-root",
                    str(ws_root),
                ]
            )
            self.assertEqual(rc, 0)

            target_path = ws_root / ".agents" / "plugins" / "google-workspace-mcp-setup" / "mcp_config.json"
            content = json.loads(target_path.read_text(encoding="utf-8"))
            self.assertIn("google-workspace-drive", content["mcpServers"])
            self.assertIn("google-workspace-gmail", content["mcpServers"])
            self.assertNotIn("google-workspace-docs", content["mcpServers"])

    def test_setup_with_payload_allows_user_deselection_via_services(self) -> None:
        payload = hr.encode_config_payload(
            "payload-project-123",
            ["drive", "gmail", "docs"],
            hr.AccessMode.READONLY,
        )
        with tempfile.TemporaryDirectory() as tmp:
            ws_root = Path(tmp)
            rc = setup_mod.main(
                [
                    "--payload",
                    payload,
                    "--services",
                    "drive,docs",  # deselected gmail
                    "--local",
                    "--workspace-root",
                    str(ws_root),
                ]
            )
            self.assertEqual(rc, 0)

            target_path = ws_root / ".agents" / "plugins" / "google-workspace-mcp-setup" / "mcp_config.json"
            content = json.loads(target_path.read_text(encoding="utf-8"))
            self.assertIn("google-workspace-drive", content["mcpServers"])
            self.assertIn("google-workspace-docs", content["mcpServers"])
            self.assertNotIn("google-workspace-gmail", content["mcpServers"])

    def test_setup_with_payload_rejects_services_exceeding_admin_boundary(self) -> None:
        payload = hr.encode_config_payload(
            "payload-project-123",
            ["drive", "gmail"],
            hr.AccessMode.READONLY,
        )
        with tempfile.TemporaryDirectory() as tmp:
            ws_root = Path(tmp)
            rc = setup_mod.main(
                [
                    "--payload",
                    payload,
                    "--services",
                    "drive,calendar",  # calendar is not allowed by admin
                    "--local",
                    "--workspace-root",
                    str(ws_root),
                ]
            )
            self.assertEqual(rc, 2)
            self.assertFalse((ws_root / ".agents" / "plugins" / "google-workspace-mcp-setup" / "mcp_config.json").exists())

    def test_setup_fails_without_project_id_or_payload(self) -> None:
        rc = setup_mod.main(["--local"])
        self.assertEqual(rc, 2)

    def test_setup_with_mismatched_project_id_and_payload(self) -> None:
        payload = hr.encode_config_payload("proj-a", ["drive"])
        rc = setup_mod.main(["proj-b", "--payload", payload, "--local"])
        self.assertEqual(rc, 2)

    def test_preserves_existing_mcp_servers_when_merging(self) -> None:
        existing = json.dumps(
            {
                "mcpServers": {
                    "existing-custom-server": {
                        "command": "/bin/sh",
                        "args": ["-c", "echo hello"],
                    }
                }
            },
            indent=2,
        )
        new_servers = setup_mod.build_mcp_servers_map(
            hr.resolve_selected_services("calendar"),
            project_id="acme-proj",
        )
        _, updated_text = setup_mod.compute_updated_config(existing, new_servers)
        parsed = json.loads(updated_text)
        self.assertIn("existing-custom-server", parsed["mcpServers"])
        self.assertIn("google-workspace-calendar", parsed["mcpServers"])

    @patch("setup_workspace_mcp.run_cmd")
    def test_admin_bootstrap_invokes_gcloud_enable_and_iam_bindings(
        self, mock_run_cmd: MagicMock
    ) -> None:
        specs = hr.resolve_selected_services("drive,gmail")
        setup_mod.run_admin_bootstrap(
            "acme-proj",
            specs,
            principal="group:devs@example.com",
            dry_run=False,
        )
        called_cmds = [call.args[0] for call in mock_run_cmd.call_args_list]
        self.assertTrue(
            any("services" in c and "enable" in c and "drivemcp.googleapis.com" in c for c in called_cmds)
        )
        self.assertTrue(
            any("roles/mcp.toolUser" in str(c) and "--member=group:devs@example.com" in str(c) for c in called_cmds)
        )

    @patch("sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="1")
    def test_prompt_for_scope_interactive_local(
        self, _mock_input: MagicMock, _mock_isatty: MagicMock
    ) -> None:
        scope = setup_mod.prompt_for_scope()
        self.assertEqual(scope, "local")

    @patch("sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="2")
    def test_prompt_for_scope_interactive_global(
        self, _mock_input: MagicMock, _mock_isatty: MagicMock
    ) -> None:
        scope = setup_mod.prompt_for_scope()
        self.assertEqual(scope, "global")

    @patch("sys.stdin.isatty", return_value=False)
    def test_prompt_for_scope_non_interactive_exits(
        self, _mock_isatty: MagicMock
    ) -> None:
        with self.assertRaises(SystemExit) as cm:
            setup_mod.prompt_for_scope()
        self.assertEqual(cm.exception.code, 2)


class TestAdminBootstrap(unittest.TestCase):
    def test_repo_skill_layout_is_self_contained_for_npx_skills(self) -> None:
        root_skill_md = REPO_ROOT / "SKILL.md"
        self.assertFalse(
            root_skill_md.exists() or root_skill_md.is_symlink(),
            "Root SKILL.md must not exist so 'npx skills' discovers both skills under skills/*.",
        )

        setup_registry = SCRIPTS_DIR / "harness_registry.py"
        admin_registry = ADMIN_SCRIPTS_DIR / "harness_registry.py"
        self.assertTrue(setup_registry.is_file())
        self.assertTrue(admin_registry.is_file())
        self.assertFalse(
            admin_registry.is_symlink(),
            "admin harness_registry.py must be a regular file (not a cross-skill symlink) for npx skills.",
        )
        self.assertEqual(
            setup_registry.read_text(encoding="utf-8"),
            admin_registry.read_text(encoding="utf-8"),
            "Both skill copies of harness_registry.py must remain identical.",
        )

    def test_skill_md_frontmatter_valid_yaml(self) -> None:
        try:
            import yaml
        except ImportError:
            yaml = None

        for rel_path in [
            "skills/google-workspace-mcp-setup/SKILL.md",
            "skills/google-workspace-mcp-admin/SKILL.md",
        ]:
            skill_path = REPO_ROOT / rel_path
            content = skill_path.read_text(encoding="utf-8")
            parts = content.split("---")
            self.assertGreaterEqual(len(parts), 3, f"{rel_path} must have frontmatter delimiters")
            fm_text = parts[1]
            if yaml is not None:
                data = yaml.safe_load(fm_text)
                self.assertIsInstance(data, dict, f"{rel_path} frontmatter must parse to dict")
                self.assertIn("name", data)
                self.assertIn("description", data)
                self.assertIsInstance(data["name"], str)
                self.assertIsInstance(data["description"], str)

    def test_format_developer_prompts_returns_install_and_payload_prompts(self) -> None:
        payload = hr.encode_config_payload("test-project-123", ["drive", "docs"])
        install_prompt, configure_prompt = admin_mod.format_developer_prompts(payload)
        self.assertEqual(
            install_prompt,
            "Install the google-workspace-mcp-setup skill: "
            "npx skills add https://github.com/alanblythe/google-workspace-mcp-setup "
            "-s google-workspace-mcp-setup -a antigravity",
        )
        self.assertIn("-s google-workspace-mcp-setup", install_prompt)
        self.assertNotIn(payload, install_prompt)
        self.assertTrue(
            configure_prompt.startswith("Use the google-workspace-mcp-setup skill"),
            f"Expected second prompt to start with using the skill, got: {configure_prompt}",
        )
        self.assertEqual(
            configure_prompt,
            f"Use the google-workspace-mcp-setup skill with payload {payload} "
            "to configure Google Workspace MCP.",
        )

    @patch("admin_bootstrap.run_cmd")
    def test_admin_bootstrap_dry_run_does_not_execute_commands(
        self, mock_run_cmd: MagicMock
    ) -> None:
        specs = hr.resolve_selected_services("drive,gmail")
        admin_mod.run_admin_bootstrap(
            "test-project-123",
            specs,
            principal="group:devs@example.com",
            dry_run=True,
        )
        mock_run_cmd.assert_not_called()

    @patch("admin_bootstrap.run_cmd")
    def test_admin_bootstrap_executes_api_enable_and_iam_bindings(
        self, mock_run_cmd: MagicMock
    ) -> None:
        specs = hr.resolve_selected_services("drive,gmail")
        admin_mod.run_admin_bootstrap(
            "test-project-123",
            specs,
            principal="group:devs@example.com",
            dry_run=False,
        )
        called_cmds = [call.args[0] for call in mock_run_cmd.call_args_list]
        self.assertTrue(
            any(
                "services" in c and "enable" in c and "drivemcp.googleapis.com" in c
                for c in called_cmds
            )
        )
        self.assertTrue(
            any(
                "roles/mcp.toolUser" in str(c) and "--member=group:devs@example.com" in str(c)
                for c in called_cmds
            )
        )
        self.assertTrue(
            any(
                "roles/serviceusage.serviceUsageConsumer" in str(c)
                and "--member=group:devs@example.com" in str(c)
                for c in called_cmds
            )
        )

    def test_print_developer_handoff_box_emits_two_prompts_with_payload(self) -> None:
        specs = hr.resolve_selected_services("drive,docs")
        payload = hr.encode_config_payload("test-project-123", ["drive", "docs"])
        install_prompt, configure_prompt = admin_mod.format_developer_prompts(payload)
        buf = io.StringIO()
        with redirect_stdout(buf):
            admin_mod.print_developer_handoff_box("test-project-123", payload, specs, hr.AccessMode.READONLY)
        output = buf.getvalue()
        self.assertIn("ADMIN BOOTSTRAP COMPLETE — DEVELOPER ONBOARDING HAND-OFF", output)
        self.assertIn("test-project-123", output)
        self.assertIn("Prompt 1", output)
        self.assertIn("Prompt 2", output)
        self.assertIn(install_prompt, output)
        self.assertIn(configure_prompt, output)
        self.assertLess(output.index(install_prompt), output.index(configure_prompt))
        self.assertNotIn("gcloud auth application-default login", output)

    @patch("admin_bootstrap.run_admin_bootstrap")
    def test_admin_bootstrap_main_dry_run_flow(self, mock_bootstrap: MagicMock) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = admin_mod.main(["my-project-123", "--services", "drive,sheets", "--dry-run"])
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        self.assertIn("ADMIN BOOTSTRAP COMPLETE", output)
        mock_bootstrap.assert_called_once()
        args = mock_bootstrap.call_args
        self.assertEqual(args.args[0], "my-project-123")
        specs = args.args[1]
        self.assertEqual([s.slug for s in specs], ["drive", "sheets"])


class TestVerifyWorkspaceMcp(unittest.TestCase):
    def test_ge_quota_coexistence_detects_agy_adc_auth_override(self) -> None:
        with patch.dict(os.environ, {"AGY_ADC_AUTH": "true"}, clear=False):
            ok, msg = verify_mod.check_ge_quota_coexistence()
            self.assertFalse(ok)
            self.assertIn("AGY_ADC_AUTH=true", msg)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGY_ADC_AUTH", None)
            ok2, _ = verify_mod.check_ge_quota_coexistence()
            self.assertTrue(ok2)


if __name__ == "__main__":
    unittest.main()
