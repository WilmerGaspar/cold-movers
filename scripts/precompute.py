"""Precompute results for the five challenge objects (runs on GitHub Actions).

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.

The public app shows these results instantly, so the demo works even when IRSA is
busy; any other coordinates are processed live in the app.

Usage: python scripts/precompute.py --objects all --max-frames 300
"""

import argparse
import json
import os
import sys
import time
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coldmovers import pipeline, spherex  # noqa: E402
from coldmovers.targets import SHOWCASE, SIMBAD_IDS, gaia_parallax, resolve_simbad  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "precomputed")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def probe_header(target):
    """Print the structure of one cutout, to verify assumptions about the files."""
    from astropy.io import fits
    import io

    ra, dec = target.position_at(pipeline.year_to_mjd(pipeline.SEARCH_YEAR))
    rows = spherex.search_images(float(ra), float(dec))
    log(f"probe: {len(rows)} images; first url: {rows[0]['url'] if rows else None}")
    if not rows:
        return
    data = spherex.fetch_bytes(spherex.cutout_url(rows[0]["url"], float(ra), float(dec), 0.05))
    with fits.open(io.BytesIO(data)) as hdul:
        for h in hdul:
            log(f"probe: HDU {h.name} shape={getattr(h.data, 'shape', None)}")
        hdr = hdul[1].header
        keys = [k for k in hdr.keys() if k and not k.startswith(("A_", "B_", "AP_", "BP_"))]
        log("probe: IMAGE header keys: " + ", ".join(keys[:120]))
        for k in ("BUNIT", "DATE", "MJD-AVG", "MJD-BEG", "MJD-END", "DETECTOR", "VERSION", "CTYPE1", "CTYPE1W", "PSCALE"):
            if k in hdr:
                log(f"probe: {k} = {hdr[k]}")
        log(f"probe: primary VERSION = {hdul[0].header.get('VERSION')}")
    frame = spherex.parse_cutout(data, rows[0])
    x, y = frame.wcs.world_to_pixel_values(float(ra), float(dec))
    log(f"probe: target pixel ({float(x):.1f}, {float(y):.1f}) wavelength {frame.wavelength_at(float(x), float(y))}"
        f" pixel_sr {frame.pixel_sr:.3e}")


def summarize(result):
    by_det = {}
    for r in result.rows:
        d = by_det.setdefault(r["detector"], {"n": 0, "clean": 0, "snr": []})
        d["n"] += 1
        if r["inside"] and not r["hard_flag"]:
            d["clean"] += 1
            if np.isfinite(r["snr"]):
                d["snr"].append(r["snr"])
    for det in sorted(by_det):
        s = by_det[det]
        med = np.median(s["snr"]) if s["snr"] else float("nan")
        log(f"   D{det}: {s['n']} images, {s['clean']} clean, median S/N {med:.1f}")
    log(f"   epochs: {[(round(e['mjd_start']), round(e['mjd_end']), e['n_frames']) for e in result.epochs]}")
    log(f"   fit: {json.dumps(pipeline.json_safe(result.fit.as_dict()))}")
    log(f"   timings: {result.timings}; failures: {len(result.failures)}; versions: {result.versions}")
    if result.failures:
        log(f"   first failure: {result.failures[0]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--objects", default="all")
    ap.add_argument("--max-frames", type=int, default=300)
    ap.add_argument("--size", type=float, default=pipeline.DEFAULT_SIZE_DEG)
    args = ap.parse_args()

    keys = list(SHOWCASE) if args.objects in ("all", "") else [k.strip() for k in args.objects.split(",")]
    os.makedirs(OUT, exist_ok=True)
    status = {}

    try:
        probe_header(SHOWCASE["barnard"])
    except Exception:
        log("probe failed:\n" + traceback.format_exc())

    for key in keys + ["__retry__"]:
        if key == "__retry__":
            # IRSA sometimes answers 502 for minutes: give failed objects one more chance.
            failed = [k for k in keys if not status.get(k, {}).get("ok")]
            if not failed:
                break
            log(f"=== retrying {failed} ===")
            time.sleep(60)
            keys_now = failed
        else:
            keys_now = [key]
        for key in keys_now:
            process(key, args, status)

    with open(os.path.join(OUT, "_status.json"), "w") as fh:
        json.dump(pipeline.json_safe(status), fh, indent=2, allow_nan=False)
    log("finished")


def process(key, args, status):
    """Resolve one challenge object, run the pipeline and save its results."""
    log(f"=== {key} ===")
    target = SHOWCASE[key]
    try:
        target = resolve_simbad(SIMBAD_IDS[key], key=key)
        fb = SHOWCASE[key]
        if key == "wise0855" and abs(target.pmra_masyr) < 1:
            log("   SIMBAD has no proper motion for WISE 0855; using literature values")
            target.pmra_masyr, target.pmdec_masyr = fb.pmra_masyr, fb.pmdec_masyr
        log(f"   SIMBAD: {json.dumps(target.to_dict())}")
    except Exception as exc:
        log(f"   SIMBAD failed ({exc}); using fallback values")
    try:
        g = gaia_parallax(target)
        if g:
            plx, err, sid = g
            log(f"   Gaia DR3 {sid}: parallax {plx:.4f} ± {err:.4f} mas (catalogue had {target.parallax_mas})")
            target.parallax_mas = plx
            target.source += f"; parallax from Gaia DR3 {sid}"
        else:
            log("   Gaia DR3: no precise parallax at this position (kept catalogue value)")
    except Exception as exc:
        log(f"   Gaia DR3 query failed ({exc}); kept catalogue parallax")
    try:
        result = pipeline.run(target, size_deg=args.size, max_frames=args.max_frames, workers=6,
                              progress=lambda s, f: None)
        summarize(result)
        pipeline.save(result, os.path.join(OUT, key))
        status[key] = {"ok": True, "fit": result.fit.as_dict(), "n_used": result.n_used,
                       "n_found": result.n_found}
    except Exception:
        tb = traceback.format_exc()
        log("   FAILED:\n" + tb)
        status[key] = {"ok": False, "error": tb[-1500:]}


if __name__ == "__main__":
    main()
