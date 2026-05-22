"""Tests for the safe YAML loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from lib_python_config.models import ConfigError
from lib_python_config.yaml_loader import load_yaml


def test_load_yaml_returns_dict_for_basic_mapping(tmp_path: Path) -> None:
    f = tmp_path / "cfg.yml"
    f.write_text("version: 1\nname: foo\n", encoding="utf-8")

    data = load_yaml(f)

    assert data == {"version": 1, "name": "foo"}


def test_load_yaml_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    f = tmp_path / "cfg.yml"
    f.write_text("", encoding="utf-8")

    assert load_yaml(f) == {}


def test_load_yaml_whitespace_only_returns_empty_dict(tmp_path: Path) -> None:
    f = tmp_path / "cfg.yml"
    f.write_text("   \n\n   \n", encoding="utf-8")

    assert load_yaml(f) == {}


def test_load_yaml_strips_utf8_bom(tmp_path: Path) -> None:
    f = tmp_path / "cfg.yml"
    f.write_bytes(b"\xef\xbb\xbfversion: 1\nname: foo\n")

    data = load_yaml(f)

    assert data == {"version": 1, "name": "foo"}


def test_load_yaml_rejects_top_level_list(tmp_path: Path) -> None:
    f = tmp_path / "cfg.yml"
    f.write_text("- a\n- b\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="top-level must be a mapping"):
        load_yaml(f)


def test_load_yaml_rejects_top_level_scalar(tmp_path: Path) -> None:
    f = tmp_path / "cfg.yml"
    f.write_text("just-a-string\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="top-level must be a mapping"):
        load_yaml(f)


def test_load_yaml_raises_config_error_on_parse_failure(tmp_path: Path) -> None:
    f = tmp_path / "cfg.yml"
    # Malformed YAML — unbalanced bracket.
    f.write_text("foo: [bar\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="YAML parse error"):
        load_yaml(f)


def test_load_yaml_does_not_validate_schema(tmp_path: Path) -> None:
    """Loader is intentionally schema-agnostic — caller validates."""
    f = tmp_path / "cfg.yml"
    f.write_text(
        "anything_goes: true\n"
        "weird_keys:\n"
        "  - nested\n"
        "  - structure\n",
        encoding="utf-8",
    )

    data = load_yaml(f)

    assert data == {
        "anything_goes": True,
        "weird_keys": ["nested", "structure"],
    }
