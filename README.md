# Cold Movers

**Watch the SPHEREx sky move, and measure how cold things are.**

NASA Space Apps Challenge 2026 · Challenge: *Planet X and SPHEREx* · Team: Cold Movers (Honduras)

Enter sky coordinates, a star name, or pick one of the five challenge objects. Cold Movers:

1. asks NASA/IPAC IRSA for **every SPHEREx image covering that spot** (Data Release 1 + Quick Release 3),
2. downloads small cutouts, **aligns them on the same patch of sky** and plays them as a **movie, visit by visit**, one per detector, so anything that moves or varies stands out,
3. **follows the object's proper motion** and measures it in every image to build its **0.75–5 µm spectrum**,
4. runs the **Madhava engine**, a band-integrated Planck fit that gives a *blackbody-equivalent temperature* with an uncertainty and a **traffic light** that says how far to trust it,
5. runs three **"Is it real?"** checks: seen again in another visit, clean pixels, and moves as the catalogue predicts.

**Live app: https://cold-movers.streamlit.app**

Every result can be shared as a link (`?object=wise0855` or `?ra=..&dec=..`) and downloaded as CSV or GIF.

## Why a blink comparator?

In 1930 Clyde Tombaugh found Pluto at Lowell Observatory, during the search for "Planet X", by blinking two photographs of the same sky taken days apart: whatever jumps between them is moving. Cold Movers is a digital blink comparator for SPHEREx. Cold brown dwarfs such as WISE 0855 are invisible to the eye; only infrared light and their motion give them away.

## How it works

| Step | What we do | Why |
|---|---|---|
| Search | IRSA Simple Image Access (collections `spherex_dr1`, `spherex_qr3`); TAP on `spherex.plane` as fallback | Uses NASA's archive directly, so new releases appear automatically |
| Cutouts | IRSA cutout service (`?center=RA,DEC&size=DEG`) around the position **propagated to each image's date** | Barnard's Star moves 10.4″/yr: a year-2000 position is 44 SPHEREx pixels off by 2026 |
| Movie | Each cutout is resampled onto one tangent-plane grid with its own WCS; images of the same detector taken during one visit (gap > 20 days) are averaged | SPHEREx's linear variable filters change wavelength across each detector, so raw frames flicker in colour; per-detector visit stacks are stable and make motion visible, in the spirit of WiseView |
| Photometry | 2.5-pixel aperture, background from a 5–9 pixel ring, FLAGS-based pixel rejection, MJy/sr × pixel solid angle → µJy | The wavelength of each measurement comes from the image's own spectral WCS (`WCS-WAVE`) at the target's pixel |
| Madhava engine | Free temperature and scale; each band integrated exactly with the series *F(0→λ) = (15/π⁴) Σ e^(−nx)(x³/n + 3x²/n² + 6x/n³ + 6/n⁴)*, x = hc/λkT; 8 % systematic floor; uncertainty from the χ² profile, inflated when χ²/dof > 1 | SPHEREx bands are wide (R ≈ 35–130); integrating the curve over each band is more faithful than sampling it at the centre |
| Traffic light | 🟢 Planck peak inside SPHEREx coverage (≈580–3860 K) and one blackbody fits; 🟡 measured but not a single blackbody (molecular bands, disk, variability) or peak outside coverage; 🔴 no reliable temperature (too faint, saturated, or edge of range) | The tool says when not to trust it |

"Madhava" is a homage to Madhava of Sangamagrama (c. 1340–1425), a pioneer of infinite series. The series itself is standard physics (Widger & Woodall 1976), not a new result.

## Honest limits

- **Blackbody-equivalent is not effective temperature.** Brown dwarfs have deep water and methane bands; a single Planck curve does not describe them, and the traffic light turns yellow. We show the published temperature next to ours.
- **Very bright stars saturate SPHEREx.** Barnard's Star overflows the detector in every image: its motion is visible in the movie, but its brightness cannot be measured, and the app says so.
- **Aperture photometry, not PSF fitting.** A constant aperture loss does not change the temperature (free scale), but crowded fields can blend neighbours.
- **Variable objects** (R Draconis, RW Aurigae) change between visits; one fit over all visits mixes epochs.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The five challenge objects are precomputed by GitHub Actions (`.github/workflows/precompute.yml`, `scripts/precompute.py`) so the public demo loads instantly; any other position is processed live.

## Tests

```bash
pip install pytest
python -m pytest -q
```

Tests check the series against numerical integration of Planck's law (to 1e-8), the classic 25 % of energy below the Wien peak, recovery of known temperatures from synthetic spectra, the traffic light, aperture photometry, proper-motion propagation and the "Is it real?" checks.

## Data and references

- SPHEREx Data Release 1 spectral images, NASA/IPAC Infrared Science Archive, doi:10.26131/IRSA678; SPHEREx Quick Release 3.
- *The SPHEREx image and spectrophotometry processing pipeline*, ApJS 285, 67 (2026), doi:10.3847/1538-4365/ae8843, arXiv:2511.15823.
- IRSA tutorials (BSD-3): "Introduction to SPHEREx Spectral Images", "Download a collection of SPHEREx Spectral Image cutouts".
- Widger, W. K. & Woodall, M. P. 1976, *Integration of the Planck blackbody radiation function*, Bull. Amer. Meteor. Soc. 57, 1217.
- SIMBAD astronomical database and Sesame name resolver (CDS, Strasbourg) for positions, proper motions and parallaxes; Gaia DR3 (Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1) through SIMBAD.
- Published temperatures for comparison: Jahandar et al. 2024 (Barnard's Star, arXiv:2310.12125); King et al. 2010 (ε Indi Ba/Bb, arXiv:0911.3143); Luhman et al. 2024 (WISE 0855−0714, arXiv:2311.17316); Rodriguez et al. 2013 (RW Aur disk, arXiv:1308.2017).
- Inspiration for the movie view: WiseView (Caselden et al. 2018), used by the Backyard Worlds: Planet 9 citizen-science project.
- Software: Astropy, Astroquery, PyVO, NumPy, SciPy, Matplotlib, Pillow, Plotly, Streamlit.

This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration.

Not an official NASA product.

## AI use

The team (Wilmer Espinoza, Miguel Eduardo Romero Sánchez) defined the idea, the method and the checks. We used Claude (Anthropic) as a coding assistant to write and test code, search documentation and draft English text. Every Python file carries a note saying it was AI-assisted. Commits made with the assistant are marked with a `Co-Authored-By: Claude` trailer.

## License

MIT, see [LICENSE](LICENSE).
