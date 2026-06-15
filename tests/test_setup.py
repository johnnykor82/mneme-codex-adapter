from __future__ import annotations

import json
import os
from pathlib import Path


def test_global_setup_creates_safe_runtime_files(tmp_path: Path) -> None:
    from mneme_codex_adapter.setup import resolve_token, setup_codex_desktop_global

    root = tmp_path / "mneme-codex"
    result = setup_codex_desktop_global(
        install_root=root,
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
    assert (root / ".local" / "mneme-codex-sample-transcript.json").exists()
    assert result["paths"]["config_file"] == str(root / "mneme.toml")
    assert any("skill install" in step for step in result["next_steps"])
    assert any("service install" in step for step in result["next_steps"])
    assert any("--install-root" in step and "codex-ingest" in step for step in result["next_steps"])

    serve_script = (root / "bin" / "mneme-serve").read_text(encoding="utf-8")
    config = (root / "mneme.toml").read_text(encoding="utf-8")
    mcp_snippet = (root / "codex" / "mcp_config.toml.snippet").read_text(encoding="utf-8")
    hook_example = (root / "codex" / "hooks.capture.example.json").read_text(encoding="utf-8")
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
    assert sample_transcript["session"]["session_id"] == "mneme-codex-global-smoke"
    assert resolve_token(install_root=root)


def test_status_reports_missing_daemon_without_token_leak(tmp_path: Path) -> None:
    from mneme_codex_adapter.setup import codex_desktop_status, setup_codex_desktop_global

    root = tmp_path / "mneme-codex"
    setup_codex_desktop_global(install_root=root)
    bin_dir = root / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "mneme").write_text("", encoding="utf-8")
    (bin_dir / "mneme-codex").write_text("", encoding="utf-8")
    result = codex_desktop_status(
        install_root=root,
        base_url="http://127.0.0.1:9",
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
    setup_codex_desktop_global(install_root=root)

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
