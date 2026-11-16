# Final validation report: Cold Movers 0.7.0

Branch `global-scientific-upgrade`, Nov 15, 2026. `main` was backed up first, as the branch
`backup/main-before-final-mission` (commit `209d359`), and was not changed by this work. Every number below comes
from a generated file named next to it. The detection metrics are all in [VALIDATION_METRICS.md](VALIDATION_METRICS.md).

**Status:** STATUS_070

## What the evidence shows (same table as the README and the app)

<!-- evidence-summary:start -->
| Kind of evidence | What it shows |
|---|---|
| **A · Real SPHEREx measurements** | Motion of Barnard's Star: **CONFIRMED**; Motion of Epsilon Indi B: **CONFIRMED**; Temperature of TRAPPIST-1: **MEASURED WITH CAVEATS**; Temperature of Epsilon Indi B: **MEASURED WITH CAVEATS**; Brightness change of R Draconis: **MEASURED**; Confirmed movers other than the known targets, six fields: **NONE FOUND**; Position errors, checked on still stars: **MEASURED** |
| **B · Injection-recovery tests** (artificial movers in real images, never discoveries) | Injected movers at S/N 8 (scoreboard campaign): partial; Injected movers at S/N 15 (scoreboard campaign): pass; Injected movers at S/N 30 (scoreboard campaign): pass; Very red injected movers (detectors 5 and 6 only): fail; Development benchmark (3,300 trials, seed 2026): reported; Held-out set A (pre-registered, seed 20261115, same six fields): reported; Held-out set B (pre-registered, new SPHEREx fields): reported; Motion uncertainties on injections (development): reported; Motion uncertainties on injections (held-out A): reported |
| **C · Candidates, not confirmed** | Motion of WISE 0855-0714: **CANDIDATE**; Candidates for new, unknown objects: **NONE FOUND** |
| **D · Inconclusive or not detected** | Motion of RW Aurigae: **NOT DETECTED**; Motion of R Draconis: **INCONCLUSIVE**; Motion of TRAPPIST-1: **NOT DETECTED**; Temperature of Barnard's Star: **INCONCLUSIVE**; Temperature of WISE 0855-0714: **INCONCLUSIVE**; Temperature of RW Aurigae: **INCONCLUSIVE**; Temperature of R Draconis: **INCONCLUSIVE**; Brightness change of RW Aurigae: **INCONCLUSIVE** |
| **S · Synthetic or computed checks** | Temperature intervals on synthetic spectra: reported; Madhava recovers known temperatures: pass; Series error stays inside Madhava's guaranteed bound: pass; Parallax bias of the straight-line motion fit: reported |

**Confirmed by our own SPHEREx measurements:** 2 motions (Barnard's Star, Epsilon Indi B). Catalogue values are shown only for comparison and are never counted as our measurement.
**Detection rates come only from injected movers:** S/N 15: precision 0.986, recall 0.40 (69 of 173, 1 false confirmation); S/N 30: precision 0.929, recall 0.46. (held-out A)
<!-- evidence-summary:end -->

## 1. Audit and stability

| Check | Where it ran | Result |
|---|---|---|
| Unit tests | Locally (Python 3.13) and on a fresh GitHub Actions machine with the pinned libraries (Python 3.12) | 94 passed, both locally and on the fresh machine |
| Dependencies | `pip install -r requirements.txt pytest`, then `pip check`, on a fresh machine | Installs as the README says; "No broken requirements found." The licence of every package is in [docs/licenses.md](../docs/licenses.md) |
| The whole app, headless, for every example | `scripts/smoke_app.py` on the fresh machine | SMOKE PASSED for all six objects: every section renders, plus the trajectory, the plain-words panel, the difference and sum views and the evaluator panel's verdicts and held-out metrics; no part reported as failed |
| README numbers against generated files | `scripts/check_readme_numbers.py` | 58 of 58 numbers match: scoreboard counts, injection rates, the validation table, verdicts, trajectory, benchmark and held-out metrics (sets A and B), the Madhava improvement and the test count |
| Original SPHEREx files at IRSA | `scripts/check_irsa_links.py`: 5 cited files per object, opened as cutouts the way the app opens them; the DR1 DOI; IRSA's two search services | Cited files and DOI: OK in all 6 runs since retries were added. Every answer was a FITS file; up to 5 files per run first answered HTTP 503 (IRSA busy). In the first run, before retries, 3 files failed with 503. Search services, which no result cites: SIA2 was OK in 5 of 7 runs and answered 502 in the other 2; TAP (the app's fallback) answered 502 or timed out in both runs that tested it |
| Reproduction of every published result | `branch_checks.yml`, job `reproduce`: scoreboard, validation table, evidence records, development benchmark and held-out set A regenerated and compared with the committed files | Scoreboard (JSON and Markdown), validation table and evidence records (Markdown and CSV): identical. Development benchmark and held-out set A: every count identical; some floating-point values (18 of each in the last run) differ only beyond the 9th significant digit (a different NumPy build). A local re-run of the development benchmark gave 0 differences |

**Problems found and fixed during the audit.**

- The pipeline failed when it was run from a standalone script, with `AttributeError: 'Logger' object has no
  attribute '_set_defaults'`. The cause: the "astropy" logger was created before Astropy itself. The app was not
  affected, because it imports Astropy first. Fixed in `coldmovers/spherex.py`; set B (new fields) needed it.
- The app's glossary said that a mover stays a candidate when a "faster" mover passes within 4 px. The rule uses
  the more *significant* mover. The wording was corrected.
- The first reproduction run reported "differs" for the benchmarks. There were two causes: NaN never equals NaN
  in Python, and some floating-point values differ beyond the 9th significant digit between NumPy builds. A local
  re-run of the development benchmark matched the committed file with 0 differences. The comparison now treats
  NaN as a label and reports every difference above rounding.

**Not reproducible, or not checkable from here.**

- The public app follows `main`; a new version is checked live by the robot only after merging and rebooting.
  On the branch, the panels are checked headless.
- The robot's live sky-atlas check reported that the Gaia archive did not answer; the page showed its message.
- A live search depends on IRSA, which answered 502 and 503 several times today.

Warnings seen and left visible: GitHub's Node.js 20 deprecation notice for the actions used; IRSA's transient
502 and 503 answers.

## 2. Scientific validation

### Three kinds of data, kept apart

| Kind | What | Where it is used | Where it is never used |
|---|---|---|---|
| Observational | SPHEREx DR1 + QR3 images and everything measured from them | Movies, positions, motions, photometry, temperatures, brightness changes, verdicts | — |
| Synthetic | Computed blackbody spectra; the series checked against numerical integration | Unit tests; the scoreboard's "Synthetic" rows | In any result about a real object |
| Injected | Fake moving point sources added to copies of the real visit stacks | Scoreboard injection rows; development benchmark; held-out sets A and B | In the app's movies and results, which show only real data |

### Were the rules tuned on the 3,300 trials?

Partly, yes. All detection thresholds were set in v0.4.0 (`dc24604`, Nov 14 19:49), before any injection test,
while developing on the six challenge fields. The neighbour-pull rule (`BLEND_PX = 4` px and the choice of rule C
among three) was chosen on the same 3,300 development trials whose metrics are published. So the post-fix
development numbers are optimistic, and the six fields are development data too. Both were measured:

- **Held-out set A:** pre-registered before running
  ([HOLDOUT_PREREGISTRATION.md](HOLDOUT_PREREGISTRATION.md), commit `0112d6c`), seed 20261115, new quiet,
  near-star and crowded spots, random speeds and directions, the same six fields; 1,740 trials, run once, nothing
  changed afterwards.
- **Held-out set B:** the same design on four SPHEREx fields never used before. The rule picked four positions. Two of them were downloaded and evaluated, 600 trials in all: the Galactic plane at l = 30° (4 visits) and high latitude at l = 90°, b = +45° (3 visits). The north ecliptic pole could not be downloaded, because IRSA's search (SIA and TAP) answered 502, and neither could the south pole in the run that counts. Both are reported missing, not replaced. Set B ran on GitHub Actions. Its result file was rebuilt from the job log by `scripts/parse_holdout_log.py`, because artifacts cannot be downloaded from our environment. The parser was tested on set A with 0 mismatches, and the raw logs are in `docs/holdout_B_logs/`. The workflow was started twice by mistake. The second, identical run gave the same headline numbers. In that run one image of one field failed to download, which changed one very red trial (37 instead of 36 confirmed). It also downloaded the south pole, but all 240 images fell in a single visit. At the ecliptic poles SPHEREx observes almost continuously, so the rule that separates visits by gaps of more than 20 days finds one visit, and the method cannot measure motion there. That field was skipped, as pre-registered. The first completed run is the one reported.

### What the independent evaluation says

Conditions: all six detectors, 5–20″/yr, 95 % Wilson intervals. Full tables in
[VALIDATION_METRICS.md](VALIDATION_METRICS.md).

| Set | S/N | Precision | Recall | FP in injections |
|---|---|---|---|---|
| Development | 15 | 0.981 (0.94–0.99) | 0.39 (0.34–0.44) | 3 in 396 |
| Held-out A | 15 | 0.986 (0.92–1.00) | 0.40 (0.33–0.47) | 1 in 173 |
| Development | 30 | 0.983 (0.95–0.99) | 0.43 (0.38–0.48) | 3 in 396 |
| Held-out A | 30 | 0.929 (0.85–0.97) | 0.46 (0.38–0.53) | 6 in 173 |
| Development | 8 | 0.991 (0.95–1.00) | 0.27 (0.23–0.32) | 1 in 396 |
| Held-out A | 8 | 0.958 (0.86–0.99) | 0.27 (0.21–0.34) | 2 in 173 |
| Held-out B | 15 | 1.000 (0.92–1.00) | 0.72 (0.59–0.81) | 0 in 60 |
| Held-out B | 30 | 1.000 (0.93–1.00) | 0.85 (0.74–0.92) | 0 in 60 |
| Held-out B | 8 | 1.000 (0.90–1.00) | 0.55 (0.42–0.67) | 0 in 60 |

**Pre-registered reading.**

- At S/N 15 (the headline) the development precision lies inside the held-out interval, so the neighbour-pull
  choice is not overfitted there.
- At S/N 8 and 30 the development precision lies above the held-out interval, so the development figures are
  optimistic at those brightnesses.
- On set B (new fields) the development precision lies inside the interval at S/N 8, 15 and 30. There was no
  false confirmation at 5–20″/yr, and recall was higher (0.72 at S/N 15), because these two fields have no
  saturated halos. Over every speed at S/N 30, set B had 3 false confirmations in 120 trials (precision 0.96).

**Diagnosis, with no parameter changed.** The 7 false confirmations of held-out A at S/N 15 and 30 sat 0.02 to 0.87 px from a
real star, in the RW Aurigae and TRAPPIST-1 fields. In 6 of them the injected mover itself was not confirmed.
The neighbour-pull rule compares two movers, so it cannot act when the passing mover is not tracked, and the
pulled star is confirmed. Any fix must be evaluated on a new set.

**By environment** (held-out A, S/N 15): recall 0.62 at quiet spots, 0.29 next to stars and 0.34 in crowded
spots, with precision between 0.94 and 1.00.

**By speed** (held-out A, S/N 15): recall 0.32 at 2–5″/yr, where precision is 0.84; 0.39 at 5–10″/yr; 0.41 at
10–20″/yr; 0.33 at 20–40″/yr.

**Very red movers** (detectors 5 and 6 only): recall 0.13 in held-out A and 0.16 in development, with no false
confirmation; 0.60 on the two new fields of set B. This supports the diagnosis that the failure comes from sparse long-wavelength fields disturbed by the target itself or by a saturated halo. This remains the main weakness: it is the scoreboard's failed check, at 28 %.

**The algorithm does not detect all moving objects.** At S/N 15 it confirms about 40 % of the injected movers in
the six test fields and 72 % in the two new fields, and at S/N 5 almost none.

## 2b. Calibration of uncertainties (new in 0.7.0)

The calibration tests were pre-registered before they ran
([CALIBRATION_PREREGISTRATION.md](CALIBRATION_PREREGISTRATION.md), commit `f3fd5c7`). Results are in
[CALIBRATION.md](CALIBRATION.md); an exploratory follow-up, written after seeing them, is in
[CALIBRATION_FOLLOWUP.md](CALIBRATION_FOLLOWUP.md).

| Test | Result | Reading |
|---|---|---|
| Real-star null test (71 still-star tracks, real SPHEREx data) | Position error scale *k* = 0.42 (robust) and 1.20 (RMS); 92 % of residuals within 1σ (68 % expected); 2 of 71 still stars reach significance 5 in one detector | Most positions are more precise than the model says, but the tails are heavy. A single detector is not enough evidence, which is why confirmation needs two |
| Injection pulls, development → held-out A | Pre-registered RMS scale 8.05 → 4.80; robust follow-up 1.67 → 2.25 | The blind-search speed uncertainty (speed / significance) is too small: read it as at least 1.7 times larger. Detectors are added as if independent, but they share sky, neighbours and alignment |
| Temperature interval coverage (synthetic spectra, real bands) | 22 % with the noise the fit assumes (68 % expected); 59 % with measurement noise only | The interval is quantized to a 0.35 % grid. It is too narrow for precise spectra, and 9 % (TRAPPIST-1) and 7 % (Epsilon Indi B) too narrow for the real objects. Best fits are not biased |

As pre-registered, no threshold, decision or displayed number was changed because of these tests. The fixes are
identified: an independence correction for the combined significance, and interpolating the χ² crossing. Each
must be checked on new data before it is used.

**Evidence ledger (new in 0.7.0).** `coldmovers/evidence.py` builds one ledger of every important result from
the generated files, labelled A (real measurement), B (injection test), C (candidate), D (inconclusive or not
detected) or S (synthetic or computed). The app's "Scientific evidence & validation" panel, the README section
"What the Evidence Actually Shows" and this report's summary are all rendered from it.
`tests/test_evidence_ledger.py` checks four things:
- nothing is CONFIRMED without the rule (two or more trusted detectors, combined significance of 5 or more);
- injection and synthetic results never carry an observation status;
- the README and the report match the ledger;
- every trace points to an existing file.

Full table: [EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md).

## 3. Astrometry and temperature

| Object | Catalogue | Blind search (no catalogue) | Trajectory fit (near the predicted track) | Parallax bias | Baseline | Trusted detectors | Verdict |
|---|---|---|---|---|---|---|---|
| Barnard's Star | 10.39″/yr, 356° | 9.83 ± 0.72″/yr, 354° (−0.79σ) | 10.69 ± 0.76″/yr, 357°, χ²r 1.05 (+0.39σ) | 0.11″/yr | 1.07 yr, 6 visits | 2 | **CONFIRMED** |
| Epsilon Indi B | 4.68″/yr, 122° | 4.54 ± 0.35″/yr, 125° (−0.41σ) | 4.59 ± 0.69″/yr, 126°, χ²r 0.51 (−0.14σ) | 0.19″/yr | 1.41 yr, 4 visits | 5 | **CONFIRMED** |
| WISE 0855−0714 | 8.15″/yr, 275° | 6.36 ± 1.24″/yr, 268° (−1.45σ) | 9.18 ± 1.87″/yr, 275°, χ²r 2.45 (+0.55σ) | 0.10″/yr | 0.99 yr, 4 visits | 5 | **CANDIDATE** |
| RW Aurigae | 0.02″/yr | — | not fitted (slower than 0.5″/yr) | 0.00″/yr | 1.01 yr, 3 visits | 4 | **NOT DETECTED** (expected) |
| R Draconis | 0.02″/yr | — | not fitted | 0.00″/yr | 1.00 yr, 3 visits | 0 | **INCONCLUSIVE** |
| TRAPPIST-1 | 1.05″/yr, 117° | — | 1.06 ± 1.04″/yr, 120°, χ²r 0.19 (+0.01σ) | 0.00″/yr | 1.00 yr, 3 visits | 6 | **NOT DETECTED** (expected) |

From [docs/validation_records.csv](../docs/validation_records.csv) and [docs/parallax_effect.md](../docs/parallax_effect.md).

- **Agreement with the catalogue.** Every measured motion agrees with its catalogue value within 1.5σ.
- **Blind-search uncertainty.** The blind search's uncertainty is approximated as speed / significance; the
  trajectory fit has a full weighted least-squares error.
- **Parallax.** Parallax is not modelled. At each object's visit dates it biases the straight-line motion by
  0.19″/yr at most, below every uncertainty. The largest parallax shift between visits is 1.09″ (0.18 px) for
  Barnard's Star.
- **Baseline.** The baseline is about one year (3 to 6 visits), so motions slower than about 3–4″/yr are
  rarely confirmed. TRAPPIST-1 shows this: its trajectory (1.06 ± 1.04″/yr) agrees with the catalogue but is not
  significant, and its verdict is NOT DETECTED.

**Units and error propagation, checked:**

- Flux: MJy/sr × pixel solid angle × 10¹² = µJy (tested).
- One pixel scale, 6.15″, for the sky grid and every measurement (tested).
- Catalogue motions: mas/yr converted with 3.6 × 10⁶ mas per degree, and RA divided by cos δ.
- Position angles: east of north, with east = −x (tested).
- Trajectory: weighted least squares with its covariance; errors scaled by √χ²r when χ²r > 1; the speed error is
  σ_v (equal on both axes); the direction error is σ_v / speed.
- Temperature: the scale is profiled analytically at each temperature, and the interval is Δχ² = max(1, χ²r),
  following Avni 1976.
- Physical constants: CODATA 2018.

**Temperature.** The Madhava engine gives a *blackbody-equivalent* temperature. That is the temperature of a
single blackbody with the same infrared colours, not the physical (effective) temperature. Brown dwarfs and
disks are not single blackbodies: TRAPPIST-1 gives 2,464 K against 2,566 ± 26 K, and Epsilon Indi B is 40 %
above its published range. Both are flagged MEASURED WITH CAVEATS.

**When no reliable conclusion is possible:**

- Saturation: Barnard's Star, RW Aurigae and R Draconis get temperature INCONCLUSIVE.
- Too narrow a wavelength range, or seen only beyond 3 µm: WISE 0855, temperature INCONCLUSIVE.
- Blending: blended measurements are excluded and flagged; a mover passing within 4 px of a more significant one
  stays a CANDIDATE.
- Untrusted detectors: R Draconis has 0 of 6, so its motion is INCONCLUSIVE.
- Weak signal: motion seen in one detector only, like WISE 0855, is a CANDIDATE.

Rules in `coldmovers/validation.py`, tested in `tests/test_verdicts.py`. Nothing without enough evidence is
labelled CONFIRMED.

## 4. What Cold Movers contributes on its own

| Capability | Where | Evidence | Limit |
|---|---|---|---|
| Blind search for motion, with no catalogue | `movers.search`, `movers.search_all` | Barnard's Star and Epsilon Indi B found with no catalogue; held-out recall 0.40 at S/N 15 | About 40 % recall at S/N 15; slow, faint and crowded movers are often missed |
| Agreement between SPHEREx's six simultaneous detectors | `movers.search_all` | CONFIRMED needs 2 or more detectors; WISE 0855 stays a CANDIDATE with one | Very red movers (2 detectors) are rarely confirmed |
| Band-integrated spectral and thermal fit (Madhava engine), with a guaranteed series-error bound | `madhava.py` | 25 synthetic spectra within 0.5 %; TRAPPIST-1 −4 % from its published temperature, a different quantity | A blackbody-equivalent temperature only |
| Control of false positives from neighbouring sources | `checks.find_blends`, neighbour-pull rule | Development false confirmations 24 → 3; held-out precision 0.99 at S/N 15 | Held-out precision 0.93 at S/N 30: a bright mover that is not tracked can still pull a star |
| Abstaining when the evidence is not enough | Verdicts, traffic light, untrusted fields | R Draconis INCONCLUSIVE; four temperatures INCONCLUSIVE; no unexplained confirmed mover in six fields | Abstention also hides some real movers (very red ones) |

No claim of superiority over other projects is made. No comparable test, with the same fields, injections and
rules, has been run on them ([COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md)). Where each method comes from:
[ORIGINALITY_AND_PROVENANCE.md](ORIGINALITY_AND_PROVENANCE.md).

## 5. For the evaluator

- **The app** has a new panel near the top, "🔬 For evaluators: the science on one page". It covers the problem,
  the real data with the IRSA DOI, how detection and validation work, a results table with the verdicts, the
  detection metrics with intervals and definitions (development, held-out A and, when available, held-out B), the
  limits, and how to reproduce the analysis. Every number in it is read from the generated files.
- **The README** opens with the same seven answers, the three kinds of data, the verdict table and the metrics.

## 6. Metrics before and after

| Stage | Code | Data | S/N 15 precision | S/N 15 recall | Scoreboard |
|---|---|---|---|---|---|
| Before the neighbour-pull fix | v0.4.9 | development set | 0.872 | 0.41 | — |
| After the fix | v0.5.0 | development set (the rule was chosen on it) | 0.981 | 0.39 | 14 pass · 4 partial · 1 fail |
| Independent check | v0.5.0 search, unchanged | held-out set A | 0.986 (0.92–1.00) | 0.40 (0.33–0.47) | — |
| Independent check on new fields | v0.5.0 search, unchanged | held-out set B (2 new fields) | 1.000 (0.92–1.00) | 0.72 (0.59–0.81) | — |
| v0.6.0 | verdicts, evaluator panel, checks; the search itself unchanged | — | — | — | 14 pass · 4 partial · 1 fail (regenerated, identical) |
| v0.7.0 | evidence ledger and calibration; the search unchanged, no displayed number changed | — | — | — | unchanged |

No validated result was changed to improve a metric. The search code is unchanged since v0.5.0. In this work,
`coldmovers/scoreboard.py` only records where each false confirmation sits, and `coldmovers/validation.py` only
adds verdicts.

## 7. Files changed on the branch (relative to `main`)

- **Code:** `coldmovers/validation.py` (verdicts), `coldmovers/scoreboard.py` (false-positive positions),
  `coldmovers/spherex.py` (logger fix), `coldmovers/__init__.py` (0.6.0), `app.py` (evaluator panel, glossary).
- **New scripts:** `benchmark_holdout.py`, `fetch_holdout_fields.py`, `validation_metrics.py`,
  `parallax_effect.py`, `check_readme_numbers.py`, `check_irsa_links.py`.
- **Changed scripts:** `validation_report.py` (verdict columns), `screenshots.py` (0.6.0, panel check).
- **Tests:** `tests/test_verdicts.py` (7 tests: verdict rules, pixel scale, flux units).
- **Results:** `docs/benchmark_holdout_A.json`, `docs/parallax_effect.md` and `.json`, and
  `docs/validation_records.md` and `.csv`, regenerated on GitHub Actions with only the verdict columns added.
- **Documents:** `README.md`; `evidence/HOLDOUT_PREREGISTRATION.md`, `VALIDATION_METRICS.md`,
  `FINAL_VALIDATION_REPORT.md` (new); `LIMITATIONS_AND_UNCERTAINTY.md`, `REPRODUCIBILITY.md` and
  `COMPETITIVE_ANALYSIS.md` (updated).
- **Workflows:** `.github/workflows/branch_checks.yml` and `holdout_b.yml`. Both are read-only and run only on this
  branch; none of them commits.

**Added in 0.7.0:**
- **Code:** `coldmovers/evidence.py` (the ledger); `coldmovers/scoreboard.py` also records the measured speed,
  direction and significance of each trial (no counts change); `coldmovers/__init__.py` (0.7.0); `app.py`
  (evidence panel and traceability table).
- **Scripts:** `calibration.py`, `calibration_followup.py`, `evidence_report.py`; the benchmarks can write
  per-trial records.
- **Results:** `docs/calibration.json`, `docs/calibration_followup.json`, `docs/evidence_ledger.json`, and
  `docs/calibration_inputs/` (per-trial records).
- **Documents:** `evidence/CALIBRATION_PREREGISTRATION.md`, `CALIBRATION.md`, `CALIBRATION_FOLLOWUP.md`,
  `EVIDENCE_LEDGER.md`.
- **Tests:** `tests/test_evidence_ledger.py` (7 tests).
- **CI:** a `calibration` job that re-runs the calibration and compares it with the committed result.

## 8. Open problems

1. **Very red movers** (detectors 5 and 6 only) are rarely confirmed: 13 % in held-out A and 28 % in the
   scoreboard. The detector-trust rule distrusts sparse long-wavelength fields.
2. **A bright mover passing a star** can make the star a confirmed mover when the mover itself is not tracked.
   Held-out precision is 0.93 at S/N 30.
3. **At S/N 5** there are false confirmations near stars (6 in 173 held-out injections) and almost no true ones.
4. **Crowding and stars nearby:** recall is about 0.3. There is no PSF photometry and no deblending.
5. **Parallax** is not modelled. The bias is small for these objects but grows with parallax and with fewer
   visits.
6. **The blind search's speed uncertainty** is an approximation (speed / significance).
7. **No independent photometric calibration** against 2MASS or WISE has been done.
8. **The public app runs the version on `main`** until the branch is merged and the app is rebooted.
9. **Set B covers only two of the four pre-registered fields.** IRSA's search was unavailable, and at the ecliptic poles the visit rule finds a single visit. With 60 injections per S/N its intervals are wide.
10. **IRSA's search services** (SIA2 and TAP) answered 502 in several runs today. The files cited by the results all opened; a live search in the app may have to wait.
11. **The blind-search speed uncertainties are too small** (calibration, §2b). The fix is identified but not applied.
12. **The temperature interval is quantized.** For the real objects it is 7 to 9 % too narrow; the fix is identified but not applied.

## 9. How to publish the final version (needs the team's authorization)

1. **Merge the branch** into `main` as a fast-forward:
   ```bash
   git checkout main && git pull --ff-only origin main
   git merge --ff-only global-scientific-upgrade
   git push origin main
   ```
2. **Let GitHub Actions run on `main`.** `tests.yml` runs the unit tests and the headless app.
   `scoreboard.yml` regenerates the scoreboard, with the same results stamped 0.7.0. `screenshots.yml`
   regenerates the evidence records and checks the live app.
3. **Reboot the app.** At share.streamlit.io, open the cold-movers app and choose Reboot. Check that the page says
   **version 0.7.0** under the title and shows "Scientific evidence & validation".
4. **Confirm the robot.** The `app screenshots` run should print "deployed app shows version 0.7.0" and
   "live check evidence panel: OK".
5. **Roll back if needed.** The previous `main` is kept as `backup/main-before-final-mission` (`209d359`). Restoring
   it is a deliberate overwrite of `main` and needs the team's explicit decision.
