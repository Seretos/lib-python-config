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
    resolve_config_path,
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

# Loading
load_yaml(path) -> dict
load_env_file(path) -> None

# Models
LoadResult  # pydantic BaseModel
ConfigError  # Exception
```

## Versioning

Semantic versioning. Currently `0.1.0` — extracted from `agent-project-issues`,
not yet stabilised for external consumers.
