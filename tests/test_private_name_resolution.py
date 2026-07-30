"""Catch unresolved private helper references before runtime.

This lightweight AST check is deliberately narrow: it verifies that names
beginning with an underscore, when loaded from a function body, resolve to a
local binding or a module-level definition/import. It catches missing renderer
helpers such as `_energy_source_rows` without requiring third-party lint tools.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    ROOT / "analytics",
    ROOT / "archive",
    ROOT / "benchmarks",
    ROOT / "config",
    ROOT / "helpers",
    ROOT / "loaders",
    ROOT / "research_overlay",
    ROOT / "sectors",
    ROOT / "tools",
)
SOURCE_FILES = (ROOT / "ai_macro.py",)


def _module_bindings(tree: ast.Module) -> set[str]:
    names = set(dir(builtins)) | {"__name__", "__file__", "__package__"}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names if alias.name != "*")
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for child in ast.walk(target):
                    if isinstance(child, ast.Name):
                        names.add(child.id)
    return names


def _function_locals(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = {
        argument.arg
        for argument in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
            + ([node.args.vararg] if node.args.vararg else [])
            + ([node.args.kwarg] if node.args.kwarg else [])
        )
    }
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Param)):
            names.add(child.id)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and child is not node:
            names.add(child.name)
        elif isinstance(child, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in child.names)
        elif isinstance(child, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in child.names if alias.name != "*")
    return names


def _python_files():
    yield from SOURCE_FILES
    for root in SOURCE_ROOTS:
        yield from root.rglob("*.py")


def test_private_helper_references_resolve():
    unresolved = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        globals_ = _module_bindings(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            available = globals_ | _function_locals(node)
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Name)
                    and isinstance(child.ctx, ast.Load)
                    and child.id.startswith("_")
                    and child.id not in available
                ):
                    unresolved.append(
                        f"{path.relative_to(ROOT)}:{child.lineno}: {child.id}"
                    )
    assert not unresolved, "Unresolved private helper references:\n" + "\n".join(sorted(set(unresolved)))
