from __future__ import annotations

from pathlib import Path
import tomllib

from vibe.core.utils import name_matches

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_template() -> dict:
    return tomllib.loads((REPO_ROOT / ".vibe/config.toml").read_text())


def test_template_models_have_distinct_names() -> None:
    names = [m["name"] for m in _load_template()["models"]]
    assert len(names) == len(set(names)), names


def test_template_active_model_is_defined() -> None:
    config = _load_template()
    aliases = {m["alias"] for m in config["models"]}
    assert config["active_model"] in aliases


def test_template_allowlist_covers_every_model() -> None:
    config = _load_template()
    allowed = config["allowed_models"]
    names = [m["name"] for m in config["models"]]
    assert names
    assert all(name_matches(n, allowed) for n in names)
