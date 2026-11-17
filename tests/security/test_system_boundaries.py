"""Regression guard: project Python must not gain operating-system control paths."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOTS = (ROOT / "src", ROOT / "scripts")
PYTHON_FILES = [ROOT / "app.py"]

BANNED_IMPORTS = {
    "subprocess",
    "winreg",
    "wmi",
    "ctypes",
}
BANNED_CALLS = {
    "eval",
    "exec",
    "compile",
    "os.system",
    "os.popen",
}
BANNED_COMMAND_TEXT = {
    "powershell",
    "pwsh",
    "cmd.exe",
    "bcdedit",
    "diskpart",
    "regedit",
    "set-executionpolicy",
    "restart-computer",
    "start-process",
    "schtasks",
    "wmic",
}


def dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def project_python_files():
    files = list(PYTHON_FILES)
    for root in PYTHON_ROOTS:
        files.extend(root.rglob("*.py"))
    return sorted(path for path in files if path.exists())


def test_runtime_has_no_system_control_or_dynamic_shell_paths():
    violations = []
    for path in project_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in BANNED_IMPORTS:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if module in BANNED_IMPORTS:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: from {node.module}")
            elif isinstance(node, ast.Call) and dotted_name(node.func) in BANNED_CALLS:
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: call {dotted_name(node.func)}"
                )
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.casefold()
                for command in BANNED_COMMAND_TEXT:
                    if command in lowered:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}: command {command}"
                        )
    assert not violations, "System-boundary violations:\n" + "\n".join(violations)
