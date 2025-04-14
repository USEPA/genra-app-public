"""Test no increase in lint warnings codebase wise.

Two tests.

1) test_clean_total creates / updates .ruff.test.best and
.ruff.test.current and fails if current has more lines than best.

The failing assert message gives two example commands that may help isolate
current changes responsible for the increase.

The test will pass if the number of warnings eliminated is equal to or greater
than the number added, so it's not a substitute for linting code, just a way of
driving the number of warnings in the codebase down over time.

This test needs to be run on the dev branch to get a "best" file the will
match what PR reviewers will see.

2) test_clean_dev - just runs ruff on changes vs. dev
"""

import io
import logging
import subprocess
from collections import defaultdict, namedtuple
from pathlib import Path

import pytest
from unidiff import PatchSet

logger = logging.getLogger("genra_top")

RUFF = (
    "/usr/local/bin/ruff" if Path("/usr/local/bin/ruff").exists() else "/usr/bin/ruff"
)

# used by test_clean_total(), BUT NOT test_clean_dev()
RUFF_CMD = (
    f"{RUFF} check "
    "--extend-exclude=venv_genra_app,genra_ni --exit-zero "
    "--line-length=88 --output-file={out_path}"
)


@pytest.mark.no_smoke  # Checks total relative to best seen, not relevant in automation.
def test_clean_total() -> None:
    """Test no increase in lint warnings codebase wise"""
    # path for current warnings (to be created)
    current_path = Path.cwd() / ".ruff.test.current"
    current_path.unlink(missing_ok=True)
    subprocess.run(
        RUFF_CMD.format(out_path=current_path).split(),  # noqa: S603 checked 2024-1-31
        check=True,
        env={"HOME": "/genra"},
    )
    current = current_path.read_text()
    current_n = len(current.split("\n"))

    # path to best recorded warnings
    best_path = Path.cwd() / ".ruff.test.best"
    if not best_path.exists():
        best_path.write_text(current)
        pytest.skip("No reference file for ruff")
    best_n = len(best_path.read_text().split("\n"))
    assert current_n <= best_n, (
        f"\nIncrease in lint warnings, {best_n} -> {current_n}\n"
        f"Try diff .ruff.test.best .ruff.test.current\n"
        "or\n"
        r"git diff --name-status dev | sed 's/\S*\s*//' | "
        "xargs -IF grep F .ruff.test.current"
    )

    # if count dropped, save shorter file
    if current_n < best_n:
        best_path.write_text(current)


@pytest.mark.no_smoke  # FIXME re-enable when ruff tests cleaned up.
def test_clean_dev() -> None:
    """Test changes in diff vs. dev.

    flake8 used to support `git diff ... | flake8 --diff ...
    but dropped that so do it ourselves
    """
    # Run git diff and parse output with unidiff.
    base = Path("/genra")
    git_cmd = ["/usr/bin/git", "diff", "-p", "-U0", "--no-prefix", "dev"]
    git = subprocess.run(
        git_cmd,  # noqa: S603 nosec checked 2024-1-31
        check=True,
        stdout=subprocess.PIPE,
    )
    patches = PatchSet(io.BytesIO(git.stdout), encoding="utf8")
    # Build set of changed lines for each changed file.
    patch = defaultdict(set)
    for patched in patches:
        if not patched.target_file.endswith(".py"):
            continue
        for hunk in patched:
            patch[base / patched.target_file].update(
                range(hunk.target_start, hunk.target_start + hunk.target_length)
            )
    # Build ruff cmd for target folders
    folders = "genraweb", "tests", "misc"
    cmd = [RUFF, "check", "--exit-zero"] + [
        str(base / folder) for folder in folders
    ]
    ruff = subprocess.run(
        cmd,  # noqa: S603 nosec checked 2024-1-31
        stdout=subprocess.PIPE,
        env={"NO_COLOR": "1"},
        check=True,
    )
    # Show complaints for changed lines only.
    complaints = 0
    Line = namedtuple("Line", "path line column complaint")
    for line in (
        Line._make(parts)
        for j in ruff.stdout.decode("utf8").split("\n")
        if len(parts := j.split(":", len(Line._fields) - 1)) == len(Line._fields)
    ):
        path = base / line.path
        if int(line.line) in patch[path]:
            print(f"{line.path}:{line.line}:{line.column}:{line.complaint}")
            complaints += 1
    assert complaints == 0
