"""Tests for filesystem discovery primitives."""
from __future__ import annotations

from pathlib import Path

import pytest

from lib_python_config.discovery import (
    find_git_repo_root,
    walk_project_boundaries,
    walk_up,
)


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("")
    return p


def _mkrepo(root: Path) -> Path:
    """Create a fake repo: just a `.git` directory marker."""
    (root / ".git").mkdir(parents=True, exist_ok=True)
    return root


# --- walk_up -----------------------------------------------------------------


def test_walk_up_finds_first_existing_name(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    target = _touch(tmp_path / "a" / "marker.txt")

    found = walk_up(nested, ("marker.txt",))

    assert found == target.resolve()


def test_walk_up_prefers_first_matching_name(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    # Only `second.txt` exists — walk should find it even though `first.txt` is listed first.
    target = _touch(nested / "second.txt")

    found = walk_up(nested, ("first.txt", "second.txt"))

    assert found == target.resolve()


def test_walk_up_returns_none_when_nothing_found(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    found = walk_up(nested, ("does-not-exist.txt",))

    assert found is None


# --- find_git_repo_root ------------------------------------------------------


def test_find_git_repo_root_returns_repo_dir(tmp_path: Path) -> None:
    repo = _mkrepo(tmp_path / "myrepo")
    nested = repo / "src" / "pkg"
    nested.mkdir(parents=True)

    assert find_git_repo_root(nested) == repo.resolve()


def test_find_git_repo_root_handles_git_as_file(tmp_path: Path) -> None:
    """Worktrees / submodules have `.git` as a file, not a directory."""
    repo = tmp_path / "wt"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere\n")
    nested = repo / "sub"
    nested.mkdir()

    assert find_git_repo_root(nested) == repo.resolve()


def test_find_git_repo_root_returns_none_when_no_repo(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert find_git_repo_root(nested) is None


# --- walk_project_boundaries -------------------------------------------------


def test_walk_project_boundaries_lists_repo_candidates(tmp_path: Path) -> None:
    repo = _mkrepo(tmp_path / "repo")
    nested = repo / "src"
    nested.mkdir()

    candidates = walk_project_boundaries(
        nested,
        config_dir=".seretos",
        filenames=("plugin.yml", "plugin.yaml"),
    )

    # One iteration: inside `repo`. Two candidates per pass (one per filename).
    assert candidates == [
        repo / ".seretos" / "plugin.yml",
        repo / ".seretos" / "plugin.yaml",
    ]


def test_walk_project_boundaries_jumps_out_of_repo(tmp_path: Path) -> None:
    outer = _mkrepo(tmp_path / "outer")
    inner = _mkrepo(outer / "inner")
    nested = inner / "src"
    nested.mkdir(parents=True)

    candidates = walk_project_boundaries(
        nested,
        config_dir=".seretos",
        filenames=("plugin.yml",),
    )

    # First pass: inner. Second pass: outer (after jumping above inner).
    assert candidates == [
        inner / ".seretos" / "plugin.yml",
        outer / ".seretos" / "plugin.yml",
    ]


def test_walk_project_boundaries_returns_empty_outside_any_repo(tmp_path: Path) -> None:
    nested = tmp_path / "no-repo" / "here"
    nested.mkdir(parents=True)

    candidates = walk_project_boundaries(
        nested,
        config_dir=".seretos",
        filenames=("plugin.yml",),
    )

    assert candidates == []
