from __future__ import annotations

from pathlib import Path
from runpy import run_path
from typing import get_type_hints

_EXPORTER = Path(__file__).resolve().parents[2] / "agent-skill-bridge" / "scripts" / "export_skills.py"


def test_classify_declares_its_return_type() -> None:
    classify = run_path(str(_EXPORTER))["classify"]
    assert get_type_hints(classify).get("return") == tuple[str, str, str, int, str]


def test_safe_dirname_trims_trailing_dots_and_whitespace_before_deduplication() -> None:
    safe_dirname = run_path(str(_EXPORTER))["safe_dirname"]
    used = {"name"}

    assert safe_dirname(" name.\u00a0. \u2003", used) == "name-2"
    assert safe_dirname(".\u00a0.", used) == "skill"
