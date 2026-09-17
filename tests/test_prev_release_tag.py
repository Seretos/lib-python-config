"""Driving tests for ``.github/scripts/prev_release_tag.py``.

Package #8 requires the previous-released-tag selection logic used by
``release.yml`` (``gh release create --notes-start-tag``) to be exercisable
by the project's own test suite, not merely present as a string in YAML.
``.github/scripts`` is not on ``pythonpath`` (pyproject.toml only sets
``pythonpath = ["src"]``, and ``.github``/``.github.scripts`` are not valid
Python package names anyway), so the module under test is loaded directly by
file path rather than imported normally.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "prev_release_tag.py"


def _load_prev_release_tag_module() -> ModuleType:
    """Load the script module by path.

    Until ``.github/scripts/prev_release_tag.py`` exists, this raises
    (spec creation fails, or ``exec_module`` raises ``FileNotFoundError``
    when it tries to read the missing source file) — that failure, not an
    assertion, is the expected RED reason for every test in this file.
    """
    spec = importlib.util.spec_from_file_location("prev_release_tag", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"could not load spec for {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def select_previous_tag():
    module = _load_prev_release_tag_module()
    return module.select_previous_tag


def test_selects_v0_1_1_from_real_repo_tags(select_previous_tag) -> None:
    tags = ["v0.1.0", "v0.1.1", "v0.2.0"]
    assert select_previous_tag(tags, "0.2.0") == "v0.1.1"


def test_new_tag_itself_never_selected_strict_less_than(select_previous_tag) -> None:
    # The new tag is already pushed by the time release.yml selects a
    # predecessor, so it is present in `git tag --list` but must not win.
    tags = ["v0.1.0", "v0.2.0"]
    assert select_previous_tag(tags, "0.2.0") == "v0.1.0"


def test_none_for_first_release_with_no_tags(select_previous_tag) -> None:
    assert select_previous_tag([], "0.1.0") is None


def test_none_when_all_existing_tags_are_at_or_above_version(select_previous_tag) -> None:
    assert select_previous_tag(["v0.2.0"], "0.1.0") is None


def test_numeric_ordering_not_lexical(select_previous_tag) -> None:
    # Lexical comparison would put "v0.9.0" above "v0.10.0"; numeric
    # comparison of the MINOR component must not make that mistake.
    tags = ["v0.9.0", "v0.10.0"]
    assert select_previous_tag(tags, "0.11.0") == "v0.10.0"


def test_prerelease_sorts_below_its_own_release(select_previous_tag) -> None:
    tags = ["v1.0.0-rc.1", "v1.0.0"]
    assert select_previous_tag(tags, "2.0.0") == "v1.0.0"


def test_prerelease_ordering_between_two_prereleases(select_previous_tag) -> None:
    tags = ["v1.0.0-rc.1", "v1.0.0-rc.2"]
    assert select_previous_tag(tags, "1.0.0-rc.2") == "v1.0.0-rc.1"


def test_malformed_and_foreign_tags_are_ignored(select_previous_tag) -> None:
    tags = ["release/0.x", "v1.2", "nightly", "v0.1.0"]
    assert select_previous_tag(tags, "0.2.0") == "v0.1.0"


def test_malformed_tag_that_sorts_above_correct_answer_is_filtered(select_previous_tag) -> None:
    # "zzz-not-a-tag" is lexically greater than any "v..." tag, so a stub
    # that does `max(tags)` (or a sort) without first filtering to valid
    # `vMAJOR.MINOR.PATCH[-PRE]` tags would wrongly return the garbage
    # entry instead of the one real, well-formed predecessor.
    tags = ["zzz-not-a-tag", "v0.1.0"]
    assert select_previous_tag(tags, "0.2.0") == "v0.1.0"


def test_current_release_tag_itself_excluded_even_when_not_the_sort_max(
    select_previous_tag,
) -> None:
    # release.yml pushes the new tag before selecting a predecessor, so it
    # is present in the candidate list. Here the correct predecessor
    # ("v0.2.0") is not simply "drop the top of a plain sort" (which would
    # drop "v0.3.0", the version's own tag, and still return "v0.2.0" by
    # coincidence) -- so also check the tag equal to `version` is excluded
    # even when a different, non-adjacent tag would otherwise be the sort
    # max if it weren't filtered by strict `<`.
    tags = ["v0.1.0", "v0.2.0", "v0.3.0"]
    assert select_previous_tag(tags, "v0.3.0") == "v0.2.0"
    assert select_previous_tag(tags, "0.3.0") == "v0.2.0"


def test_numeric_ordering_across_double_digit_minor(select_previous_tag) -> None:
    # Lexical ("drop top of lexical sort") would rank
    # "v0.9.0" > "v0.11.0" > "v0.10.0" as strings, so lexical-max ==
    # "v0.9.0" and a naive "second from the lexical top" would misfire
    # too. Numeric comparison must yield "v0.11.0", the true predecessor
    # of "0.12.0".
    tags = ["v0.9.0", "v0.10.0", "v0.11.0"]
    assert select_previous_tag(tags, "0.12.0") == "v0.11.0"


def test_prerelease_dash_is_required_not_incidental(select_previous_tag) -> None:
    # Plain string comparison ranks "v1.0.0-rc.1" > "v1.0.0" (the "-" byte
    # sorts above the empty continuation), so a stub doing bare string
    # comparison instead of the semver "-" special case would treat the
    # rc as the greater/"current" tag, exclude it as the string-max, and
    # wrongly return the rc as the predecessor of "2.0.0" instead of the
    # actual release.
    tags = ["v1.0.0", "v1.0.0-rc.1"]
    assert select_previous_tag(tags, "2.0.0") == "v1.0.0"


def test_cli_prints_selected_tag_from_stdin() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "0.2.0"],
        input="v0.1.0\nv0.1.1\nv0.2.0\n",
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "v0.1.1"


def test_cli_prints_nothing_when_no_predecessor() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "0.1.0"],
        input="",
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_cli_reads_version_arg_not_hardcoded(select_previous_tag) -> None:
    # Run the CLI twice with the *same* stdin but two different version
    # args, expecting two different correct outputs -- a stub that
    # hard-codes its output (or ignores argv[1]) cannot pass both.
    stdin = "v0.1.0\nv0.1.1\nv0.2.0\n"
    result_a = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "0.1.1"],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    result_b = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "0.2.0"],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result_a.returncode == 0
    assert result_b.returncode == 0
    assert result_a.stdout.strip() == "v0.1.0"
    assert result_b.stdout.strip() == "v0.1.1"
    assert result_a.stdout.strip() != result_b.stdout.strip()
