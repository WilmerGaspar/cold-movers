"""Held-out evaluation of the catalogue-free mover search (pre-registered, nothing is tuned on it).

The neighbour-pull rule (movers.BLEND_PX and the choice of rule C) was chosen with the 3,300 trials of
scripts/benchmark_injection.py, so those trials cannot also measure it without bias. This script draws a
new, independent set of injections with its own seed, its own spots and random motions, and only reports.
Its design is fixed in evidence/HOLDOUT_PREREGISTRATION.md, committed before the first run.

Usage:
  python scripts/benchmark_holdout.py                                  # set A: the six frozen fields
  python scripts/benchmark_holdout.py --fields-dir DIR --label B       # set B: new fields (never used before)
Writes docs/benchmark_holdout_<label>.json and prints the tables.
"""

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from coldmovers import __version__, movers, pipeline, scoreboard, validation  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 20261115            # pre-registered; the development benchmark used 2026
SNRS = (5.0, 8.0, 15.0, 30.0)
RATE_RANGE = (2.0, 40.0)   # arcsec/yr, drawn log-uniformly
SPEED_BINS = ((2.0, 5.0), (5.0, 10.0), (10.0, 20.0), (20.0, 40.0))
SPOTS_PER_KIND = 4         # per field and per kind of spot
MOTIONS_PER_SPOT = 6
CROWD_RADIUS_PX, CROWD_MIN = 7.0, 3   # "crowded spot": at least 3 sources within 7 px


def wilson(k, n, z=1.96):
    """95 % Wilson score interval for a proportion k/n."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def first_visit_sources(stacks, epochs, snr=6.0):
    """Sources of the first visit in every detector, merged when closer than 1.5 px."""
    first = min(epochs, key=lambda ep: ep["mjd_mid"])
    pts = [s[:2] for d, im in stacks[first["index"]].items() if d != 0 for s in movers.detect(im, snr=snr)]
    merged = []
    for x, y in pts:
        if all(math.hypot(x - a, y - b) > 1.5 for a, b in merged):
            merged.append((x, y))
    shape = next(im for d, im in stacks[first["index"]].items() if d != 0).shape
    return merged, shape


def crowded_spots(stacks, epochs, rng, n, margin=7.0):
    """Random positions with at least CROWD_MIN sources within CROWD_RADIUS_PX, and none closer than 2.5 px."""
    sources, shape = first_visit_sources(stacks, epochs)
    spots, tries = [], 0
    while sources and len(spots) < n and tries < 5000:
        tries += 1
        x, y = rng.uniform(margin, shape[1] - 1 - margin), rng.uniform(margin, shape[0] - 1 - margin)
        d = [math.hypot(x - a, y - b) for a, b in sources]
        if sum(v <= CROWD_RADIUS_PX for v in d) >= CROWD_MIN and min(d) >= 2.5:
            spots.append((x, y))
    return spots


def speed_bin(rate):
    for lo, hi in SPEED_BINS:
        if lo <= rate < hi or (hi == RATE_RANGE[1] and rate == hi):
            return f"{lo:g}-{hi:g}"
    return "other"


def summarize(trials):
    s = scoreboard.summarize_trials(trials)
    tp, n, fp = s["confirmed"], s["n"], s["false_confirmed"]
    distinct = {(t["field"], round(x), round(y)) for t in trials for (x, y) in t.get("false_positions", [])}
    s.update(false_negatives=n - tp, distinct_false_sources=len(distinct),
             recall_ci95=wilson(tp, n), precision_ci95=wilson(tp, tp + fp) if tp + fp else (float("nan"),) * 2)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields-dir", default=os.path.join(ROOT, "data", "precomputed"))
    ap.add_argument("--label", default="A")
    ap.add_argument("--out", default=None)
    ap.add_argument("--smoke", action="store_true", help="tiny run with another seed, only to check the code runs")
    args = ap.parse_args()
    global SEED, SPOTS_PER_KIND, MOTIONS_PER_SPOT
    if args.smoke:
        SEED, SPOTS_PER_KIND, MOTIONS_PER_SPOT = 1, 1, 1
    rng = np.random.default_rng(SEED)
    trials, fields, t0 = [], {}, time.time()
    for key in sorted(os.listdir(args.fields_dir)):
        outdir = os.path.join(args.fields_dir, key)
        view = pipeline.load(outdir) if os.path.isdir(outdir) else None
        if not view:
            continue
        epochs, stacks = view["epochs"], validation.load_stacks(outdir)
        if len(epochs) < 2 or not stacks:
            fields[key] = {"skipped": f"{len(epochs)} visit(s)"}
            continue
        base = movers.search_all(epochs, stacks)
        baseline = [c for c in base["candidates"] if c["confirmed"]]
        sources, shape = first_visit_sources(stacks, epochs)
        fields[key] = {"visits": len(epochs), "reliable_detectors": sum(x["reliable"] for x in base["per_detector"].values()),
                       "baseline_confirmed": len(baseline), "sources_6sigma": len(sources),
                       "source_density_per_1000px2": round(1000 * len(sources) / (shape[0] * shape[1]), 2)}
        kinds = {"quiet": scoreboard._quiet_spots(stacks, epochs, rng, SPOTS_PER_KIND),
                 "near a star": scoreboard._spots_near_sources(stacks, epochs, rng, SPOTS_PER_KIND),
                 "crowded": crowded_spots(stacks, epochs, rng, SPOTS_PER_KIND)}
        fields[key]["spots"] = {k: len(v) for k, v in kinds.items()}
        for kind, spots in kinds.items():
            for (x0, y0) in spots:
                for _ in range(MOTIONS_PER_SPOT):
                    rate = float(math.exp(rng.uniform(math.log(RATE_RANGE[0]), math.log(RATE_RANGE[1]))))
                    pa = float(rng.uniform(0.0, 360.0))
                    common = dict(field=key, place=kind, rate=round(rate, 3), pa=round(pa, 2), speed_bin=speed_bin(rate))
                    for snr in SNRS:
                        r = scoreboard.blind_trial(epochs, stacks, baseline, x0, y0, rate, pa, snr)
                        trials.append(dict(r, snr=snr, set="all six", **common))
                    r = scoreboard.blind_trial(epochs, stacks, baseline, x0, y0, rate, pa, 15.0, detectors=(5, 6))
                    trials.append(dict(r, snr=15.0, set="D5+D6 only", **common))

    def group(keyfn, sel):
        g = defaultdict(list)
        for t in trials:
            if sel(t):
                g[keyfn(t)].append(t)
        return {str(k): summarize(v) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}

    six = lambda t: t["set"] == "all six"  # noqa: E731
    core = lambda t: six(t) and 5.0 <= t["rate"] < 20.0  # noqa: E731
    out = {
        "label": args.label, "app_version": __version__, "seed": SEED, "trials": len(trials),
        "seconds": round(time.time() - t0, 1), "fields_dir": os.path.relpath(args.fields_dir, ROOT),
        "design": {"snr": SNRS, "rate_range_arcsec_yr": RATE_RANGE, "rate_draw": "log-uniform",
                   "pa_draw": "uniform 0-360", "spots_per_kind_per_field": SPOTS_PER_KIND,
                   "motions_per_spot": MOTIONS_PER_SPOT, "match_px": scoreboard.MATCH_PX,
                   "crowded_spot": f">= {CROWD_MIN} sources within {CROWD_RADIUS_PX} px, none closer than 2.5 px",
                   "preregistration": "evidence/HOLDOUT_PREREGISTRATION.md"},
        "fields": fields,
        "headline_snr15_core": summarize([t for t in trials if core(t) and t["snr"] == 15.0]),
        "by_snr_core": group(lambda t: t["snr"], core),
        "by_snr_all_speeds": group(lambda t: t["snr"], six),
        "by_speed_snr15": group(lambda t: t["speed_bin"], lambda t: six(t) and t["snr"] == 15.0),
        "by_place_snr15_core": group(lambda t: t["place"], lambda t: core(t) and t["snr"] == 15.0),
        "by_place_snr30_core": group(lambda t: t["place"], lambda t: core(t) and t["snr"] == 30.0),
        "by_field_snr15_core": group(lambda t: t["field"], lambda t: core(t) and t["snr"] == 15.0),
        "red_D5D6_snr15_core": summarize([t for t in trials if t["set"] == "D5+D6 only" and 5.0 <= t["rate"] < 20.0]),
        "red_by_field": group(lambda t: t["field"], lambda t: t["set"] == "D5+D6 only" and 5.0 <= t["rate"] < 20.0),
    }
    path = args.out or os.path.join(ROOT, "docs", f"benchmark_holdout_{args.label}.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: out[k] for k in ("label", "trials", "seconds", "fields")}, indent=1))
    for sec in ("headline_snr15_core", "by_snr_core", "by_snr_all_speeds", "by_speed_snr15", "by_place_snr15_core",
                "by_place_snr30_core", "by_field_snr15_core", "red_D5D6_snr15_core", "red_by_field"):
        block = out[sec] if "n" not in out[sec] else {"all": out[sec]}
        print("==", sec)
        for k, s in block.items():
            print(f"  {k:12s} n={s['n']:4d} TP={s['confirmed']:4d} FN={s['false_negatives']:4d} FP={s['false_confirmed']:3d} "
                  f"(distinct {s['distinct_false_sources']}) recall={s['recall']:.2f} "
                  f"[{s['recall_ci95'][0]:.2f}-{s['recall_ci95'][1]:.2f}] precision={s['precision']:.3f} "
                  f"[{s['precision_ci95'][0]:.2f}-{s['precision_ci95'][1]:.2f}] f1={s['f1']:.2f} "
                  f"rate_err_med={s['rate_err_median']:.3f}")


if __name__ == "__main__":
    main()
