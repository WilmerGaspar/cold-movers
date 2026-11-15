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
| Catalogue prediction | linear proper motion; parallax ignored (≤ 0.55″ for Barnard's Star, < 0.1 px) | — |

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

## What is never claimed

No discovery, no "Planet X", no water detection, no real (effective) temperature, no confirmation of a source as
real by the consistency checks (they are indicators).
