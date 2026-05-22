"""Tests for the tiny .env loader."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from lib_python_config.env import load_env_file


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets a fresh process env — nothing leaks between cases."""
    # Don't blanket-clear (would nuke PATH etc); just guarantee our test keys
    # aren't pre-set. Individual tests can monkeypatch as needed.
    for k in [
        "TEST_BASIC",
        "TEST_DQUOTE",
        "TEST_SQUOTE",
        "TEST_BOM",
        "TEST_EQUALS",
        "TEST_EXISTING",
        "TEST_EMPTY",
    ]:
        monkeypatch.delenv(k, raising=False)


def test_load_env_file_parses_basic_key_value(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("TEST_BASIC=hello\n", encoding="utf-8")

    load_env_file(f)

    assert os.environ["TEST_BASIC"] == "hello"


def test_load_env_file_strips_double_quotes(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text('TEST_DQUOTE="hello world"\n', encoding="utf-8")

    load_env_file(f)

    assert os.environ["TEST_DQUOTE"] == "hello world"


def test_load_env_file_strips_single_quotes(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("TEST_SQUOTE='hi there'\n", encoding="utf-8")

    load_env_file(f)

    assert os.environ["TEST_SQUOTE"] == "hi there"


def test_load_env_file_ignores_comments_and_blanks(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text(
        "# leading comment\n"
        "\n"
        "TEST_BASIC=ok\n"
        "   # indented comment after strip\n",
        encoding="utf-8",
    )

    load_env_file(f)

    assert os.environ["TEST_BASIC"] == "ok"


def test_load_env_file_handles_bom(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_bytes(b"\xef\xbb\xbfTEST_BOM=present\n")

    load_env_file(f)

    assert os.environ["TEST_BOM"] == "present"


def test_load_env_file_splits_only_on_first_equals(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("TEST_EQUALS=key=value=more\n", encoding="utf-8")

    load_env_file(f)

    assert os.environ["TEST_EQUALS"] == "key=value=more"


def test_load_env_file_does_not_overwrite_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_EXISTING", "original")
    f = tmp_path / ".env"
    f.write_text("TEST_EXISTING=overridden\n", encoding="utf-8")

    load_env_file(f)

    assert os.environ["TEST_EXISTING"] == "original"


def test_load_env_file_silent_on_missing_file(tmp_path: Path) -> None:
    # Should NOT raise — `.env` files are best-effort.
    load_env_file(tmp_path / "missing.env")


def test_load_env_file_skips_malformed_lines(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text(
        "this line has no equals\n"
        "TEST_BASIC=ok\n",
        encoding="utf-8",
    )

    load_env_file(f)

    assert os.environ["TEST_BASIC"] == "ok"
