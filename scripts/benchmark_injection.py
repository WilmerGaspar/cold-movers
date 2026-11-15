"""Blind injection benchmark: recall, precision, F1, false positives and errors, by condition.

Fake moving point sources are added to the frozen SPHEREx visit stacks one at a time and the
catalogue-free search (movers.search_all) runs without knowing where or how they move. Matching
is done afterwards. Conditions: S/N, speed, quiet spots vs spots 2.5-4 px from a star, all six
detectors vs only the two longest-wavelength ones, every frozen field (reliable or not).
Writes docs/benchmark_injection.json. Usage: python scripts/benchmark_injection.py [--quick]
"""

import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from coldmovers import __version__, movers, pipeline, scoreboard, validation  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE = os.path.join(ROOT, "data", "precomputed")
QUICK = "--quick" in sys.argv
SNRS = (5.0, 8.0, 15.0, 30.0)
RATES = (2.0, 5.0, 10.0, 20.0, 40.0)
PAS = (30.0, 120.0, 210.0, 300.0)
SPOTS = 1 if QUICK else 3

rng = np.random.default_rng(2026)
trials = []
fields = {}
t_start = time.time()
for key in sorted(os.listdir(PRE)):
    outdir = os.path.join(PRE, key)
    view = pipeline.load(outdir) if os.path.isdir(outdir) else None
    if not view:
        continue
    epochs, stacks = view["epochs"], validation.load_stacks(outdir)
    base = movers.search_all(epochs, stacks)
    baseline = [c for c in base["candidates"] if c["confirmed"]]
    n_rel = sum(x["reliable"] for x in base["per_detector"].values())
    fields[key] = {"reliable_detectors": n_rel, "baseline_confirmed": len(baseline),
                   "visits": len(epochs)}
    places = {"quiet": scoreboard._quiet_spots(stacks, epochs, rng, SPOTS),
              "near a star": scoreboard._spots_near_sources(stacks, epochs, rng, SPOTS)}
    for place, spots in places.items():
        for (x0, y0) in spots:
            for rate in RATES:
                for pa in PAS:
                    for snr in SNRS:
                        r = scoreboard.blind_trial(epochs, stacks, baseline, x0, y0, rate, pa, snr)
                        trials.append(dict(r, field=key, place=place, rate=rate, snr=snr, set="all six"))
                    r = scoreboard.blind_trial(epochs, stacks, baseline, x0, y0, rate, pa, 15.0, detectors=(5, 6))
                    trials.append(dict(r, field=key, place=place, rate=rate, snr=15.0, set="D5+D6 only"))


def group(keyfn, sel=lambda t: True):
    g = defaultdict(list)
    for t in trials:
        if sel(t):
            g[keyfn(t)].append(t)
    return {str(k): scoreboard.summarize_trials(v) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}


core = lambda t: t["set"] == "all six" and t["rate"] in (5.0, 10.0, 20.0)  # noqa: E731
out = {
    "app_version": __version__, "trials": len(trials), "seconds": round(time.time() - t_start, 1),
    "design": {"snr": SNRS, "rates_arcsec_yr": RATES, "pa_deg": PAS, "spots_per_place_per_field": SPOTS,
               "match_px": scoreboard.MATCH_PX, "psf_sigma_px": movers.PSF_SIGMA_PX,
               "note": "One fake mover per trial, Gaussian PSF, same S/N in every detector used; the search is "
                       "blind and matching is done afterwards; false positives are confirmed movers that are "
                       "neither the injection nor present before injecting."},
    "fields": fields,
    "by_snr_core": group(lambda t: t["snr"], core),
    "by_snr_core_quiet": group(lambda t: t["snr"], lambda t: core(t) and t["place"] == "quiet"),
    "by_snr_core_near_star": group(lambda t: t["snr"], lambda t: core(t) and t["place"] == "near a star"),
    "by_rate_snr15": group(lambda t: t["rate"], lambda t: t["set"] == "all six" and t["snr"] == 15.0),
    "by_field_snr15_core": group(lambda t: t["field"], lambda t: core(t) and t["snr"] == 15.0),
    "red_by_field": group(lambda t: t["field"], lambda t: t["set"] == "D5+D6 only" and t["rate"] in (5.0, 10.0, 20.0)),
    "red_all": group(lambda t: "all", lambda t: t["set"] == "D5+D6 only" and t["rate"] in (5.0, 10.0, 20.0)),
}
os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
if "--per-trial" in sys.argv:  # every trial as JSON lines, for scripts/calibration.py
    with open(sys.argv[sys.argv.index("--per-trial") + 1], "w") as fh:
        for t in trials:
            fh.write(json.dumps(t) + "\n")
name = "benchmark_injection_quick.json" if QUICK else "benchmark_injection.json"
with open(os.path.join(ROOT, "docs", name), "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps({k: out[k] for k in ("trials", "seconds", "fields")}, indent=1))
for sec in ("by_snr_core", "by_snr_core_quiet", "by_snr_core_near_star", "by_rate_snr15", "by_field_snr15_core",
            "red_by_field", "red_all"):
    print("==", sec)
    for k, s in out[sec].items():
        print(f"  {k:12s} n={s['n']:4d} conf={s['confirmed']:4d} cand={s['candidate_only']:3d} fp={s['false_confirmed']:3d} "
              f"recall={s['recall']:.2f} precision={s['precision']:.3f} f1={s['f1']:.2f} "
              f"rate_err_med={s['rate_err_median']:.3f} p84={s['rate_err_p84']:.3f} pa_med={s['pa_err_median']:.1f}")
