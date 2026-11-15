"""Download the pre-registered held-out fields (set B) from IRSA and save them like the frozen fields.

These four positions were never used to develop or tune Cold Movers (see evidence/HOLDOUT_PREREGISTRATION.md).
They are chosen by a rule, not by looking at the data: the two ecliptic poles (where SPHEREx returns most
often), a field in the Galactic plane (crowded) and one at high Galactic latitude (sparse).
Runs on GitHub Actions; the output goes to a scratch folder, not to the repository.

Usage: python scripts/fetch_holdout_fields.py OUTDIR [--max-frames 240]
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coldmovers import pipeline  # noqa: E402
from coldmovers.targets import Target  # noqa: E402

FIELDS = (
    ("nep", "North ecliptic pole", 270.0000, 66.5607),
    ("sep", "South ecliptic pole", 90.0000, -66.5607),
    ("gal_l30_b0", "Galactic plane, l = 30°, b = 0°", 281.5216, -2.6091),
    ("gal_l90_b45", "High latitude, l = 90°, b = +45°", 239.8415, 58.2798),
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--max-frames", type=int, default=240)
    ap.add_argument("--budget-s", type=float, default=900.0)
    args = ap.parse_args()
    for key, name, ra, dec in FIELDS:
        t0 = time.time()
        target = Target(key=key, name=name, ra_deg=ra, dec_deg=dec, ref_epoch=2016.0, source="held-out field")
        try:
            result = pipeline.run(target, max_frames=args.max_frames, time_budget_s=args.budget_s)
            pipeline.save(result, os.path.join(args.outdir, key))
            print(f"{key}: {len(result.rows)} images, {len(result.epochs)} visits, "
                  f"{len(result.failures)} failed downloads, {time.time() - t0:.0f} s", flush=True)
        except Exception as exc:  # report and continue: a field that cannot be fetched is reported as missing
            print(f"{key}: FAILED ({type(exc).__name__}: {exc})", flush=True)


if __name__ == "__main__":
    main()
