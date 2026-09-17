"""lib-python-config — generic config-loading utilities.

Public re-exports. See `README.md` for usage.
"""
from __future__ import annotations

from lib_python_config.discovery import (
    find_git_repo_root,
    walk_project_boundaries,
    walk_up,
)
from lib_python_config.env import load_env_file
from lib_python_config.merge import merge_layers
from lib_python_config.models import ConfigError, LoadResult
from lib_python_config.resolver import (
    resolve_config_path,
    resolve_config_paths,
    resolve_search_root,
)
from lib_python_config.yaml_loader import load_yaml

__version__ = "0.2.0"

__all__ = [
    "ConfigError",
    "LoadResult",
    "find_git_repo_root",
    "load_env_file",
    "load_yaml",
    "merge_layers",
    "resolve_config_path",
    "resolve_config_paths",
    "resolve_search_root",
    "walk_project_boundaries",
    "walk_up",
    "__version__",
]
