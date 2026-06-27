from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
from typing import Any

import httpx

from .ingest import DEFAULT_TIMESTAMP, _post_json, _safe_id
from .utils import canonical_json, sha256_text, token_estimate


@dataclass(frozen=True)
class CodexHookPayloads:
    session: dict[str, Any]
    event_batch: dict[str, Any]


CODEX_HOOK_MATCHERS = {
    "SessionStart": "startup|resume|clear|compact",
    "UserPromptSubmit": "",
    "PostToolUse": "",
    "PostCompact": "manual|auto",
    "Stop": "",
}
DEFAULT_CODEX_CONTEXT_PREVIEW_OUTPUT = ".local/mneme-codex-context-preview.jsonl"
DEFAULT_CODEX_CONTEXT_WINDOW_TOKENS = 128_000
DEFAULT_CODEX_CONTEXT_BUDGET_TOKENS = 6_000


def normalize_codex_hook_payload(
    payload: dict[str, Any],
    *,
    event_name: str | None = None,
    captured_at: str | None = None,
) -> CodexHookPayloads:
    if not isinstance(payload, dict):
        raise ValueError("Codex hook payload must be an object.")

    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
    hook_event = _hook_event_name(payload, event_name=event_name)
    timestamp = _hook_timestamp(payload, metadata, captured_at=captured_at)
    session_id = _session_id(payload, metadata)
    agent_id = str(payload.get("agent_id") or metadata.get("agent_id") or "codex")
    runtime = str(payload.get("runtime") or metadata.get("runtime") or "CODEX")
    project_id = str(payload.get("project_id") or metadata.get("project_id") or payload.get("cwd") or session_id)
    cwd = payload.get("cwd") or metadata.get("cwd")

    session_metadata = {
        "source": "codex_hook",
        "codex_hook_event": hook_event,
        "payload_keys": sorted(str(key) for key in payload.keys()),
    }
    if isinstance(cwd, str) and cwd:
        session_metadata["cwd"] = cwd
    if isinstance(metadata.get("thread_id"), str):
        session_metadata["thread_id"] = metadata["thread_id"]
    for payload_key, metadata_key in (
        ("permission_mode", "permission_mode"),
        ("source", "codex_hook_source"),
        ("transcript_path", "transcript_path"),
    ):
        value = payload.get(payload_key)
        if isinstance(value, str) and value:
            session_metadata[metadata_key] = value

    session = {
        "schema_version": "mneme.session.v0",
        "session_id": session_id,
        "agent_id": agent_id,
        "runtime": runtime,
        "project_id": project_id,
        "model": payload.get("model") or metadata.get("model"),
        "tokenizer": payload.get("tokenizer") or "approx",
        "context_window_tokens": payload.get("context_window_tokens") or 0,
        "cost_mode": payload.get("cost_mode") or "STANDARD",
        "started_at": timestamp,
        "metadata": session_metadata,
        "privacy": dict(
            payload.get("privacy")
            or {
                "project_isolation_key": project_id,
                "retention_days": 30,
                "redaction_profile": "DEFAULT",
                "redaction_policy": "IRREVERSIBLE",
            }
        ),
    }

    content_text = _content_text(payload, hook_event)
    event = {
        "schema_version": "mneme.event.v0",
        "event_id": _event_id(payload, hook_event=hook_event, session_id=session_id),
        "session_id": session_id,
        "turn_id": payload.get("turn_id") or metadata.get("turn_id"),
        "agent_id": agent_id,
        "runtime": runtime,
        "role": "RUNTIME",
        "type": "CODEX_HOOK",
        "timestamp": timestamp,
        "content": {"format": "TEXT", "text": content_text},
        "parent_event_ids": list(payload.get("parent_event_ids") or []),
        "metadata": {
            "source": "codex_hook",
            "codex_hook_event": hook_event,
            "payload_keys": sorted(str(key) for key in payload.keys()),
        },
        "token_estimate": token_estimate(content_text),
    }
    _enrich_event_metadata(event["metadata"], payload)

    return CodexHookPayloads(
        session=session,
        event_batch={"schema_version": "mneme.event_batch.v0", "session_id": session_id, "events": [event]},
    )


async def import_codex_hook_payload(
    payload: dict[str, Any],
    *,
    event_name: str | None = None,
    captured_at: str | None = None,
    base_url: str,
    token: str | None = None,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    payloads = normalize_codex_hook_payload(
        payload,
        event_name=event_name,
        captured_at=captured_at or _utc_now(),
    )
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers=headers,
        timeout=timeout,
        transport=transport,
    ) as client:
        session = await _post_json(client, "/v1/sessions/start", payloads.session)
        events = await _post_json(client, "/v1/events", payloads.event_batch)
    return {"session": session, "events": events}


async def import_codex_hook_capture_file(
    path: Path,
    *,
    base_url: str,
    token: str | None = None,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    results = []
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers=headers,
        timeout=timeout,
        transport=transport,
    ) as client:
        for item_event_name, payload, captured_at in _load_capture_items(path):
            payloads = normalize_codex_hook_payload(
                payload,
                event_name=item_event_name,
                captured_at=captured_at or _utc_now(),
            )
            session = await _post_json(client, "/v1/sessions/start", payloads.session)
            events = await _post_json(client, "/v1/events", payloads.event_batch)
            results.append(
                {
                    "event_name": item_event_name or _hook_event_name(payload),
                    "session_created": bool(session.get("created")),
                    "accepted": int(events.get("accepted", 0)),
                    "duplicates": int(events.get("duplicates", 0)),
                }
            )
    return {
        "schema_version": "mneme.codex_hook_capture_import.v0",
        "input_path": str(path),
        "payload_count": len(results),
        "accepted": sum(item["accepted"] for item in results),
        "duplicates": sum(item["duplicates"] for item in results),
        "results": results,
    }


def build_codex_context_prepare_request(
    payload: dict[str, Any],
    *,
    event_name: str | None = None,
    captured_at: str | None = None,
    context_window_tokens: int = DEFAULT_CODEX_CONTEXT_WINDOW_TOKENS,
    budget_tokens: int = DEFAULT_CODEX_CONTEXT_BUDGET_TOKENS,
    query: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Codex hook payload must be an object.")
    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
    hook_event = _hook_event_name(payload, event_name=event_name)
    session_id = _session_id(payload, metadata)
    turn_id = payload.get("turn_id") or metadata.get("turn_id")
    prompt = _prepare_prompt_text(payload, hook_event)
    request_key = {
        "session_id": session_id,
        "turn_id": turn_id,
        "hook_event": hook_event,
        "prompt": prompt,
        "captured_at": captured_at,
    }
    request_id = f"codex-prepare-{sha256_text(canonical_json(request_key))[:16]}"
    return {
        "schema_version": "mneme.context_prepare_request.v0",
        "request_id": request_id,
        "prepare_id": request_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "agent_id": str(payload.get("agent_id") or metadata.get("agent_id") or "codex"),
        "runtime": str(payload.get("runtime") or metadata.get("runtime") or "CODEX"),
        "model": payload.get("model") or metadata.get("model"),
        "context_window_tokens": context_window_tokens,
        "budget_tokens": budget_tokens,
        "request_messages": [
            {
                "schema_version": "mneme.message.v0",
                "role": "USER",
                "content": prompt,
            }
        ],
        "policy": {
            "mode": "AUTO",
            "cost_mode": "STANDARD",
            "preserve_system_prompt": True,
            "include_execution_state": True,
            "include_recent_tail": False,
            "include_retrieved_events": True,
            "retrieval": {"query": query or prompt, "top_k": 8},
            "budget_split": {
                "execution_state_ratio": 0.10,
                "retrieved_evidence_ratio": 0.55,
                "protected_tail_ratio": 0.25,
                "headroom_ratio": 0.10,
            },
        },
        "metadata": {
            "source": "codex_hook_context_preview",
            "codex_hook_event": hook_event,
            "codex_hook_captured_at": captured_at or _hook_timestamp(payload, metadata, captured_at=None),
        },
    }


async def prepare_codex_context_preview(
    payload: dict[str, Any],
    *,
    event_name: str | None = None,
    captured_at: str | None = None,
    output_path: Path | None = None,
    base_url: str,
    token: str | None = None,
    timeout: float = 10.0,
    context_window_tokens: int = DEFAULT_CODEX_CONTEXT_WINDOW_TOKENS,
    budget_tokens: int = DEFAULT_CODEX_CONTEXT_BUDGET_TOKENS,
    dry_run: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    receipt_timestamp = captured_at or _utc_now()
    prepare_request = build_codex_context_prepare_request(
        payload,
        event_name=event_name,
        captured_at=receipt_timestamp,
        context_window_tokens=context_window_tokens,
        budget_tokens=budget_tokens,
    )
    prepare_response: dict[str, Any] | None = None
    if not dry_run:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        ) as client:
            prepare_response = await _post_json(client, "/v1/context/prepare", prepare_request)
    record = {
        "schema_version": "mneme.codex_context_preview.v0",
        "event_name": _hook_event_name(payload, event_name=event_name),
        "captured_at": receipt_timestamp,
        "dry_run": dry_run,
        "codex_prompt_injection": "not_supported_by_current_command_hooks",
        "prepare_request": prepare_request,
        "prepare_response": prepare_response,
    }
    if output_path is not None:
        _append_jsonl(output_path, record)
    return record


def capture_codex_hook_payload(
    payload: dict[str, Any],
    *,
    output_path: Path,
    event_name: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Codex hook payload must be an object.")
    record = {
        "schema_version": "mneme.codex_hook_capture.v0",
        "event_name": _hook_event_name(payload, event_name=event_name),
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": payload,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
        handle.write("\n")
    return record


def current_codex_hook_timestamp() -> str:
    return _utc_now()


def validate_codex_hook_payload(
    payload: dict[str, Any],
    *,
    event_name: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
    warnings: list[str] = []
    if not _has_text(payload, metadata, ("session_id", "conversation_id", "thread_id")):
        warnings.append("SESSION_ID_INFERRED")
    if not (_has_text(payload, metadata, ("timestamp", "time")) or _has_text_value(captured_at)):
        warnings.append("TIMESTAMP_DEFAULTED")
    if not _has_text(payload, metadata, ("project_id", "cwd")):
        warnings.append("PROJECT_ID_INFERRED")
    if not _has_supported_content(payload, metadata):
        warnings.append("CONTENT_SUMMARY_FALLBACK")

    normalized = normalize_codex_hook_payload(payload, event_name=event_name, captured_at=captured_at)
    event = normalized.event_batch["events"][0]
    hook_event = _hook_event_name(payload, event_name=event_name)
    valid_for_enablement = not warnings
    return {
        "schema_version": "mneme.codex_hook_validation_report.v0",
        "event_name": hook_event,
        "valid_for_enablement": valid_for_enablement,
        "payload_keys": sorted(str(key) for key in payload.keys()),
        "warnings": warnings,
        "normalized": {
            "session_id": normalized.session["session_id"],
            "project_id": normalized.session["project_id"],
            "event_ids": [event["event_id"]],
            "event_count": len(normalized.event_batch["events"]),
            "event_timestamps": [event["timestamp"]],
            "has_turn_id": bool(event.get("turn_id")),
        },
    }


def validate_codex_hook_capture_file(path: Path, *, event_name: str | None = None) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": "mneme.codex_hook_capture_validation.v0",
            "input_path": str(path),
            "payload_count": 0,
            "valid_for_enablement": False,
            "warnings": ["CAPTURE_FILE_MISSING"],
            "reports": [],
        }
    reports = [
        validate_codex_hook_payload(
            payload,
            event_name=item_event_name or event_name,
            captured_at=captured_at,
        )
        for item_event_name, payload, captured_at in _load_capture_items(path)
    ]
    valid_for_enablement = bool(reports) and all(report["valid_for_enablement"] for report in reports)
    return {
        "schema_version": "mneme.codex_hook_capture_validation.v0",
        "warnings": [],
        "payload_count": len(reports),
        "valid_for_enablement": valid_for_enablement,
        "reports": reports,
    }


def select_codex_hook_capture_item(
    path: Path,
    *,
    event_name: str | None = None,
) -> tuple[str | None, dict[str, Any], str | None]:
    items = _load_capture_items(path)
    if not items:
        raise ValueError("Codex hook capture file is empty.")
    if event_name is None:
        return items[0]
    for item_event_name, payload, captured_at in items:
        item_name = item_event_name or _hook_event_name(payload)
        if item_name == event_name:
            return item_event_name, payload, captured_at
    raise ValueError(f"Codex hook capture file has no {event_name} event.")


def render_codex_hook_config(
    *,
    mode: str,
    python: str,
    capture_output: str = ".local/mneme-codex-hooks.jsonl",
    base_url: str = "http://127.0.0.1:8765",
    token_env: str = "MNEME_AUTH_TOKEN",
    timeout: float = 10.0,
) -> dict[str, Any]:
    if mode not in {"capture", "dry-run", "write"}:
        raise ValueError("mode must be one of: capture, dry-run, write.")

    hooks: dict[str, list[dict[str, Any]]] = {}
    for event_name, matcher in CODEX_HOOK_MATCHERS.items():
        hooks[event_name] = [
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": _render_hook_command(
                            event_name=event_name,
                            mode=mode,
                            python=python,
                            capture_output=capture_output,
                            base_url=base_url,
                            token_env=token_env,
                            timeout=timeout,
                        ),
                    }
                ],
            }
        ]

    return {"hooks": hooks}


def render_codex_context_preview_hook_config(
    *,
    python: str,
    output: str = DEFAULT_CODEX_CONTEXT_PREVIEW_OUTPUT,
    base_url: str = "http://127.0.0.1:8765",
    token_env: str = "MNEME_AUTH_TOKEN",
    timeout: float = 10.0,
    context_window_tokens: int = DEFAULT_CODEX_CONTEXT_WINDOW_TOKENS,
    budget_tokens: int = DEFAULT_CODEX_CONTEXT_BUDGET_TOKENS,
) -> dict[str, Any]:
    return {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": _render_context_preview_command(
                                python=python,
                                output=output,
                                base_url=base_url,
                                token_env=token_env,
                                timeout=timeout,
                                context_window_tokens=context_window_tokens,
                                budget_tokens=budget_tokens,
                            ),
                            "statusMessage": "Preparing Mneme context preview",
                        }
                    ],
                }
            ]
        }
    }


def _session_id(payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    for key in ("session_id", "conversation_id", "thread_id"):
        value = payload.get(key) or metadata.get(key)
        if isinstance(value, str) and value:
            return _safe_id(value)
    digest = sha256_text(canonical_json(payload))[:16]
    return f"codex-hook-{digest}"


def _hook_event_name(payload: dict[str, Any], *, event_name: str | None = None) -> str:
    for value in (
        event_name,
        payload.get("hook_event_name"),
        payload.get("hook_event"),
        payload.get("event"),
    ):
        if isinstance(value, str) and value:
            return value
    return "CodexHook"


def _hook_timestamp(payload: dict[str, Any], metadata: dict[str, Any], *, captured_at: str | None) -> str:
    for value in (payload.get("timestamp"), payload.get("time"), metadata.get("timestamp"), metadata.get("time"), captured_at):
        if isinstance(value, str) and value:
            return value
    return DEFAULT_TIMESTAMP


def _event_id(payload: dict[str, Any], *, hook_event: str, session_id: str) -> str:
    explicit = payload.get("event_id")
    if isinstance(explicit, str) and explicit:
        return _safe_id(explicit)
    stable = {
        "hook_event": hook_event,
        "session_id": session_id,
        "turn_id": payload.get("turn_id"),
        "tool_name": payload.get("tool_name"),
        "tool_use_id": payload.get("tool_use_id"),
        "summary": payload.get("summary"),
        "message": payload.get("message"),
        "prompt": payload.get("prompt"),
        "last_assistant_message": payload.get("last_assistant_message"),
        "tool_input": payload.get("tool_input"),
        "tool_response": payload.get("tool_response"),
        "payload_keys": sorted(str(key) for key in payload.keys()),
    }
    digest = sha256_text(canonical_json(stable))[:16]
    return _safe_id(f"codex-hook-{session_id}-{hook_event}-{digest}")


def _content_text(payload: dict[str, Any], hook_event: str) -> str:
    parts = [f"Codex hook {hook_event}"]
    for label, key in (("Summary", "summary"), ("Message", "message")):
        value = payload.get(key)
        if isinstance(value, str) and value:
            parts.append(f"{label}: {value}")
    prompt = payload.get("prompt")
    if isinstance(prompt, str) and prompt:
        parts.append(f"Prompt: {prompt}")
    assistant_message = payload.get("last_assistant_message")
    if isinstance(assistant_message, str) and assistant_message:
        parts.append(f"Assistant message: {assistant_message}")
    tool_name = payload.get("tool_name")
    if isinstance(tool_name, str) and tool_name:
        parts.append(f"Tool: {tool_name}")
    if "tool_input" in payload:
        parts.append(f"Tool input: {_format_hook_value(payload.get('tool_input'))}")
    if "tool_response" in payload:
        parts.append(f"Tool response: {_format_hook_value(payload.get('tool_response'))}")
    if hook_event == "SessionStart":
        for label, key in (
            ("Session source", "source"),
            ("Model", "model"),
            ("CWD", "cwd"),
            ("Permission mode", "permission_mode"),
        ):
            value = payload.get(key)
            if isinstance(value, str) and value:
                parts.append(f"{label}: {value}")
    if len(parts) == 1:
        parts.append(f"Payload keys: {', '.join(sorted(str(key) for key in payload.keys()))}")
    return "\n".join(parts)


def _enrich_event_metadata(metadata: dict[str, Any], payload: dict[str, Any]) -> None:
    for key in ("permission_mode", "tool_name", "tool_use_id", "transcript_path"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            metadata[key] = value
    source = payload.get("source")
    if isinstance(source, str) and source:
        metadata["codex_hook_source"] = source


def _format_hook_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return canonical_json(value)
    if isinstance(value, str):
        return value
    return str(value)


def _prepare_prompt_text(payload: dict[str, Any], hook_event: str) -> str:
    prompt = payload.get("prompt")
    if isinstance(prompt, str) and prompt:
        return prompt
    message = payload.get("message")
    if isinstance(message, str) and message:
        return message
    return _content_text(payload, hook_event)


def _has_supported_content(payload: dict[str, Any], metadata: dict[str, Any]) -> bool:
    string_keys = (
        "summary",
        "message",
        "prompt",
        "last_assistant_message",
        "tool_name",
        "source",
        "model",
        "cwd",
    )
    if _has_text(payload, metadata, string_keys):
        return True
    for key in ("tool_input", "tool_response"):
        if key in payload and payload.get(key) is not None:
            return True
        if key in metadata and metadata.get(key) is not None:
            return True
    return False


def _has_text(payload: dict[str, Any], metadata: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return True
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return True
    return False


def _has_text_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
        handle.write("\n")


def _load_capture_items(path: Path) -> list[tuple[str | None, dict[str, Any], str | None]]:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        raw_items = json.loads(stripped)
        if not isinstance(raw_items, list):
            raise ValueError("Codex hook capture JSON list expected.")
        return [_capture_item(raw_item) for raw_item in raw_items]
    if stripped.startswith("{") and "\n" not in stripped:
        return [_capture_item(json.loads(stripped))]
    items = []
    for line in text.splitlines():
        if line.strip():
            items.append(_capture_item(json.loads(line)))
    return items


def _capture_item(raw_item: Any) -> tuple[str | None, dict[str, Any], str | None]:
    if not isinstance(raw_item, dict):
        raise ValueError("Codex hook capture item must be an object.")
    if isinstance(raw_item.get("payload"), dict):
        event_name = raw_item.get("event_name")
        captured_at = raw_item.get("captured_at")
        return (
            str(event_name) if isinstance(event_name, str) else None,
            raw_item["payload"],
            str(captured_at) if isinstance(captured_at, str) else None,
        )
    captured_at = raw_item.get("captured_at")
    return None, raw_item, str(captured_at) if isinstance(captured_at, str) else None


def _render_hook_command(
    *,
    event_name: str,
    mode: str,
    python: str,
    capture_output: str,
    base_url: str,
    token_env: str,
    timeout: float,
) -> str:
    prefix = f"{shlex.quote(python)} -m mneme_codex_adapter.cli"
    if mode == "capture":
        parts = [
            prefix,
            "codex-hook-capture",
            "--input -",
            f"--event {shlex.quote(event_name)}",
            f"--output {shlex.quote(capture_output)}",
        ]
        return " ".join(parts)
    parts = [
        prefix,
        "codex-hook-ingest",
        "--input -",
        f"--event {shlex.quote(event_name)}",
    ]
    if mode == "dry-run":
        parts.append("--dry-run")
    else:
        parts.extend(
            [
                f"--base-url {shlex.quote(base_url)}",
                f'--token "${token_env}"',
                f"--timeout {timeout:g}",
            ]
        )
    return " ".join(parts)


def _render_context_preview_command(
    *,
    python: str,
    output: str,
    base_url: str,
    token_env: str,
    timeout: float,
    context_window_tokens: int,
    budget_tokens: int,
) -> str:
    parts = [
        f"{shlex.quote(python)} -m mneme_codex_adapter.cli",
        "codex-hook-prepare-preview",
        "--input -",
        "--event UserPromptSubmit",
        f"--output {shlex.quote(output)}",
        f"--base-url {shlex.quote(base_url)}",
        f'--token "${token_env}"',
        f"--timeout {timeout:g}",
        f"--context-window-tokens {context_window_tokens}",
        f"--budget-tokens {budget_tokens}",
    ]
    return " ".join(parts)
