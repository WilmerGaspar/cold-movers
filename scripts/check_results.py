"""Check that the five precomputed results exist, are valid JSON and can be opened.

Exit code 1 if anything is missing or broken, so GitHub Actions marks the run red.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coldmovers import pipeline  # noqa: E402
from coldmovers.targets import ALL_EXAMPLES, SHOWCASE  # noqa: E402

SHOWCASE_KEYS = set(SHOWCASE)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "precomputed")


def reject_nan(value):
    raise ValueError(f"invalid JSON constant {value}")


problems = []
for key in ALL_EXAMPLES:
    d = os.path.join(OUT, key)
    if key not in SHOWCASE_KEYS and not os.path.exists(d):
        continue  # extras are optional until reviewed
    try:
        with open(os.path.join(d, "result.json")) as fh:
            summary = json.load(fh, parse_constant=reject_nan)
        view = pipeline.load(d)
        if not view["rows"]:
            problems.append(f"{key}: no photometry rows")
        for det, name in summary.get("gifs", {}).items():
            if not os.path.getsize(os.path.join(d, name)):
                problems.append(f"{key}: empty movie for detector {det}")
        if not summary.get("gifs"):
            problems.append(f"{key}: no movies")
        if not os.path.exists(os.path.join(d, "stacks.npz")):
            problems.append(f"{key}: no epoch stacks")
        print(f"{key}: OK ({summary['n_used']} images, {len(summary['epochs'])} visits)")
    except Exception as exc:
        problems.append(f"{key}: {exc}")

if problems:
    print("RESULTS CHECK FAILED")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("RESULTS CHECK PASSED")
