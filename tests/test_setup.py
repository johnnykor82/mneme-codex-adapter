from __future__ import annotations

import json
import os
from pathlib import Path


def test_global_setup_creates_safe_runtime_files(tmp_path: Path) -> None:
    from mneme_codex_adapter.setup import setup_codex_desktop_global

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
    assert (root / "codex" / "mcp_config.toml.snippet").exists()
    assert (root / "codex" / "hooks.capture.example.json").exists()
    assert (root / ".local" / "mneme-codex-sample-transcript.json").exists()

    serve_script = (root / "bin" / "mneme-serve").read_text(encoding="utf-8")
    mcp_snippet = (root / "codex" / "mcp_config.toml.snippet").read_text(encoding="utf-8")
    hook_example = (root / "codex" / "hooks.capture.example.json").read_text(encoding="utf-8")
    sample_transcript = json.loads(
        (root / ".local" / "mneme-codex-sample-transcript.json").read_text(encoding="utf-8")
    )

    assert "mneme_service.cli serve" in serve_script
    assert str(root / ".local" / "mneme.db") in serve_script
    assert str(root / "bin" / "mneme-mcp") in mcp_snippet
    assert "MNEME_AUTH_TOKEN" not in mcp_snippet
    assert "mneme_codex_adapter.cli codex-hook-capture" in hook_example
    assert "codex-hook-ingest" not in hook_example
    assert sample_transcript["session"]["session_id"] == "mneme-codex-global-smoke"


def test_status_reports_missing_daemon_without_token_leak(tmp_path: Path) -> None:
    from mneme_codex_adapter.setup import codex_desktop_status, setup_codex_desktop_global

    root = tmp_path / "mneme-codex"
    setup_codex_desktop_global(install_root=root)
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
    assert "MNEME_AUTH_TOKEN=" not in serialized
