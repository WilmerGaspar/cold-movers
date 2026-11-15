# Originality and provenance

Where every part of Cold Movers comes from: the established science it uses, the third-party techniques and
data it credits, what was designed and tested in this repository, and which results are new and which reproduce
known values. Written on Nov 15, 2026, for code version 0.5.0. Every date below is a git commit date
(Honduras time, UTC−6) that anyone can check with `git log`.

**Authorship.** Who did what is declared in one place, [README → AI use](../README.md#ai-use). The team chose the
challenge, the idea and the scientific approach and decided every feature. Code and documentation were written
with an AI coding assistant and reviewed and tested by the team. In this file, *developed in Cold Movers* means
designed, implemented and tested in this repository for this project, and not adapted from another project. It
does not say who typed the code.

## At a glance

| An evaluator asks | Short answer | Details |
|---|---|---|
| Which established science does Cold Movers use? | Planck's law and its standard series, the Bernoulli expansion of the same integral, the TAN sky projection, linear proper-motion propagation, aperture photometry, centroids, robust noise, least squares with χ², artificial-source injection, and precision and recall. | [§2](#2-established-methods-and-what-cold-movers-does-with-them) |
| Which third-party techniques does it credit? | The IRSA tutorials' way of searching and cutting SPHEREx images (BSD-3-Clause), the WiseView-style blink view (idea only), the SPHEREx FLAGS bit definitions, Gaia DR3 and SIMBAD data, and the open-source libraries in [docs/licenses.md](../docs/licenses.md). | [§2](#2-established-methods-and-what-cold-movers-does-with-them), [§7](#7-dependencies-data-and-licences) |
| What was developed in Cold Movers? | The blind mover search with confirmation across SPHEREx's six simultaneous detectors, the field-trust rule, the neighbour-pull rule, the target blend check, Madhava's correction term with a guaranteed bound on the band-integral series, the traffic-light abstention rules, the validation scoreboard, the blind benchmark, the trajectory panel, and the explanations written only from measurements. | [§3](#3-components-developed-in-cold-movers) |
| What was designed and tested during this project? | Each version from 0.4.0 to 0.5.0, with the reason for the change, the experiment behind it and its result, negative results included. | [§4](#4-changes-made-during-this-project-and-the-experiment-behind-each) |
| What is really new? | No new astrophysical result is claimed. The motions, temperatures and brightness changes reproduce known values with SPHEREx data. What is new is measured about the tool itself on real SPHEREx data: recovery rates, precision, a failure mode found and fixed, and a failure still open. | [§5](#5-results-new-or-reproduced) |
| Was anything copied from competitors? | No competitor code was used. A line-by-line and token-by-token comparison with SkyShift's full repository (the only competitor repository we could open) found no shared function, file or algorithm. Three sentences with similar wording were rewritten. | [§6](#6-competitor-projects-what-we-looked-at-and-what-we-did-with-it), [CODE_COMPARISON.md](CODE_COMPARISON.md) |

## 1. The scientific line of Cold Movers

| Pillar | Where in the code | Evidence | Known limit |
|---|---|---|---|
| Blind detection of moving sources in SPHEREx data | `movers.detect`, `movers.search` | Barnard's Star 9.83″/yr and Epsilon Indi B 4.54″/yr, found with no catalogue (−5 % and −3 % from the catalogue, [scoreboard](../docs/scoreboard.md)) | Best from 5 to 20″/yr: at 2″/yr the shift in a year is under 0.5 px, and at 40″/yr recall falls to 0.26; crowded spots recover 0.22 at S/N 15 ([benchmark](BENCHMARK_RESULTS.md)) |
| Confirmation by independent evidence across detectors | `movers.search_all`: SPHEREx images all six detectors at the same moments; a mover is confirmed only when two or more agree in position and velocity and the combined significance reaches 5 | Epsilon Indi B confirmed by 5 detectors; WISE 0855 stays a *candidate* (1 detector); tests `test_mover_confirmed_in_two_detectors_with_right_rate`, `test_one_detector_is_only_a_candidate` | Very red movers seen by two detectors are confirmed in only 28 % of injections (the scoreboard's one failed check) |
| Explicit rejection of false positives from blended sources | `checks.find_blends` (around the target); the neighbour-pull rule in `movers.search_all` (across the field) | False confirmations at S/N 15: 24 → 3; precision 0.872 → 0.981 ([benchmark](BENCHMARK_RESULTS.md)) | Recall fell from 0.41 to 0.39 |
| Spectral and thermal characterisation with the Madhava engine | `madhava.fit_temperature`, `madhava.traffic_light` | TRAPPIST-1: 2,464 K blackbody-equivalent against 2,566 ± 26 K published (−4 %, a different quantity); 25 synthetic spectra recovered within 0.5 % | A blackbody-equivalent temperature is not an effective temperature (brown dwarfs, disks) |
| Uncertainty quantification | Δχ² interval of the fit, the series bound, `assistant.trajectory_fit` (error bars, fitted motion ± σ, χ²r), injection medians | Barnard's Star 10.69 ± 0.76″/yr, 0.4σ from the catalogue, χ²r 1.05 | The blind search's uncertainty is approximated as rate / significance |
| Abstention when the evidence is not enough | Red traffic light, untrusted fields, candidate instead of confirmed | Barnard's Star (saturated) and WISE 0855 (too cold for SPHEREx to see its peak) get a red light; R Draconis' field is reported as not trusted; no unexplained confirmed mover in six fields | Abstention can hide real signal (the red-mover failure) |

## 2. Established methods, and what Cold Movers does with them

| Method | Source | Where | What is specific to Cold Movers |
|---|---|---|---|
| Fraction of blackbody energy below a wavelength, as the series (15/π⁴) Σ e^(−nx)(x³/n + 3x²/n² + 6x/n³ + 6/n⁴) | Widger & Woodall 1976 | `madhava._large_x_with_bound` | Applied to SPHEREx's wide linear-variable-filter bands: the model is the exact mean over each band, not a sample at its centre |
| The same integral for small x, from Bernoulli numbers (Debye-function expansion) | Abramowitz & Stegun 1964, §27.1 | `madhava._fraction_small_x` | Standard. The switch between the two branches is tested (`test_both_series_agree_at_switch_point`) |
| Bounding the rest of a series whose term ratios increase towards a limit (comparison with a geometric series) | Standard real analysis, for example Knopp 1951 | `madhava._large_x_with_bound` | See §3, item 5: a two-sided bound for this series, its midpoint added as a correction, the half-width reported as a guaranteed bound and shown in the app |
| The name "Madhava" | Madhava of Sangamagrama (c. 1340–1425), who added end corrections to truncated series for π (Plofker 2009) | | A homage and an analogy (correcting a truncated series instead of cutting it). Madhava's own correction formulas are not used. |
| Physical constants | CODATA 2018 (Tiesinga et al. 2021) | `madhava.py` | |
| χ² fit with a free scale; uncertainty where χ² rises by 1 above its minimum, raised to χ²r when the fit is poor | Avni 1976; Bevington & Robinson 2003 | `madhava.fit_temperature` | The 8 % systematic floor, the grid in temperature and the contiguous-interval rule are our choices |
| Gnomonic (TAN) projection and world coordinate systems | Calabretta & Greisen 2002; Astropy | `movie.make_reference_wcs` | One common sky grid per object, with east = −x (tested by `test_trajectory_fit_east_is_minus_x`) |
| Bilinear resampling | SciPy `map_coordinates` | `movie.reproject_frame` | |
| Stacking all images of one detector from one visit | Suggested in the challenge brief (a sum per detector) | `movie.build_epoch_stacks` | Visits separated by gaps of more than 20 days |
| Linear proper-motion propagation | Standard astrometry; Gaia DR3 epoch 2016.0 (Gaia Collaboration, Vallenari et al. 2023) | `targets.Target.position_at` | Every image is measured at the position propagated to its own date. Parallax is ignored (a stated limitation) |
| Aperture photometry with a sky annulus | Standard; for example DAOPHOT (Stetson 1987) | `photometry.measure` | Pixels rejected with the SPHEREx FLAGS bits; wings measured for saturated stars |
| Robust noise as 1.4826 × the median absolute deviation | Hampel 1974 | `movers._noise`, `photometry._robust_stats` | |
| Peak detection and a flux-weighted centroid | Standard | `movers.detect`, `checks.centroid` | |
| Centroid uncertainty proportional to the PSF width over the S/N | King 1983 | `movers.search`, `assistant.trajectory_fit` | σ = √(0.12² + (0.9/S/N)²) px: 0.12 px from how well still stars line up in our stacks, 0.9 px an approximate SPHEREx PSF width |
| Linking detections across visits by nearest neighbour | Common in moving-object searches, for example Kubica et al. 2007 for asteroids | `movers.search` | A simple version (no k-d trees) for a few visits about six months apart |
| Weighted straight-line fit, errors scaled by √χ²r when χ²r > 1 | Bevington & Robinson 2003 | `assistant.trajectory_fit` | |
| Artificial-source injection and recovery to measure detection limits | Long-standing practice, for example the artificial-star tests of DAOPHOT (Stetson 1987) | `scoreboard.inject_and_search`, `scoreboard.blind_trial` | Injected into the real SPHEREx visit stacks, run through the same blind search the app uses |
| Precision, recall and F1 | van Rijsbergen 1979 | `scoreboard.summarize_trials` | |
| Abstaining instead of answering (the "reject option") | Chow 1970 | `madhava.traffic_light`; the `reliable` flag in `movers.search` | The rules are physical and ours: saturation, too narrow a wavelength range, a Planck peak outside SPHEREx's coverage, an uncertainty above 50 % on either side |
| Blinking two epochs to reveal motion | Tombaugh's 1930 discovery of Pluto (history); WiseView (Caselden et al. 2018) | `movie.py`, `app.py` | The idea only; no WiseView code was used |
| Searching SPHEREx images (SIA2, TAP fallback), the cutout URL syntax, wavelength from the WCS-WAVE layer | IRSA tutorials "Introduction to SPHEREx Spectral Images" and "Download a collection of SPHEREx Spectral Image cutouts" (BSD-3-Clause) | `spherex.py` | We followed their documented approach. The comparison found 5 short identical lines (a TAP join and common Python idioms) and no identical stretch of 20 or more tokens ([CODE_COMPARISON.md](CODE_COMPARISON.md)) |
| SPHEREx FLAGS bit names | The FLAGS layer header of the SPHEREx images (MSKN keywords) and the SPHEREx archive documentation | `spherex.FLAG_NAMES` | Our choice of which bits remove a pixel and which are only reported |

Software we cite as its authors ask: Astropy (Astropy Collaboration 2022), NumPy (Harris et al. 2020),
SciPy (Virtanen et al. 2020), Matplotlib (Hunter 2007), Astroquery (Ginsburg et al. 2019).

## 3. Components developed in Cold Movers

| # | Component | File | Design | Evidence |
|---|---|---|---|---|
| 1 | Confirmation across detectors | `movers.search_all` | Detections in different detectors are grouped when within 1.5 px (first visit) and 1 px/yr in velocity. The combined significance is √Σs². A mover is confirmed with 2+ detectors and a combined significance of 5 or more; otherwise it is a candidate. | Tests in `tests/test_movers.py`; Epsilon Indi B in D2–D6; WISE 0855 a candidate in D5 |
| 2 | Field-trust rule | `movers.search` | The median apparent shift of the field's sources, the fastest left out, says how well the visits line up. Above 0.5 px the detector is not trusted and reports nothing. | `test_badly_aligned_field_is_not_trusted`; R Draconis' field is not trusted. It is also the cause of the red-mover failure (§5) |
| 3 | Neighbour-pull rule | `movers.search_all` (`BLEND_PX = 4`) | When two movers come within 4 px at any visit time, the less significant one stays a candidate, because a moving neighbour's light can pull a still star's centroid. | Found and chosen with the blind benchmark (§4, v0.5.0); `test_slower_of_two_crossing_movers_is_not_confirmed` (in that synthetic case the slower star is also the less significant) |
| 4 | Target blend check | `checks.find_blends`, `checks.mark_blends` | Visits and detectors where the light near the target is centred somewhere else are flagged, and their measurements are left out of the fit. | `test_fixed_neighbour_is_flagged_and_its_detector_excluded`; WISE 0855's blended measurements are excluded |
| 5 | Madhava correction with a guaranteed bound | `madhava._large_x_with_bound`, `madhava.fraction_with_bound`, `madhava.series_report` | The coefficients c_n = x³/n + 3x²/n² + 6x/n³ + 6/n⁴ are log-convex in n, so the ratio of consecutive terms grows but stays below e^(−x). The rest of the series after N terms therefore lies between t_(N+1)/(1−q_(N+1)), with q_(N+1) = t_(N+2)/t_(N+1), and t_(N+1)/(1−e^(−x)). The engine adds the midpoint and reports half the width as a guaranteed bound, shown under each temperature. The idea of the correction term was proposed by the team. | `test_madhava_correction_bound_is_guaranteed` (tolerances 1e-3 to 1e-15); `scripts/madhava_correction_check.py`: 7× to 274× smaller error than plain truncation with the same terms, inside the bound in 14 of 14 comparisons; TRAPPIST-1 bound below 10⁻¹² |
| 6 | Band-integrated fit and traffic light for SPHEREx | `madhava.fit_temperature`, `madhava.traffic_light` | A free temperature and scale, an 8 % floor, and rules that say when not to trust the number. | Synthetic check: 25 spectra, worst error 0.5 %; red light for Barnard's Star and WISE 0855; `test_uncertainty_rule_uses_the_larger_side` |
| 7 | Movie, difference and sum views on one sky grid | `movie.py` | Per-detector visit stacks with a common stretch; the difference from the first visit; the mean of all visits. | `test_frames_and_difference_render_with_layers`; screenshots in `docs/screens/` |
| 8 | Visual assistant and plain-language explanations | `assistant.py` | Every layer and every sentence is written from a measurement already made; a missing measurement means the layer or sentence is left out. | `tests/test_assistant.py` (saturated star, slow star, cold object, coin geometry) |
| 9 | Trajectory panel | `assistant.trajectory_fit`, `app.py` | Positions against time with 1σ bars, a weighted straight line, motion ± σ, direction ± σ, χ²r and the difference from the catalogue in σ. | `test_trajectory_fit_recovers_a_known_motion`; Barnard's Star 10.69 ± 0.76″/yr, 0.4σ |
| 10 | Brightness change visit by visit | `variability.py` | Per detector, a quadratic in wavelength (in magnitudes) is fitted over all visits; the residuals are the change. Wings are used for saturated stars. "Yes" above 5σ, "Possibly" from 3σ to 5σ. | R Draconis 0.57 mag at 9.6σ; RW Aurigae 4.6σ, "Possibly" |
| 11 | Validation scoreboard | `scoreboard.py`, `scripts/scoreboard.py`, CI | Pass rules written in code before the results; every result shown; regenerated by GitHub Actions. | [docs/scoreboard.md](../docs/scoreboard.md): 14 pass, 4 partial, 1 fail |
| 12 | Blind injection benchmark | `scoreboard.blind_trial`, `scripts/benchmark_injection.py` | 3,300 trials, seed 2026: speeds, directions, S/N, quiet and crowded spots, all detectors or only D5 and D6. Precision as well as recall. | [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) |
| 13 | Gaia match that requires the same motion | `app.py`, `atlas.py` | A mover is called a known Gaia star only if the Gaia star also moves the same way, not just because it sits nearby. | v0.4.1 |
| 14 | No frozen pages | `net.py`, `app.py` | Every outside call has a time limit; Gaia pauses for 5 minutes after a timeout; failures are listed on the page. | `test_external_calls_cannot_freeze_the_page`, `test_gaia_pause_after_timeout` |
| 15 | Evidence tooling | `scripts/validation_report.py`, `scripts/licenses.py`, `scripts/compare_code.py`, `scripts/madhava_correction_check.py` | Per-object evidence records, the licence table from package metadata, the code comparison, the series check. | [docs/validation_records.md](../docs/validation_records.md), [docs/licenses.md](../docs/licenses.md), [CODE_COMPARISON.md](CODE_COMPARISON.md) |

**What Madhava's correction does and does not do.** It makes the *numerical* band integral exact to a known,
guaranteed level (below 10⁻¹² for TRAPPIST-1). It does not correct measurement errors and does not improve
trajectories: the measurement errors (percent-level fluxes, tenths of a pixel in position) are many orders of
magnitude larger than the series error. A proposal within the team to use the series error to correct
measurements was examined and not adopted, for that reason.

We have not found the two-sided bound of component 5, or the neighbour-pull rule of component 3, in the
literature we know, but we did not do an exhaustive search. Both use standard mathematics. What we claim is the
design for this problem and the tests that check it, not a new theorem.

## 4. Changes made during this project, and the experiment behind each

| Version (commit, date) | Change | Why | Experiment or check | Result, negatives included |
|---|---|---|---|---|
| 0.4.0 (`dc24604`, Nov 14 19:49) | Catalogue-free mover search, confirmed across detectors | Measuring near the predicted track only tests agreement; an independent check needs no catalogue | Real objects and synthetic tests | Barnard's Star −5 %, Epsilon Indi B −3 %; WISE 0855 only a candidate (−22 %) |
| 0.4.1 (`f8e79ba`, Nov 14 20:12) | Gaia match requires the same motion | A nearby Gaia star is not the same object unless it moves the same way | A design rule, not tested on its own | |
| 0.4.2 (`fd47f96`, Nov 14 20:41) | "Possibly" tier for brightness changes (3σ to 5σ) | Avoid a yes/no verdict near the threshold | RW Aurigae at 4.6σ | Reported as "Possibly", not as a detection |
| 0.4.3 (`53ccd2d`, Nov 14 22:07) | Madhava's correction term with a guaranteed bound | Know the series error instead of assuming it | Bound tests from 1e-3 to 1e-15; `scripts/madhava_correction_check.py` | 7× to 274× smaller error; the bound holds in 14 of 14 comparisons |
| 0.4.4 (`9fd53ed`, Nov 14 23:00) | Visual assistant, plain-words panel, detector count | Make the evidence visible to non-specialists without inventing anything | Unit tests on every sentence type | |
| 0.4.5 (`74443c1`, Nov 14 23:32) | Validation scoreboard: positive and negative controls, injected movers | Rules fixed before the results | CI-generated | Current: 14 pass, 4 partial, 1 fail (the failure is kept and diagnosed) |
| (`6c19222`, `763d835`, Nov 14–15) | Time limits on outside services; Gaia pause | The headless app test hung for 20+ minutes when the Gaia archive did not answer | Tests on time limits and the pause | The test no longer hangs |
| 0.4.6 (`f362c5f`, Nov 15 05:24) | Sum of all visits, movers CSV, "Tests, not discoveries" note | Show still faint sources; let others check our movers; state plainly that nothing is a discovery | Headless app test | |
| 0.4.7 (`98b1dd9`, Nov 15 05:50) | No silent failures; versioned User-Agent; uncertainty rule uses the larger side of the interval | Found in an independent review | `test_uncertainty_rule_uses_the_larger_side` | |
| 0.4.8 (`72c5c99`, Nov 15 06:12) | Readability for everyone | Team review | Live screenshots | A suggested linear scale was not adopted (unreadable) |
| 0.4.9 (`3949f57`, Nov 15 06:49) | Trajectory panel with uncertainties | Show motion with its error bars, not just a number | Trajectory tests; live check | Barnard's Star 10.69 ± 0.76″/yr, 0.4σ, χ²r 1.05 |
| 0.5.0 (`a46e42b`, Nov 15 13:15) | Blind injection benchmark; neighbour-pull rule; evidence dossier | Measure precision, not only recall | 3,300 trials, before and after; three candidate rules compared | Rule A (no confirmation near any source) removed every false confirmation but halved recall (0.41 → 0.20), so it was rejected; rule B 3 false confirmations, recall 0.36; rule C adopted: 3 false confirmations, recall 0.39. The real objects' results did not change |
| (`51d969c`, `c348ae1`, Nov 15) | Per-object evidence records saved by CI | Every number traceable to its files | Generated by the app's own code | [docs/validation_records.md](../docs/validation_records.md) |
| This file (Nov 15) | Provenance, licence table from metadata, code comparison; three sentences reworded; README figure corrected | Make origin and authorship checkable | `scripts/licenses.py` (CI), `scripts/compare_code.py`, `scripts/madhava_correction_check.py` | The README said the correction makes the error "5 to 40 times smaller"; the check measures 7× to 274×, and the README now says so. No GPL-family licence among the 72 installed packages |

## 5. Results: new or reproduced?

| Result | Kind | Comment |
|---|---|---|
| Barnard's Star motion: 9.83″/yr blind, 10.69 ± 0.76″/yr fitted, against 10.39″/yr | Reproduction of a known value with SPHEREx data | Agreement within 0.4σ (fitted) and −5 % (blind) |
| Epsilon Indi B motion: 4.54″/yr blind, 5 detectors, against 4.68″/yr | Reproduction | −3 %, 4° in direction |
| WISE 0855−0714 motion: 6.36″/yr, a candidate, against 8.15″/yr | Partial reproduction | One detector only, −22 %: reported as a candidate, not confirmed |
| TRAPPIST-1: 2,464 K blackbody-equivalent against 2,566 ± 26 K effective temperature | A comparison of two different quantities | Not a new temperature; yellow light because one blackbody does not describe the spectrum |
| Epsilon Indi B: 1,874 K blackbody-equivalent | A measurement of the blended pair's blackbody-equivalent light | Not an effective temperature; flagged yellow; 40 % above the published range |
| R Draconis 0.57 mag change at 9.6σ; RW Aurigae 0.21 mag at 4.6σ | Reproduction of known variability | RW Aurigae only "Possibly" |
| No unexplained confirmed mover in the six fields | A negative control | Not a claim that no unknown movers exist |
| Injection recovery 66 %, 88 % and 91 % at S/N 8, 15 and 30; blind-benchmark recall and precision | **New**, about the tool, on real SPHEREx DR1 + QR3 stacks | Not compared with other tools' numbers: conditions differ |
| The neighbour-pull failure mode, its fix and its cost | **New**, about the tool | Precision 0.872 → 0.981 at S/N 15; recall 0.41 → 0.39 |
| Very red movers confirmed in only 28 % of cases, and why | **New**, a negative result about the tool | Diagnosed in [docs/scoreboard.md](../docs/scoreboard.md); our first next step |
| Guaranteed series-error bound used in a temperature fit | **New in this application** | Standard mathematics; see §3, item 5 |

Not claimed: any discovery, new object, new proper motion or new effective temperature.

## 6. Competitor projects: what we looked at and what we did with it

**Rule.** Competitor projects are references for the state of the art and for open problems, nothing more. No
competitor code, architecture, interface, text or report structure is copied.

**What was read.** As recorded in [COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md), only the README of
SkyShift (github.com/Nsa-2026/skyshift) was read, on Nov 15. Its code was read only for the comparison below, after
Cold Movers 0.5.0 was finished. The other competitors' repositories could not be opened from our
environment, so nothing is claimed about them.

**Code comparison** (full output in [CODE_COMPARISON.md](CODE_COMPARISON.md); SkyShift at commit `a6427d8`,
Apache-2.0, about 59,600 lines of Python, read as text only):

- **Identical lines:** 32 of 3,374 Cold Movers lines. Twenty-eight are one-line idioms of NumPy, Astropy and the
  standard library, such as `rng = np.random.default_rng(seed)`, the TAN projection line and warning filters.
  The other four are the SPHEREx FLAGS bit names.
- **Longest identical stretches:** the longest is the SPHEREx FLAGS table (91 tokens). It is mission data that
  both projects copied from the FLAGS layer's header keywords; SkyShift's file says the same. Ours was committed
  on Nov 14 at 14:02 (`c9f6f58`), before SkyShift's README was read on Nov 15. Every other stretch is 1 to 3 lines: the 2-D Gaussian formula, Astropy's TAN
  set-up, a percentile stretch and finite-value masks. The same kind of match appears in photutils, an unrelated
  library we certainly did not copy.
- **Renamed-copy check:** 2.69 % of our 25-token runs, with names and values masked, also occur in SkyShift,
  against 0.98 % in photutils. That is higher, as expected for code that works on the same data with the same
  libraries. The matches are scattered: 167 stretches with a median of 31 tokens (1 to 3 lines). Each one pairs
  with unrelated code, for example our blackbody-fit docstring with one of their frame-rendering functions. No
  function, file or algorithm is shared.
- **Limits:** these measures cannot prove a negative, and only SkyShift and the IRSA tutorials were compared.

**Texts rewritten in this commit.** The text comparison found three overlaps. We rewrote all three, whatever
their origin:

1. **The Tombaugh sentence** in the README and the app ("by blinking two photographs of the same sky taken
   days apart"). Ours dates from Nov 14 at 15:35 (`eff57c4`). The same words are in SkyShift's project page.
2. **The SPHEREx glossary line** ("maps the whole sky every six months in 102 colours"). Ours was added in
   0.4.8 (Nov 15 06:12). The phrase is not in SkyShift's README; it is in SkyShift's slides and website. We
   cannot rule out that its wording reached us indirectly through descriptions of competitors.
3. **The scoreboard card's title** "How do we know it works?". Ours dates from 0.4.5 (Nov 14 23:32). SkyShift's
   README labels its scoreboard link "How we know it works". Ours is now "Validation scoreboard: known objects,
   injected movers, fixed rules".

The only shared text that remains is the challenge's name, object names, citations, URLs and the
acknowledgements the data providers require word for word.

**Ideas, not code.** Some generic features were added on Nov 15, after the team reviewed lists of competitors'
strengths taken from public descriptions:

- the sum of all visits and the CSV export of movers (0.4.6), and the trajectory panel (0.4.9, also asked for by a
  team member);
- SkyShift also publishes a scoreboard. Ours (0.4.5) is a pass/partial/fail table, a common format for test
  reports. Its checks, its rules and its injection campaign are ours.

SkyShift's strengths that we deliberately did not reproduce: a search for asteroids within one visit,
photometric calibration against 2MASS and WISE, community voting, and an MCP server (considered, not built).

## 7. Dependencies, data and licences

- **Our code:** MIT ([LICENSE](../LICENSE)).
- **Libraries:** the licence of every installed package is read from its own metadata on GitHub Actions, in
  [docs/licenses.md](../docs/licenses.md). The 13 direct dependencies are under BSD-style, MIT, Apache-2.0, the
  PSF licence (Matplotlib) or MIT-CMU (Pillow) licences; NumPy's metadata also lists 0BSD, Zlib and CC0 for bundled
  parts. Among all 72 installed packages, none declares a GPL-family licence.
  One, certifi (the certificate bundle used by Requests), is under MPL-2.0. All are installed unmodified with
  pip and none of their code is copied into this repository, so they are compatible with releasing our code
  under MIT.
- **No vendored or pasted code:** no third-party source file is included, and no code is marked as copied or
  adapted from elsewhere. The IRSA tutorials (BSD-3-Clause) were followed for the query and cutout syntax and
  are credited (§2).
- **Data:** SPHEREx DR1 and QR3 (NASA/IPAC IRSA), Gaia DR3 (CC BY-SA 3.0 IGO), SIMBAD and Sesame (CDS), and
  the NASA Exoplanet Archive. Terms and the required acknowledgements are in
  [DATA_AND_RESOURCES.md](../DATA_AND_RESOURCES.md).
- **Images:** every image in the app, the README and the evidence comes from SPHEREx data processed by our code,
  or is a capture of the live app. The team logo ([docs/logo_ai_marked.png](../docs/logo_ai_marked.png)) was
  generated with Gemini and carries a visible mark. No NASA branding is used.

## 8. How to check all of this

```bash
python -m pytest -q                              # 87 tests
python scripts/madhava_correction_check.py      # series error with and without the correction, against its bound
python scripts/scoreboard.py                    # the validation scoreboard (needs the requirements)
python scripts/benchmark_injection.py           # the 3,300-trial blind benchmark (about 2 minutes)
python scripts/licenses.py                      # licences from package metadata
python -I scripts/compare_code.py <other-repository> [<unrelated-baseline>]   # code and text comparison
git log --format='%h %ad %s' --date=iso         # every date quoted here
```

## References

- Abramowitz, M. & Stegun, I. A. 1964, *Handbook of Mathematical Functions*, NBS Applied Mathematics Series 55, §27.1.
- Astropy Collaboration 2022, ApJ 935, 167.
- Avni, Y. 1976, ApJ 210, 642.
- Bevington, P. R. & Robinson, D. K. 2003, *Data Reduction and Error Analysis for the Physical Sciences*, 3rd ed., McGraw-Hill.
- Calabretta, M. R. & Greisen, E. W. 2002, A&A 395, 1077.
- Caselden, D. et al. 2018, WiseView (Astrophysics Source Code Library).
- Chow, C. K. 1970, IEEE Trans. Inf. Theory 16, 41.
- Gaia Collaboration, Vallenari, A. et al. 2023, A&A 674, A1.
- Ginsburg, A. et al. 2019, AJ 157, 98 (Astroquery).
- Hampel, F. R. 1974, J. Am. Stat. Assoc. 69, 383.
- Harris, C. R. et al. 2020, Nature 585, 357 (NumPy).
- Hunter, J. D. 2007, Comput. Sci. Eng. 9, 90 (Matplotlib).
- King, I. R. 1983, PASP 95, 163.
- Knopp, K. 1951, *Theory and Application of Infinite Series*, Blackie (Dover reprint 1990).
- Kubica, J. et al. 2007, Icarus 189, 151.
- Plofker, K. 2009, *Mathematics in India*, Princeton University Press.
- Stetson, P. B. 1987, PASP 99, 191.
- Tiesinga, E. et al. 2021, Rev. Mod. Phys. 93, 025010 (CODATA 2018).
- van Rijsbergen, C. J. 1979, *Information Retrieval*, 2nd ed., Butterworths.
- Virtanen, P. et al. 2020, Nature Methods 17, 261 (SciPy).
- Widger, W. K. & Woodall, M. P. 1976, Bull. Amer. Meteor. Soc. 57, 1217.
- Published values compared with (Agol et al. 2021; Jahandar et al. 2024; King et al. 2010; Luhman et al. 2024; Rodriguez et al. 2013): see [DATA_AND_RESOURCES.md](../DATA_AND_RESOURCES.md).
