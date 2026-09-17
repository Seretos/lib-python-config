"""Select the previously-released tag for ``gh release create --notes-start-tag``.

``release.yml`` creates and pushes the new release tag *before* running the
"Create GitHub Release" step, so at selection time the new tag is already
present in ``git tag --list``. This module's job is to pick the tag that
immediately precedes the version being released -- strictly, so the new tag
never selects itself -- following SemVer 2.0.0 §11 precedence: the numeric
``MAJOR.MINOR.PATCH`` triple is compared first (numerically, not lexically);
a version with a pre-release has *lower* precedence than the same triple
without one; and pre-release identifiers are compared dot-separated
component by component (numeric identifiers compare numerically and always
have lower precedence than alphanumeric ones; a shorter set of pre-release
identifiers has lower precedence than a longer set that shares the same
prefix).

Only well-formed ``vMAJOR.MINOR.PATCH[-PRERELEASE]`` tags participate; any
other tag (a branch-like name, a short/partial version, unrelated text) is
silently ignored rather than accidentally winning a lexical comparison.
"""
from __future__ import annotations

import re
import sys
from typing import Iterable

_VERSION_CORE = r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?"
TAG_RE = re.compile(r"^v" + _VERSION_CORE + r"$")
VERSION_RE = re.compile(r"^v?" + _VERSION_CORE + r"$")

# Sort key type: (major, minor, patch, is_release, prerelease_key)
# ``is_release`` is 1 for a plain release and 0 for a pre-release, so that
# (per SemVer §11.3) a release always outranks a pre-release sharing the
# same MAJOR.MINOR.PATCH triple.
_VersionKey = tuple


def _prerelease_key(prerelease: str | None) -> tuple:
    if prerelease is None:
        return ()
    parts = []
    for identifier in prerelease.split("."):
        if identifier.isdigit():
            # Numeric identifiers compare numerically and always have
            # lower precedence than alphanumeric ones (leading 0 flag).
            parts.append((0, int(identifier)))
        else:
            parts.append((1, identifier))
    return tuple(parts)


def _version_key(major: str, minor: str, patch: str, prerelease: str | None) -> _VersionKey:
    is_release = 1 if prerelease is None else 0
    return (int(major), int(minor), int(patch), is_release, _prerelease_key(prerelease))


def _parse(pattern: re.Pattern[str], text: str) -> _VersionKey | None:
    match = pattern.match(text)
    if match is None:
        return None
    major, minor, patch, prerelease = match.groups()
    return _version_key(major, minor, patch, prerelease)


def select_previous_tag(tags: Iterable[str], version: str) -> str | None:
    """Return the tag immediately preceding ``version``, or ``None``.

    ``tags`` is the full candidate list (e.g. the output of
    ``git tag --list 'v*'``), which may already include the tag for
    ``version`` itself (it is excluded by strict ``<``) and may contain
    malformed or unrelated entries (silently ignored). ``version`` may be
    given with or without a leading ``v`` (``release.yml`` passes the bare
    ``inputs.version``).
    """
    version_key = _parse(VERSION_RE, version)
    if version_key is None:
        raise ValueError(f"version {version!r} is not valid semver")

    best: _VersionKey | None = None
    best_tag: str | None = None
    for tag in tags:
        tag_key = _parse(TAG_RE, tag)
        if tag_key is None:
            continue
        if tag_key < version_key and (best is None or tag_key > best):
            best = tag_key
            best_tag = tag
    return best_tag


def _main(argv: list[str]) -> int:
    version = argv[1]
    tags = [line.strip() for line in sys.stdin if line.strip()]
    result = select_previous_tag(tags, version)
    if result is not None:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
