# Limitations and uncertainty

## Motion

| Limitation | Size | Where it shows |
|---|---|---|
| Baseline of about one year (3-6 visits) | motion below ~0.5 px/yr (≈3″/yr) cannot be confirmed; at 2″/yr recall is 0.04 | `BENCHMARK_RESULTS.md`, TRAPPIST-1 trajectory (1.1 ± 1.0″/yr, not significant) |
| Visit-to-visit match radius 4 px | fast movers (40″/yr) recovered less often (recall 0.26 at S/N 15) | benchmark |
| Flux-weighted centroids, not PSF fits | crowding biases positions; a mover 2-4 px from a star can pull the star's centroid | benchmark; fixed for detected movers by the neighbour-pull rule, open for movers below 6σ (9 false confirmations in 216 trials at S/N 5 near stars) |
| Alignment between visits trusted only when still stars line up (median shift ≤ 0.5 px) | saturated halos (Barnard's Star, R Draconis) and sparse long-wavelength fields leave detectors untrusted | scoreboard's failed check (very red movers, 28 %) |
| Position uncertainty model | per position: 0.12 px alignment ⊕ 0.9 px / S/N; when the scatter exceeds it, trajectory errors are scaled by √χ²ᵣ | trajectory panel |
| Blind-search speed uncertainty | approximated as speed / significance | evidence records |
| Parallax not modelled | at each object's own visit dates, parallax shifts the position by at most 1.09″ (0.18 px, Barnard's Star) between visits and biases the straight-line motion by at most 0.19″/yr (Epsilon Indi B), below every motion uncertainty | `docs/parallax_effect.md` (`scripts/parallax_effect.py`) |
| Bright movers passing stars (held-out finding) | in held-out set A at S/N 30, 6 false confirmations in 173 trials (precision 0.93, interval 0.85–0.97, below the development 0.98). Each sat 0.02–0.87 px from a star; in most of them the injected mover itself was not confirmed, so the neighbour-pull rule, which compares two movers, could not act | `VALIDATION_METRICS.md`; not fixed: a fix must be tested on a new set |

## Light and temperature

| Limitation | Effect |
|---|---|
| Aperture photometry (2.5 px aperture, 5-9 px sky ring); no PSF photometry | neighbours inside the ring bias fluxes; blends are flagged and excluded, not deblended |
| Saturation | saturated cores are excluded; Barnard's Star, RW Aurigae and R Draconis get no temperature (red light) |
| Blackbody-equivalent temperature | describes the shape of the measured infrared light; not an effective temperature. Molecular bands make cool atmospheres "not a single blackbody" (yellow) |
| Coverage | 0.75-5 µm: objects colder than about 580 K peak beyond 5 µm and get a red light (WISE 0855) |
| Fit uncertainty | contiguous χ² region with Δχ² = max(1, χ²/dof) and an 8 % flux floor; the series itself contributes a guaranteed error below 10⁻¹² (Madhava's correction) |
| No independent photometric calibration | SPHEREx fluxes are not compared with 2MASS or WISE in this project |
| Variability | needs ≥ 2 visits with ≥ 4 points; "possibly" between 3σ and 5σ; saturated stars use the light in the wings |

## Data and service

* Frozen results for six objects; a live search depends on IRSA (which returned 502 errors on the night of Nov 14-15).
* Gaia and SIMBAD calls have time limits; when they fail the page says so and the SPHEREx measurements are unaffected.
* SPHEREx DR1 and QR3 are the releases available on Nov 15, 2026; a new release is a one-line change.

## When the answer is CANDIDATE or INCONCLUSIVE

| Situation | Verdict | Example |
|---|---|---|
| Motion seen in one detector only, or a brighter mover passes within 4 px | CANDIDATE | WISE 0855 (detector 5 only) |
| Fewer than two detectors can be trusted (saturated halo, too few still stars) | INCONCLUSIVE | R Draconis (0 of 6 trusted) |
| Saturated, too faint, too narrow a wavelength range, or uncertainty above 50 % | temperature INCONCLUSIVE | Barnard's Star, RW Aurigae, R Draconis, WISE 0855 |

## What is never claimed

No discovery, no "Planet X", no water detection, no real (effective) temperature, no confirmation of a source as
real by the consistency checks (they are indicators).
