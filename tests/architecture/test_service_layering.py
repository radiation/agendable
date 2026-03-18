from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parents[2] / "src" / "agendable" / "services"


@dataclass(frozen=True)
class Violation:
    file_path: Path
    line: int
    column: int
    message: str


def _iter_service_files() -> list[Path]:
    return sorted(path for path in SERVICES_ROOT.rglob("*.py") if path.is_file())


def _collect_violations(file_path: Path) -> list[Violation]:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    violations: list[Violation] = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("agendable.web")
        ):
            violations.append(
                Violation(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset,
                    message=(
                        "service layer must not import from agendable.web; "
                        "move shared helpers to non-web modules"
                    ),
                )
            )

        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("agendable.web"):
                    violations.append(
                        Violation(
                            file_path=file_path,
                            line=node.lineno,
                            column=node.col_offset,
                            message=(
                                "service layer must not import from agendable.web; "
                                "move shared helpers to non-web modules"
                            ),
                        ),
                    )

    return violations


def test_service_layer_has_no_web_imports() -> None:
    all_violations: list[Violation] = []
    for file_path in _iter_service_files():
        all_violations.extend(_collect_violations(file_path))

    if all_violations:
        details = "\n".join(
            f"{violation.file_path.relative_to(SERVICES_ROOT.parents[2])}:{violation.line}:{violation.column} {violation.message}"
            for violation in all_violations
        )
        raise AssertionError(
            "Web-layer imports detected in service modules. "
            "Keep service dependencies within domain/repo/util layers.\n"
            f"{details}"
        )
