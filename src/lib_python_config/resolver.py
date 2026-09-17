"""Config-path resolution.

`resolve_search_root` decides *where to start looking*; `resolve_config_path`
decides *which file wins*. Both push every hardcoded string the original
plugin had (env-var names, config dir, filenames) up to caller-supplied
parameters so the same machinery can serve multiple plugins.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
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


def _build_candidates(
    cwd: Path,
    *,
    config_dir: str,
    filenames: tuple[str, ...],
    override_env: str | None,
    plugin_root_env: str | None,
    home_default: bool,
) -> Iterator[Path]:
    """Lazily yield the full, priority-ordered candidate list, highest-
    priority first.

    Emits **exactly** the sequence `resolve_config_path` inspects, in the
    same order, with no filtering, no dedupe, and no reordering — including
    any duplicates (e.g. a home directory that is itself a git repo produces
    the same path from both the walk step and the home-default step).

    Order: explicit override (when set) → plugin-root (one candidate per
    filename, when set) → `walk_project_boundaries(cwd, config_dir,
    filenames)` (nearest enclosing repo first, then outward) → home default
    (one candidate per filename, when enabled).

    This is a **generator**, not a function that builds the list eagerly:
    each step's work only happens once the consumer has actually asked for
    that many items. `resolve_config_path` stops pulling as soon as it hits
    an existing candidate, so when an override or plugin-root candidate
    already wins, the generator body never reaches the `walk_project_boundaries`
    call (which walks up to the filesystem root and can hit a `PermissionError`
    on an inaccessible ancestor directory) or the home-default step — exactly
    matching the short-circuit behaviour `resolve_config_path` had before this
    builder was extracted. `resolve_config_paths` needs every layer, so it
    exhausts the generator fully (via `list(...)`), which walks and builds the
    home defaults exactly as before too.
    """
    # 1) Explicit override.
    if override_env:
        override = os.environ.get(override_env)
        if override:
            override_path = Path(override).resolve()
            if not override_path.exists():
                raise ConfigError(
                    f"{override_env} points to non-existent path: "
                    f"{override_path}"
                )
            yield override_path

    # 2) Plugin-root config.
    if plugin_root_env:
        plugin_root = os.environ.get(plugin_root_env)
        if plugin_root:
            root_dir = Path(plugin_root)
            for name in filenames:
                yield (root_dir / name).resolve()

    # 3) Walk project boundaries. Not reached at all if the consumer
    # (resolve_config_path) already stopped pulling above.
    yield from walk_project_boundaries(cwd, config_dir, filenames)

    # 4) Home default. Same laziness as step 3.
    if home_default:
        yield from _home_default_candidates(config_dir, filenames)


def _dedupe_keep_first(paths: list[Path]) -> list[Path]:
    """Drop later duplicates of a real path, keeping each one's first
    (highest-priority) occurrence. Keys on `Path.resolve()` so that two
    distinct-looking candidates pointing at the same real file collapse.
    """
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


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
    for candidate in _build_candidates(
        cwd,
        config_dir=config_dir,
        filenames=filenames,
        override_env=override_env,
        plugin_root_env=plugin_root_env,
        home_default=home_default,
    ):
        searched.append(candidate)
        if candidate.exists():
            return candidate, searched
    return None, searched


def resolve_config_paths(
    cwd: Path,
    *,
    config_dir: str,
    filenames: tuple[str, ...],
    override_env: str | None = None,
    plugin_root_env: str | None = None,
    home_default: bool = True,
) -> tuple[list[Path], list[Path]]:
    """Resolve *every* existing config candidate, for layered merging.

    Where `resolve_config_path` stops at the first existing file,
    `resolve_config_paths` is the opt-in second semantic: it returns every
    candidate that exists, ordered **lowest-priority-first** (home → outer
    repo → ... → inner repo → plugin-root → override) so that folding the
    result into `merge_layers` makes the nearest/most-specific layer win,
    the same way `resolve_config_path`'s priority order already does for its
    single winner.

    Returns `(existing, inspected)`:

      - `inspected` is the **full, non-deduped** candidate list, reversed
        (lowest-priority-first) — every candidate genuinely inspected,
        including duplicates. This is a diagnostics list.
      - `existing` is `inspected`, first deduped by `Path.resolve()`
        (keeping each real file's **highest-priority** occurrence), then
        filtered to the paths that actually exist. `existing` is always a
        subsequence of `inspected`.

    Limitation, intentional: a config file reachable via two distinct
    candidate paths — for example when the home directory is itself inside
    a git repository — is deduplicated and reported **once** in `existing`,
    at its highest-priority position; it still appears at every position it
    was inspected from in `inspected`. Dedupe never touches
    `resolve_config_path`'s `searched` list or the shared candidate builder
    — only this function's `existing` computation.

    Raises `ConfigError` under the same condition as `resolve_config_path`:
    `override_env` set to a value that doesn't point to an existing file.
    """
    candidates = list(
        _build_candidates(
            cwd,
            config_dir=config_dir,
            filenames=filenames,
            override_env=override_env,
            plugin_root_env=plugin_root_env,
            home_default=home_default,
        )
    )
    inspected = list(reversed(candidates))
    existing = [
        path
        for path in reversed(_dedupe_keep_first(candidates))
        if path.exists()
    ]
    return existing, inspected
