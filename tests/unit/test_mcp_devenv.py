from __future__ import annotations

import json
from pathlib import Path

import yaml  # pyyaml — already a dependency via config loading

ROOT = Path(__file__).resolve().parents[2]


def test_gitpod_yaml_is_valid():
    data = yaml.safe_load((ROOT / ".gitpod.yml").read_text())
    assert data["tasks"], "expected at least one Gitpod task"


def test_devcontainer_json_is_valid():
    data = json.loads((ROOT / ".devcontainer" / "devcontainer.json").read_text())
    assert data["image"], "expected a devcontainer base image"
    assert data["postCreateCommand"], "expected a postCreateCommand"
