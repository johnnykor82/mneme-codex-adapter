from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from mneme_service.app import create_app
from mneme_service.config import Settings


TOKEN = "test-token"


def sample_transcript() -> dict[str, Any]:
    return {
        "session": {
            "session_id": "codex-session-1",
            "agent_id": "codex",
            "runtime": "CODEX",
            "project_id": "mneme",
            "model": "gpt-5-codex",
            "started_at": "2026-06-12T12:00:00Z",
            "metadata": {"cwd": "/repo/mneme"},
        },
        "turns": [
            {
                "turn_id": "turn-1",
                "started_at": "2026-06-12T12:00:00Z",
                "completed_at": "2026-06-12T12:00:30Z",
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "tool_call_count": 1},
                "messages": [
                    {"role": "USER", "text": "Continue the Mneme ingestion work.", "timestamp": "2026-06-12T12:00:01Z"},
                    {"role": "ASSISTANT", "text": "I will add a Codex transcript importer.", "timestamp": "2026-06-12T12:00:02Z"},
                    {
                        "role": "TOOL",
                        "type": "TOOL_OUTPUT",
                        "text": "focused pytest passed with sk-codex-secret",
                        "timestamp": "2026-06-12T12:00:03Z",
                        "tool": {"name": "pytest", "call_id": "tool-call-1"},
                    },
                ],
            }
        ],
    }


def test_codex_transcript_normalizes_to_session_events_and_turn_payloads() -> None:
    from mneme_codex_adapter.ingest import normalize_codex_transcript

    payloads = normalize_codex_transcript(sample_transcript())

    assert payloads.session["schema_version"] == "mneme.session.v0"
    assert payloads.session["session_id"] == "codex-session-1"
    assert payloads.session["runtime"] == "CODEX"
    assert payloads.session["privacy"]["project_isolation_key"] == "mneme"

    assert payloads.event_batch["schema_version"] == "mneme.event_batch.v0"
    assert payloads.event_batch["session_id"] == "codex-session-1"
    events = payloads.event_batch["events"]
    assert [event["event_id"] for event in events] == [
        "codex-codex-session-1-turn-1-0001",
        "codex-codex-session-1-turn-1-0002",
        "codex-codex-session-1-turn-1-0003",
    ]
    assert [event["type"] for event in events] == ["USER_MESSAGE", "ASSISTANT_MESSAGE", "TOOL_OUTPUT"]
    assert events[1]["parent_event_ids"] == ["codex-codex-session-1-turn-1-0001"]
    assert events[2]["tool"] == {"name": "pytest", "call_id": "tool-call-1"}

    assert len(payloads.turns) == 1
    assert payloads.turns[0]["schema_version"] == "mneme.turn.v0"
    assert payloads.turns[0]["event_ids"] == [event["event_id"] for event in events]
    assert payloads.turns[0]["usage"]["tool_call_count"] == 1


def test_codex_transcript_imports_through_rest_and_replay_is_idempotent(tmp_path: Path) -> None:
    from mneme_codex_adapter.ingest import import_codex_transcript

    async def run() -> None:
        app = create_app(Settings(db_path=tmp_path / "mneme.db", auth_token=TOKEN))
        transport = httpx.ASGITransport(app=app)

        first = await import_codex_transcript(
            sample_transcript(),
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )
        assert first["session"]["created"] is True
        assert first["events"]["accepted"] == 3
        assert first["events"]["duplicates"] == 0
        assert first["turns"][0]["status"] == "RECORDED"

        second = await import_codex_transcript(
            sample_transcript(),
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )
        assert second["session"]["created"] is False
        assert second["events"]["accepted"] == 0
        assert second["events"]["duplicates"] == 3

    asyncio.run(run())


def test_codex_imported_secret_is_redacted_before_storage_and_search(tmp_path: Path) -> None:
    from mneme_codex_adapter.ingest import import_codex_transcript

    async def run() -> None:
        app = create_app(Settings(db_path=tmp_path / "mneme.db", auth_token=TOKEN))
        transport = httpx.ASGITransport(app=app)

        await import_codex_transcript(
            sample_transcript(),
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )
        async with httpx.AsyncClient(
            base_url="http://mneme.test",
            headers={"Authorization": f"Bearer {TOKEN}"},
            transport=transport,
        ) as client:
            exported = await client.get("/v1/sessions/codex-session-1/export")
            assert exported.status_code == 200
            body = exported.json()
            assert "sk-codex-secret" not in str(body)
            assert "[REDACTED]" in str(body)

            search = await client.post(
                "/v1/tools/context_search",
                json={"session_id": "codex-session-1", "query": "focused pytest secret", "scope": "SESSION", "top_k": 5},
            )
            assert search.status_code == 200
            assert "sk-codex-secret" not in str(search.json())

    asyncio.run(run())


def test_codex_ingest_cli_accepts_input_base_url_token_and_timeout() -> None:
    from mneme_codex_adapter.cli import build_parser

    args = build_parser().parse_args(
        [
            "codex-ingest",
            "--input",
            "transcript.json",
            "--base-url",
            "http://mneme.test",
            "--token",
            "secret-token",
            "--timeout",
            "3",
        ]
    )

    assert args.command == "codex-ingest"
    assert args.input == Path("transcript.json")
    assert args.base_url == "http://mneme.test"
    assert args.token == "secret-token"
    assert args.timeout == 3


def test_codex_ingest_usage_docs_are_offline_reference_only() -> None:
    guide_path = Path("adapters/codex/MNEME_CODEX_INGEST_USAGE.md")

    guide = guide_path.read_text(encoding="utf-8")

    assert "offline/reference" in guide
    assert "mneme-codex codex-ingest --input transcript.json" in guide
    assert "does not modify live Codex configuration" in guide
    assert "POST /v1/sessions/start" in guide
    assert "POST /v1/events" in guide
    assert "MCP remains read-side" in guide
