from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _script(path: str) -> list[str]:
    return [str(sys.executable), str(_repo_root() / "scripts" / path)]


def test_check_no_core_internal_imports_passes_within_clean_adapter(tmp_path: Path) -> None:
    package_dir = tmp_path / "mneme_codex_adapter"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("\n", encoding="utf-8")
    (package_dir / "clean.py").write_text("import os\n", encoding="utf-8")

    result = subprocess.run(
        _script("check_no_core_internal_imports.py") + ["--path", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "FAIL" not in result.stdout


def test_check_no_core_internal_imports_blocks_core_import_outside_tests(tmp_path: Path) -> None:
    package_dir = tmp_path / "mneme_codex_adapter"
    package_dir.mkdir()
    (package_dir / "bad.py").write_text("from mneme_service.app import create_app\n", encoding="utf-8")

    result = subprocess.run(
        _script("check_no_core_internal_imports.py") + ["--path", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "mneme_service" in result.stdout


def test_check_no_core_internal_imports_ignores_tests_by_default(tmp_path: Path) -> None:
    package_dir = tmp_path / "mneme_codex_adapter"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_bad.py").write_text("from mneme_service.app import create_app\n", encoding="utf-8")

    result = subprocess.run(
        _script("check_no_core_internal_imports.py") + ["--path", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "FAIL" not in result.stdout


def test_check_core_contract_drift_valid_openapi(tmp_path: Path) -> None:
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "mneme", "version": "0.7.5"},
        "paths": {
            "/v1/health": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/HealthResponse"
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/v1/capabilities": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/CapabilitiesResponse"
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/v1/context/prepare": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/ContextPrepareRequest"
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ContextPrepareResponse"
                                    }
                                }
                            }
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "HealthResponse": {
                    "type": "object",
                    "required": ["mneme_contract_version"],
                    "properties": {
                        "mneme_contract_version": {
                            "type": "string"
                        }
                    },
                },
                "CapabilitiesResponse": {
                    "type": "object",
                    "required": ["mneme_contract_version"],
                    "properties": {
                        "mneme_contract_version": {
                            "type": "string"
                        }
                    },
                },
                "ContextPrepareRequest": {"type": "object"},
                "ContextPrepareResponse": {"type": "object"},
            }
        },
    }

    openapi_path = tmp_path / "openapi.json"
    openapi_path.write_text(json.dumps(openapi), encoding="utf-8")
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[tool.mneme]\nsupported_core_contract = ">=0.7,<0.8"\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        _script("check_core_contract_drift.py")
        + ["--openapi", str(openapi_path), "--adapter-pyproject", str(pyproject_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "PASS" in result.stdout


def test_check_core_contract_drift_fails_when_contract_range_mismatches(tmp_path: Path) -> None:
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "mneme", "version": "0.8.0"},
        "paths": {
            "/v1/health": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"}
                                }
                            }
                        }
                    }
                }
            },
            "/v1/capabilities": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CapabilitiesResponse"}
                                }
                            }
                        }
                    }
                }
            },
            "/v1/context/prepare": {
                "post": {
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ContextPrepareResponse"}
                                }
                            }
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "HealthResponse": {
                    "required": ["mneme_contract_version"],
                    "properties": {"mneme_contract_version": {"type": "string"}},
                },
                "CapabilitiesResponse": {
                    "required": ["mneme_contract_version"],
                    "properties": {"mneme_contract_version": {"type": "string"}},
                },
                "ContextPrepareResponse": {"type": "object"},
            }
        },
    }
    openapi_path = tmp_path / "openapi.json"
    openapi_path.write_text(json.dumps(openapi), encoding="utf-8")
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[tool.mneme]\nsupported_core_contract = ">=0.7,<0.8"\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        _script("check_core_contract_drift.py")
        + ["--openapi", str(openapi_path), "--adapter-pyproject", str(pyproject_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "outside adapter supported range" in result.stdout


def test_check_core_contract_drift_fails_when_fields_are_stale(tmp_path: Path) -> None:
    openapi_path = tmp_path / "openapi.json"
    openapi_path.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "mneme", "version": "0.7.0"},
                "paths": {},
                "components": {"schemas": {}},
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        _script("check_core_contract_drift.py")
        + ["--openapi", str(openapi_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "missing required path" in result.stdout
