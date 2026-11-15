# Pre-registration of the held-out evaluation

Written and committed **before** the held-out evaluation was run for the first time (Nov 15, 2026). The commit
that adds this file freezes the code that will be evaluated. No parameter of the search may be changed after
seeing these results. If a change is made later, it must be evaluated on a new, independent set, and the
results of this one stay published.

## Why a held-out set is needed

Which parameters of the catalogue-free search were set with which data (from `git log`, Honduras time):

| Parameter | Value | Set in | Set with |
|---|---|---|---|
| `DETECT_SNR`, `MATCH_RADIUS_PX`, `EDGE_PX`, `MIN_SIGNIFICANCE`, `CANDIDATE_SIGNIFICANCE`, `MIN_SHIFT_PX`, `SYS_ALIGN_PX`, `PSF_SIGMA_PX`, `MAX_FIELD_MEDIAN_SHIFT_PX`, `MAX_FIT_RMS_PX` | 6, 4 px, 3 px, 5, 3, 0.5 px, 0.12 px, 0.9 px, 0.5 px, 0.6 px | v0.4.0 (`dc24604`, Nov 14 19:49), unchanged since | Development on the six challenge fields, before any injection test |
| Grouping across detectors (1.5 px, 1 px/yr) | | v0.4.0, unchanged | Same |
| `BLEND_PX` and the neighbour-pull rule (rule C) | 4 px | v0.5.0 (`a46e42b`, Nov 15 13:15) | **The same 3,300 trials** (seed 2026) whose metrics are reported in `evidence/BENCHMARK_RESULTS.md` |

So the 3,300-trial metrics after the fix are optimistic for the neighbour-pull rule: the rule was chosen
among three on those trials. In addition, all parameters were set while developing on the same six fields.
The held-out evaluation measures both effects separately.

## Set A: same six fields, new injections

* Fields: the six frozen fields in `data/precomputed/` (the sky is not new; the injections are).
* Random seed **20261115** (the development benchmark used 2026), drawn with NumPy's `default_rng`.
* Spots per field: 4 **quiet** (at least 5 px from any 4σ source), 4 **near a star** (2.5–4 px from a 6σ
  source), 4 **crowded** (at least 3 sources within 7 px, none closer than 2.5 px). Fewer when a field has no
  such place.
* Motions: 6 per spot, speed drawn log-uniformly in 2–40″/yr, direction uniformly in 0–360°. The development
  set used fixed speeds (2, 5, 10, 20, 40″/yr) and fixed directions (30°, 120°, 210°, 300°).
* Brightness: each motion at S/N 5, 8, 15 and 30 (peak height over the image noise), in all six detectors; plus
  once at S/N 15 in detectors 5 and 6 only (very red movers).
* Code: `scripts/benchmark_holdout.py --label A`, output `docs/benchmark_holdout_A.json`.

## Set B: new SPHEREx fields never used before

* Four positions chosen by a rule, without looking at the data: the north ecliptic pole (RA 270.0000°,
  Dec +66.5607°), the south ecliptic pole (90.0000°, −66.5607°), the Galactic plane at l = 30°, b = 0°
  (281.5216°, −2.6091°, crowded) and high Galactic latitude at l = 90°, b = +45° (239.8415°, +58.2798°).
* Downloaded from IRSA (SPHEREx DR1 + QR3) by `scripts/fetch_holdout_fields.py` on GitHub Actions, up to 240
  images each. Processed with the same pipeline as the frozen fields.
* Same injection design as set A, the same seed, `--label B`.
* If a field cannot be downloaded, or has fewer than two visits, it is reported as missing, not replaced.

Before this commit, the script was run once with another seed (1) and one spot and one motion per kind
(`--smoke`, 85 trials), only to check that it runs; its output was discarded without reading the metrics.

## Metrics (defined before the run)

Per injection: **true positive** = the search confirms a mover within 1.5 px of the injected position at that
detector's first visit; **false negative** = not confirmed (whether missed or only a candidate; candidates are
counted separately). Per trial: **false positive** = a confirmed mover that is neither the injection nor a mover
already confirmed before injecting. Also counted: **distinct false sources**, the same spurious source counted
once per field. Recall = TP / injections; precision = TP / (TP + FP); F1. 95 % Wilson intervals for recall and
precision. The median speed error and direction error are taken over the true positives.

Reported by S/N (brightness), by speed (2–5, 5–10, 10–20, 20–40″/yr), by environment (quiet, near a star,
crowded), by field, and for very red movers (D5 + D6 only). The headline is S/N 15, all six detectors, speeds
5–20″/yr, the same headline condition as the development benchmark.

## How the results will be read (fixed now)

* **Overfitting of the neighbour-pull choice.** Compare set A's headline precision with the development value
  (0.981). It is consistent if the development value lies inside set A's 95 % interval.
* **Overfitting to the six fields.** Compare set B with set A, condition by condition, using the intervals.
* Every number is published, whatever it is. No claim is made that the search finds every moving object.
