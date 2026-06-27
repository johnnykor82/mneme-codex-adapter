from __future__ import annotations

import json
import os
import plistlib
import platform
import secrets
import shutil
import stat
import subprocess
import sys
from importlib import resources
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
DEFAULT_CODEX_SERVICE_LABEL = "com.mneme.codex"
DEFAULT_CODEX_SKILLS_DIR = "~/.codex/skills"
MNEME_MEMORY_SKILL_NAME = "mneme-memory"
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
    config_path = root / "mneme.toml"
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
        _serve_script(root=root, db_path=db_path, config_path=config_path, python=python),
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
    _write_text_file(
        config_path,
        _default_config(db_path=db_path),
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
            "config_file": str(config_path),
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
            f"Install skill: mneme-codex skill install --target-dir {Path(DEFAULT_CODEX_SKILLS_DIR).expanduser()}",
            f"Install service: mneme-codex service install --install-root {root} --start",
            f"Or start foreground daemon: {bin_dir / 'mneme-serve'}",
            f"Check health: curl -sS {base_url}/v1/health",
            f"Smoke ingest: mneme-codex codex-ingest --install-root {root} --input {sample_transcript_path}",
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
    service_label: str = DEFAULT_CODEX_SERVICE_LABEL,
    timeout: float = 2.0,
) -> dict[str, Any]:
    root = _install_root(install_root)
    local_dir = root / ".local"
    env_file = local_dir / "mneme.env"
    capture_path = local_dir / "mneme-codex-hooks.jsonl"
    resolved_token = resolve_token(token=token, install_root=root)

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
            "ambient_path": {
                "mneme": shutil.which("mneme"),
                "mneme-codex": shutil.which("mneme-codex"),
            },
            "install_root": {
                "mneme": _entrypoint(root, "mneme"),
                "mneme-codex": _entrypoint(root, "mneme-codex"),
            },
        },
        "service": codex_service_status(install_root=root, label=service_label, check_launchctl=False),
        "provider_capabilities": _capability_summary(capabilities),
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


def install_mneme_memory_skill(
    *,
    target_dir: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = Path(DEFAULT_CODEX_SKILLS_DIR) if target_dir is None else target_dir
    skills_dir = root.expanduser().resolve()
    skill_dir = skills_dir / MNEME_MEMORY_SKILL_NAME
    skill_path = skill_dir / "SKILL.md"
    skill_text = _mneme_memory_skill_text()
    report: dict[str, Any] = {
        "schema_version": "mneme.codex_skill_install.v0",
        "skill": MNEME_MEMORY_SKILL_NAME,
        "target_dir": str(skills_dir),
        "skill_path": str(skill_path),
        "dry_run": dry_run,
        "force": force,
        "created": [],
        "preserved": [],
        "warnings": [],
    }
    if dry_run:
        report["would_write"] = str(skill_path)
        return report
    if skill_path.exists():
        existing = skill_path.read_text(encoding="utf-8")
        if existing == skill_text:
            report["preserved"].append(str(skill_path))
            return report
        if not force:
            report["warnings"].append("Skill already exists with different content; rerun with --force to replace it.")
            report["status"] = "exists-different"
            return report
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(skill_text, encoding="utf-8")
    report["created"].append(str(skill_path))
    report["status"] = "installed"
    return report


def resolve_token(*, token: str | None = None, install_root: Path | None = None) -> str | None:
    root = _install_root(install_root)
    return token or os.environ.get("MNEME_AUTH_TOKEN") or _read_token(root / ".local" / "mneme.env")


def codex_service_install(
    *,
    install_root: Path | None = None,
    label: str = DEFAULT_CODEX_SERVICE_LABEL,
    start: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = _install_root(install_root)
    paths = _service_paths(root=root, label=label)
    plist = _launchd_plist(root=root, label=label, paths=paths)
    report: dict[str, Any] = {
        "schema_version": "mneme.codex_service.v0",
        "action": "install",
        "label": label,
        "install_root": str(root),
        "plist_path": str(paths["plist"]),
        "dry_run": dry_run,
        "start_requested": start,
        "warnings": _service_warnings(root),
    }
    if dry_run:
        report["would_write"] = str(paths["plist"])
    else:
        paths["plist"].parent.mkdir(parents=True, exist_ok=True)
        paths["plist"].write_bytes(plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=True))
        report["written"] = str(paths["plist"])
    if start:
        report["start"] = codex_service_start(install_root=root, label=label, dry_run=dry_run)
    return report


def codex_service_start(
    *,
    install_root: Path | None = None,
    label: str = DEFAULT_CODEX_SERVICE_LABEL,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = _install_root(install_root)
    plist_path = _service_paths(root=root, label=label)["plist"]
    domain = _launchd_domain()
    commands = [
        ["launchctl", "bootstrap", domain, str(plist_path)],
        ["launchctl", "kickstart", "-k", f"{domain}/{label}"],
    ]
    return {
        "schema_version": "mneme.codex_service.v0",
        "action": "start",
        "label": label,
        "plist_path": str(plist_path),
        "dry_run": dry_run,
        "commands": [_run_command(command, dry_run=dry_run) for command in commands],
    }


def codex_service_stop(
    *,
    install_root: Path | None = None,
    label: str = DEFAULT_CODEX_SERVICE_LABEL,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = _install_root(install_root)
    domain = _launchd_domain()
    command = ["launchctl", "bootout", f"{domain}/{label}"]
    return {
        "schema_version": "mneme.codex_service.v0",
        "action": "stop",
        "label": label,
        "install_root": str(root),
        "dry_run": dry_run,
        "command": _run_command(command, dry_run=dry_run),
    }


def codex_service_uninstall(
    *,
    install_root: Path | None = None,
    label: str = DEFAULT_CODEX_SERVICE_LABEL,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = _install_root(install_root)
    plist_path = _service_paths(root=root, label=label)["plist"]
    report: dict[str, Any] = {
        "schema_version": "mneme.codex_service.v0",
        "action": "uninstall",
        "label": label,
        "install_root": str(root),
        "plist_path": str(plist_path),
        "dry_run": dry_run,
        "stop": codex_service_stop(install_root=root, label=label, dry_run=dry_run),
    }
    if dry_run:
        report["would_remove"] = str(plist_path)
    elif plist_path.exists():
        plist_path.unlink()
        report["removed"] = str(plist_path)
    else:
        report["removed"] = None
    return report


def codex_service_status(
    *,
    install_root: Path | None = None,
    label: str = DEFAULT_CODEX_SERVICE_LABEL,
    check_launchctl: bool = True,
) -> dict[str, Any]:
    root = _install_root(install_root)
    paths = _service_paths(root=root, label=label)
    report: dict[str, Any] = {
        "schema_version": "mneme.codex_service_status.v0",
        "label": label,
        "install_root": str(root),
        "plist_path": str(paths["plist"]),
        "plist_exists": paths["plist"].exists(),
        "stdout_log": str(paths["stdout_log"]),
        "stderr_log": str(paths["stderr_log"]),
    }
    if check_launchctl:
        command = ["launchctl", "print", f"{_launchd_domain()}/{label}"]
        result = _run_command(command, dry_run=False)
        report["launchctl"] = result
        output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
        report["running"] = result.get("returncode") == 0 and "state = running" in output
    return report


def codex_service_logs(
    *,
    install_root: Path | None = None,
    label: str = DEFAULT_CODEX_SERVICE_LABEL,
    lines: int = 80,
) -> dict[str, Any]:
    root = _install_root(install_root)
    paths = _service_paths(root=root, label=label)
    return {
        "schema_version": "mneme.codex_service_logs.v0",
        "label": label,
        "stdout_log": str(paths["stdout_log"]),
        "stderr_log": str(paths["stderr_log"]),
        "stdout_tail": _tail_file(paths["stdout_log"], lines=lines),
        "stderr_tail": _tail_file(paths["stderr_log"], lines=lines),
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


def _serve_script(*, root: Path, db_path: Path, config_path: Path, python: str) -> str:
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        f'ENV_FILE="{root / ".local" / "mneme.env"}"\n'
        f'CONFIG_FILE="{config_path}"\n'
        'if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi\n'
        ': "${MNEME_AUTH_TOKEN:?MNEME_AUTH_TOKEN is not set}"\n'
        'if [ -f "$CONFIG_FILE" ]; then\n'
        f'  exec "{python}" -m mneme_service.cli serve --config "$CONFIG_FILE" --db "{db_path}" --token "$MNEME_AUTH_TOKEN" "$@"\n'
        "else\n"
        f'  exec "{python}" -m mneme_service.cli serve --db "{db_path}" --token "$MNEME_AUTH_TOKEN" "$@"\n'
        "fi\n"
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
        stripped = line.strip()
        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").strip()
        if stripped.startswith("MNEME_AUTH_TOKEN="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _mneme_memory_skill_text() -> str:
    return (
        resources.files("mneme_codex_adapter")
        .joinpath("skills", MNEME_MEMORY_SKILL_NAME, "SKILL.md")
        .read_text(encoding="utf-8")
    )


def _capability_summary(capabilities: dict[str, Any]) -> dict[str, Any]:
    if not capabilities.get("ok") or not isinstance(capabilities.get("body"), dict):
        return {
            "supports_embeddings": False,
            "requires_embeddings": False,
            "supports_reranking": False,
            "supports_llm_enrichment": False,
        }
    body = capabilities["body"]
    return {
        "supports_embeddings": bool(body.get("supports_embeddings")),
        "requires_embeddings": bool(body.get("requires_embeddings")),
        "supports_reranking": bool(body.get("supports_reranking")),
        "supports_llm_enrichment": bool(body.get("supports_llm_enrichment")),
    }


def _entrypoint(root: Path, name: str) -> str | None:
    path = root / ".venv" / "bin" / name
    return str(path) if path.exists() else None


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


def _service_paths(*, root: Path, label: str) -> dict[str, Path]:
    return {
        "plist": Path.home() / "Library" / "LaunchAgents" / f"{label}.plist",
        "stdout_log": root / ".local" / "launchd.out.log",
        "stderr_log": root / ".local" / "launchd.err.log",
    }


def _launchd_plist(*, root: Path, label: str, paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "Label": label,
        "ProgramArguments": [str(root / "bin" / "mneme-serve")],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(paths["stdout_log"]),
        "StandardErrorPath": str(paths["stderr_log"]),
    }


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _run_command(command: list[str], *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"command": command, "dry_run": True}
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except Exception as exc:  # pragma: no cover - OS/tool availability varies.
        return {"command": command, "ok": False, "error": type(exc).__name__, "message": str(exc)}
    return {
        "command": command,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _tail_file(path: Path, *, lines: int) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(lines, 0) :]


def _service_warnings(root: Path | None = None) -> list[str]:
    warnings = [
        "Service commands manage a macOS user LaunchAgent for this account only.",
        "The service script sources the local env file but service reports never print token values.",
    ]
    if root is not None and not (root / "bin" / "mneme-serve").exists():
        warnings.append("Run setup codex-desktop --global before installing the service.")
    if platform.system() != "Darwin":
        warnings.append("launchd service commands are intended for macOS.")
    return warnings


def _default_config(*, db_path: Path) -> str:
    return f"""# Mneme Codex local config.
# Put non-secret provider settings here. Put API keys in .local/mneme.env.

[daemon]
db_path = "{db_path}"
host = "127.0.0.1"
port = 8765
insecure_dev = false
require_embeddings = false

[providers.embeddings]
enabled = false
provider = "openai_compatible"
model = "text-embedding-3-small"
base_url = "https://api.openai.com/v1"
timeout_seconds = 30.0
batch_size = 16

[providers.reranker]
enabled = false
provider = "jina"
model = "jina-reranker-v2-base-multilingual"
base_url = "https://api.jina.ai/v1"
timeout_seconds = 30.0

[providers.llm_enrichment]
enabled = false
provider = "openai_compatible"
model = "gpt-4.1-mini"
base_url = "https://api.openai.com/v1"
timeout_seconds = 30.0
"""


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
