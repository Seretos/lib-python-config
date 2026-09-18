"""Render and dedupe the per-consumer "chore(deps): update lib-python-config"
issue that ``notify-consumer`` files/updates on each direct consumer repo.

Pure logic, stdlib only -- mirrors the ``prev_release_tag.py`` idiom
(importable functions + a small CLI) so the composite action can shell out
to it while the behaviour itself stays unit-testable without any GitHub
API access.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Iterable

MARKER = "<!-- lib-python-config-deps-update -->"

BODY_LIMIT = 65536

TRUNCATION_NOTICE = "_Release notes truncated; see the full notes at {release_url}._"


def issue_title(version: str) -> str:
    """Render the issue title for a ``lib-python-config`` release.

    Must genuinely interpolate ``version`` -- two different versions
    produce two different titles.
    """
    return f"chore(deps): update lib-python-config to {version}"


def _render_body(version: str, tag: str, release_url: str, notes: str) -> str:
    return (
        f"{MARKER}\n"
        f"A new lib-python-config release is available: **{tag}** "
        f"(version {version}).\n\n"
        f"Release: {release_url}\n\n"
        f"### Release notes\n\n"
        f"{notes}"
    )


def issue_body(version: str, tag: str, release_url: str, notes: str) -> str:
    """Render the issue body.

    ``tag`` and ``version`` are two independently-sourced values -- both
    are used verbatim as given, never derived from one another. When the
    naive body would exceed ``BODY_LIMIT``, ``notes`` is truncated so the
    total length is ``<= BODY_LIMIT`` and a truncation notice (carrying
    the real ``release_url``) is appended; the notice is only added when
    the naive body would *strictly exceed* the limit -- landing exactly on
    the limit needs no notice.
    """
    naive_body = _render_body(version, tag, release_url, notes)
    if len(naive_body) <= BODY_LIMIT:
        return naive_body

    notice = TRUNCATION_NOTICE.format(release_url=release_url)
    # Overhead is everything in the rendered body except the notes
    # themselves, plus the notice appended after a blank-line separator.
    overhead = len(_render_body(version, tag, release_url, "")) + len("\n\n") + len(notice)
    truncated_notes_len = max(0, BODY_LIMIT - overhead)
    truncated_notes = notes[:truncated_notes_len]
    body = _render_body(version, tag, release_url, truncated_notes) + "\n\n" + notice
    return body[:BODY_LIMIT]


def select_existing_issue(issues: Iterable[dict[str, Any]], marker: str) -> int | None:
    """Return the lowest-numbered open issue whose body carries ``marker``.

    Filters to marker-matching AND open (state absent or "open", compared
    case-insensitively) issues first, then picks the lowest ``number``
    among that filtered set -- never the other order, so a closed issue
    carrying the marker can never block (or itself be) the match.

    The case-insensitive comparison matters because the real ``gh`` CLI
    (``gh issue list --json state``) returns GitHub's GraphQL ``IssueState``
    enum verbatim -- uppercase ``"OPEN"``/``"CLOSED"`` -- never the
    lowercase ``"open"``/``"closed"`` that this module's own default and
    the unit tests happen to use.
    """
    candidates = [
        issue
        for issue in issues
        if marker in issue.get("body", "")
        and issue.get("state", "open").lower() == "open"
    ]
    if not candidates:
        return None
    return min(issue["number"] for issue in candidates)


def _cmd_title(argv: list[str]) -> int:
    version = argv[0]
    print(issue_title(version))
    return 0


def _cmd_body(argv: list[str]) -> int:
    version, tag, release_url = argv[0], argv[1], argv[2]
    notes = sys.stdin.read()
    print(issue_body(version=version, tag=tag, release_url=release_url, notes=notes))
    return 0


def _cmd_select(argv: list[str]) -> int:
    issues = json.loads(sys.stdin.read())
    selected = select_existing_issue(issues, MARKER)
    if selected is not None:
        print(selected)
    return 0


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: consumer_ticket.py <title|body|select> [args...]", file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    if command == "title":
        return _cmd_title(rest)
    if command == "body":
        return _cmd_body(rest)
    if command == "select":
        return _cmd_select(rest)
    print(f"unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
