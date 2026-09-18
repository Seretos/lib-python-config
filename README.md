# lib-python-config

Generic, plugin-agnostic config-loading utilities extracted from the Seretos
`agent-project-issues` MCP plugin. Provides the *mechanism* (walking the
filesystem, resolving env-var-driven overrides, parsing YAML / `.env` files);
the *policy* (which directory name, which file names, which env-var names) is
caller-supplied.

## Install

```bash
pip install lib-python-config
```

## Usage

```python
from pathlib import Path

from lib_python_config import (
    ConfigError,
    LoadResult,
    load_env_file,
    load_yaml,
    merge_layers,
    resolve_config_path,
    resolve_config_paths,
    resolve_search_root,
)

cwd = resolve_search_root(explicit=None, env_vars=("CLAUDE_PROJECT_DIR",))

config_path, searched = resolve_config_path(
    cwd,
    config_dir=".seretos",
    filenames=("my-plugin.yml", "my-plugin.yaml"),
    override_env="MY_PLUGIN_CONFIG",
    plugin_root_env="MY_PLUGIN_PLUGIN_ROOT",
    home_default=True,
)

if config_path:
    try:
        data: dict = load_yaml(config_path)
    except ConfigError as exc:
        result = LoadResult(
            state="config_error",
            config_file=str(config_path),
            search_root=str(cwd),
            error=str(exc),
            searched_paths=[str(p) for p in searched],
        )
    else:
        # validate `data` with your own pydantic model here
        ...
```

## Choosing a resolution semantic

One config file owns the answer → `resolve_config_path`; several files
contribute and the nearest wins → `resolve_config_paths` + `merge_layers`.

`resolve_config_path` walks the same priority order every time (explicit
override → plugin-root → enclosing repos, nearest first → home) and stops at
the first existing file — exactly one file wins, and everything else is
never even loaded. Use it when a single config file is the whole answer,
e.g. "load the active plugin config."

`resolve_config_paths` walks the same candidates but keeps going, returning
every existing file it found, ordered lowest-priority-first (home → outer
repo → ... → inner repo → plugin-root → override). Pass that list straight
into `merge_layers` to fold them into one mapping where the more specific
(nearer, or override) layer wins per key, with unset keys inherited from
the broader layers underneath. Use it when several layers legitimately
contribute settings and the nearest one should only override what it
actually mentions — e.g. `~/.seretos/harness.yml` → `<outer
repo>/.seretos/harness.yml` → `<inner repo>/.seretos/harness.yml`, inner
winning per key rather than replacing the whole file.

```python
from lib_python_config import merge_layers, resolve_config_paths
from lib_python_config import load_yaml

existing, inspected = resolve_config_paths(
    cwd,
    config_dir=".seretos",
    filenames=("harness.yml", "harness.yaml"),
)

merged = merge_layers(
    [load_yaml(path) for path in existing],
    list_strategy="replace",  # or "append" to concatenate list values
)
```

## Public API

```python
# Discovery
walk_up(start, names) -> Path | None
find_git_repo_root(start) -> Path | None
walk_project_boundaries(start, config_dir, filenames) -> list[Path]

# Resolution
resolve_search_root(explicit, env_vars=("CLAUDE_PROJECT_DIR",)) -> Path
resolve_config_path(
    cwd, *, config_dir, filenames,
    override_env=None, plugin_root_env=None, home_default=True,
) -> tuple[Path | None, list[Path]]
resolve_config_paths(
    cwd, *, config_dir, filenames,
    override_env=None, plugin_root_env=None, home_default=True,
) -> tuple[list[Path], list[Path]]  # (existing, inspected)

# Merging
merge_layers(layers, *, list_strategy="replace") -> dict
# list_strategy: "replace" (default) or "append"

# Loading
load_yaml(path) -> dict
load_env_file(path) -> None

# Models
LoadResult  # pydantic BaseModel
ConfigError  # Exception
```

## Versioning

Semantic versioning. Currently `0.2.0` — extracted from `agent-project-issues`,
not yet stabilised for external consumers.

## Releasing

`release.yml` (manual `workflow_dispatch`) stamps and tags a new version,
publishes the GitHub Release, and then calls `notify-consumers.yml`, which
files or updates one `chore(deps): update lib-python-config` issue per
direct consumer repo (`Seretos/lib-python-projects`,
`Seretos/agent-project-issues`, `Seretos/agent-worktree`), carrying that
release's notes, and adds it to Seretos board #2. Each consumer is notified
through its own PAT secret so a bad or expired token for one consumer only
affects that consumer, never the other two:

- `LIB_PYTHON_PROJECTS_TICKET_TOKEN` — for `Seretos/lib-python-projects`
- `AGENT_PROJECT_ISSUES_TICKET_TOKEN` — for `Seretos/agent-project-issues`
- `AGENT_WORKTREE_TICKET_TOKEN` — for `Seretos/agent-worktree`

Each secret must be a **classic PAT** with `repo` and `project` scopes on
its target repo/org. Configure all three as repository secrets on
**`Seretos/lib-python-config`** (the repo running the workflow, not the
consumer repos) before the mechanism works end to end. Until they are
configured, the notify steps are `continue-on-error: true` and fail
silently — the release still goes green, it just notifies nobody, so set
these up before relying on it.

`notify-consumers.yml` can also be run standalone via `workflow_dispatch`
(input `version`) to (re-)notify consumers for a release that already
exists, without cutting a new one — useful if a consumer's step failed and
just needs a retry, or if a release was published before this mechanism
existed.

To add a fourth consumer: add a new PAT secret, add a matching
`continue-on-error: true` step calling `./.github/actions/notify-consumer`
in `notify-consumers.yml`, and add that secret to the `secrets:` block
release.yml passes to `notify-consumers.yml`.
