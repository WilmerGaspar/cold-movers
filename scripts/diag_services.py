"""Check from GitHub Actions that the external services used by the atlas answer.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.
"""
import time
import traceback

import requests

URL = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits"
params = {"hips": "CDS/P/allWISE/color", "width": 480, "height": 480, "fov": 0.1, "projection": "TAN",
          "coordsys": "icrs", "ra": 133.7602, "dec": -7.2436, "format": "jpg"}
t = time.time()
try:
    r = requests.get(URL, params=params, timeout=60)
    print("hips2fits:", r.status_code, r.headers.get("content-type"), len(r.content), "bytes",
          f"{time.time() - t:.1f}s", r.url)
    if r.status_code != 200:
        print(r.text[:600])
except Exception:
    print("hips2fits failed:\n" + traceback.format_exc())

t = time.time()
try:
    from astroquery.gaia import Gaia

    job = Gaia.launch_job("SELECT TOP 5 source_id, ra, dec FROM gaiadr3.gaia_source WHERE "
                          "1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', 133.76, -7.24, 0.05))")
    print("gaia:", len(job.get_results()), "rows", f"{time.time() - t:.1f}s")
except Exception:
    print("gaia failed:\n" + traceback.format_exc())
