# Pre-registration of the calibration tests

Written and committed on Nov 15, 2026 **before** any of these tests was run on its real inputs. The code is
`scripts/calibration.py` at the commit that adds this file. Before this commit it was run once with tiny,
throwaway inputs (`--smoke`, output discarded unread), only to check that it runs.

## Question

Are Cold Movers' quoted uncertainties honest? A result with an error bar is only as good as the error bar.

## Tests

1. **Real-star null test.** This test uses real SPHEREx data and no simulation.
   - **Input:** every track that `movers.search` follows in a *trusted* detector of the six frozen fields, except
     those within 3 px of the target's first-visit position. Nearly all field stars move far less than a pixel a
     year, so for them the measured "motion" is noise.
   - **Positions:** for tracks with three or more visits, the residuals from a straight line are divided by
     σ_pos = √(0.12² + (0.9 / S/N)²) px per axis and corrected for leverage. If the error model is right they
     follow N(0, 1). Statistics: the robust scale *k* = 1.4826 × MAD (primary), the RMS, and the fraction
     within 1σ and 2σ.
   - **Significance:** the fraction of still-star tracks with motion significance ≥ 3 (the per-detector
     candidate level) and ≥ 5. If the model were exact and the significance used the slope uncertainty, at
     most e^(−4.5) = 1.1 % and e^(−12.5) = 0.0004 % would pass. The significance actually uses the
     first-to-last shift uncertainty (√2 σ_pos), which is larger whenever there are more than two visits, so
     a calibrated model should give fewer crossings than this.
2. **Injection pulls.**
   - **Input:** confirmed injected movers (all six detectors). The quoted velocity uncertainty is
     speed / significance.
   - **Statistic:** pull = |measured − true velocity| / that uncertainty. If calibrated, the pulls follow a
     Rayleigh distribution of scale 1: *k* = √(mean(pull²) / 2) ≈ 1, with 68.3 % below 1.515 and 95.4 % below
     2.486.
   - **Sets:** *estimated* on the development set (seed 2026, the 3,300 trials) and *checked* on held-out set A
     (seed 20261115). Both are re-run with the per-trial output switched on; their summary numbers must not
     change.
3. **Temperature interval coverage.**
   - **Input:** synthetic blackbodies at 800, 1,200, 1,800, 2,500 and 3,200 K, observed with TRAPPIST-1's real
     clean SPHEREx bands (237 points) and its real relative errors. There are 60 spectra per temperature,
     seed 20261116.
   - **Two noise models:** (a) the measurement errors only; (b) the measurement errors plus the 8 % floor
     that the fit assumes.
   - **Statistic:** the fraction of fits whose interval [T_low, T_high] contains the true temperature.
     Expected: about 68 % in (b), and more in (a), because the floor then makes the interval conservative.

## How the results will be read (fixed now)

- **Calibrated** if the scale *k* lies between **0.8 and 1.25**. Above 1.25 the uncertainties are too small;
  below 0.8 they are too large, which is conservative.
- **Temperature coverage** in case (b) between **58 % and 78 %** counts as calibrated.
- **In this release no threshold, no detection decision and no displayed number is changed because of these
  tests.** The scales are published next to the uncertainties they concern, together with what they imply.
  For example, if *k* = 1.5 the quoted motion errors should be read as 1.5 times larger. Adopting a
  correction in the code is a later change that must be checked on new data.
- Every result is published, whatever it is.
