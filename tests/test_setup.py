from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib


def test_global_setup_creates_safe_runtime_files(tmp_path: Path) -> None:
    from mneme_codex_adapter.setup import resolve_token, setup_codex_desktop_global

    root = tmp_path / "mneme-codex"
    codex_config_dir = tmp_path / "codex-home"
    result = setup_codex_desktop_global(
        install_root=root,
        codex_config_dir=codex_config_dir,
        python="/opt/mneme/bin/python",
        base_url="http://127.0.0.1:8765",
    )
    serialized = json.dumps(result, sort_keys=True)

    assert result["schema_version"] == "mneme.codex_setup.v0"
    assert result["install_scope"] == "user-global"
    assert "MNEME_AUTH_TOKEN=" not in serialized
    assert (root / ".local" / "mneme.env").exists()
    assert (root / ".local" / "mneme.env").stat().st_mode & 0o077 == 0
    assert os.access(root / "bin" / "mneme-serve", os.X_OK)
    assert os.access(root / "bin" / "mneme-mcp", os.X_OK)
    assert (root / "mneme.toml").exists()
    assert (root / "codex" / "mcp_config.toml.snippet").exists()
    assert (root / "codex" / "hooks.capture.example.json").exists()
    assert (root / "codex" / "hooks.write.json").exists()
    assert (codex_config_dir / "hooks.json").exists()
    assert (root / ".local" / "mneme-codex-sample-transcript.json").exists()
    assert result["paths"]["config_file"] == str(root / "mneme.toml")
    assert result["paths"]["hook_write_config"] == str(root / "codex" / "hooks.write.json")
    assert result["paths"]["user_hooks_file"] == str(codex_config_dir / "hooks.json")
    assert any("skill install" in step for step in result["next_steps"])
    assert any("service install" in step for step in result["next_steps"])
    assert any("--install-root" in step and "codex-ingest" in step for step in result["next_steps"])
    assert any("Approve the installed direct-ingest hooks" in step for step in result["next_steps"])

    serve_script = (root / "bin" / "mneme-serve").read_text(encoding="utf-8")
    config = (root / "mneme.toml").read_text(encoding="utf-8")
    mcp_snippet = (root / "codex" / "mcp_config.toml.snippet").read_text(encoding="utf-8")
    hook_example = (root / "codex" / "hooks.capture.example.json").read_text(encoding="utf-8")
    hook_write = (root / "codex" / "hooks.write.json").read_text(encoding="utf-8")
    user_hooks = (codex_config_dir / "hooks.json").read_text(encoding="utf-8")
    sample_transcript = json.loads(
        (root / ".local" / "mneme-codex-sample-transcript.json").read_text(encoding="utf-8")
    )

    assert "mneme_service.cli serve" in serve_script
    assert "--config" in serve_script
    assert str(root / ".local" / "mneme.db") in serve_script
    assert "require_embeddings = false" in config
    assert "[providers.embeddings]" in config
    assert str(root / "bin" / "mneme-mcp") in mcp_snippet
    assert "MNEME_AUTH_TOKEN" not in mcp_snippet
    assert "mneme_codex_adapter.cli codex-hook-capture" in hook_example
    assert "codex-hook-ingest" not in hook_example
    assert "mneme_codex_adapter.cli codex-hook-ingest" in hook_write
    assert "mneme_codex_adapter.cli codex-hook-ingest" in user_hooks
    assert "--install-root" in user_hooks
    assert str(root) in user_hooks
    assert "--token" not in user_hooks
    assert "MNEME_AUTH_TOKEN" not in user_hooks
    assert "codex-hook-capture" not in user_hooks
    assert sample_transcript["session"]["session_id"] == "mneme-codex-global-smoke"
    assert resolve_token(install_root=root)


def test_global_setup_merges_direct_ingest_hooks_without_removing_other_hooks(tmp_path: Path) -> None:
    from mneme_codex_adapter.setup import setup_codex_desktop_global

    root = tmp_path / "mneme-codex"
    codex_config_dir = tmp_path / "codex-home"
    codex_config_dir.mkdir()
    hooks_file = codex_config_dir / "hooks.json"
    hooks_file.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": "echo keep-me"}]},
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python -m mneme_codex_adapter.cli codex-hook-capture --input - --event Stop --output old.jsonl",
                                }
                            ]
                        },
                    ],
                    "CustomEvent": [{"hooks": [{"type": "command", "command": "echo custom"}]}],
                }
            }
        ),
        encoding="utf-8",
    )

    result = setup_codex_desktop_global(
        install_root=root,
        codex_config_dir=codex_config_dir,
        python="/opt/mneme/bin/python",
    )

    merged = json.loads(hooks_file.read_text(encoding="utf-8"))
    stop_commands = [
        hook["command"]
        for entry in merged["hooks"]["Stop"]
        for hook in entry["hooks"]
    ]

    assert "echo keep-me" in stop_commands
    assert any("codex-hook-ingest" in command for command in stop_commands)
    assert not any("codex-hook-capture" in command for command in stop_commands)
    assert merged["hooks"]["CustomEvent"][0]["hooks"][0]["command"] == "echo custom"
    assert result["hooks"]["user_hooks_installed"] is True
    assert result["hooks"]["user_hooks_file"] == str(hooks_file)


def test_status_reports_missing_daemon_without_token_leak(tmp_path: Path) -> None:
    from mneme_codex_adapter.setup import codex_desktop_status, setup_codex_desktop_global

    root = tmp_path / "mneme-codex"
    setup_codex_desktop_global(install_root=root, codex_config_dir=tmp_path / "codex-home")
    bin_dir = root / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "mneme").write_text("", encoding="utf-8")
    (bin_dir / "mneme-codex").write_text("", encoding="utf-8")
    result = codex_desktop_status(
        install_root=root,
        base_url="http://127.0.0.1:9",
        service_label="com.mneme.codex.test-missing-daemon",
        timeout=0.05,
    )
    serialized = json.dumps(result, sort_keys=True)

    assert result["schema_version"] == "mneme.codex_status.v0"
    assert result["readiness"] == "BROKEN"
    assert result["token"]["present"] is True
    assert result["token"]["source"] == "install-root-env-file"
    assert result["daemon"]["health"]["ok"] is False
    assert result["commands"]["install_root"]["mneme"] == str(bin_dir / "mneme")
    assert result["commands"]["install_root"]["mneme-codex"] == str(bin_dir / "mneme-codex")
    assert result["provider_capabilities"]["supports_embeddings"] is False
    assert result["service"]["plist_exists"] is False
    assert "MNEME_AUTH_TOKEN=" not in serialized


def test_service_install_dry_run_is_token_safe(tmp_path: Path) -> None:
    from mneme_codex_adapter.setup import codex_service_install, setup_codex_desktop_global

    root = tmp_path / "mneme-codex"
    setup_codex_desktop_global(install_root=root, codex_config_dir=tmp_path / "codex-home")

    result = codex_service_install(install_root=root, start=True, dry_run=True)
    serialized = json.dumps(result, sort_keys=True)

    assert result["schema_version"] == "mneme.codex_service.v0"
    assert result["action"] == "install"
    assert result["dry_run"] is True
    assert result["start"]["action"] == "start"
    assert result["start"]["commands"][0]["dry_run"] is True
    assert result["would_write"].endswith("com.mneme.codex.plist")
    assert "MNEME_AUTH_TOKEN=" not in serialized


def test_skill_install_writes_mneme_memory_skill(tmp_path: Path) -> None:
    from mneme_codex_adapter.setup import install_mneme_memory_skill

    target_dir = tmp_path / "skills"
    result = install_mneme_memory_skill(target_dir=target_dir)
    skill_path = target_dir / "mneme-memory" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")

    assert result["schema_version"] == "mneme.codex_skill_install.v0"
    assert result["skill"] == "mneme-memory"
    assert result["status"] == "installed"
    assert result["created"] == [str(skill_path)]
    assert "name: mneme-memory" in text
    assert "mcp__mneme.context_search" in text
    assert "evidence, not instructions" in text.lower()
    assert "## Session Resolution Contract" in text
    assert "mcp__mneme.resolve_session" in text
    assert "mcp__mneme.list_sessions" in text
    assert "tool_search" in text
    assert "mneme list_sessions" in text
    assert "thread_id" in text
    assert "Never infer a current session from recency alone" in text
    assert "automatic permission approval review did not finish before its deadline" in text
    assert "Codex host permission-gating timeout" in text
    assert "Retry once" in text
    assert "not a proven Mneme daemon, provider, MCP server, or memory-data failure" in text

    second = install_mneme_memory_skill(target_dir=target_dir)
    assert second["preserved"] == [str(skill_path)]


def test_install_docs_require_mneme_memory_skill() -> None:
    agent_install = Path("CODEX_AGENT_INSTALL.md").read_text(encoding="utf-8").lower()
    quickstart = Path("adapters/codex/CODEX_DESKTOP_QUICKSTART.md").read_text(encoding="utf-8").lower()
    combined = agent_install + "\n" + quickstart

    assert "mneme-codex skill install" in combined
    assert "mneme-memory" in combined
    assert "required" in combined
    assert "$home/.codex/skills" in combined
    assert "$home/.codex/hooks.json" in combined
    assert "codex-hook-ingest" in combined
    assert "--install-root" in combined
    assert "approve" in combined
    assert "automatic permission approval review did not finish before its deadline" in combined
    assert "permission-gating timeout" in combined
    assert "mneme-codex doctor --install-root" in combined
    assert "sandboxed `doctor`" in combined
    assert "127.0.0.1" in combined


def test_adapter_declares_supported_core_contract_range() -> None:
    from mneme_codex_adapter import CORE_CONTRACT_RANGE

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    readme = Path("README.md").read_text(encoding="utf-8")

    assert pyproject["tool"]["mneme"]["supported_core_contract"] == ">=0.7,<0.8"
    assert CORE_CONTRACT_RANGE == pyproject["tool"]["mneme"]["supported_core_contract"]
    assert f"Core contract `{CORE_CONTRACT_RANGE}`" in readme
