"""Guard against accidentally re-introducing syntax that breaks Python 3.8.

The backend supports Python 3.8 - 3.12. Pydantic and SQLAlchemy evaluate type
annotations at runtime, so on 3.8/3.9 things like `str | None` or `list[str]`
crash at import time (this is exactly the bug that broke `pytest` and
`uvicorn` on Python 3.8). A developer on Python 3.11+ would never notice such a
regression locally, so this test statically scans the source instead.

If you deliberately drop Python 3.8 support in the future, delete this file
and update `backend/pyproject.toml` (ruff `keep-runtime-typing`) and
`INSTRUCTIONS.md`.
"""

import ast
from pathlib import Path
from typing import Iterator, List

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRS = ("app", "alembic")
BUILTIN_GENERICS = {"list", "dict", "tuple", "set", "frozenset", "type"}


def _source_files() -> Iterator[Path]:
    for directory in SCANNED_DIRS:
        yield from (BACKEND_ROOT / directory).rglob("*.py")


def _annotation_nodes(tree: ast.AST) -> Iterator[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AnnAssign, ast.arg)) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            yield node.returns


def _problems(path: Path) -> List[str]:
    source = path.read_text(encoding="utf-8")
    # feature_version makes the parser reject syntax newer than 3.8 (match
    # statements, parenthesised context managers, ...).
    tree = ast.parse(source, filename=str(path), feature_version=(3, 8))
    rel = path.relative_to(BACKEND_ROOT)
    found: List[str] = []

    # Everything inside an annotation, so we can tell annotation uses apart
    # from runtime uses (e.g. `response_model=list[X]`).
    in_annotation = {id(n) for a in _annotation_nodes(tree) for n in ast.walk(a)}

    for node in ast.walk(tree):
        if (
            id(node) in in_annotation
            and isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.BitOr)
        ):
            found.append(f"{rel}:{node.lineno}: use Optional/Union instead of `X | Y`")
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in BUILTIN_GENERICS
        ):
            found.append(
                f"{rel}:{node.lineno}: `{node.value.id}[...]` needs 3.9+; "
                f"use typing.{node.value.id.capitalize()}"
            )
        if isinstance(node, ast.ImportFrom):
            names = {alias.name for alias in node.names}
            if node.module == "datetime" and "UTC" in names:
                found.append(f"{rel}:{node.lineno}: datetime.UTC needs 3.11+; use timezone.utc")
            if node.module == "collections.abc" and names & {"Sequence", "Callable", "Iterable"}:
                found.append(f"{rel}:{node.lineno}: import subscripted ABCs from typing (3.8)")
        if isinstance(node, ast.Call) and any(k.arg == "strict" for k in node.keywords):
            found.append(f"{rel}:{node.lineno}: zip(strict=...) needs 3.10+")
    return found


def test_backend_source_is_python38_compatible() -> None:
    problems: List[str] = []
    for path in _source_files():
        problems.extend(_problems(path))
    assert not problems, "Python 3.8-incompatible code:\n" + "\n".join(problems)
