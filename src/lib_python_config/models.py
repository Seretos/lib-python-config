"""Shared models / exception types."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConfigError(Exception):
    """Raised when a config file is unreadable, malformed, or rejected.

    Generic: this library raises it for YAML parse failures and explicit
    overrides that point to non-existent files. Downstream callers may
    subclass / re-raise for their own validation errors.
    """


class LoadResult(BaseModel):
    """Diagnostic record of a config-loading attempt.

    `state` lets callers distinguish the four empty/non-empty cases:
      - "ok":            config loaded successfully.
      - "config_empty":  config exists but has no actionable content.
      - "no_config":     no config file found.
      - "config_error":  config exists but failed to parse/validate.

    `searched_paths` is the ordered list of candidate paths the resolver
    inspected (including the winning one when present). Useful for
    surfacing in diagnostics so users can see *why* the resolver picked
    (or failed to pick) a particular config.

    This is the generic base shape — downstream libraries may subclass
    to add domain-specific fields (e.g. a `projects:` list).
    """

    state: Literal["ok", "config_empty", "no_config", "config_error"]
    config_file: str | None = None
    git_config: str | None = None
    search_root: str
    error: str | None = None
    searched_paths: list[str] = Field(default_factory=list)
