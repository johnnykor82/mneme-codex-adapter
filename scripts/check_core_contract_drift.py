#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
import tomllib

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _as_json_schema_ref_name(schema: object) -> str | None:
    if not isinstance(schema, dict):
        return None

    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        return ref.rsplit("/", 1)[-1]
    return None


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    match = _SEMVER_RE.match(version)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _bound_tuple(raw: str) -> tuple[int, int, int]:
    parts = raw.split(".")
    if len(parts) not in {2, 3} or not all(part.isdigit() for part in parts):
        raise ValueError(f"unsupported version bound: {raw}")
    values = [int(part) for part in parts]
    while len(values) < 3:
        values.append(0)
    return values[0], values[1], values[2]


def _version_satisfies(version: str, range_expr: str) -> bool:
    current = _version_tuple(version)
    if current is None:
        return False
    for item in range_expr.split(","):
        item = item.strip()
        if not item:
            continue
        if item.startswith(">="):
            if current < _bound_tuple(item.removeprefix(">=").strip()):
                return False
        elif item.startswith(">"):
            if current <= _bound_tuple(item.removeprefix(">").strip()):
                return False
        elif item.startswith("<="):
            if current > _bound_tuple(item.removeprefix("<=").strip()):
                return False
        elif item.startswith("<"):
            if current >= _bound_tuple(item.removeprefix("<").strip()):
                return False
        elif item.startswith("=="):
            if current != _bound_tuple(item.removeprefix("==").strip()):
                return False
        else:
            raise ValueError(f"unsupported range clause: {item}")
    return True


def _adapter_supported_contract_range(path: Path) -> str:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    value = data.get("tool", {}).get("mneme", {}).get("supported_core_contract")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing tool.mneme.supported_core_contract in {path}")
    return value.strip()


def _response_json_schema(operation: dict, status: str, errors: list[str], endpoint: str) -> object | None:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        errors.append(f"{endpoint}: missing responses")
        return None
    response = responses.get(status)
    if not isinstance(response, dict):
        errors.append(f"{endpoint}: missing response {status}")
        return None
    content = response.get("content")
    if not isinstance(content, dict):
        errors.append(f"{endpoint}: missing response content")
        return None
    schema = content.get("application/json", {}).get("schema")
    if not isinstance(schema, dict):
        errors.append(f"{endpoint}: missing application/json response schema")
        return None
    return schema


def _validate_schema_has_contract_version(
    schema_name: str,
    schemas: dict[str, object],
    version: str,
    errors: list[str],
    endpoint: str,
) -> None:
    schema = schemas.get(schema_name)
    if not isinstance(schema, dict):
        errors.append(f"{endpoint}: missing schema #{schema_name}")
        return

    props = schema.get("properties")
    if not isinstance(props, dict) or "mneme_contract_version" not in props:
        errors.append(f"{endpoint}: {schema_name} missing mneme_contract_version")
        return

    required = schema.get("required")
    if not isinstance(required, list) or "mneme_contract_version" not in required:
        errors.append(f"{endpoint}: {schema_name} does not require mneme_contract_version")

    prop = props["mneme_contract_version"]
    if isinstance(prop, dict):
        const = prop.get("const")
        if isinstance(const, str) and const != version:
            errors.append(
                f"{endpoint}: {schema_name} mneme_contract_version must match info.version"
            )


def _validate_openapi_contract(openapi: dict, supported_range: str | None = None) -> list[str]:
    errors: list[str] = []

    info = openapi.get("info")
    if not isinstance(info, dict):
        errors.append("missing info")
        return errors
    version = info.get("version")
    if not isinstance(version, str) or not _SEMVER_RE.match(version):
        errors.append("info.version missing or invalid semver")
        return errors
    if supported_range is not None:
        try:
            if not _version_satisfies(version, supported_range):
                errors.append(
                    f"info.version {version} is outside adapter supported range {supported_range}"
                )
        except ValueError as exc:
            errors.append(str(exc))

    paths = openapi.get("paths")
    if not isinstance(paths, dict):
        errors.append("missing paths")
        return errors

    required_paths = ("/v1/health", "/v1/capabilities", "/v1/context/prepare")
    for path in required_paths:
        if path not in paths:
            errors.append(f"missing required path: {path}")

    components = openapi.get("components")
    if not isinstance(components, dict):
        errors.append("missing components")
        return errors

    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        errors.append("missing components.schemas")
        return errors

    health_op = paths.get("/v1/health") if isinstance(paths, dict) else None
    if not isinstance(health_op, dict) or not isinstance(health_op.get("get"), dict):
        if isinstance(health_op, dict):
            errors.append("missing /v1/health GET operation")
    else:
        health_schema = _response_json_schema(health_op["get"], "200", errors, "/v1/health")
        if health_schema is not None:
            health_name = _as_json_schema_ref_name(health_schema)
            if health_name is None:
                errors.append("/v1/health: response schema should reference components schema")
            else:
                _validate_schema_has_contract_version(
                    health_name, schemas, version, errors, "/v1/health"
                )

    capabilities_op = paths.get("/v1/capabilities") if isinstance(paths, dict) else None
    if not isinstance(capabilities_op, dict) or not isinstance(capabilities_op.get("get"), dict):
        if isinstance(capabilities_op, dict):
            errors.append("missing /v1/capabilities GET operation")
    else:
        capabilities_schema = _response_json_schema(
            capabilities_op["get"], "200", errors, "/v1/capabilities"
        )
        if capabilities_schema is not None:
            capabilities_name = _as_json_schema_ref_name(capabilities_schema)
            if capabilities_name is None:
                errors.append("/v1/capabilities: response schema should reference components schema")
            else:
                _validate_schema_has_contract_version(
                    capabilities_name, schemas, version, errors, "/v1/capabilities"
                )

    prepare_op = paths.get("/v1/context/prepare") if isinstance(paths, dict) else None
    if not isinstance(prepare_op, dict) or not isinstance(prepare_op.get("post"), dict):
        if isinstance(prepare_op, dict):
            errors.append("missing /v1/context/prepare POST operation")
    else:
        req = prepare_op["post"].get("requestBody")
        if not isinstance(req, dict):
            errors.append("/v1/context/prepare: missing requestBody")
        else:
            req_content = req.get("content")
            if not isinstance(req_content, dict) or "application/json" not in req_content:
                errors.append("/v1/context/prepare: missing application/json request body")
        prep_schema = _response_json_schema(prepare_op["post"], "200", errors, "/v1/context/prepare")
        if prep_schema is not None:
            if not _as_json_schema_ref_name(prep_schema):
                errors.append("/v1/context/prepare: response schema should reference components schema")

    return errors


def run(path: Path, adapter_pyproject: Path | None = None) -> int:
    if not path.exists():
        print(f"openapi path not found: {path}", file=sys.stderr)
        return 1
    supported_range: str | None = None
    if adapter_pyproject is not None:
        try:
            supported_range = _adapter_supported_contract_range(adapter_pyproject)
        except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
            print(f"cannot load adapter contract range: {exc}", file=sys.stderr)
            return 1

    try:
        with path.open("r", encoding="utf-8") as fp:
            openapi = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot load openapi json: {exc}", file=sys.stderr)
        return 1

    errors = _validate_openapi_contract(openapi, supported_range=supported_range)
    if errors:
        for error in errors:
            print(f"{error}")
        print(f"FAIL: contract drift check found {len(errors)} issue(s)")
        return 1

    print("PASS: core contract drift check")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Core openapi contract fixture for adapter-facing endpoints."
    )
    parser.add_argument(
        "--openapi",
        required=True,
        help="Path to Core openapi.json fixture.",
    )
    parser.add_argument(
        "--adapter-pyproject",
        default=str(Path(__file__).resolve().parents[1] / "pyproject.toml"),
        help="Path to adapter pyproject.toml with tool.mneme.supported_core_contract.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(Path(args.openapi), adapter_pyproject=Path(args.adapter_pyproject))


if __name__ == "__main__":
    raise SystemExit(main())
