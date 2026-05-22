"""Tests for `resolve_search_root` and `resolve_config_path`."""
from __future__ import annotations

from pathlib import Path

import pytest

from lib_python_config.models import ConfigError
from lib_python_config.resolver import resolve_config_path, resolve_search_root

CONFIG_DIR = ".seretos"
FILENAMES = ("plugin.yml", "plugin.yaml")


def _mkrepo(root: Path) -> Path:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    return root


def _write_config(repo: Path, name: str = "plugin.yml") -> Path:
    cfg_dir = repo / CONFIG_DIR
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / name
    cfg.write_text("version: 1\n", encoding="utf-8")
    return cfg


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure tests don't accidentally read real env vars."""
    for var in (
        "MY_PLUGIN_CONFIG",
        "MY_PLUGIN_PLUGIN_ROOT",
        "MY_PLUGIN_CWD",
        "CLAUDE_PROJECT_DIR",
    ):
        monkeypatch.delenv(var, raising=False)


# --- resolve_search_root -----------------------------------------------------


def test_resolve_search_root_prefers_explicit(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    explicit.mkdir()

    assert resolve_search_root(explicit) == explicit.resolve()


def test_resolve_search_root_reads_env_vars_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("MY_PLUGIN_CWD", str(first))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(second))

    result = resolve_search_root(
        explicit=None, env_vars=("MY_PLUGIN_CWD", "CLAUDE_PROJECT_DIR")
    )

    assert result == first.resolve()


def test_resolve_search_root_falls_through_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = resolve_search_root(explicit=None, env_vars=("DOES_NOT_EXIST",))

    assert result == tmp_path.resolve()


# --- resolve_config_path -----------------------------------------------------


def test_resolve_config_path_override_env_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _mkrepo(tmp_path / "repo")
    walk_cfg = _write_config(repo)  # would normally win
    override = tmp_path / "override.yml"
    override.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("MY_PLUGIN_CONFIG", str(override))

    winner, searched = resolve_config_path(
        repo,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        override_env="MY_PLUGIN_CONFIG",
        plugin_root_env="MY_PLUGIN_PLUGIN_ROOT",
    )

    assert winner == override.resolve()
    # Walk-candidate must NOT be inspected once override won.
    assert walk_cfg.resolve() not in [p.resolve() for p in searched]
    assert searched == [override.resolve()]


def test_resolve_config_path_override_missing_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bogus = tmp_path / "nope.yml"
    monkeypatch.setenv("MY_PLUGIN_CONFIG", str(bogus))

    with pytest.raises(ConfigError, match="MY_PLUGIN_CONFIG points to non-existent"):
        resolve_config_path(
            tmp_path,
            config_dir=CONFIG_DIR,
            filenames=FILENAMES,
            override_env="MY_PLUGIN_CONFIG",
        )


def test_resolve_config_path_plugin_root_beats_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _mkrepo(tmp_path / "repo")
    _write_config(repo)  # walk candidate — should LOSE
    plugin_root = tmp_path / "binroot"
    plugin_root.mkdir()
    binroot_cfg = plugin_root / "plugin.yml"
    binroot_cfg.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("MY_PLUGIN_PLUGIN_ROOT", str(plugin_root))

    winner, searched = resolve_config_path(
        repo,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        override_env="MY_PLUGIN_CONFIG",
        plugin_root_env="MY_PLUGIN_PLUGIN_ROOT",
    )

    assert winner == binroot_cfg.resolve()
    # Walk candidates are NOT inspected once plugin-root won.
    assert searched == [binroot_cfg.resolve()]


def test_resolve_config_path_plugin_root_missing_falls_through_to_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _mkrepo(tmp_path / "repo")
    walk_cfg = _write_config(repo)
    empty_root = tmp_path / "empty-root"
    empty_root.mkdir()
    monkeypatch.setenv("MY_PLUGIN_PLUGIN_ROOT", str(empty_root))

    winner, searched = resolve_config_path(
        repo,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        plugin_root_env="MY_PLUGIN_PLUGIN_ROOT",
    )

    assert winner == walk_cfg.resolve()
    # Plugin-root candidates were inspected (and failed) before walk-candidate won.
    assert (empty_root / "plugin.yml").resolve() in [p.resolve() for p in searched]
    assert winner.resolve() == walk_cfg.resolve()


def test_resolve_config_path_walks_outward_to_outer_repo(
    tmp_path: Path,
) -> None:
    outer = _mkrepo(tmp_path / "outer")
    inner = _mkrepo(outer / "inner")
    outer_cfg = _write_config(outer)
    # No inner config — outer should win after one boundary jump.

    winner, searched = resolve_config_path(
        inner,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
    )

    assert winner == outer_cfg.resolve()
    # Inner candidate inspected first, then outer.
    inner_paths = [inner / CONFIG_DIR / n for n in FILENAMES]
    assert all(p.resolve() in [q.resolve() for q in searched] for p in inner_paths)


def test_resolve_config_path_home_default_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    cfg_dir = home / CONFIG_DIR
    cfg_dir.mkdir(parents=True)
    home_cfg = cfg_dir / "plugin.yml"
    home_cfg.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows
    # No git repo around `start` so walk yields nothing.
    start = tmp_path / "no-repo"
    start.mkdir()

    winner, searched = resolve_config_path(
        start,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        home_default=True,
    )

    assert winner == home_cfg.resolve()
    assert home_cfg.resolve() in [p.resolve() for p in searched]


def test_resolve_config_path_skips_home_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    cfg_dir = home / CONFIG_DIR
    cfg_dir.mkdir(parents=True)
    home_cfg = cfg_dir / "plugin.yml"
    home_cfg.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    start = tmp_path / "no-repo"
    start.mkdir()

    winner, searched = resolve_config_path(
        start,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        home_default=False,
    )

    assert winner is None
    # Home candidate should NOT appear in the searched list.
    assert home_cfg.resolve() not in [p.resolve() for p in searched]


def test_resolve_config_path_returns_none_when_nothing_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force HOME away from any real config dir.
    fake_home = tmp_path / "empty-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    start = tmp_path / "no-repo"
    start.mkdir()

    winner, searched = resolve_config_path(
        start,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        home_default=True,
    )

    assert winner is None
    # Home candidates were inspected (but nothing matched).
    assert len(searched) >= 1


def test_resolve_config_path_filenames_order_matters(tmp_path: Path) -> None:
    """First filename listed wins when multiple exist in the same repo."""
    repo = _mkrepo(tmp_path / "repo")
    cfg_dir = repo / CONFIG_DIR
    cfg_dir.mkdir()
    yml = cfg_dir / "plugin.yml"
    yml.write_text("a: 1\n", encoding="utf-8")
    yaml = cfg_dir / "plugin.yaml"
    yaml.write_text("b: 2\n", encoding="utf-8")

    winner, _ = resolve_config_path(
        repo,
        config_dir=CONFIG_DIR,
        filenames=("plugin.yml", "plugin.yaml"),
    )

    assert winner == yml.resolve()
