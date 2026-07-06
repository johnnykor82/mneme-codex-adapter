from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from mneme_service.app import create_app
from mneme_service.config import Settings


TOKEN = "test-token"


def sample_hook_payload() -> dict[str, Any]:
    return {
        "hook_event": "Stop",
        "session_id": "codex-hook-session",
        "turn_id": "turn-42",
        "agent_id": "codex",
        "runtime": "CODEX",
        "project_id": "mneme",
        "timestamp": "2026-06-14T12:00:00Z",
        "cwd": "/repo/mneme",
        "summary": "Completed Codex adapter foundation.",
        "message": "Stop hook saw tests pass with sk-hook-secret.",
        "metadata": {"thread_id": "thread-1"},
    }


REAL_CODEX_SESSION_ID = "019ec6c0-65a9-7bf3-9faa-830730a560c5"
REAL_CODEX_TURN_ID = "turn-real-1"
REAL_CODEX_PROJECT = "/workspace/mneme"
REAL_CODEX_CAPTURED_AT = "2026-06-14T12:34:56Z"


def real_session_start_payload() -> dict[str, Any]:
    return {
        "hook_event_name": "SessionStart",
        "session_id": REAL_CODEX_SESSION_ID,
        "cwd": REAL_CODEX_PROJECT,
        "model": "gpt-5-codex",
        "permission_mode": "on-request",
        "source": "startup",
        "transcript_path": "/home/user/.codex/sessions/session.jsonl",
    }


def real_user_prompt_payload() -> dict[str, Any]:
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": REAL_CODEX_SESSION_ID,
        "turn_id": REAL_CODEX_TURN_ID,
        "cwd": REAL_CODEX_PROJECT,
        "model": "gpt-5-codex",
        "permission_mode": "on-request",
        "prompt": "Validate real Mneme Codex hook capture.",
        "transcript_path": "/home/user/.codex/sessions/session.jsonl",
    }


def real_post_tool_use_payload() -> dict[str, Any]:
    return {
        "hook_event_name": "PostToolUse",
        "session_id": REAL_CODEX_SESSION_ID,
        "turn_id": REAL_CODEX_TURN_ID,
        "cwd": REAL_CODEX_PROJECT,
        "model": "gpt-5-codex",
        "permission_mode": "on-request",
        "tool_input": {"cmd": "pwd", "workdir": REAL_CODEX_PROJECT},
        "tool_name": "exec_command",
        "tool_response": {"exit_code": 0, "output": REAL_CODEX_PROJECT},
        "tool_use_id": "call-real-tool-1",
        "transcript_path": "/home/user/.codex/sessions/session.jsonl",
    }


def real_stop_payload() -> dict[str, Any]:
    return {
        "hook_event_name": "Stop",
        "session_id": REAL_CODEX_SESSION_ID,
        "turn_id": REAL_CODEX_TURN_ID,
        "cwd": REAL_CODEX_PROJECT,
        "last_assistant_message": "Validated the real hook capture path.",
        "model": "gpt-5-codex",
        "permission_mode": "on-request",
        "stop_hook_active": True,
        "transcript_path": "/home/user/.codex/sessions/session.jsonl",
    }


def real_codex_capture_records() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": "mneme.codex_hook_capture.v0",
            "event_name": "SessionStart",
            "captured_at": REAL_CODEX_CAPTURED_AT,
            "payload": real_session_start_payload(),
        },
        {
            "schema_version": "mneme.codex_hook_capture.v0",
            "event_name": "UserPromptSubmit",
            "captured_at": REAL_CODEX_CAPTURED_AT,
            "payload": real_user_prompt_payload(),
        },
        {
            "schema_version": "mneme.codex_hook_capture.v0",
            "event_name": "PostToolUse",
            "captured_at": REAL_CODEX_CAPTURED_AT,
            "payload": real_post_tool_use_payload(),
        },
        {
            "schema_version": "mneme.codex_hook_capture.v0",
            "event_name": "Stop",
            "captured_at": REAL_CODEX_CAPTURED_AT,
            "payload": real_stop_payload(),
        },
    ]


def test_codex_hook_normalizes_to_session_and_stable_event_payloads() -> None:
    from mneme_codex_adapter.hooks import normalize_codex_hook_payload

    first = normalize_codex_hook_payload(sample_hook_payload(), event_name="Stop")
    second = normalize_codex_hook_payload(sample_hook_payload(), event_name="Stop")

    assert first.session["schema_version"] == "mneme.session.v0"
    assert first.session["session_id"] == "codex-hook-session"
    assert first.session["runtime"] == "CODEX"
    assert first.session["project_id"] == "mneme"
    assert first.session["metadata"]["source"] == "codex_hook"
    assert first.session["metadata"]["cwd"] == "/repo/mneme"

    events = first.event_batch["events"]
    assert len(events) == 1
    event = events[0]
    assert event["event_id"] == second.event_batch["events"][0]["event_id"]
    assert event["schema_version"] == "mneme.event.v0"
    assert event["session_id"] == "codex-hook-session"
    assert event["turn_id"] == "turn-42"
    assert event["role"] == "RUNTIME"
    assert event["type"] == "CODEX_HOOK"
    assert event["metadata"]["source"] == "codex_hook"
    assert event["metadata"]["codex_hook_event"] == "Stop"
    assert event["metadata"]["payload_keys"] == sorted(sample_hook_payload().keys())
    assert "Completed Codex adapter foundation." in event["content"]["text"]
    assert "Stop hook saw tests pass" in event["content"]["text"]
    assert "raw_payload" not in event["metadata"]


def test_codex_hook_normalizes_real_codex_desktop_fields() -> None:
    from mneme_codex_adapter.hooks import normalize_codex_hook_payload

    prompt = normalize_codex_hook_payload(
        real_user_prompt_payload(),
        captured_at=REAL_CODEX_CAPTURED_AT,
    )
    tool = normalize_codex_hook_payload(
        real_post_tool_use_payload(),
        captured_at=REAL_CODEX_CAPTURED_AT,
    )
    stop = normalize_codex_hook_payload(
        real_stop_payload(),
        captured_at=REAL_CODEX_CAPTURED_AT,
    )

    prompt_event = prompt.event_batch["events"][0]
    tool_event = tool.event_batch["events"][0]
    stop_event = stop.event_batch["events"][0]

    assert prompt.session["project_id"] == REAL_CODEX_PROJECT
    assert prompt_event["role"] == "USER"
    assert prompt_event["type"] == "USER_MESSAGE"
    assert prompt_event["metadata"]["codex_hook_event"] == "UserPromptSubmit"
    assert prompt_event["timestamp"] == REAL_CODEX_CAPTURED_AT
    assert prompt_event["content"]["text"] == "Validate real Mneme Codex hook capture."
    assert "Payload keys:" not in prompt_event["content"]["text"]

    assert tool_event["role"] == "RUNTIME"
    assert tool_event["type"] == "CODEX_HOOK"
    assert tool_event["metadata"]["codex_hook_event"] == "PostToolUse"
    assert tool_event["metadata"]["tool_name"] == "exec_command"
    assert tool_event["metadata"]["tool_use_id"] == "call-real-tool-1"
    assert "Tool: exec_command" in tool_event["content"]["text"]
    assert "Tool input:" in tool_event["content"]["text"]
    assert "Tool response:" in tool_event["content"]["text"]

    assert stop_event["metadata"]["codex_hook_event"] == "Stop"
    assert "Validated the real hook capture path." in stop_event["content"]["text"]


def test_codex_hook_imports_through_rest_and_replay_is_idempotent(tmp_path: Path) -> None:
    from mneme_codex_adapter.hooks import import_codex_hook_payload

    async def run() -> None:
        app = create_app(Settings(db_path=tmp_path / "mneme.db", auth_token=TOKEN))
        transport = httpx.ASGITransport(app=app)

        first = await import_codex_hook_payload(
            sample_hook_payload(),
            event_name="Stop",
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )
        assert first["session"]["created"] is True
        assert first["events"]["accepted"] == 1
        assert first["events"]["duplicates"] == 0

        second = await import_codex_hook_payload(
            sample_hook_payload(),
            event_name="Stop",
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )
        assert second["session"]["created"] is False
        assert second["events"]["accepted"] == 0
        assert second["events"]["duplicates"] == 1

    asyncio.run(run())


def test_codex_hook_import_capture_file_replays_real_capture_through_rest(tmp_path: Path) -> None:
    from mneme_codex_adapter.hooks import import_codex_hook_capture_file

    capture_path = tmp_path / "real-captures.jsonl"
    capture_path.write_text(
        "\n".join(json.dumps(record) for record in real_codex_capture_records()),
        encoding="utf-8",
    )

    async def run() -> None:
        app = create_app(Settings(db_path=tmp_path / "mneme.db", auth_token=TOKEN))
        transport = httpx.ASGITransport(app=app)

        first = await import_codex_hook_capture_file(
            capture_path,
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )
        assert first["schema_version"] == "mneme.codex_hook_capture_import.v0"
        assert first["payload_count"] == 4
        assert first["accepted"] == 4
        assert first["duplicates"] == 0

        second = await import_codex_hook_capture_file(
            capture_path,
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )
        assert second["accepted"] == 0
        assert second["duplicates"] == 4

    asyncio.run(run())


def test_codex_hook_prepare_preview_writes_context_file(tmp_path: Path) -> None:
    from mneme_codex_adapter.hooks import (
        import_codex_hook_capture_file,
        prepare_codex_context_preview,
    )

    capture_path = tmp_path / "real-captures.jsonl"
    preview_path = tmp_path / "context-preview.jsonl"
    capture_path.write_text(
        "\n".join(json.dumps(record) for record in real_codex_capture_records()),
        encoding="utf-8",
    )

    async def run() -> None:
        app = create_app(Settings(db_path=tmp_path / "mneme.db", auth_token=TOKEN))
        transport = httpx.ASGITransport(app=app)
        await import_codex_hook_capture_file(
            capture_path,
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )

        preview = await prepare_codex_context_preview(
            real_user_prompt_payload(),
            event_name="UserPromptSubmit",
            captured_at=REAL_CODEX_CAPTURED_AT,
            output_path=preview_path,
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )

        assert preview["schema_version"] == "mneme.codex_context_preview.v0"
        assert preview["event_name"] == "UserPromptSubmit"
        assert preview["codex_prompt_injection"] == "not_supported_by_current_command_hooks"
        assert preview["prepare_request"]["session_id"] == REAL_CODEX_SESSION_ID
        assert preview["prepare_response"]["schema_version"] == "mneme.context_prepare_response.v0"
        assert preview["prepare_response"]["changed"] is True

        record = json.loads(preview_path.read_text(encoding="utf-8"))
        assert record["prepare_response"]["trace_id"]
        rendered_messages = "\n".join(
            message["content"]
            for message in record["prepare_response"]["messages"]
            if isinstance(message, dict)
        )
        assert "[MNEME RETRIEVED EVIDENCE]" in rendered_messages

    asyncio.run(run())


def test_codex_hook_secret_is_redacted_after_service_ingestion(tmp_path: Path) -> None:
    from mneme_codex_adapter.hooks import import_codex_hook_payload

    async def run() -> None:
        app = create_app(Settings(db_path=tmp_path / "mneme.db", auth_token=TOKEN))
        transport = httpx.ASGITransport(app=app)

        await import_codex_hook_payload(
            sample_hook_payload(),
            event_name="Stop",
            base_url="http://mneme.test",
            token=TOKEN,
            transport=transport,
        )
        async with httpx.AsyncClient(
            base_url="http://mneme.test",
            headers={"Authorization": f"Bearer {TOKEN}"},
            transport=transport,
        ) as client:
            exported = await client.get("/v1/sessions/codex-hook-session/export")
            assert exported.status_code == 200
            body = exported.json()
            assert "sk-hook-secret" not in str(body)
            assert "[REDACTED]" in str(body)

    asyncio.run(run())


def test_codex_hook_ingest_cli_accepts_input_event_and_dry_run() -> None:
    from mneme_codex_adapter.cli import build_parser

    args = build_parser().parse_args(
        [
            "codex-hook-ingest",
            "--input",
            "hook.json",
            "--event",
            "PostCompact",
            "--base-url",
            "http://mneme.test",
            "--token",
            "secret-token",
            "--timeout",
            "3",
            "--dry-run",
        ]
    )

    assert args.command == "codex-hook-ingest"
    assert args.input == Path("hook.json")
    assert args.event == "PostCompact"
    assert args.base_url == "http://mneme.test"
    assert args.token == "secret-token"
    assert args.timeout == 3
    assert args.dry_run is True


def test_codex_hook_ingest_cli_dry_run_prints_normalized_payload(tmp_path: Path, capsys: Any) -> None:
    from mneme_codex_adapter.cli import main

    hook_path = tmp_path / "hook.json"
    hook_path.write_text(json.dumps(sample_hook_payload()), encoding="utf-8")

    main(["codex-hook-ingest", "--input", str(hook_path), "--event", "Stop", "--dry-run"])

    output = json.loads(capsys.readouterr().out)
    assert output["dry_run"] is True
    assert output["session"]["session_id"] == "codex-hook-session"
    assert output["event_batch"]["events"][0]["metadata"]["codex_hook_event"] == "Stop"


def test_codex_hook_prepare_preview_cli_dry_run_writes_jsonl(tmp_path: Path, capsys: Any) -> None:
    from mneme_codex_adapter.cli import main

    hook_path = tmp_path / "hook.json"
    preview_path = tmp_path / "preview.jsonl"
    hook_path.write_text(json.dumps(real_user_prompt_payload()), encoding="utf-8")

    main(
        [
            "codex-hook-prepare-preview",
            "--input",
            str(hook_path),
            "--event",
            "UserPromptSubmit",
            "--output",
            str(preview_path),
            "--dry-run",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    record = json.loads(preview_path.read_text(encoding="utf-8"))
    assert output["dry_run"] is True
    assert output["prepare_response"] is None
    assert record["prepare_request"]["session_id"] == REAL_CODEX_SESSION_ID
    assert record["prepare_request"]["request_messages"][0]["content"] == real_user_prompt_payload()["prompt"]


def test_codex_hook_prepare_preview_cli_selects_event_from_capture_jsonl(tmp_path: Path, capsys: Any) -> None:
    from mneme_codex_adapter.cli import main

    capture_path = tmp_path / "real-captures.jsonl"
    preview_path = tmp_path / "preview.jsonl"
    capture_path.write_text(
        "\n".join(json.dumps(record) for record in real_codex_capture_records()),
        encoding="utf-8",
    )

    main(
        [
            "codex-hook-prepare-preview",
            "--input",
            str(capture_path),
            "--event",
            "UserPromptSubmit",
            "--output",
            str(preview_path),
            "--dry-run",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["event_name"] == "UserPromptSubmit"
    assert output["captured_at"] == REAL_CODEX_CAPTURED_AT
    assert output["prepare_request"]["request_messages"][0]["content"] == real_user_prompt_payload()["prompt"]


def test_codex_hook_validation_reports_enablement_readiness_without_content_leak() -> None:
    from mneme_codex_adapter.hooks import validate_codex_hook_payload

    report = validate_codex_hook_payload({"message": "payload has sk-hook-secret"}, event_name="Stop")

    assert report["schema_version"] == "mneme.codex_hook_validation_report.v0"
    assert report["valid_for_enablement"] is False
    assert report["event_name"] == "Stop"
    assert report["payload_keys"] == ["message"]
    assert "SESSION_ID_INFERRED" in report["warnings"]
    assert "TIMESTAMP_DEFAULTED" in report["warnings"]
    assert "PROJECT_ID_INFERRED" in report["warnings"]
    assert report["normalized"]["event_count"] == 1
    assert report["normalized"]["session_id"].startswith("codex-hook-")
    assert "sk-hook-secret" not in json.dumps(report, sort_keys=True)


def test_codex_hook_capture_file_validation_summarizes_jsonl(tmp_path: Path) -> None:
    from mneme_codex_adapter.hooks import validate_codex_hook_capture_file

    capture_path = tmp_path / "captures.jsonl"
    capture_path.write_text(
        "\n".join(
            [
                json.dumps({"event_name": "Stop", "payload": sample_hook_payload()}),
                json.dumps({"payload": {"message": "missing identifiers sk-hook-secret"}}),
            ]
        ),
        encoding="utf-8",
    )

    summary = validate_codex_hook_capture_file(capture_path)

    assert summary["schema_version"] == "mneme.codex_hook_capture_validation.v0"
    assert summary["payload_count"] == 2
    assert summary["valid_for_enablement"] is False
    assert summary["reports"][0]["valid_for_enablement"] is True
    assert summary["reports"][1]["valid_for_enablement"] is False
    assert "sk-hook-secret" not in json.dumps(summary, sort_keys=True)


def test_codex_hook_capture_validation_accepts_real_codex_desktop_payload_shapes(tmp_path: Path) -> None:
    from mneme_codex_adapter.hooks import validate_codex_hook_capture_file

    capture_path = tmp_path / "real-captures.jsonl"
    capture_path.write_text(
        "\n".join(json.dumps(record) for record in real_codex_capture_records()),
        encoding="utf-8",
    )

    first = validate_codex_hook_capture_file(capture_path)
    second = validate_codex_hook_capture_file(capture_path)

    assert first["schema_version"] == "mneme.codex_hook_capture_validation.v0"
    assert first["payload_count"] == 4
    assert first["valid_for_enablement"] is True
    assert [report["event_name"] for report in first["reports"]] == [
        "SessionStart",
        "UserPromptSubmit",
        "PostToolUse",
        "Stop",
    ]
    assert all(report["warnings"] == [] for report in first["reports"])
    assert all(
        report["normalized"]["session_id"] == REAL_CODEX_SESSION_ID
        for report in first["reports"]
    )
    assert all(
        report["normalized"]["project_id"] == REAL_CODEX_PROJECT
        for report in first["reports"]
    )
    assert all(
        report["normalized"]["event_timestamps"] == [REAL_CODEX_CAPTURED_AT]
        for report in first["reports"]
    )
    assert first["reports"][0]["normalized"]["has_turn_id"] is False
    assert all(report["normalized"]["has_turn_id"] for report in first["reports"][1:])
    assert [report["normalized"]["event_ids"] for report in first["reports"]] == [
        report["normalized"]["event_ids"] for report in second["reports"]
    ]


def test_codex_hook_capture_file_validation_reports_missing_file(tmp_path: Path) -> None:
    from mneme_codex_adapter.hooks import validate_codex_hook_capture_file

    missing_path = tmp_path / "missing.jsonl"

    summary = validate_codex_hook_capture_file(missing_path)

    assert summary["schema_version"] == "mneme.codex_hook_capture_validation.v0"
    assert summary["payload_count"] == 0
    assert summary["valid_for_enablement"] is False
    assert summary["warnings"] == ["CAPTURE_FILE_MISSING"]
    assert summary["input_path"] == str(missing_path)
    assert summary["reports"] == []


def test_codex_hook_capture_cli_appends_jsonl_record(tmp_path: Path) -> None:
    from mneme_codex_adapter.cli import main

    hook_path = tmp_path / "hook.json"
    capture_path = tmp_path / "captures.jsonl"
    hook_path.write_text(json.dumps(sample_hook_payload()), encoding="utf-8")

    main(["codex-hook-capture", "--input", str(hook_path), "--event", "Stop", "--output", str(capture_path)])

    record = json.loads(capture_path.read_text(encoding="utf-8"))
    assert record["schema_version"] == "mneme.codex_hook_capture.v0"
    assert record["event_name"] == "Stop"
    assert record["payload"]["session_id"] == "codex-hook-session"
    assert record["captured_at"]


def test_codex_hook_validate_cli_prints_capture_summary(tmp_path: Path, capsys: Any) -> None:
    from mneme_codex_adapter.cli import main

    capture_path = tmp_path / "captures.jsonl"
    capture_path.write_text(json.dumps({"event_name": "Stop", "payload": sample_hook_payload()}), encoding="utf-8")

    main(["codex-hook-validate", "--input", str(capture_path)])

    output = json.loads(capsys.readouterr().out)
    assert output["payload_count"] == 1
    assert output["valid_for_enablement"] is True
    assert output["reports"][0]["normalized"]["session_id"] == "codex-hook-session"


def test_codex_hook_render_capture_config_uses_explicit_python_runner() -> None:
    from mneme_codex_adapter.hooks import render_codex_hook_config

    config = render_codex_hook_config(
        mode="capture",
        python="/tmp/mneme venv/bin/python",
        capture_output=".local/captures.jsonl",
    )
    serialized = json.dumps(config, sort_keys=True)

    assert sorted(config.keys()) == ["hooks"]

    for event_name in ("SessionStart", "UserPromptSubmit", "PostCompact", "PostToolUse", "Stop"):
        command = config["hooks"][event_name][0]["hooks"][0]["command"]
        assert "'/tmp/mneme venv/bin/python' -m mneme_codex_adapter.cli" in command
        assert "codex-hook-capture" in command
        assert f"--event {event_name}" in command
        assert "--input -" in command
        assert "--output .local/captures.jsonl" in command
        assert "codex-hook-ingest" not in command

    assert "MNEME_AUTH_TOKEN" not in serialized


def test_codex_hook_render_write_config_keeps_validation_warning_and_token_env() -> None:
    from mneme_codex_adapter.hooks import render_codex_hook_config

    config = render_codex_hook_config(
        mode="write",
        python="/opt/mneme/bin/python",
        base_url="http://127.0.0.1:9876",
        token_env="MNEME_TOKEN",
        timeout=2.5,
    )

    for event_name in ("SessionStart", "UserPromptSubmit", "PostCompact", "PostToolUse", "Stop"):
        command = config["hooks"][event_name][0]["hooks"][0]["command"]
        assert "/opt/mneme/bin/python -m mneme_codex_adapter.cli" in command
        assert "codex-hook-ingest" in command
        assert f"--event {event_name}" in command
        assert "--input -" in command
        assert "--dry-run" not in command
        assert "--base-url http://127.0.0.1:9876" in command
        assert "--token \"$MNEME_TOKEN\"" in command
        assert "--timeout 2.5" in command


def test_codex_hook_render_write_config_can_resolve_token_from_install_root() -> None:
    from mneme_codex_adapter.hooks import render_codex_hook_config

    config = render_codex_hook_config(
        mode="write",
        python="/opt/mneme/bin/python",
        base_url="http://127.0.0.1:9876",
        install_root="/Users/example/.mneme-codex",
    )

    command = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "codex-hook-ingest" in command
    assert "--base-url http://127.0.0.1:9876" in command
    assert "--install-root /Users/example/.mneme-codex" in command
    assert "--timeout 300" in command
    assert "--token" not in command
    assert "MNEME_AUTH_TOKEN" not in command


def test_codex_hook_render_config_cli_prints_json(capsys: Any) -> None:
    from mneme_codex_adapter.cli import main

    main(
        [
            "codex-hook-render-config",
            "--mode",
            "dry-run",
            "--python",
            "/opt/mneme/bin/python",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    command = output["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "codex-hook-ingest" in command
    assert "--dry-run" in command


def test_codex_hook_render_context_preview_config_cli_prints_user_prompt_hook(capsys: Any) -> None:
    from mneme_codex_adapter.cli import main

    main(
        [
            "codex-hook-render-context-preview-config",
            "--python",
            "/opt/mneme/bin/python",
            "--preview-output",
            ".local/preview.jsonl",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert sorted(output["hooks"].keys()) == ["UserPromptSubmit"]
    command = output["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "/opt/mneme/bin/python -m mneme_codex_adapter.cli" in command
    assert "codex-hook-prepare-preview" in command
    assert "--input -" in command
    assert "--event UserPromptSubmit" in command
    assert "--output .local/preview.jsonl" in command
    assert "--token \"$MNEME_AUTH_TOKEN\"" in command
    assert "--timeout 300" in command


def test_project_local_codex_hooks_file_is_ignored() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert ".codex/hooks.json" in gitignore


def test_codex_hook_capture_example_is_capture_only_and_publication_friendly() -> None:
    config = json.loads(Path("adapters/codex/codex_hooks.capture.example.json").read_text(encoding="utf-8"))
    serialized = json.dumps(config, sort_keys=True).lower()

    meta = config["mneme_codex_hook_capture_example"]
    assert meta["status"] == "capture_only"
    assert meta["writes_enabled"] is False
    assert meta["output_path"] == ".local/mneme-codex-hooks.jsonl"
    assert "mneme-codex codex-hook-validate --input .local/mneme-codex-hooks.jsonl" in meta["next_command"]

    for event_name in ("SessionStart", "UserPromptSubmit", "PostCompact", "PostToolUse", "Stop"):
        assert event_name in config["hooks"]
        command = config["hooks"][event_name][0]["hooks"][0]["command"]
        assert "mneme-codex codex-hook-capture" in command
        assert "--input -" in command
        assert "--output .local/mneme-codex-hooks.jsonl" in command
        assert "codex-hook-ingest" not in command

    assert "/users/openclaw/.hermes/hermes-agent" not in serialized
    assert "/users/openclaw/.hermes/plugins/hermes-mneme" not in serialized


def test_codex_hooks_usage_doc_documents_direct_ingest_default_and_fallback() -> None:
    guide = Path("adapters/codex/MNEME_CODEX_HOOKS_USAGE.md").read_text(encoding="utf-8")
    lower = guide.lower()

    assert "setup codex-desktop --global" in lower
    assert "$home/.codex/hooks.json" in lower
    assert "direct-ingest hooks by default" in lower
    assert "mneme_codex_adapter.cli codex-hook-ingest" in lower
    assert "--install-root" in lower
    assert "does not embed the bearer token" in lower
    assert "approve the installed hooks" in lower
    assert "mneme-codex codex-hook-ingest --input hook.json --event stop --dry-run" in lower
    assert "mneme-codex codex-hook-validate" in lower
    assert "mneme-codex codex-hook-import-capture" in lower
    assert "mneme-codex codex-hook-prepare-preview" in lower
    assert "capture-only remains available" in lower
    assert "codex prompt injection is" in lower
    assert "not supported by current command hooks" in lower
    assert "codex-hook-render-config" in lower
    assert "--mode capture" in lower
    assert "mcp remains read-only" in lower
    assert "do not paste" in lower
