"""Config-path resolution.

`resolve_search_root` decides *where to start looking*; `resolve_config_path`
decides *which file wins*. Both push every hardcoded string the original
plugin had (env-var names, config dir, filenames) up to caller-supplied
parameters so the same machinery can serve multiple plugins.
"""
from __future__ import annotations

import os
from pathlib import Path

from lib_python_config.discovery import walk_project_boundaries
from lib_python_config.models import ConfigError


def resolve_search_root(
    explicit: Path | None,
    env_vars: tuple[str, ...] = ("CLAUDE_PROJECT_DIR",),
) -> Path:
    """Where the loader should start walking up to find the config.

    Precedence:
      1. The explicit argument (used by tests / direct callers).
      2. Each `env_vars` entry in order — first non-empty value wins.
         Typical usage: `("MY_PLUGIN_CWD", "CLAUDE_PROJECT_DIR")` to give
         the plugin's own escape hatch priority over the host-provided one.
      3. The process's current working directory.
    """
    if explicit:
        return explicit.resolve()
    for var in env_vars:
        candidate = os.environ.get(var)
        if candidate:
            return Path(candidate).resolve()
    return Path.cwd().resolve()


def _home_default_candidates(
    config_dir: str, filenames: tuple[str, ...]
) -> list[Path]:
    """User-level fallback: `~/<config_dir>/<filename>` for each filename.

    Used when no enclosing git repo carries a matching config. Documented
    escape hatch for hosts that don't pass a usable CWD into the plugin.
    """
    try:
        home = Path.home()
    except RuntimeError:
        return []
    return [home / config_dir / name for name in filenames]


def resolve_config_path(
    cwd: Path,
    *,
    config_dir: str,
    filenames: tuple[str, ...],
    override_env: str | None = None,
    plugin_root_env: str | None = None,
    home_default: bool = True,
) -> tuple[Path | None, list[Path]]:
    """Resolve the active config-file path + the full searched list.

    Priority (first existing file wins):

      1. ``$<override_env>`` (when ``override_env`` is supplied) — explicit
         override, highest priority. If the value points to a non-existent
         file the resolver raises ``ConfigError`` rather than silently
         falling through; this makes typos loud instead of mysterious.
      2. ``$<plugin_root_env>/<filename>`` for each filename (when
         ``plugin_root_env`` is supplied) — for self-contained plugin
         checkouts that ship their own config next to the binary. Note:
         this is the only resolver step that does NOT live under
         ``<config_dir>/``, because it's a binary-adjacent override for
         distribution scenarios, not a user-level config.
      3. Walk **git project boundaries** outward from ``cwd``: every
         enclosing repo's ``<repo>/<config_dir>/<filename>`` per filename.
      4. (Optional, ``home_default=True``) User-level fallback
         ``~/<config_dir>/<filename>`` for each filename.

    Returns a `(winner_or_None, all_paths_inspected)` tuple. The
    `all_paths_inspected` list always reflects the order the resolver
    actually walked, so callers can surface it in diagnostics.
    """
    searched: list[Path] = []

    # 1) Explicit override.
    if override_env:
        override = os.environ.get(override_env)
        if override:
            override_path = Path(override).resolve()
            searched.append(override_path)
            if not override_path.exists():
                raise ConfigError(
                    f"{override_env} points to non-existent path: "
                    f"{override_path}"
                )
            return override_path, searched

    # 2) Plugin-root config.
    if plugin_root_env:
        plugin_root = os.environ.get(plugin_root_env)
        if plugin_root:
            root_dir = Path(plugin_root)
            for name in filenames:
                candidate = (root_dir / name).resolve()
                searched.append(candidate)
                if candidate.exists():
                    return candidate, searched

    # 3) Walk project boundaries.
    for candidate in walk_project_boundaries(cwd, config_dir, filenames):
        searched.append(candidate)
        if candidate.exists():
            return candidate, searched

    # 4) Home default.
    if home_default:
        for candidate in _home_default_candidates(config_dir, filenames):
            searched.append(candidate)
            if candidate.exists():
                return candidate, searched

    return None, searched
