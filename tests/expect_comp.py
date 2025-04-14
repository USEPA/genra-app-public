"""
expect_comp.py - compare expected JSON dumps using DeepDiff

Need python 3.6 compat, missing some options for subprocess.run()

Terry N. Brown Brown.TerryN@epa.gov Wed 19 May 2021 04:34:34 PM UTC
"""

import json
import sys
from pathlib import Path
from subprocess import PIPE, run

from deepdiff import DeepDiff

# the commit to compare against
compare_to = sys.argv[1] if len(sys.argv) > 1 else "dev"


# find JSON files that have changed
jsons = run(
    f"git diff --name-only {compare_to} | grep '.*expect.*json$'",
    stdout=PIPE,
    shell=True,
    encoding="utf8",
)
jsons = jsons.stdout.strip().split("\n")

# compare with current (working tree) versions, ignore pval
for path in jsons:
    old = run(f"git show {compare_to}:{path}", stdout=PIPE, shell=True, encoding="utf8")
    new = Path(path).read_text()
    old = json.loads(old.stdout)
    new = json.loads(new)
    print(f"\n\n{path}\n\n")
    diff = DeepDiff(
        old,
        new,
        ignore_order=True,
        exclude_regex_paths=[r"\['predClass'\]", r"\['(AUC)?pval'\]"],
    )
    print(diff.pretty())

print(f"\n\n# Copy / paste to view diffs\ngit diff {compare_to} -- {' '.join(jsons)}")
