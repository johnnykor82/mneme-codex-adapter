#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable
from pathlib import Path


class _ViolationCollector(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "mneme_service" or alias.name.startswith("mneme_service."):
                self.violations.append((node.lineno, alias.name))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level == 0 and node.module and (
            node.module == "mneme_service" or node.module.startswith("mneme_service.")
        ):
            self.violations.append((node.lineno, node.module))
        self.generic_visit(node)


def _iter_python_files(root: Path, include_tests: bool) -> Iterable[Path]:
    package_dir = root / "mneme_codex_adapter"
    search_roots = [package_dir] if package_dir.exists() else [root]

    for base in search_roots:
        for path in base.rglob("*.py"):
            if path.name == "__pycache__":
                continue
            if not include_tests and "tests" in path.parts:
                continue
            yield path


def _find_violations(root: Path, include_tests: bool = False) -> list[tuple[Path, int, str]]:
    results: list[tuple[Path, int, str]] = []
    for path in _iter_python_files(root, include_tests):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError) as exc:
            results.append((path, 0, f"Cannot parse file: {exc}"))
            continue

        collector = _ViolationCollector(path)
        collector.visit(tree)
        results.extend((path, lineno, module) for lineno, module in collector.violations)

    return results


def run(root: Path, include_tests: bool = False) -> int:
    violations = _find_violations(root, include_tests=include_tests)
    if not violations:
        return 0

    for path, lineno, module in violations:
        location = f"{path}:{lineno}" if lineno else str(path)
        print(f"{location}: import of '{module}' from Core daemon internals is forbidden")
    print(
        f"FAIL: found {len(violations)} forbidden import(s) from mneme_service in adapter source"
    )
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail if adapter source imports mneme_service internals."
    )
    parser.add_argument(
        "--path",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root to scan (default: current repo).",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include tests/** files in scanning.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(Path(args.path).resolve(), include_tests=args.include_tests)


if __name__ == "__main__":
    raise SystemExit(main())
