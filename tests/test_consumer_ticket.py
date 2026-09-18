"""Driving tests for ``.github/scripts/consumer_ticket.py``.

Package #11 requires a pure-logic module that renders the per-consumer
"chore(deps): update lib-python-config" issue title/body and picks which
existing issue (if any) should be reused rather than duplicated, so
``notify-consumer``'s composite action can stay a thin shell around
tested logic. As with ``prev_release_tag.py`` (package #8),
``.github/scripts`` is not on ``pythonpath`` (pyproject.toml only sets
``pythonpath = ["src"]``, and ``.github``/``.github.scripts`` are not valid
Python package names anyway), so the module under test is loaded directly
by file path rather than imported normally -- following the exact idiom
established in ``tests/test_prev_release_tag.py``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "consumer_ticket.py"


def _load_consumer_ticket_module() -> ModuleType:
    """Load the script module by path.

    Until ``.github/scripts/consumer_ticket.py`` exists, this raises
    (spec creation fails, or ``exec_module`` raises ``FileNotFoundError``
    when it tries to read the missing source file) -- that failure, not an
    assertion, is the expected RED reason for every test in this file.
    """
    spec = importlib.util.spec_from_file_location("consumer_ticket", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"could not load spec for {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def consumer_ticket() -> ModuleType:
    return _load_consumer_ticket_module()


# --- R1: issue rendering ----------------------------------------------------


def test_issue_title_contains_version_and_literal_substrings(consumer_ticket) -> None:
    title = consumer_ticket.issue_title("1.2.3")
    assert "chore(deps):" in title
    assert "lib-python-config" in title
    assert "1.2.3" in title


def test_issue_title_distinguishes_versions(consumer_ticket) -> None:
    # A stub that hard-codes the version string cannot pass this.
    assert consumer_ticket.issue_title("1.2.3") != consumer_ticket.issue_title("9.9.9")


def test_issue_body_contains_marker_tag_url_and_notes_verbatim(consumer_ticket) -> None:
    notes = "- fixed a bug\n- added a feature\n"
    body = consumer_ticket.issue_body(
        version="1.2.3",
        tag="v1.2.3",
        release_url="https://github.com/Seretos/lib-python-config/releases/tag/v1.2.3",
        notes=notes,
    )
    assert consumer_ticket.MARKER in body
    assert "v1.2.3" in body
    assert "https://github.com/Seretos/lib-python-config/releases/tag/v1.2.3" in body
    assert notes in body


def test_issue_body_interpolates_tag_and_version_independently(consumer_ticket) -> None:
    # tag deliberately bears no textual relationship to version (unlike
    # every other fixture in this file, which uses tag == "v" + version
    # and so cannot tell a genuine interpolation of both apart from an
    # implementation that silently derives tag as "v" + version and
    # ignores the tag argument entirely).
    body = consumer_ticket.issue_body(
        version="1.2.3",
        tag="release-42",
        release_url="https://example.invalid/releases/tag/release-42",
        notes="notes body",
    )
    assert "release-42" in body
    assert "1.2.3" in body


def test_issue_body_empty_notes_still_valid_with_marker(consumer_ticket) -> None:
    body = consumer_ticket.issue_body(
        version="1.2.3",
        tag="v1.2.3",
        release_url="https://example.invalid/releases/tag/v1.2.3",
        notes="",
    )
    assert consumer_ticket.MARKER in body
    assert len(body) <= consumer_ticket.BODY_LIMIT


def test_issue_body_truncates_with_notice_when_over_limit(consumer_ticket) -> None:
    release_url = "https://github.com/Seretos/lib-python-config/releases/tag/v1.2.3"
    huge_notes = "x" * 100_000
    body = consumer_ticket.issue_body(
        version="1.2.3",
        tag="v1.2.3",
        release_url=release_url,
        notes=huge_notes,
    )
    assert len(body) <= consumer_ticket.BODY_LIMIT
    assert consumer_ticket.MARKER in body
    expected_notice_line = (
        f"_Release notes truncated; see the full notes at {release_url}._"
    )
    assert body.rstrip().endswith(expected_notice_line)


def test_issue_body_exactly_at_limit_needs_no_truncation_notice(consumer_ticket) -> None:
    release_url = "https://example.invalid/releases/tag/v1.2.3"
    # Find the notes length that lands the rendered body exactly on
    # BODY_LIMIT, by growing notes until the boundary is reached or
    # crossed, then asserting the boundary case itself carries no notice.
    probe = consumer_ticket.issue_body(
        version="1.2.3", tag="v1.2.3", release_url=release_url, notes=""
    )
    fixed_overhead = len(probe)
    notes_len = consumer_ticket.BODY_LIMIT - fixed_overhead
    assert notes_len > 0, "fixed overhead alone must fit under BODY_LIMIT"
    notes = "y" * notes_len
    body = consumer_ticket.issue_body(
        version="1.2.3", tag="v1.2.3", release_url=release_url, notes=notes
    )
    assert len(body) == consumer_ticket.BODY_LIMIT
    assert consumer_ticket.TRUNCATION_NOTICE not in body
    assert consumer_ticket.MARKER in body


# --- R2: idempotent, open-only reuse ---------------------------------------


def test_select_existing_issue_returns_lowest_numbered_open_match(consumer_ticket) -> None:
    marker = consumer_ticket.MARKER
    issues = [
        {"number": 42, "body": f"some body {marker}", "state": "open"},
        {"number": 7, "body": f"other body {marker}"},
    ]
    assert consumer_ticket.select_existing_issue(issues, marker) == 7


def test_select_existing_issue_none_when_no_marker_match(consumer_ticket) -> None:
    marker = consumer_ticket.MARKER
    issues = [
        {"number": 1, "body": "unrelated body", "state": "open"},
        {"number": 2, "body": "also unrelated"},
    ]
    assert consumer_ticket.select_existing_issue(issues, marker) is None


def test_select_existing_issue_none_when_only_marker_matches_are_closed(consumer_ticket) -> None:
    marker = consumer_ticket.MARKER
    issues = [
        {"number": 1, "body": f"stale {marker}", "state": "closed"},
        {"number": 2, "body": "no marker here", "state": "open"},
    ]
    # Critical case: a closed issue carrying the marker must NEVER be
    # selected/reused, even though it is the only marker match.
    assert consumer_ticket.select_existing_issue(issues, marker) is None


def test_select_existing_issue_open_higher_number_beats_closed_lower_number(
    consumer_ticket,
) -> None:
    marker = consumer_ticket.MARKER
    # Exercises the specific ordering bug the plan flags: "pick the
    # lowest-numbered marker-match first, THEN check if it's open" would
    # wrongly stop at #1 (closed) and return None; the correct rule
    # filters to (marker-match AND open) first, then picks the lowest
    # number among survivors, which here is #5, not #1 and not None.
    issues = [
        {"number": 1, "body": f"stale {marker}", "state": "closed"},
        {"number": 5, "body": f"fresh {marker}", "state": "open"},
    ]
    assert consumer_ticket.select_existing_issue(issues, marker) == 5


def test_select_existing_issue_handles_real_gh_cli_uppercase_state(consumer_ticket) -> None:
    marker = consumer_ticket.MARKER
    # The real `gh issue list --json state` CLI output uses GitHub's
    # GraphQL IssueState enum verbatim -- uppercase "OPEN"/"CLOSED" -- not
    # the lowercase "open"/"closed" convention the rest of this suite
    # uses for readability. select_existing_issue itself must normalize
    # case, since it is the function that gets real CLI JSON piped into
    # it via the `select` subcommand.
    issues = [
        {"number": 1, "body": f"stale {marker}", "state": "CLOSED"},
        {"number": 5, "body": f"fresh {marker}", "state": "OPEN"},
    ]
    assert consumer_ticket.select_existing_issue(issues, marker) == 5


def test_select_existing_issue_lower_number_wins_among_two_open_matches(consumer_ticket) -> None:
    marker = consumer_ticket.MARKER
    issues = [
        {"number": 10, "body": f"{marker} second", "state": "open"},
        {"number": 3, "body": f"{marker} first", "state": "open"},
    ]
    assert consumer_ticket.select_existing_issue(issues, marker) == 3


def test_select_existing_issue_missing_state_key_treated_as_open(consumer_ticket) -> None:
    marker = consumer_ticket.MARKER
    issues = [{"number": 5, "body": f"{marker} no state key at all"}]
    assert consumer_ticket.select_existing_issue(issues, marker) == 5


def test_select_existing_issue_marker_in_unrelated_body_still_counts(consumer_ticket) -> None:
    marker = consumer_ticket.MARKER
    # A plain substring test, not a strict "issue we created" check: the
    # marker quoted inside a fenced code block in someone else's issue
    # still counts as a match by design (documented simplification).
    issues = [
        {
            "number": 9,
            "body": f"```\nsome unrelated issue quoting {marker} in a code block\n```",
            "state": "open",
        }
    ]
    assert consumer_ticket.select_existing_issue(issues, marker) == 9
