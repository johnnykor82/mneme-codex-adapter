from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import httpx

from .utils import token_estimate


DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"


@dataclass(frozen=True)
class CodexIngestPayloads:
    session: dict[str, Any]
    event_batch: dict[str, Any]
    turns: list[dict[str, Any]]


class CodexIngestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int, body: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def normalize_codex_transcript(transcript: dict[str, Any]) -> CodexIngestPayloads:
    session_source = _required_object(transcript, "session")
    session_id = _required_str(session_source, "session_id")
    agent_id = str(session_source.get("agent_id") or "codex")
    runtime = str(session_source.get("runtime") or "CODEX")
    project_id = str(session_source.get("project_id") or session_id)
    started_at = str(session_source.get("started_at") or DEFAULT_TIMESTAMP)

    session = {
        "schema_version": "mneme.session.v0",
        "session_id": session_id,
        "agent_id": agent_id,
        "runtime": runtime,
        "project_id": project_id,
        "model": session_source.get("model"),
        "tokenizer": session_source.get("tokenizer", "approx"),
        "context_window_tokens": session_source.get("context_window_tokens", 0),
        "cost_mode": session_source.get("cost_mode", "STANDARD"),
        "started_at": started_at,
        "metadata": dict(session_source.get("metadata") or {}),
        "privacy": dict(
            session_source.get("privacy")
            or {
                "project_isolation_key": project_id,
                "retention_days": 30,
                "redaction_profile": "DEFAULT",
                "redaction_policy": "IRREVERSIBLE",
            }
        ),
    }

    events: list[dict[str, Any]] = []
    turn_payloads: list[dict[str, Any]] = []
    turns = transcript.get("turns") or []
    if not isinstance(turns, list):
        raise ValueError("Codex transcript requires turns to be a list.")

    for turn_index, raw_turn in enumerate(turns, start=1):
        if not isinstance(raw_turn, dict):
            raise ValueError("Codex transcript turn must be an object.")
        turn_id = str(raw_turn.get("turn_id") or f"turn-{turn_index}")
        messages = raw_turn.get("messages") or []
        if not isinstance(messages, list):
            raise ValueError("Codex transcript turn messages must be a list.")

        turn_event_ids: list[str] = []
        previous_event_id: str | None = None
        for message_index, raw_message in enumerate(messages, start=1):
            if not isinstance(raw_message, dict):
                raise ValueError("Codex transcript message must be an object.")
            event = _message_to_event(
                raw_message,
                session_id=session_id,
                turn_id=turn_id,
                turn_index=turn_index,
                message_index=message_index,
                agent_id=agent_id,
                runtime=runtime,
                default_timestamp=str(raw_turn.get("started_at") or started_at),
                previous_event_id=previous_event_id,
            )
            events.append(event)
            turn_event_ids.append(event["event_id"])
            previous_event_id = event["event_id"]

        if raw_turn.get("completed_at"):
            turn_payloads.append(
                {
                    "schema_version": "mneme.turn.v0",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "status": raw_turn.get("status", "COMPLETED"),
                    "started_at": raw_turn.get("started_at", started_at),
                    "completed_at": raw_turn["completed_at"],
                    "event_ids": turn_event_ids,
                    "usage": dict(raw_turn.get("usage") or {}),
                    "metadata": dict(raw_turn.get("metadata") or {}),
                }
            )

    return CodexIngestPayloads(
        session=session,
        event_batch={"schema_version": "mneme.event_batch.v0", "session_id": session_id, "events": events},
        turns=turn_payloads,
    )


async def import_codex_transcript(
    transcript: dict[str, Any],
    *,
    base_url: str,
    token: str | None = None,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    payloads = normalize_codex_transcript(transcript)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers=headers,
        timeout=timeout,
        transport=transport,
    ) as client:
        session = await _post_json(client, "/v1/sessions/start", payloads.session)
        events = await _post_json(client, "/v1/events", payloads.event_batch)
        turns = [await _post_json(client, "/v1/turns/complete", turn) for turn in payloads.turns]

    return {"session": session, "events": events, "turns": turns}


def _message_to_event(
    raw_message: dict[str, Any],
    *,
    session_id: str,
    turn_id: str,
    turn_index: int,
    message_index: int,
    agent_id: str,
    runtime: str,
    default_timestamp: str,
    previous_event_id: str | None,
) -> dict[str, Any]:
    role = str(raw_message.get("role") or "RUNTIME").upper()
    event_type = str(raw_message.get("type") or _default_event_type(role))
    event_id = str(raw_message.get("event_id") or _default_event_id(session_id, turn_id, message_index))
    content = raw_message.get("content")
    if not isinstance(content, dict):
        content = {"format": "TEXT", "text": str(raw_message.get("text") or "")}
    parent_event_ids = raw_message.get("parent_event_ids")
    if parent_event_ids is None:
        parent_event_ids = [previous_event_id] if previous_event_id else []

    metadata = {
        "source": "codex_transcript",
        "turn_index": turn_index,
        "message_index": message_index,
    }
    metadata.update(dict(raw_message.get("metadata") or {}))

    event = {
        "schema_version": "mneme.event.v0",
        "event_id": event_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "agent_id": agent_id,
        "runtime": runtime,
        "role": role,
        "type": event_type,
        "timestamp": raw_message.get("timestamp") or default_timestamp,
        "content": content,
        "parent_event_ids": list(parent_event_ids),
        "metadata": metadata,
        "token_estimate": raw_message.get("token_estimate") or token_estimate(str(content.get("text") or "")),
    }
    if isinstance(raw_message.get("tool"), dict):
        event["tool"] = dict(raw_message["tool"])
    return event


def _default_event_type(role: str) -> str:
    return {
        "SYSTEM": "SYSTEM_MESSAGE",
        "USER": "USER_MESSAGE",
        "ASSISTANT": "ASSISTANT_MESSAGE",
        "TOOL": "TOOL_OUTPUT",
        "RUNTIME": "STATE",
    }.get(role, "STATE")


def _default_event_id(session_id: str, turn_id: str, message_index: int) -> str:
    return _safe_id(f"codex-{session_id}-{turn_id}-{message_index:04d}")


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")


def _required_object(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"Codex transcript requires {field} object.")
    return value


def _required_str(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Codex transcript requires {field}.")
    return value


async def _post_json(client: httpx.AsyncClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(path, json=payload)
    if response.status_code >= 400:
        body = _response_json(response)
        raise CodexIngestError(f"Mneme import request failed: {path}", status_code=response.status_code, body=body)
    body = _response_json(response)
    if not isinstance(body, dict):
        raise CodexIngestError(f"Mneme import returned non-object response: {path}", status_code=response.status_code, body=body)
    return body


def _response_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text
