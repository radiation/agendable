from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

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


def _annotation_contains_async_session(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False

    for node in ast.walk(annotation):
        if isinstance(node, ast.Name) and node.id == "AsyncSession":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "AsyncSession":
            return True
    return False


def _collect_violations(file_path: Path) -> list[Violation]:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    imported_repo_names: set[str] = set()
    session_like_names: set[str] = set()
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                if _annotation_contains_async_session(arg.annotation):
                    session_like_names.add(arg.arg)

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
                and func.value.id in session_like_names
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


def _collect_violations_from_source(source: str) -> list[Violation]:
    file_path = Path("src/agendable/web/routes/_architecture_test_case.py")
    tree = ast.parse(source, filename=str(file_path))

    imported_repo_names: set[str] = set()
    session_like_names: set[str] = set()
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                if _annotation_contains_async_session(arg.annotation):
                    session_like_names.add(arg.arg)

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
                and func.value.id in session_like_names
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


def test_route_layer_guard_flags_async_session_calls_for_any_param_name() -> None:
    violations = _collect_violations_from_source(
        """
from sqlalchemy.ext.asyncio import AsyncSession

async def route(db: AsyncSession) -> None:
    await db.execute("select 1")
"""
    )

    assert len(violations) == 1
    assert "must not call session.execute()" in violations[0].message


def test_route_layer_guard_ignores_non_session_execute_calls() -> None:
    violations = _collect_violations_from_source(
        """
class Dummy:
    def execute(self, sql: str) -> None:
        pass

def route() -> None:
    dummy = Dummy()
    dummy.execute("select 1")
"""
    )

    assert violations == []


@pytest.mark.parametrize(
    "source_snippet",
    [
        (
            """
from agendable.db.repos.user_repo import UserRepository

def route() -> None:
    UserRepository()
"""
        ),
        (
            """
from agendable.db.repos.user_repo import UserRepository as Repo

def route() -> None:
    Repo()
"""
        ),
    ],
)
def test_route_layer_guard_flags_repo_instantiation(source_snippet: str) -> None:
    violations = _collect_violations_from_source(source_snippet)

    assert len(violations) == 1
    assert "must not instantiate repository" in violations[0].message
