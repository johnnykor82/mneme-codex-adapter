from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from .hooks import (
    DEFAULT_CODEX_CONTEXT_BUDGET_TOKENS,
    DEFAULT_CODEX_CONTEXT_PREVIEW_OUTPUT,
    DEFAULT_CODEX_CONTEXT_WINDOW_TOKENS,
    DEFAULT_CODEX_HOOK_TIMEOUT_SECONDS,
    capture_codex_hook_payload,
    current_codex_hook_timestamp,
    import_codex_hook_capture_file,
    import_codex_hook_payload,
    normalize_codex_hook_payload,
    prepare_codex_context_preview,
    render_codex_context_preview_hook_config,
    render_codex_hook_config,
    select_codex_hook_capture_item,
    validate_codex_hook_capture_file,
)
from .ingest import import_codex_transcript
from .setup import (
    DEFAULT_CODEX_BASE_URL,
    DEFAULT_CODEX_INSTALL_ROOT,
    DEFAULT_CODEX_SERVICE_LABEL,
    codex_service_install,
    codex_service_logs,
    codex_service_start,
    codex_service_status,
    codex_service_stop,
    codex_service_uninstall,
    codex_desktop_status,
    install_mneme_memory_skill,
    resolve_token,
    setup_codex_desktop_global,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mneme-codex")
    subcommands = parser.add_subparsers(dest="command", required=True)

    codex_ingest = subcommands.add_parser("codex-ingest")
    codex_ingest.add_argument("--input", type=Path, required=True)
    codex_ingest.add_argument("--base-url", default=os.environ.get("MNEME_BASE_URL", "http://127.0.0.1:8765"))
    codex_ingest.add_argument("--token", default=os.environ.get("MNEME_AUTH_TOKEN"))
    codex_ingest.add_argument("--install-root", type=Path, default=Path(DEFAULT_CODEX_INSTALL_ROOT))
    codex_ingest.add_argument("--timeout", type=float, default=10.0)

    codex_hook_ingest = subcommands.add_parser("codex-hook-ingest")
    codex_hook_ingest.add_argument("--input", type=Path, required=True)
    codex_hook_ingest.add_argument("--event", default=None)
    codex_hook_ingest.add_argument("--base-url", default=os.environ.get("MNEME_BASE_URL", "http://127.0.0.1:8765"))
    codex_hook_ingest.add_argument("--token", default=os.environ.get("MNEME_AUTH_TOKEN"))
    codex_hook_ingest.add_argument("--install-root", type=Path, default=Path(DEFAULT_CODEX_INSTALL_ROOT))
    codex_hook_ingest.add_argument("--timeout", type=float, default=DEFAULT_CODEX_HOOK_TIMEOUT_SECONDS)
    codex_hook_ingest.add_argument("--dry-run", action="store_true")

    codex_hook_capture = subcommands.add_parser("codex-hook-capture")
    codex_hook_capture.add_argument("--input", type=Path, required=True)
    codex_hook_capture.add_argument("--event", default=None)
    codex_hook_capture.add_argument("--output", type=Path, required=True)

    codex_hook_validate = subcommands.add_parser("codex-hook-validate")
    codex_hook_validate.add_argument("--input", type=Path, required=True)
    codex_hook_validate.add_argument("--event", default=None)

    codex_hook_import_capture = subcommands.add_parser("codex-hook-import-capture")
    codex_hook_import_capture.add_argument("--input", type=Path, required=True)
    codex_hook_import_capture.add_argument("--base-url", default=os.environ.get("MNEME_BASE_URL", "http://127.0.0.1:8765"))
    codex_hook_import_capture.add_argument("--token", default=os.environ.get("MNEME_AUTH_TOKEN"))
    codex_hook_import_capture.add_argument("--install-root", type=Path, default=Path(DEFAULT_CODEX_INSTALL_ROOT))
    codex_hook_import_capture.add_argument("--timeout", type=float, default=DEFAULT_CODEX_HOOK_TIMEOUT_SECONDS)

    codex_hook_prepare_preview = subcommands.add_parser("codex-hook-prepare-preview")
    codex_hook_prepare_preview.add_argument("--input", type=Path, required=True)
    codex_hook_prepare_preview.add_argument("--event", default=None)
    codex_hook_prepare_preview.add_argument("--output", type=Path, default=Path(DEFAULT_CODEX_CONTEXT_PREVIEW_OUTPUT))
    codex_hook_prepare_preview.add_argument("--base-url", default=os.environ.get("MNEME_BASE_URL", "http://127.0.0.1:8765"))
    codex_hook_prepare_preview.add_argument("--token", default=os.environ.get("MNEME_AUTH_TOKEN"))
    codex_hook_prepare_preview.add_argument("--install-root", type=Path, default=Path(DEFAULT_CODEX_INSTALL_ROOT))
    codex_hook_prepare_preview.add_argument("--timeout", type=float, default=DEFAULT_CODEX_HOOK_TIMEOUT_SECONDS)
    codex_hook_prepare_preview.add_argument("--context-window-tokens", type=int, default=DEFAULT_CODEX_CONTEXT_WINDOW_TOKENS)
    codex_hook_prepare_preview.add_argument("--budget-tokens", type=int, default=DEFAULT_CODEX_CONTEXT_BUDGET_TOKENS)
    codex_hook_prepare_preview.add_argument("--dry-run", action="store_true")

    codex_hook_render_config = subcommands.add_parser("codex-hook-render-config")
    codex_hook_render_config.add_argument("--mode", choices=["capture", "dry-run", "write"], required=True)
    codex_hook_render_config.add_argument("--python", default=sys.executable)
    codex_hook_render_config.add_argument("--capture-output", default=".local/mneme-codex-hooks.jsonl")
    codex_hook_render_config.add_argument("--base-url", default=os.environ.get("MNEME_BASE_URL", "http://127.0.0.1:8765"))
    codex_hook_render_config.add_argument("--token-env", default="MNEME_AUTH_TOKEN")
    codex_hook_render_config.add_argument("--install-root", default=None)
    codex_hook_render_config.add_argument("--timeout", type=float, default=DEFAULT_CODEX_HOOK_TIMEOUT_SECONDS)
    codex_hook_render_config.add_argument("--output", type=Path, default=None)

    codex_hook_render_context_preview = subcommands.add_parser("codex-hook-render-context-preview-config")
    codex_hook_render_context_preview.add_argument("--python", default=sys.executable)
    codex_hook_render_context_preview.add_argument("--preview-output", default=DEFAULT_CODEX_CONTEXT_PREVIEW_OUTPUT)
    codex_hook_render_context_preview.add_argument("--base-url", default=os.environ.get("MNEME_BASE_URL", "http://127.0.0.1:8765"))
    codex_hook_render_context_preview.add_argument("--token-env", default="MNEME_AUTH_TOKEN")
    codex_hook_render_context_preview.add_argument("--timeout", type=float, default=DEFAULT_CODEX_HOOK_TIMEOUT_SECONDS)
    codex_hook_render_context_preview.add_argument("--context-window-tokens", type=int, default=DEFAULT_CODEX_CONTEXT_WINDOW_TOKENS)
    codex_hook_render_context_preview.add_argument("--budget-tokens", type=int, default=DEFAULT_CODEX_CONTEXT_BUDGET_TOKENS)
    codex_hook_render_context_preview.add_argument("--output", type=Path, default=None)

    setup = subcommands.add_parser("setup")
    setup_targets = setup.add_subparsers(dest="target", required=True)
    codex_desktop_setup = setup_targets.add_parser("codex-desktop")
    codex_desktop_setup.add_argument("--global", dest="global_install", action="store_true")
    codex_desktop_setup.add_argument("--install-root", type=Path, default=Path(DEFAULT_CODEX_INSTALL_ROOT))
    codex_desktop_setup.add_argument("--base-url", default=DEFAULT_CODEX_BASE_URL)
    codex_desktop_setup.add_argument("--python", default=sys.executable)
    codex_desktop_setup.add_argument("--codex-config-dir", type=Path, default=None)
    codex_desktop_setup.add_argument("--skip-user-hooks", action="store_true")
    codex_desktop_setup.add_argument("--dry-run", action="store_true")
    codex_desktop_setup.add_argument("--force-token", action="store_true")

    doctor = subcommands.add_parser("doctor")
    doctor.add_argument("--install-root", type=Path, default=Path(DEFAULT_CODEX_INSTALL_ROOT))
    doctor.add_argument("--base-url", default=os.environ.get("MNEME_BASE_URL", DEFAULT_CODEX_BASE_URL))
    doctor.add_argument("--token", default=os.environ.get("MNEME_AUTH_TOKEN"))
    doctor.add_argument("--service-label", default=DEFAULT_CODEX_SERVICE_LABEL)
    doctor.add_argument("--timeout", type=float, default=2.0)

    status = subcommands.add_parser("status")
    status.add_argument("--install-root", type=Path, default=Path(DEFAULT_CODEX_INSTALL_ROOT))
    status.add_argument("--base-url", default=os.environ.get("MNEME_BASE_URL", DEFAULT_CODEX_BASE_URL))
    status.add_argument("--token", default=os.environ.get("MNEME_AUTH_TOKEN"))
    status.add_argument("--service-label", default=DEFAULT_CODEX_SERVICE_LABEL)
    status.add_argument("--timeout", type=float, default=2.0)

    service = subcommands.add_parser("service")
    service_actions = service.add_subparsers(dest="action", required=True)
    for action_name in ("install", "start", "stop", "status", "logs", "uninstall"):
        action = service_actions.add_parser(action_name)
        action.add_argument("--install-root", type=Path, default=Path(DEFAULT_CODEX_INSTALL_ROOT))
        action.add_argument("--label", default=DEFAULT_CODEX_SERVICE_LABEL)
        if action_name in {"install", "start", "stop", "uninstall"}:
            action.add_argument("--dry-run", action="store_true")
        if action_name == "install":
            action.add_argument("--start", action="store_true")
        if action_name == "logs":
            action.add_argument("--lines", type=int, default=80)

    skill = subcommands.add_parser("skill")
    skill_actions = skill.add_subparsers(dest="action", required=True)
    skill_install = skill_actions.add_parser("install")
    skill_install.add_argument("--target-dir", type=Path, default=Path("~/.codex/skills"))
    skill_install.add_argument("--force", action="store_true")
    skill_install.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "codex-ingest":
        transcript = json.loads(args.input.read_text(encoding="utf-8"))
        result = asyncio.run(
            import_codex_transcript(
                transcript,
                base_url=args.base_url,
                token=resolve_token(token=args.token, install_root=args.install_root),
                timeout=args.timeout,
            )
        )
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "codex-hook-ingest":
        raw = sys.stdin.read() if str(args.input) == "-" else args.input.read_text(encoding="utf-8")
        payload = json.loads(raw)
        captured_at = current_codex_hook_timestamp()
        if args.dry_run:
            normalized = normalize_codex_hook_payload(payload, event_name=args.event, captured_at=captured_at)
            result = {"dry_run": True, "session": normalized.session, "event_batch": normalized.event_batch}
        else:
            result = asyncio.run(
                import_codex_hook_payload(
                    payload,
                    event_name=args.event,
                    captured_at=captured_at,
                    base_url=args.base_url,
                    token=resolve_token(token=args.token, install_root=args.install_root),
                    timeout=args.timeout,
                )
            )
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "codex-hook-capture":
        raw = sys.stdin.read() if str(args.input) == "-" else args.input.read_text(encoding="utf-8")
        payload = json.loads(raw)
        result = capture_codex_hook_payload(payload, output_path=args.output, event_name=args.event)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "codex-hook-validate":
        result = validate_codex_hook_capture_file(args.input, event_name=args.event)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "codex-hook-import-capture":
        result = asyncio.run(
            import_codex_hook_capture_file(
                args.input,
                base_url=args.base_url,
                token=resolve_token(token=args.token, install_root=args.install_root),
                timeout=args.timeout,
            )
        )
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "codex-hook-prepare-preview":
        if str(args.input) == "-":
            raw = sys.stdin.read()
            payload = json.loads(raw)
            captured_at = None
            event_name = args.event
            if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
                event_name = event_name or payload.get("event_name")
                captured_at = payload.get("captured_at") if isinstance(payload.get("captured_at"), str) else None
                payload = payload["payload"]
        else:
            item_event_name, payload, captured_at = select_codex_hook_capture_item(args.input, event_name=args.event)
            event_name = args.event or item_event_name
        result = asyncio.run(
            prepare_codex_context_preview(
                payload,
                event_name=event_name,
                captured_at=captured_at,
                output_path=args.output,
                base_url=args.base_url,
                token=resolve_token(token=args.token, install_root=args.install_root),
                timeout=args.timeout,
                context_window_tokens=args.context_window_tokens,
                budget_tokens=args.budget_tokens,
                dry_run=args.dry_run,
            )
        )
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "codex-hook-render-config":
        result = render_codex_hook_config(
            mode=args.mode,
            python=args.python,
            capture_output=args.capture_output,
            base_url=args.base_url,
            token_env=args.token_env,
            install_root=args.install_root,
            timeout=args.timeout,
        )
        _print_or_write(result, args.output)
        return

    if args.command == "codex-hook-render-context-preview-config":
        result = render_codex_context_preview_hook_config(
            python=args.python,
            output=args.preview_output,
            base_url=args.base_url,
            token_env=args.token_env,
            timeout=args.timeout,
            context_window_tokens=args.context_window_tokens,
            budget_tokens=args.budget_tokens,
        )
        _print_or_write(result, args.output)
        return

    if args.command == "setup":
        if args.target != "codex-desktop":
            raise SystemExit(f"Unsupported Codex setup target: {args.target}")
        if not args.global_install:
            raise SystemExit("setup codex-desktop currently requires --global.")
        result = setup_codex_desktop_global(
            install_root=args.install_root,
            base_url=args.base_url,
            python=args.python,
            codex_config_dir=args.codex_config_dir,
            install_user_hooks=not args.skip_user_hooks,
            dry_run=args.dry_run,
            force_token=args.force_token,
        )
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return

    if args.command in {"doctor", "status"}:
        result = codex_desktop_status(
            install_root=args.install_root,
            base_url=args.base_url,
            token=args.token,
            service_label=args.service_label,
            timeout=args.timeout,
        )
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "service":
        if args.action == "install":
            result = codex_service_install(
                install_root=args.install_root,
                label=args.label,
                start=args.start,
                dry_run=args.dry_run,
            )
        elif args.action == "start":
            result = codex_service_start(
                install_root=args.install_root,
                label=args.label,
                dry_run=args.dry_run,
            )
        elif args.action == "stop":
            result = codex_service_stop(
                install_root=args.install_root,
                label=args.label,
                dry_run=args.dry_run,
            )
        elif args.action == "status":
            result = codex_service_status(install_root=args.install_root, label=args.label)
        elif args.action == "logs":
            result = codex_service_logs(
                install_root=args.install_root,
                label=args.label,
                lines=args.lines,
            )
        elif args.action == "uninstall":
            result = codex_service_uninstall(
                install_root=args.install_root,
                label=args.label,
                dry_run=args.dry_run,
            )
        else:
            raise SystemExit(f"Unsupported service action: {args.action}")
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "skill":
        if args.action != "install":
            raise SystemExit(f"Unsupported skill action: {args.action}")
        result = install_mneme_memory_skill(
            target_dir=args.target_dir,
            force=args.force,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return


def _print_or_write(result: dict[str, object], output: Path | None) -> None:
    text = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False)
    if output is None:
        print(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
