from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

import httpx

from .hooks import (
    DEFAULT_CODEX_CONTEXT_PREVIEW_OUTPUT,
    render_codex_context_preview_hook_config,
    render_codex_hook_config,
    validate_codex_hook_capture_file,
)


DEFAULT_CODEX_INSTALL_ROOT = "~/.mneme-codex"
DEFAULT_CODEX_BASE_URL = "http://127.0.0.1:8765"
CODEX_ADAPTER_MODULE = "mneme_codex_adapter.cli"


def setup_codex_desktop_global(
    *,
    install_root: Path | None = None,
    base_url: str = DEFAULT_CODEX_BASE_URL,
    python: str = sys.executable,
    dry_run: bool = False,
    force_token: bool = False,
) -> dict[str, Any]:
    root = _install_root(install_root)
    local_dir = root / ".local"
    bin_dir = root / "bin"
    codex_dir = root / "codex"
    env_file = local_dir / "mneme.env"
    db_path = local_dir / "mneme.db"
    capture_path = local_dir / "mneme-codex-hooks.jsonl"
    preview_path = local_dir / "mneme-codex-context-preview.jsonl"
    sample_transcript_path = local_dir / "mneme-codex-sample-transcript.json"

    created: list[str] = []
    preserved: list[str] = []
    would_create: list[str] = []

    for directory in (root, local_dir, bin_dir, codex_dir):
        _ensure_dir(directory, created=created, would_create=would_create, dry_run=dry_run)

    if dry_run:
        if force_token or not env_file.exists():
            would_create.append(str(env_file))
    else:
        if force_token or not env_file.exists():
            token = secrets.token_urlsafe(32)
            _write_secret_env(env_file, token)
            created.append(str(env_file))
        else:
            preserved.append(str(env_file))

    _write_text_file(
        root / ".gitignore",
        ".local/\n*.db\n*.db-*\n*.log\n__pycache__/\n",
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )
    _write_executable(
        bin_dir / "mneme-serve",
        _serve_script(root=root, db_path=db_path, python=python),
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )
    _write_executable(
        bin_dir / "mneme-mcp",
        _mcp_script(root=root, base_url=base_url, python=python),
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )

    mcp_json = {
        "mcpServers": {
            "mneme": {
                "command": str(bin_dir / "mneme-mcp"),
                "args": [],
                "env": {},
            }
        }
    }
    _write_json_file(
        codex_dir / "mcp_server.example.json",
        mcp_json,
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )
    _write_text_file(
        codex_dir / "mcp_config.toml.snippet",
        "[mcp_servers.mneme]\n"
        f'command = "{bin_dir / "mneme-mcp"}"\n'
        "args = []\n",
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )

    capture_config = render_codex_hook_config(
        mode="capture",
        python=python,
        capture_output=str(capture_path),
        base_url=base_url,
    )
    preview_config = render_codex_context_preview_hook_config(
        python=python,
        output=str(preview_path),
        base_url=base_url,
    )
    _write_json_file(
        codex_dir / "hooks.capture.example.json",
        capture_config,
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )
    _write_json_file(
        codex_dir / "hooks.context_preview.example.json",
        preview_config,
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )
    _write_json_file(
        sample_transcript_path,
        _sample_transcript(),
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )

    return {
        "schema_version": "mneme.codex_setup.v0",
        "install_scope": "user-global",
        "install_root": str(root),
        "base_url": base_url,
        "dry_run": dry_run,
        "created": sorted(created),
        "preserved": sorted(preserved),
        "would_create": sorted(would_create),
        "paths": {
            "env_file": str(env_file),
            "db_path": str(db_path),
            "serve_script": str(bin_dir / "mneme-serve"),
            "mcp_script": str(bin_dir / "mneme-mcp"),
            "mcp_json": str(codex_dir / "mcp_server.example.json"),
            "mcp_toml_snippet": str(codex_dir / "mcp_config.toml.snippet"),
            "hook_capture_example": str(codex_dir / "hooks.capture.example.json"),
            "context_preview_example": str(codex_dir / "hooks.context_preview.example.json"),
            "hook_capture_file": str(capture_path),
            "context_preview_file": str(preview_path),
            "sample_transcript": str(sample_transcript_path),
        },
        "next_steps": [
            f"Start daemon: {bin_dir / 'mneme-serve'}",
            f"Check health: curl -sS {base_url}/v1/health",
            f"Smoke ingest: mneme-codex codex-ingest --input {sample_transcript_path}",
            f"Configure Codex MCP using: {codex_dir / 'mcp_config.toml.snippet'}",
            "Restart Codex or open a fresh session after MCP config changes.",
            f"Run doctor: mneme-codex doctor --install-root {root}",
        ],
        "warnings": [
            "Setup does not edit Codex config automatically.",
            "Setup renders capture-only hooks; write hooks require separate validation.",
            "Tokens are written to the local env file and are not included in this report.",
        ],
    }


def codex_desktop_status(
    *,
    install_root: Path | None = None,
    base_url: str = DEFAULT_CODEX_BASE_URL,
    token: str | None = None,
    timeout: float = 2.0,
) -> dict[str, Any]:
    root = _install_root(install_root)
    local_dir = root / ".local"
    env_file = local_dir / "mneme.env"
    capture_path = local_dir / "mneme-codex-hooks.jsonl"
    resolved_token = token or os.environ.get("MNEME_AUTH_TOKEN") or _read_token(env_file)

    health = _http_get_json(f"{base_url}/v1/health", token=None, timeout=timeout)
    capabilities = _http_get_json(
        f"{base_url}/v1/capabilities",
        token=resolved_token,
        timeout=timeout,
    )
    hook_validation = validate_codex_hook_capture_file(capture_path)
    files = {
        "install_root": root.exists(),
        "env_file": env_file.exists(),
        "db_path": (local_dir / "mneme.db").exists(),
        "serve_script": (root / "bin" / "mneme-serve").exists(),
        "mcp_script": (root / "bin" / "mneme-mcp").exists(),
        "mcp_toml_snippet": (root / "codex" / "mcp_config.toml.snippet").exists(),
        "hook_capture_example": (root / "codex" / "hooks.capture.example.json").exists(),
        "hook_capture_file": capture_path.exists(),
    }

    health_ok = health["ok"]
    capabilities_ok = capabilities["ok"]
    if health_ok and capabilities_ok:
        readiness = "READY"
    elif health_ok:
        readiness = "PARTIAL"
    else:
        readiness = "BROKEN"

    return {
        "schema_version": "mneme.codex_status.v0",
        "readiness": readiness,
        "install_root": str(root),
        "base_url": base_url,
        "python": sys.executable,
        "commands": {
            "mneme": shutil.which("mneme"),
            "mneme-codex": shutil.which("mneme-codex"),
        },
        "files": files,
        "token": {"present": bool(resolved_token), "source": _token_source(token, env_file)},
        "daemon": {
            "health": health,
            "capabilities": capabilities,
        },
        "hooks": {
            "capture_path": str(capture_path),
            "payload_count": hook_validation["payload_count"],
            "valid_for_enablement": hook_validation["valid_for_enablement"],
            "warnings": hook_validation["warnings"],
        },
        "next_steps": _status_next_steps(readiness, root),
    }


def _install_root(path: Path | None) -> Path:
    raw = Path(DEFAULT_CODEX_INSTALL_ROOT) if path is None else path
    return raw.expanduser().resolve()


def _ensure_dir(path: Path, *, created: list[str], would_create: list[str], dry_run: bool) -> None:
    if path.exists():
        return
    if dry_run:
        would_create.append(str(path))
        return
    path.mkdir(parents=True, exist_ok=True)
    created.append(str(path))


def _write_secret_env(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"MNEME_AUTH_TOKEN={token}\n")


def _write_text_file(
    path: Path,
    text: str,
    *,
    created: list[str],
    preserved: list[str],
    would_create: list[str],
    dry_run: bool,
) -> None:
    if dry_run:
        would_create.append(str(path))
        return
    if path.exists() and path.read_text(encoding="utf-8") == text:
        preserved.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    created.append(str(path))


def _write_json_file(
    path: Path,
    payload: dict[str, Any],
    *,
    created: list[str],
    preserved: list[str],
    would_create: list[str],
    dry_run: bool,
) -> None:
    _write_text_file(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )


def _write_executable(
    path: Path,
    text: str,
    *,
    created: list[str],
    preserved: list[str],
    would_create: list[str],
    dry_run: bool,
) -> None:
    _write_text_file(
        path,
        text,
        created=created,
        preserved=preserved,
        would_create=would_create,
        dry_run=dry_run,
    )
    if not dry_run:
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _serve_script(*, root: Path, db_path: Path, python: str) -> str:
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        f'ENV_FILE="{root / ".local" / "mneme.env"}"\n'
        'if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi\n'
        ': "${MNEME_AUTH_TOKEN:?MNEME_AUTH_TOKEN is not set}"\n'
        f'exec "{python}" -m mneme_service.cli serve --db "{db_path}" --token "$MNEME_AUTH_TOKEN" "$@"\n'
    )


def _mcp_script(*, root: Path, base_url: str, python: str) -> str:
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        f'ENV_FILE="{root / ".local" / "mneme.env"}"\n'
        'if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi\n'
        ': "${MNEME_AUTH_TOKEN:?MNEME_AUTH_TOKEN is not set}"\n'
        f'exec "{python}" -m mneme_service.cli mcp --base-url "{base_url}" --token "$MNEME_AUTH_TOKEN" "$@"\n'
    )


def _read_token(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("MNEME_AUTH_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _token_source(cli_token: str | None, env_file: Path) -> str | None:
    if cli_token:
        return "cli"
    if os.environ.get("MNEME_AUTH_TOKEN"):
        return "environment"
    if _read_token(env_file):
        return "install-root-env-file"
    return None


def _http_get_json(url: str, *, token: str | None, timeout: float) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
        body: Any
        try:
            body = response.json()
        except ValueError:
            body = response.text[:200]
        return {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "body": body,
        }
    except Exception as exc:  # pragma: no cover - exact network errors vary.
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def _status_next_steps(readiness: str, root: Path) -> list[str]:
    if readiness == "READY":
        return [
            "Daemon and authenticated capabilities are reachable.",
            f"Use MCP snippet: {root / 'codex' / 'mcp_config.toml.snippet'}",
            "Open a fresh Codex session and verify Mneme MCP tools are visible.",
        ]
    if readiness == "PARTIAL":
        return [
            "Daemon health is reachable, but authenticated capabilities are not.",
            f"Check token env file: {root / '.local' / 'mneme.env'}",
            "Do not print the token while debugging.",
        ]
    return [
        f"Start daemon: {root / 'bin' / 'mneme-serve'}",
        "If local bind is blocked by a sandbox, start it outside the sandbox.",
        "Then run doctor again.",
    ]


def _sample_transcript() -> dict[str, Any]:
    return {
        "session": {
            "session_id": "mneme-codex-global-smoke",
            "agent_id": "codex",
            "runtime": "CODEX",
            "project_id": "mneme-codex-global-install",
            "model": "gpt-5-codex",
            "started_at": "2026-06-15T00:00:00Z",
            "metadata": {"source": "mneme-codex setup sample"},
        },
        "turns": [
            {
                "turn_id": "install-turn-1",
                "started_at": "2026-06-15T00:00:00Z",
                "completed_at": "2026-06-15T00:00:05Z",
                "messages": [
                    {
                        "role": "USER",
                        "text": "Install Mneme Codex adapter globally.",
                        "timestamp": "2026-06-15T00:00:01Z",
                    },
                    {
                        "role": "ASSISTANT",
                        "text": "Mneme Codex global install smoke event.",
                        "timestamp": "2026-06-15T00:00:02Z",
                    },
                ],
            }
        ],
    }
