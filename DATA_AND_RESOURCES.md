# Data, resources and tools used by Cold Movers

Complete inventory of everything external that Cold Movers uses, how we use it, its licence or terms, and the attribution it asks for. NASA Space Apps Challenge 2026, team Cold Movers.

The project's own code is released under the MIT licence (see [LICENSE](LICENSE)). That licence covers only our code; every third-party item below keeps its own licence or terms. The licence of every installed package, read from its own metadata on GitHub Actions, is in [docs/licenses.md](docs/licenses.md); where each method and component comes from is in [evidence/ORIGINALITY_AND_PROVENANCE.md](evidence/ORIGINALITY_AND_PROVENANCE.md).

## 1. Original data (not ours)

| Resource | Link | How we use it | Licence / terms | Attribution |
|---|---|---|---|---|
| SPHEREx Data Release 1, spectral images (NASA/JPL-Caltech, NASA/IPAC IRSA) | https://doi.org/10.26131/IRSA678 | Searched (SIA2 / TAP) and downloaded as small cutouts for every position; images, FLAGS, VARIANCE and WCS-WAVE layers feed the movie, photometry and spectrum | Public NASA data; acknowledgement requested | SPHEREx acknowledgement and IRSA acknowledgement below; cite the DOI |
| SPHEREx Quick Release 3, spectral images (NASA/IPAC IRSA) | https://irsa.ipac.caltech.edu/Missions/spherex.html | Same as DR1, for the most recent visits | Public NASA data; acknowledgement requested | Same as above |
| NASA/IPAC Infrared Science Archive (IRSA) services: SIA2, TAP, cutout service | https://irsa.ipac.caltech.edu | Finding and cutting the SPHEREx images | Public service; acknowledgement requested | IRSA acknowledgement below |
| NASA Exoplanet Archive (NASA/IPAC) | https://exoplanetarchive.ipac.caltech.edu | Published effective temperature of TRAPPIST-1 (Agol et al. 2021), for comparison only | Public NASA service; acknowledgement requested | "This research has made use of the NASA Exoplanet Archive, which is operated by the California Institute of Technology, under contract with the National Aeronautics and Space Administration under the Exoplanet Exploration Program." |
| Gaia Data Release 3 (ESA, Gaia/DPAC) | https://www.cosmos.esa.int/web/gaia/dr3 | Parallax (distance) of the challenge objects in the precompute; Gaia DR3 stars drawn over the SPHEREx image, and the check that a mover is a known Gaia star with the same motion (ESA Gaia archive) | CC BY-SA 3.0 IGO | Gaia acknowledgement below; Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1 |
| SIMBAD astronomical database (CDS, Strasbourg) | https://simbad.cds.unistra.fr | Positions, proper motions and parallaxes by object name | Free use with acknowledgement (CDS terms) | "This research has made use of the SIMBAD database, operated at CDS, Strasbourg, France" (Wenger et al. 2000, A&AS 143, 9) |
| Sesame name resolver (CDS) and its Harvard mirror | https://cds.unistra.fr/cgi-bin/Sesame | Backup name lookup when SIMBAD's TAP service is down | Free use with acknowledgement (CDS terms) | Credited with SIMBAD/CDS |

## 2. Scientific references (facts and equations, no text or images copied)

| Reference | How we use it |
|---|---|
| Widger, W. K. & Woodall, M. P. 1976, *Bull. Amer. Meteor. Soc.* 57, 1217 | Series for the fraction of blackbody energy below a wavelength (Madhava engine) |
| *The SPHEREx image and spectrophotometry processing pipeline*, ApJS 285, 67 (2026), doi:10.3847/1538-4365/ae8843, arXiv:2511.15823 | Meaning of the SPHEREx data layers and flags |
| Agol et al. 2021, Planet. Sci. J. 2, 1, arXiv:2010.01074 (via the NASA Exoplanet Archive) | Published effective temperature of TRAPPIST-1, 2,566 ± 26 K (comparison only) |
| Jahandar et al. 2024, arXiv:2310.12125 | Published temperature of Barnard's Star (comparison only) |
| King et al. 2010, A&A, arXiv:0911.3143 | Published temperatures of Epsilon Indi Ba and Bb (comparison only) |
| Luhman et al. 2024, AJ, arXiv:2311.17316 | Published temperature of WISE 0855−0714 (comparison only) |
| Rodriguez et al. 2013, AJ, arXiv:1308.2017 | RW Aurigae's disk (context only) |
| Caselden et al. 2018 (WiseView); Backyard Worlds: Planet 9 | Inspiration for the blinking movie; no code used. WiseView is linked from the app |
| Clyde Tombaugh's 1930 discovery of Pluto with a blink comparator (Lowell Observatory) | Historical context in the app and README |

## 3. Tutorials and documentation

| Resource | Licence | How we use it |
|---|---|---|
| IRSA tutorial notebooks: "Introduction to SPHEREx Spectral Images", "Download a collection of SPHEREx Spectral Image cutouts" (https://caltech-ipac.github.io/irsa-tutorials/) | BSD-3-Clause | We followed their documented approach (SIA2 collections, cutout URL syntax, reading wavelength from the WCS-WAVE layer); our code was written for this project |
| SPHEREx archive documentation (https://caltech-ipac.github.io/spherex-archive-documentation/) | Public documentation | Collection names, data release status, FLAGS bit meanings |

## 4. Software libraries

| Software | Licence | How we use it |
|---|---|---|
| Python 3.12 | PSF License | Language |
| NumPy | BSD-3-Clause | Arrays and numerics |
| SciPy | BSD-3-Clause | Optimisation, image resampling, special functions |
| pandas | BSD-3-Clause | Tables in the app |
| Astropy | BSD-3-Clause | FITS files, world coordinate systems, time |
| Astroquery | BSD-3-Clause | IRSA, SIMBAD and Gaia queries |
| PyVO | BSD-3-Clause | Virtual Observatory protocols (dependency of Astroquery) |
| Requests | Apache-2.0 | Downloading cutouts |
| Matplotlib | Matplotlib License (BSD-style) | Movie frames, difference image |
| Pillow | MIT-CMU (HPND) | Animated GIFs |
| Plotly | MIT | Interactive spectrum, residuals, light curve |
| Streamlit | Apache-2.0 | Web application |
| Aladin Lite (CDS) | External page only | The app links to it to explore the wider sky; nothing is embedded or downloaded |
| pytest | MIT | Unit tests |
| Playwright | Apache-2.0 | Opening the app on a schedule so it stays awake, and the screenshot robot that checks the live app |

## 5. Services

| Service | Terms | How we use it |
|---|---|---|
| GitHub | GitHub Terms of Service | Code hosting |
| GitHub Actions | GitHub Terms of Service | Running the tests, precomputing the five challenge objects, keeping the app awake |
| Streamlit Community Cloud | Streamlit terms | Public hosting of the app at https://cold-movers.streamlit.app |
| Claude (Anthropic) | Anthropic terms | AI coding assistant (see README, "AI use") |
| Gemini (Google) | Google terms | Generated the team logo only; the logo carries a visible "AI-generated image (Gemini)" mark (see README, "AI use") |

## 6. Products we generated (derived from the data above)

Everything in `data/precomputed/` (movie GIFs, epoch stacks, photometry tables, result files) and everything the app shows (movies, spectra, temperatures, light curves, checks) is **derived** by our code from the SPHEREx images and the catalogues above. They are not original NASA products and are not endorsed by NASA. The acknowledgements of the original data apply to them. Our code and these derived files are released under MIT.

## 7. Images, fonts and audio

The app contains no third-party images, fonts or audio: all graphics are generated from data by our code, and the text uses the default Streamlit fonts. No NASA logos or mission insignia are used. Our team logo ([docs/logo_ai_marked.png](docs/logo_ai_marked.png), also on the Space Apps team page) was generated with Gemini (Google) and carries a visible "AI-generated image (Gemini)" mark; it is not used inside the app.

## Required acknowledgements (verbatim)

**SPHEREx:** This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration.

**NASA Exoplanet Archive:** This research has made use of the NASA Exoplanet Archive, which is operated by the California Institute of Technology, under contract with the National Aeronautics and Space Administration under the Exoplanet Exploration Program.

**IRSA:** This research has made use of the NASA/IPAC Infrared Science Archive, which is funded by the National Aeronautics and Space Administration and operated by the California Institute of Technology.

**Gaia:** This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC has been provided by national institutions, in particular the institutions participating in the Gaia Multilateral Agreement.


**CDS:** This research has made use of the SIMBAD database and the Sesame name resolver, operated at CDS, Strasbourg, France.
