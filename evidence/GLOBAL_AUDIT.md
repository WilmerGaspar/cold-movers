# Global audit of Cold Movers

Audit made on the branch `global-scientific-upgrade`, started from `main` at commit `ef5d02a`
(app version 0.4.9, the version deployed at https://cold-movers.streamlit.app). That commit is
the recovery point: nothing on `main` was changed by this audit.

## 1. Architecture

| Part | File | Role |
|---|---|---|
| Data access | `coldmovers/spherex.py` | SPHEREx DR1 + QR3 image search at NASA/IPAC IRSA (SIA2, TAP fallback), cutouts, retries, cache |
| Targets | `coldmovers/targets.py` | Positions and proper motions (SIMBAD/Sesame, Gaia DR3), coordinate parsing, linear motion propagation |
| Photometry | `coldmovers/photometry.py` | Aperture photometry (2.5 px aperture, 5-9 px sky ring), quality flags, saturated-star wings |
| Movie | `coldmovers/movie.py` | TAN reference grid (north up, east left), bilinear reprojection, visit stacks per detector, frames, difference and sum views, overlays |
| Checks | `coldmovers/checks.py` | Centroids, "Is it real?" checks, blend detection, best detector |
| Blind search | `coldmovers/movers.py` | Catalogue-free mover search per detector, cross-detector confirmation, neighbour-pull rule |
| Temperature | `coldmovers/madhava.py` | Band-integrated Planck series with Madhava's correction and a guaranteed truncation bound, fit, traffic light |
| Brightness | `coldmovers/variability.py` | Visit-to-visit change after removing the spectral shape |
| Explanations | `coldmovers/assistant.py` | Plain-language sentences, overlay layers, trajectory fit |
| Validation | `coldmovers/validation.py`, `coldmovers/scoreboard.py` | Validation table, scoreboard rules, injection campaign and blind benchmark |
| App | `app.py` | Streamlit interface |
| Automation | `scripts/`, `.github/workflows/` | Precompute, smoke test of the whole app, scoreboard, validation records, screenshots, benchmark |

## 2. Functionality verified, and how

| Function | Verified by |
|---|---|
| App starts and renders every section for all six frozen objects | `scripts/smoke_app.py` on GitHub Actions (headless Streamlit, pinned libraries) on every push to `main` |
| The challenge's own coordinate formats parse to the right position | `scripts/smoke_app.py` (six formats of WISE 0855) |
| Live public app shows the expected version, sections and panels | `scripts/screenshots.py` (Playwright against the public URL) |
| Series, fit, photometry, checks, variability, movers, assistant, scoreboard rules | 87 unit tests (`pytest tests`) |
| Numbers quoted in the README equal the app's | `scripts/validation_report.py` and `scripts/scoreboard.py` run the app's code on GitHub Actions |

## 3. Test results

* Baseline (commit `ef5d02a`): 86 unit tests passed.
* After this audit's change: 87 passed (one new test for the neighbour-pull rule).
* Real-object results before and after the change: identical (Barnard's Star and Epsilon Indi B confirmed by
  the blind search in 2 and 5 detectors, WISE 0855 a candidate, no mover at R Dra, RW Aur or TRAPPIST-1, no other
  confirmed mover in any of the six fields).

## 4. Errors found

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | **Blend-induced false movers.** A moving source passing 2-4 px from a still star pulls the star's centroid, and the star is reported as a *confirmed* mover. Found with the new blind benchmark (24 false confirmations in 396 trials at S/N 15, precision 0.87). | Critical (false detections) | **Fixed** with the neighbour-pull rule: 3 false confirmations, precision 0.98, recall 0.41 → 0.39. See `BENCHMARK_RESULTS.md`. |
| 2 | **The scoreboard's injection test was conditional.** It injected only at quiet spots, speeds 5-20″/yr, in fields where at least four detectors line up (4 of 6 fields). Its 92 % recall is true under those conditions only. | High (overstated generality) | **Documented**; the new benchmark covers all six fields, spots next to stars, 2-40″/yr and S/N 5-30. |
| 3 | **Faint movers below the detection threshold can still pull a star** (S/N 5 near a star: 9 false confirmations in 216 trials after the fix; the rule cannot act because the faint mover itself is never detected). | Medium | **Open, documented.** |
| 4 | **Very red movers** seen only by D5 and D6 are confirmed in 16 % of all trials (28 % in the scoreboard's fields): sparse long-wavelength fields make the alignment rule distrust a detector. | High (sensitivity) | **Open**, the scoreboard's one failed check. |
| 5 | **The catalogue prediction ignores parallax** (up to 0.55″ for Barnard's Star, below 0.1 px and below the ±0.76″ trajectory uncertainty). | Low | **Documented.** |
| 6 | **Speed range.** Below ~2″/yr a mover shifts less than 0.5 px over SPHEREx's ~1-year baseline (recall 0.04 at S/N 15); at 40″/yr the visit-to-visit match radius (4 px) starts to lose it (recall 0.26). | Medium (scope) | **Documented.** |

## 5. Scientific risks

* Blind search: positions are flux-weighted centroids on visit stacks, not PSF fits; crowding biases them (finding 1, 3).
* Trajectory panel: positions are measured near the predicted track (catalogue-assisted); it is labelled as such in the app.
* Temperatures are blackbody-equivalent, not effective temperatures; only TRAPPIST-1 is a clean comparison (−4 %).
* Aperture photometry only; no PSF photometry comparison was run (see `LIMITATIONS_AND_UNCERTAINTY.md`).
* Precomputed results are frozen; a live search downloads from IRSA and depends on its availability.

## 6. Performance risks

* Streamlit Community Cloud does not always redeploy on push; the version string under the title shows which code runs.
* Outside services can stall (Gaia archive on Nov 15, IRSA 502 errors at night): Gaia calls have a 12 s limit and a 5-minute pause; SIMBAD falls back to Sesame after 20 s; a live run has a 240 s budget.

## 7. Priorities after this audit

1. Very red movers in sparse fields (finding 4): use alignment information shared between detectors.
2. PSF photometry with simultaneous neighbour fitting, compared against aperture photometry on the same data (findings 1, 3).
3. Parallax in the predicted track (finding 5).
4. Independent photometric calibration against 2MASS Ks and WISE W1 (a check one competitor publishes and we do not).
