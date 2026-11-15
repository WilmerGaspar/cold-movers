# Reproducibility

## Environment

* Python 3.12. Pinned libraries in `requirements.txt` (Streamlit 1.45.1, NumPy 2.5.4, SciPy 1.18.1, Astropy 7.2.3,
  Astroquery 0.4.11, PyVO 1.10.0, Matplotlib 3.11.2, Pillow 11.3.0, Plotly 7.1.0, pandas 2.3.3, requests 2.34.2).
  `docs/pip_freeze.txt` records the exact environment GitHub Actions used.
* Data: SPHEREx DR1 and QR3 from NASA/IPAC IRSA. Frozen results for the six objects are in `data/precomputed/`
  (photometry with one IRSA URL per image, visit stacks, results); they were computed by `scripts/precompute.py`
  on GitHub Actions and are not modified by the app or by the benchmark.

## Commands

```bash
pip install -r requirements.txt

# 1. Unit tests (87): series against numerical integration and against Madhava's bound, fit, photometry,
#    checks, variability, movers (including the neighbour-pull rule), assistant, scoreboard rules
python -m pytest -q tests

# 2. The whole app, headless, for every frozen object (fails on any broken section)
python scripts/check_results.py
python scripts/smoke_app.py

# 3. Validation table and per-object evidence records (docs/validation.md, docs/validation_records.*)
python scripts/validation_report.py

# 4. Scoreboard with fixed pass rules (data/scoreboard.json, docs/scoreboard.md)
python scripts/scoreboard.py

# 5. Blind injection benchmark (about 2 minutes, fixed seed) and its tables
python scripts/benchmark_injection.py
python scripts/benchmark_report.py

# 6. Run the app
streamlit run app.py
```

To reproduce the "before" column of the benchmark, check out commit `ef5d02a` and run step 5 there.

## Automation on GitHub Actions (on every push to `main`)

| Workflow | What it does |
|---|---|
| `tests.yml` | unit tests; headless run of the whole app with the pinned libraries |
| `scoreboard.yml` | rebuilds the scoreboard with the app's code |
| `screenshots.yml` | validation records with the app's code, then checks and screenshots the live public app |
| `regen_gifs.yml` | re-renders the frozen movies from the stored stacks |
| `precompute.yml` | (manual only) recomputes the frozen results from IRSA |

## Determinism

The benchmark and the scoreboard's injection campaign use fixed random seeds (2026 and 7). Results computed in this
environment and on GitHub Actions were identical for the scoreboard; floating-point differences between NumPy
builds could change a borderline trial.
