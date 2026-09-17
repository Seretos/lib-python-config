"""Tests for `resolve_search_root` and `resolve_config_path`."""
from __future__ import annotations

from pathlib import Path

import pytest

from lib_python_config.models import ConfigError
from lib_python_config.resolver import resolve_config_path, resolve_search_root
from lib_python_config.resolver import resolve_config_paths  # noqa: E402,F401 — append-only
from lib_python_config import resolver as resolver_module  # noqa: E402 — append-only

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


# --- resolve_config_paths (R1: all existing layers, lowest-priority-first) --


def test_resolve_config_paths_returns_all_layers_lowest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    home_cfg = _write_config(home)
    outer = _mkrepo(tmp_path / "outer")
    inner = _mkrepo(outer / "inner")
    outer_cfg = _write_config(outer)
    inner_cfg = _write_config(inner)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    existing, inspected = resolve_config_paths(
        inner / "sub",
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
    )

    assert [p.resolve() for p in existing] == [
        home_cfg.resolve(),
        outer_cfg.resolve(),
        inner_cfg.resolve(),
    ]

    inspected_resolved = [p.resolve() for p in inspected]
    # Lowest-priority-first: home before outer before inner.
    assert (
        inspected_resolved.index(home_cfg.resolve())
        < inspected_resolved.index(outer_cfg.resolve())
        < inspected_resolved.index(inner_cfg.resolve())
    )
    # Non-existing candidates (the .yaml sibling in each layer) are present too.
    for repo_dir in (home, outer, inner):
        assert (repo_dir / CONFIG_DIR / "plugin.yaml").resolve() in inspected_resolved

    # resolve_config_path on the same tree still returns only the inner file.
    winner, _ = resolve_config_path(
        inner / "sub", config_dir=CONFIG_DIR, filenames=FILENAMES
    )
    assert winner == inner_cfg.resolve()


def test_resolve_config_paths_tail_order_includes_plugin_root_and_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    home_cfg = _write_config(home)
    outer = _mkrepo(tmp_path / "outer")
    inner = _mkrepo(outer / "inner")
    outer_cfg = _write_config(outer)
    inner_cfg = _write_config(inner)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    plugin_root = tmp_path / "binroot"
    plugin_root.mkdir()
    binroot_cfg = plugin_root / "plugin.yml"
    binroot_cfg.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("MY_PLUGIN_PLUGIN_ROOT", str(plugin_root))

    override = tmp_path / "override.yml"
    override.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("MY_PLUGIN_CONFIG", str(override))

    existing, _ = resolve_config_paths(
        inner,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        override_env="MY_PLUGIN_CONFIG",
        plugin_root_env="MY_PLUGIN_PLUGIN_ROOT",
    )

    assert [p.resolve() for p in existing] == [
        home_cfg.resolve(),
        outer_cfg.resolve(),
        inner_cfg.resolve(),
        binroot_cfg.resolve(),
        override.resolve(),
    ]


def test_resolve_config_paths_home_default_false_drops_home_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    home_cfg = _write_config(home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    start = tmp_path / "no-repo"
    start.mkdir()

    existing, inspected = resolve_config_paths(
        start,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        home_default=False,
    )

    assert existing == []
    assert home_cfg.resolve() not in [p.resolve() for p in inspected]


def test_resolve_config_paths_nothing_exists_returns_empty_existing_with_inspected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "empty-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    start = tmp_path / "no-repo"
    start.mkdir()

    existing, inspected = resolve_config_paths(
        start,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
    )

    assert existing == []
    assert len(inspected) >= 1


def test_resolve_config_paths_both_yaml_and_yml_in_one_dir(tmp_path: Path) -> None:
    repo = _mkrepo(tmp_path / "repo")
    cfg_dir = repo / CONFIG_DIR
    cfg_dir.mkdir()
    yml = cfg_dir / "plugin.yml"
    yml.write_text("a: 1\n", encoding="utf-8")
    yaml = cfg_dir / "plugin.yaml"
    yaml.write_text("b: 2\n", encoding="utf-8")

    existing, _ = resolve_config_paths(
        repo,
        config_dir=CONFIG_DIR,
        filenames=("plugin.yml", "plugin.yaml"),
        home_default=False,
    )

    assert [p.resolve() for p in existing] == [yaml.resolve(), yml.resolve()]


# --- resolve_config_paths (R2: dedupe confined to the `existing` list) -----


def test_resolve_config_paths_dedupes_home_that_is_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _mkrepo(tmp_path / "home")
    home_cfg = _write_config(home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    existing, inspected = resolve_config_paths(
        home,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
    )

    existing_resolved = [p.resolve() for p in existing]
    inspected_resolved = [p.resolve() for p in inspected]
    assert existing_resolved.count(home_cfg.resolve()) == 1
    assert inspected_resolved.count(home_cfg.resolve()) == 2


def test_resolve_config_path_searched_keeps_duplicate_when_home_is_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lock: dedupe must never leak into `_build_candidates`/`resolve_config_path`.

    HOME is itself a git repo but carries no config file, so the walk step
    and the home-default step both inspect (and fail to find) the same two
    filenames — `searched` must still count each one twice.
    """
    home = _mkrepo(tmp_path / "home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    winner, searched = resolve_config_path(
        home,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
    )

    assert winner is None
    resolved = [p.resolve() for p in searched]
    assert resolved.count((home / CONFIG_DIR / "plugin.yml").resolve()) == 2
    assert resolved.count((home / CONFIG_DIR / "plugin.yaml").resolve()) == 2


def test_resolve_config_paths_dedupe_keeps_highest_priority_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The duplicate's two slots must be separated by a genuine, existing,
    non-duplicated candidate (here: the inner repo's own config) so that
    "keep the first/highest-priority occurrence" and "keep the
    last/lowest-priority occurrence" produce genuinely different result
    lists. Priority order is plugin-root > walk-inner > walk-outer:

      - `outer`'s own config is duplicated across the plugin-root step
        (pointed directly at `outer`'s config dir) and the walk step's
        outer-repo candidate — same physical file, two slots, the
        highest-priority one first (plugin-root) and the lowest-priority
        one later (walk-outer).
      - `inner`'s own (distinct, existing, non-duplicated) config sits at
        the walk-inner slot, strictly between those two duplicate slots.

    Keeping the first (plugin-root) occurrence yields
    `[inner_cfg, outer_cfg]` (outer's file promoted to the highest-priority
    end); keeping the last (walk-outer) occurrence would instead yield
    `[outer_cfg, inner_cfg]`. Only the former is correct.
    """
    outer = _mkrepo(tmp_path / "outer")
    inner = _mkrepo(outer / "inner")
    outer_cfg = _write_config(outer)
    inner_cfg = _write_config(inner)
    monkeypatch.setenv("MY_PLUGIN_PLUGIN_ROOT", str(outer / CONFIG_DIR))

    existing, inspected = resolve_config_paths(
        inner,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        plugin_root_env="MY_PLUGIN_PLUGIN_ROOT",
        home_default=False,
    )

    existing_resolved = [p.resolve() for p in existing]
    inspected_resolved = [p.resolve() for p in inspected]
    # Deduped to a single entry, kept at its highest-priority (plugin-root)
    # slot: after inner's own distinct layer, not before it.
    assert existing_resolved == [inner_cfg.resolve(), outer_cfg.resolve()]
    assert inspected_resolved.count(outer_cfg.resolve()) == 2


# --- resolve_config_paths (R3: override still raises when missing) ---------


def test_resolve_config_paths_override_missing_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bogus = tmp_path / "nope.yml"
    monkeypatch.setenv("MY_PLUGIN_CONFIG", str(bogus))

    with pytest.raises(ConfigError, match="points to non-existent"):
        resolve_config_paths(
            tmp_path,
            config_dir=CONFIG_DIR,
            filenames=FILENAMES,
            override_env="MY_PLUGIN_CONFIG",
        )


def test_resolve_config_paths_override_existing_wins_last_position(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    home_cfg = _write_config(home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    repo = _mkrepo(tmp_path / "repo")
    repo_cfg = _write_config(repo)

    override = tmp_path / "override.yml"
    override.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("MY_PLUGIN_CONFIG", str(override))

    existing, _ = resolve_config_paths(
        repo,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        override_env="MY_PLUGIN_CONFIG",
    )

    assert [p.resolve() for p in existing] == [
        home_cfg.resolve(),
        repo_cfg.resolve(),
        override.resolve(),
    ]


# --- resolve_config_paths (R7: exported from the package root) -------------


def test_resolve_config_paths_is_exported() -> None:
    import lib_python_config

    assert lib_python_config.resolve_config_paths is resolve_config_paths
    assert "resolve_config_paths" in lib_python_config.__all__


# --- Regression: override/plugin-root short-circuit must never touch the ---
# --- filesystem walk or the home default once a winner already exists. ----


def test_resolve_config_path_override_wins_without_touching_walk_or_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`walk_project_boundaries` walks up to the filesystem root and can hit
    a `PermissionError` on an inaccessible ancestor directory. Once the
    override already wins, that walk (and the home-default construction)
    must never be reached — matching the short-circuit behaviour
    `resolve_config_path` had before candidate-building was extracted into
    `_build_candidates`. Proven here by making both steps raise if called.
    """
    override = tmp_path / "override.yml"
    override.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("MY_PLUGIN_CONFIG", str(override))

    def _must_not_be_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not be called once override already won")

    monkeypatch.setattr(
        resolver_module, "walk_project_boundaries", _must_not_be_called
    )
    monkeypatch.setattr(
        resolver_module, "_home_default_candidates", _must_not_be_called
    )

    winner, searched = resolve_config_path(
        tmp_path,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        override_env="MY_PLUGIN_CONFIG",
        plugin_root_env="MY_PLUGIN_PLUGIN_ROOT",
        home_default=True,
    )

    assert winner == override.resolve()
    assert searched == [override.resolve()]


def test_resolve_config_path_plugin_root_wins_without_touching_walk_or_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same regression as above, for the plugin-root candidate winning."""
    plugin_root = tmp_path / "binroot"
    plugin_root.mkdir()
    binroot_cfg = plugin_root / "plugin.yml"
    binroot_cfg.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("MY_PLUGIN_PLUGIN_ROOT", str(plugin_root))

    def _must_not_be_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not be called once plugin-root already won")

    monkeypatch.setattr(
        resolver_module, "walk_project_boundaries", _must_not_be_called
    )
    monkeypatch.setattr(
        resolver_module, "_home_default_candidates", _must_not_be_called
    )

    winner, searched = resolve_config_path(
        tmp_path,
        config_dir=CONFIG_DIR,
        filenames=FILENAMES,
        plugin_root_env="MY_PLUGIN_PLUGIN_ROOT",
        home_default=True,
    )

    assert winner == binroot_cfg.resolve()
    assert searched == [binroot_cfg.resolve()]
