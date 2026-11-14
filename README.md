# Cold Movers

**Watch the SPHEREx sky move, and measure how cold things are.**

NASA Space Apps Challenge 2026 · Challenge: *Planet X and SPHEREx* · Team: Cold Movers (Honduras)

Enter sky coordinates (or pick one of the five challenge objects) and Cold Movers:

1. asks NASA/IPAC IRSA for every SPHEREx image covering that spot (DR1 + QR3),
2. downloads small cutouts, aligns them on the same sky grid and plays them as a **movie by epoch**, one per detector, so anything that moves or varies stands out,
3. measures the object in every image (following its proper motion) to build its **0.75–5 µm spectrum**,
4. runs the **Madhava engine**: a band-integrated Planck fit that gives a *blackbody-equivalent temperature* with an uncertainty and a traffic light that says how far to trust it.

> Work in progress during the hackathon (Nov 14–15, 2026).

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Tests

```bash
pip install pytest
python -m pytest -q
```

## Data and references

- SPHEREx Data Release 1 spectral images, NASA/IPAC Infrared Science Archive, doi:10.26131/IRSA678; SPHEREx Quick Release 3.
- IRSA tutorials (BSD-3): "Introduction to SPHEREx Spectral Images", "Download a collection of SPHEREx Spectral Image cutouts".
- Blackbody fraction series: Widger, W. K. & Woodall, M. P. (1976), *Bull. Amer. Meteor. Soc.* 57, 1217.
- SIMBAD astronomical database (CDS, Strasbourg) for positions, proper motions and parallaxes.
- Inspiration for the movie view: WiseView (Caselden et al.), used by Backyard Worlds: Planet 9.
- Software: Astropy, Astroquery, PyVO, NumPy, SciPy, Matplotlib, Pillow, Plotly, Streamlit.

This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration.

## AI use

The team (Wilmer Espinoza, Miguel Eduardo Romero Sánchez) defined the idea, the method and the checks. We used Claude (Anthropic) as a coding assistant to write and test code, search documentation and draft English text. Every code file carries a note saying it was AI-assisted. Commits made with the assistant are marked with a `Co-Authored-By: Claude` trailer.

## License

MIT, see [LICENSE](LICENSE).
