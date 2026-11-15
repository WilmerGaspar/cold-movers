# Blind injection benchmark

## Question

Does the catalogue-free search find moving sources it was never told about, and how often does it report
a mover that is not there?

## Method

* **Data:** the frozen SPHEREx DR1 + QR3 visit stacks of all six objects (`data/precomputed/*/stacks.npz`),
  i.e. real backgrounds, real noise, real stars, real alignment between visits.
* **Injection:** one fake moving point source per trial (Gaussian PSF, σ = 0.9 px), added to copies of the
  stacks at its position on each visit date. Same S/N in every detector used.
* **Blindness:** `movers.search_all` receives only the images. The injected position and motion are used
  *afterwards*, to match its output (within 1.5 px of where the fake mover was at that detector's first visit).
* **Controls:** before injecting, the search runs on each field; movers already confirmed there (the real
  targets) are excluded from the false-positive count. A confirmed mover that is neither the injection nor
  one of those is a false positive of that trial.
* **Conditions:** S/N 5, 8, 15, 30; speeds 2, 5, 10, 20, 40″/yr; directions 30°, 120°, 210°, 300°; quiet spots
  (≥5 px from any source) and spots 2.5-4 px from a star; all six detectors, or only D5 and D6 (very red);
  three spots of each kind per field where possible. 3,300 trials in all, random seed 2026.
* **Metrics:** recall = confirmed injections / injections; precision = confirmed injections / (confirmed
  injections + false confirmations); F1; median absolute relative speed error; median direction error.

Reproduce: `python scripts/benchmark_injection.py` (about 2 minutes), then `python scripts/benchmark_report.py`.
Results: `docs/benchmark_injection.json` (after) and `docs/benchmark_injection_before.json` (before);
full tables in `BENCHMARK_TABLES.md`.

## Main result: the neighbour-pull fix

The benchmark found that a mover passing 2-4 px from a still star makes the star look like a confirmed mover
(diagnosed trial by trial: every false confirmation sat 0.1-0.8 px from a star, 2-4 px from the fake mover's
track). The fix keeps the less significant of two movers that come within 4 px of each other as a candidate.
Three versions were compared on the same 3,300 trials:

| S/N 15, all fields and spots, 5-20″/yr (n = 396) | False confirmations | Precision | Recall | F1 |
|---|---|---|---|---|
| Before (v0.4.9) | 24 | 0.872 | 0.41 | 0.56 |
| Rule A: "no confirmation within 4 px of any source" | 0 | 1.000 | 0.20 | 0.34 |
| Rule B: "the slower of two crossing movers is a candidate" | 3 | 0.980 | 0.36 | 0.53 |
| **Rule C, adopted: "the less significant of two crossing movers is a candidate"** | **3** | **0.981** | **0.39** | **0.55** |

Rule A was rejected (it halves recall); rule C keeps nearly all of F1 and removes 88 % of false confirmations.
At S/N 8 the false confirmations fall from 21 to 1 (precision 0.846 → 0.991). The real objects' results do not
change.

## What the benchmark says about the search (after the fix)

| Condition | Recall | Precision | Notes |
|---|---|---|---|
| Quiet spots, S/N 15, 5-20″/yr (n = 180) | 0.58 | 1.000 | median speed error 5.1 % |
| Quiet spots, S/N 30 (n = 180) | 0.61 | 1.000 | median speed error 2.9 % |
| Near a star, S/N 15 (n = 216) | 0.22 | 0.941 | crowding is the main weakness |
| S/N 5, any spot (n = 396) | 0.00 | — | below the 6σ detection threshold, by design; 9 false confirmations near stars remain |
| 2″/yr, S/N 15 (n = 132) | 0.04 | — | shifts < 0.5 px in a year: out of range, by design |
| 40″/yr, S/N 15 (n = 132) | 0.26 | 0.895 | visit-to-visit match radius limits fast movers |
| Very red (D5 + D6 only), S/N 15 (n = 396) | 0.16 | 1.000 | works in the TRAPPIST-1 field, fails in sparse fields |

Recall over *all* six fields is lower than the scoreboard's 88 % because two fields (Barnard's Star, R Draconis)
are dominated by saturated halos: their detectors are not trusted and the search reports nothing there, which is
the intended behaviour (no confirmations rather than wrong ones). The scoreboard keeps its original, stated
conditions (quiet spots, fields where at least four detectors line up).

## Limits of this benchmark

* Fake movers are Gaussians with the same S/N in every detector: real sources have colours and SPHEREx's PSF varies.
* The S/N is the injected peak over the image noise, not a photometric S/N.
* Spots "near a star" are 2.5-4 px from sources detected at 6σ; fainter neighbours are not controlled.
* The fields are small (about 30-45 px across), so a fast mover often passes near other sources anyway.
* Computed in this environment with the repository code; `scripts/benchmark_injection.py` reproduces it exactly
  (fixed seed). It was not used to tune anything except the choice between rules A, B and C reported above.
