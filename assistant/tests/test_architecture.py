"""AST architecture / import-boundary tests."""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

ASSISTANT_ROOT = Path(__file__).resolve().parents[1]


def _imports_in(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            found.append(mod)
    return found


class ArchitectureTests(SimpleTestCase):
    def test_tools_do_not_import_catalog_models_or_channels_or_redis(self):
        tools_dir = ASSISTANT_ROOT / "tools"
        for path in tools_dir.rglob("*.py"):
            imports = _imports_in(path)
            for mod in imports:
                self.assertFalse(
                    mod == "catalog.models" or mod.startswith("catalog.models."),
                    f"{path} imports catalog.models directly",
                )
                self.assertNotIn("assistant.channels", mod)
                self.assertNotIn("assistant.views", mod)
                self.assertFalse(
                    mod == "assistant.redis_client" or mod.startswith("redis"),
                    f"{path} must not import redis",
                )

    def test_channels_do_not_import_tools_or_llm(self):
        channels_dir = ASSISTANT_ROOT / "channels"
        for path in channels_dir.rglob("*.py"):
            imports = _imports_in(path)
            for mod in imports:
                self.assertFalse(mod.startswith("assistant.tools"))
                self.assertNotEqual(mod, "assistant.llm")

    def test_llm_does_not_import_clinic_code(self):
        imports = _imports_in(ASSISTANT_ROOT / "llm.py")
        for mod in imports:
            self.assertNotIn("catalog", mod)
            self.assertNotIn("assistant.repo", mod)
            self.assertNotIn("assistant.tools", mod)

    def test_no_hardcoded_api_paths_outside_urls(self):
        for path in ASSISTANT_ROOT.rglob("*.py"):
            if path.name in {"urls.py"} or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('/api/assistant/', text, msg=str(path))
