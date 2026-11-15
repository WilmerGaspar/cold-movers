# Competitive analysis

Rule followed: only capabilities that could be verified in public documentation are listed. From this audit's
environment, only the SkyShift repository at https://github.com/Nsa-2026/skyshift could be opened (its README,
read on Nov 15, 2026). The other repositories named in the brief (cucuradu/skyshift, ESuperCode/squeeze_test,
ayoubna99/spherex-skyshift, ahmedm12j/spherex-time-machine) could not be opened from here, so **nothing is
claimed about them**; their rows are left for a manual review with the repository open.

## SkyShift (Nsa-2026/skyshift), from its README

The two columns describe different tests on different data with different pass rules. **They are not
comparable and no ranking is implied**: a larger number of checks or a higher pass count says nothing about
which tool works better. A fair comparison would need both tools run on the same fields with the same
injections, which has not been done.

| Area | SkyShift (as documented) | Cold Movers |
|---|---|---|
| Moving objects, months | Visits compared; motion compared with Gaia (Barnard +5.5 %) | Blind search (Barnard −5 %, Epsilon Indi B −3 %), trajectory with uncertainty (Barnard 0.4σ), Gaia match requiring the same motion |
| Moving objects, hours | Exposures within a visit compared; 60 of 60 known asteroids recovered; 93 % of sessions with asteroids brighter than V 16, 0-1 % negative control | Not implemented |
| Thermal model | NEATM for asteroid diameters (1.06× published) | Madhava blackbody-equivalent temperatures for stars and brown dwarfs (TRAPPIST-1 −4 %), traffic light |
| Photometric calibration | SPHEREx ÷ 2MASS Ks = 1.010, ÷ WISE W1 = 0.994 | Not done |
| Community | Flag and vote on candidates (Firestore), CSV export, MCP server | CSV export of movers; no voting, no MCP |
| Validation summary | Scoreboard: 8 pass, 1 partial, 2 cut | Scoreboard: 14 pass, 4 partial, 1 fail (19 checks), plus the blind benchmark (3,300 trials) |
| Injection tests | Not described in the README | Yes (scoreboard campaign and blind benchmark with precision and recall) |
| Variability | Not described for R Draconis ("no spectrum yet") | R Draconis 0.57 mag at 9.6σ |
| Plain-language explanations | Not described | Panel written from the measurements, glossary |

### What SkyShift does better
Asteroids within a visit; an independent photometric calibration; community tools.

### What it does differently
Two time scales; a thermal model for asteroids rather than stars.

### Opportunities it leaves open (from its own README)
Its hunt for unknown movers was not finished when read; no injection-based detection limits are described.

### What we could legitimately improve
Photometric calibration against 2MASS / WISE for unsaturated stars; a within-visit search for asteroids. Neither is
copied here, and neither was attempted in this audit.

## Others (not verifiable from this environment)

| Project | Status of this analysis |
|---|---|
| SkyShift (cucuradu) | not opened; may be the same project as Nsa-2026/skyshift; check manually |
| Planet X Explorer (ESuperCode/squeeze_test) | not opened |
| SkyShift NGDev (ayoubna99/spherex-skyshift) | not opened |
| SPHEREx Time Machine (ahmedm12j/spherex-time-machine) | not opened |
