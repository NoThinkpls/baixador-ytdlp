"""Sincroniza os metadados derivados de APP_VERSION."""
from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "baixador_ytdlp" / "config.py"


def app_version() -> str:
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in node.targets
        ):
            return str(ast.literal_eval(node.value))
    raise RuntimeError("APP_VERSION não encontrado")


def main() -> None:
    version = app_version()
    numeric = ", ".join((*version.split("."), "0"))

    installer = ROOT / "installer.iss"
    text = installer.read_text(encoding="utf-8")
    text = re.sub(r'#define AppVersion "[^"]+"', f'#define AppVersion "{version}"', text)
    installer.write_text(text, encoding="utf-8")

    info = ROOT / "version_info.txt"
    text = info.read_text(encoding="utf-8")
    text = re.sub(r"filevers=\([^)]+\)", f"filevers=({numeric})", text)
    text = re.sub(r"prodvers=\([^)]+\)", f"prodvers=({numeric})", text)
    text = re.sub(r"StringStruct\('FileVersion', '[^']+'\)",
                  f"StringStruct('FileVersion', '{version}.0')", text)
    text = re.sub(r"StringStruct\('ProductVersion', '[^']+'\)",
                  f"StringStruct('ProductVersion', '{version}.0')", text)
    info.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
