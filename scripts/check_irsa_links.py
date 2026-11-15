"""Check that the original SPHEREx files cited by Cold Movers still open at NASA/IPAC IRSA (GitHub Actions).

For every frozen object, five image URLs from the `url` column of photometry.csv (first, last and three in
between) are opened as small cutouts (the app's own request), and the answer must be a FITS file. The IRSA
image search (SIA2) is queried for one position, and the DOI of SPHEREx DR1 must resolve.
Prints a Markdown table. Exit code 1 if any cited file or the DOI fails. The two search services (SIA2 and TAP)
are reported too, as service availability: they are not cited by any result, and IRSA answers 502 when busy.
"""

import csv
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE = os.path.join(ROOT, "data", "precomputed")
HEADERS = {"User-Agent": "ColdMovers-link-check"}

rows, failures = [], 0


def check(label, url, want_fits=False, informational=False):
    global failures
    t = time.time()
    tries = []
    for attempt in range(4):  # IRSA answers 502/503 when busy; the app retries the same way
        try:
            r = requests.get(url, headers=HEADERS, timeout=90, allow_redirects=True)
            ok = r.status_code == 200 and (not want_fits or r.content[:6] == b"SIMPLE")
            note = f"HTTP {r.status_code}, {len(r.content):,} bytes" + (", FITS" if r.content[:6] == b"SIMPLE" else "")
        except Exception as exc:  # report every failure; nothing is hidden
            ok, note = False, f"{type(exc).__name__}: {exc}"
        tries.append(note.split(",")[0])
        if ok or "HTTP 4" in note:
            break
        time.sleep(10 * (attempt + 1))
    if len(tries) > 1:
        note += f" (attempts: {' → '.join(tries)})"
    failures += (not ok) and not informational
    status = "OK" if ok else ("UNAVAILABLE (service, not a cited file)" if informational else "FAILED")
    rows.append((label, status, note, f"{time.time() - t:.1f} s", url))


for key in sorted(os.listdir(PRE)):
    path = os.path.join(PRE, key, "photometry.csv")
    if not os.path.exists(path):
        continue
    with open(path) as fh:
        data = [r for r in csv.DictReader(fh) if r.get("url")]
    picks = sorted({0, len(data) - 1, len(data) // 4, len(data) // 2, 3 * len(data) // 4})
    for i in picks:
        r = data[i]
        url = f"{r['url']}?center={float(r['ra']):.6f},{float(r['dec']):.6f}&size=0.01"
        check(f"{key}: image {i + 1} of {len(data)} (D{r['detector']}, MJD {float(r['mjd']):.1f})", url, want_fits=True)

check("IRSA SIA2 search (spherex_dr1, TRAPPIST-1)",
      "https://irsa.ipac.caltech.edu/SIA?COLLECTION=spherex_dr1&POS=circle+346.6264+-5.0434+0.001&RESPONSEFORMAT=VOTABLE",
      informational=True)
check("IRSA TAP (the app's fallback search, spherex.plane)",
      "https://irsa.ipac.caltech.edu/TAP/sync?LANG=ADQL&FORMAT=csv&QUERY=SELECT+TOP+1+planeid+FROM+spherex.plane",
      informational=True)
check("DOI of SPHEREx DR1 (doi:10.26131/IRSA678)", "https://doi.org/10.26131/IRSA678")

print(f"# IRSA link check ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})\n")
ok_n = sum(r[1] == "OK" for r in rows)
print(f"{ok_n} of {len(rows)} links OK; cited files and DOI failing: {failures}.\n")
print("| Link | Result | Answer | Time | URL |\n|---|---|---|---|---|")
for label, res, note, dt, url in rows:
    print(f"| {label} | {res} | {note} | {dt} | {url} |")
sys.exit(1 if failures else 0)
