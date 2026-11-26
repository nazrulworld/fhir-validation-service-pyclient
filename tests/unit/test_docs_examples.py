"""README and docs examples stay in sync with the API (T095).

The examples talk to a live service, so they are not executed here; instead every ``python``
code block must compile, and every name imported from ``fvs_client`` must exist.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import fvs_client

ROOT = Path(__file__).resolve().parents[2]
DOCS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _blocks() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in DOCS:
        for i, code in enumerate(BLOCK.findall(path.read_text(encoding="utf-8"))):
            found.append((f"{path.relative_to(ROOT)}#{i}", code))
    return found


BLOCKS = _blocks()


def test_examples_found() -> None:
    assert len(BLOCKS) >= 10


@pytest.mark.parametrize(("where", "code"), BLOCKS, ids=[w for w, _ in BLOCKS])
def test_example_compiles_and_imports_exist(where: str, code: str) -> None:
    # Top-level ``await`` appears in async snippets; allow it.
    tree = compile(code, where, "exec", flags=ast.PyCF_ONLY_AST | ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    assert isinstance(tree, ast.Module)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "fvs_client":
            for alias in node.names:
                assert hasattr(fvs_client, alias.name), f"{where}: fvs_client.{alias.name}"
