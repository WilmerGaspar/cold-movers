"""List the SPHEREx collections IRSA offers today, to see whether a newer release exists (GitHub Actions).

Compares them with the collections the app is configured to use (coldmovers.spherex.COLLECTIONS).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coldmovers.spherex import COLLECTIONS  # noqa: E402

found = set()
try:
    from astroquery.ipac.irsa import Irsa

    for servicetype in ("SIA", None):
        try:
            cols = Irsa.list_collections(servicetype=servicetype) if servicetype else Irsa.list_collections()
            names = [str(n) for n in cols["collection"]]
            found |= {n for n in names if "spherex" in n.lower()}
            print(f"list_collections({servicetype}): {len(names)} collections, spherex: {sorted(n for n in names if 'spherex' in n.lower())}")
        except Exception as exc:
            print(f"list_collections({servicetype}) failed: {type(exc).__name__}: {exc}")
except Exception as exc:
    print("astroquery Irsa import failed:", exc)

try:
    import pyvo

    tap = pyvo.dal.TAPService("https://irsa.ipac.caltech.edu/TAP")
    res = tap.run_sync("SELECT DISTINCT obs_collection FROM spherex.obscore")
    names = sorted(str(r["obs_collection"]) for r in res)
    print("TAP spherex.obscore obs_collection:", names)
    found |= set(names)
except Exception as exc:
    print("TAP obscore query failed:", type(exc).__name__, exc)

print("configured in the app:", list(COLLECTIONS))
print("offered by IRSA:", sorted(found))
print("NEW, not used by the app:", sorted(set(found) - set(COLLECTIONS)) or "none")
