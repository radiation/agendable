from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

ROUTES_ROOT = Path(__file__).resolve().parents[2] / "src" / "agendable" / "web" / "routes"
SESSION_METHODS = {"execute", "commit", "flush", "add", "add_all"}


@dataclass(frozen=True)
class Violation:
    file_path: Path
    line: int
    column: int
    message: str


def _iter_route_files() -> list[Path]:
    return sorted(path for path in ROUTES_ROOT.rglob("*.py") if path.is_file())


def _collect_violations(file_path: Path) -> list[Violation]:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    imported_repo_names: set[str] = set()
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_name = alias.asname or alias.name
                if alias.name.endswith("Repository"):
                    imported_repo_names.add(imported_name)

        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if isinstance(func, ast.Attribute):
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "session"
                and func.attr in SESSION_METHODS
            ):
                violations.append(
                    Violation(
                        file_path=file_path,
                        line=node.lineno,
                        column=node.col_offset,
                        message=f"route layer must not call session.{func.attr}()",
                    )
                )

            if func.attr.endswith("Repository"):
                violations.append(
                    Violation(
                        file_path=file_path,
                        line=node.lineno,
                        column=node.col_offset,
                        message=f"route layer must not instantiate repository via {func.attr}()",
                    )
                )

        if isinstance(func, ast.Name) and (
            func.id.endswith("Repository") or func.id in imported_repo_names
        ):
            violations.append(
                Violation(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset,
                    message=f"route layer must not instantiate repository via {func.id}()",
                )
            )

    return violations


def test_route_layer_has_no_direct_db_or_repo_calls() -> None:
    all_violations: list[Violation] = []
    for file_path in _iter_route_files():
        all_violations.extend(_collect_violations(file_path))

    if all_violations:
        details = "\n".join(
            f"{violation.file_path.relative_to(ROUTES_ROOT.parents[2])}:{violation.line}:{violation.column} {violation.message}"
            for violation in all_violations
        )
        raise AssertionError(
            "Direct DB/repo usage detected in route modules. "
            "Move DB access behind services/repositories and keep routes thin.\n"
            f"{details}"
        )
