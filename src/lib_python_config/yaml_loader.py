"""Safe YAML loader returning a raw mapping.

Generic: validation / schema-mapping is the caller's job. We only enforce
that the top-level shape is a mapping (or empty) and surface parse errors
as `ConfigError` so callers can map them to their own diagnostics.
"""
from __future__ import annotations

import io
from pathlib import Path

from ruamel.yaml import YAML, YAMLError

from lib_python_config.models import ConfigError

# Single, reusable YAML parser. `safe` blocks arbitrary-tag instantiation;
# `pure=True` avoids the optional C extension so behaviour is consistent
# across platforms (Windows / frozen builds).
_yaml = YAML(typ="safe", pure=True)


def load_yaml(yaml_path: Path) -> dict:
    """Load a YAML file and return its top-level mapping as a `dict`.

    - Empty file → `{}` (deliberate: matches "config exists but has no
      content" semantics; callers can distinguish from missing-file by
      checking the path themselves).
    - Top-level must be a mapping; lists / scalars raise `ConfigError`.
    - Parse errors raise `ConfigError` wrapping the original `YAMLError`.
    - UTF-8 BOM (`EF BB BF`) at the file head is stripped so files saved
      by Windows tools (`Set-Content -Encoding utf8`, Notepad) parse
      cleanly.
    """
    raw = yaml_path.read_bytes()
    # Strip a UTF-8 BOM if present (Notepad / `Set-Content -Encoding utf8`).
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        data = _yaml.load(io.BytesIO(raw))
    except YAMLError as exc:
        raise ConfigError(f"{yaml_path}: YAML parse error: {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(
            f"{yaml_path}: top-level must be a mapping, got {type(data).__name__}"
        )
    return data
