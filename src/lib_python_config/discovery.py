"""Filesystem walking primitives.

`walk_up` and `find_git_repo_root` are the two pure walks — they don't
know anything about config formats. `walk_project_boundaries` builds on
both to produce the ordered list of candidate config paths an
outer-most-repo-first lookup should inspect.
"""
from __future__ import annotations

from pathlib import Path


def walk_up(start: Path, names: tuple[str, ...]) -> Path | None:
    """Walk up from `start` looking for the first existing path that ends
    with any of `names`. `names` are relative to each visited directory.
    """
    cur = start.resolve()
    while True:
        for name in names:
            candidate = cur / name
            if candidate.exists():
                return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent


def find_git_repo_root(start: Path) -> Path | None:
    """Return the nearest ancestor of `start` containing a `.git` entry,
    or None if no enclosing git repo exists.

    `.git` can be either a directory (regular checkout) or a file
    (worktrees / submodules), so we use `.exists()` instead of
    `.is_dir()`.
    """
    cur = start.resolve()
    while True:
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def walk_project_boundaries(
    start: Path,
    config_dir: str,
    filenames: tuple[str, ...],
) -> list[Path]:
    """`<repo>/<config_dir>/<filename>` candidates walked outward by
    **git project boundary** rather than directory level.

    From `start`, find the nearest enclosing git repo and emit one
    candidate per `filename` under its `config_dir`. Then jump *out* of
    that repo (start the next iteration above its root) and repeat. The
    walk terminates when no enclosing git repo exists.

    Rationale: deeply-nested meta-repos would otherwise produce a chain
    of every directory between `start` and `/`. Project-by-project keeps
    the candidate list short and semantically meaningful — each repo
    gets exactly one chance to own its config.
    """
    out: list[Path] = []
    cur = start.resolve()
    while True:
        repo = find_git_repo_root(cur)
        if not repo:
            return out
        for name in filenames:
            out.append(repo / config_dir / name)
        if repo.parent == repo:
            return out
        cur = repo.parent
