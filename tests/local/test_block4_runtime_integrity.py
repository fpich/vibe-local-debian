from __future__ import annotations

import ast
import builtins
from pathlib import Path
import symtable

REPO_ROOT = Path(__file__).resolve().parents[2]
VIBE_ROOT = REPO_ROOT / "vibe"


def _class_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text())
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_agent_loop_keeps_required_legacy_runtime_surface() -> None:
    path = VIBE_ROOT / "core/agent_loop/_loop.py"
    methods = _class_methods(path, "AgentLoop")
    required = {
        "agent_profile",
        "config_orchestrator",
        "config",
        "bypass_tool_permissions",
        "runtime_policy",
        "record_child_session",
        "replace_child_session",
        "forget_child_session",
        "persist_empty_session",
        "resolve_approval_request",
        "resolve_user_input_request",
        "reject_request",
        "set_tool_permission",
        "approve_always",
        "refresh_config",
        "refresh_system_prompt",
        "aclose",
        "backend_factory",
        "notice_retry",
    }
    assert required <= methods
    source = path.read_text()
    assert "self._mcp_pool = None" in source


def test_legacy_session_controller_keeps_open_attach_helpers() -> None:
    methods = _class_methods(
        VIBE_ROOT / "app_server/_legacy_session_runtime.py",
        "LegacySessionRuntimeController",
    )
    assert {"_open_runtime", "_attach_opened_runtime", "_report_created_worktree"} <= methods


def test_no_duplicate_decorators_remain() -> None:
    duplicates: list[str] = []
    for path in VIBE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [ast.dump(item, include_attributes=False) for item in node.decorator_list]
            if len(decorators) != len(set(decorators)):
                duplicates.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}:{node.name}")
    assert duplicates == []


def test_no_undefined_global_names_in_runtime_sources() -> None:
    builtin_names = set(dir(builtins)) | {
        "__file__",
        "__name__",
        "__package__",
        "__spec__",
        "__loader__",
        "__cached__",
        "__doc__",
        "__annotations__",
    }
    failures: list[str] = []

    def inspect_table(table: symtable.SymbolTable, module_defs: set[str], path: Path) -> None:
        for symbol in table.get_symbols():
            name = symbol.get_name()
            if (
                symbol.is_referenced()
                and symbol.is_global()
                and name not in module_defs
                and name not in builtin_names
            ):
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{table.get_lineno()}:{table.get_name()}:{name}"
                )
        for child in table.get_children():
            inspect_table(child, module_defs, path)

    for path in VIBE_ROOT.rglob("*.py"):
        table = symtable.symtable(path.read_text(), str(path), "exec")
        module_defs = {
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_assigned()
            or symbol.is_imported()
            or symbol.is_namespace()
            or symbol.is_parameter()
        }
        inspect_table(table, module_defs, path)

    assert failures == []


def test_removed_mcp_auth_type_is_not_used_by_server_runtime() -> None:
    source = (VIBE_ROOT / "app_server/server.py").read_text()
    assert "MCPAuthUrlParams" not in source
