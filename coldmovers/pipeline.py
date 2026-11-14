"""End-to-end run: coordinates -> SPHEREx images -> sky movie + spectrum + temperature.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import numpy as np

from . import checks, madhava, movie, photometry, spherex
from .targets import Target, mjd_to_year, year_to_mjd

DEFAULT_SIZE_DEG = 0.05  # 3 arcmin field of view
DEFAULT_MAX_FRAMES = 240
SEARCH_YEAR = 2025.9  # position used to ask IRSA which images cover the target


@dataclass
class RunResult:
    target: Target
    size_deg: float
    n_found: int
    n_used: int
    failures: list
    rows: list  # photometry, one dict per image
    fit: madhava.FitResult
    epochs: list
    ref_wcs: object
    shape: tuple
    versions: list
    timings: dict = field(default_factory=dict)

    def marker_pixels(self, mjd):
        ra, dec = self.target.position_at(mjd)
        x, y = self.ref_wcs.wcs_world2pix(ra, dec, 0)
        return float(x), float(y)

    def clean_rows(self):
        return clean_rows(self.rows)


def clean_rows(rows):
    return [r for r in rows if r["inside"] and not r["hard_flag"] and not r.get("blend")
            and np.isfinite(r["wavelength_um"]) and np.isfinite(r["flux_ujy"])]


MIN_WAVELENGTH_SPAN = 2.0  # longest / shortest usable wavelength needed for a temperature


def fit_rows(rows) -> madhava.FitResult:
    """Madhava fit on the clean measurements, with the reasons when the data limit it."""
    good = clean_rows(rows)
    fit = madhava.fit_temperature(
        [r["wavelength_um"] for r in good], [r["bandwidth_um"] for r in good],
        [r["flux_ujy"] for r in good], [r["err_ujy"] for r in good],
    )
    inside = [r for r in rows if r["inside"]]
    sat_frac = sum(bool(r.get("saturated")) for r in inside) / len(inside) if inside else 0.0
    if fit.light == "red":
        if sat_frac > 0.5:
            fit.reasons = ["too_bright"]
        return fit
    lam = np.array([r["wavelength_um"] for r in good])
    if lam.size and lam.max() / lam.min() < MIN_WAVELENGTH_SPAN:
        fit.light = "red"
        fit.reasons = ["narrow_coverage"] + (["too_bright"] if sat_frac > 0.3 else [])
        if lam.min() > 3.0:
            fit.reasons.append("only_long_wavelengths")
    elif sat_frac > 0.2:
        fit.reasons = list(fit.reasons) + ["partly_saturated"]
        if fit.light == "green":
            fit.light = "yellow"
            fit.reasons = [r for r in fit.reasons if r != "clean_blackbody_fit"]
    if any(r.get("blend") for r in inside):
        fit.reasons = list(fit.reasons) + ["neighbour_removed"]
    return fit


def run(target: Target, size_deg: float = DEFAULT_SIZE_DEG, max_frames: int = DEFAULT_MAX_FRAMES,
        workers: int = 12, progress=None) -> RunResult:
    def say(stage, frac):
        if progress:
            progress(stage, frac)

    t0 = time.time()
    say("Asking IRSA which SPHEREx images cover this position", 0.02)
    ra0, dec0 = target.position_at(year_to_mjd(SEARCH_YEAR))
    all_rows = spherex.search_images(float(ra0), float(dec0))
    t_search = time.time() - t0
    rows = spherex.select_spread(all_rows, max_frames)

    def centre(row):
        ra, dec = target.position_at(row["mjd"])
        return float(ra), float(dec)

    def dl_progress(done, total):
        say(f"Downloading SPHEREx cutouts ({done}/{total})", 0.05 + 0.75 * done / max(total, 1))

    t1 = time.time()
    # Download a margin around the field so the aligned (rotated) frames fill it completely.
    frames, failures = spherex.download_frames(rows, centre, size_deg * 1.45, workers=workers, progress=dl_progress)
    t_download = time.time() - t1

    say("Measuring the target in every image", 0.82)
    phot = []
    for f in frames:
        ra, dec = target.position_at(f.mjd)
        phot.append(photometry.measure_frame(f, float(ra), float(dec)))

    say("Aligning images and building the sky movie", 0.86)
    mid = float(np.median([f.mjd for f in frames])) if frames else year_to_mjd(SEARCH_YEAR)
    ra_c, dec_c = target.position_at(mid)
    ref_wcs, shape = movie.make_reference_wcs(float(ra_c), float(dec_c), size_deg)
    epochs = movie.build_epoch_stacks(frames, ref_wcs, shape)

    def marker(mjd):
        ra, dec = target.position_at(mjd)
        x, y = ref_wcs.wcs_world2pix(ra, dec, 0)
        return float(x), float(y)

    say("Checking for neighbouring sources", 0.93)
    checks.mark_blends(phot, epochs, {ep["index"]: ep["stacks"] for ep in epochs}, marker)

    say("Running the Madhava engine", 0.96)
    fit = fit_rows(phot)
    say("Done", 1.0)

    return RunResult(
        target=target, size_deg=size_deg, n_found=len(all_rows), n_used=len(frames),
        failures=failures, rows=phot, fit=fit, epochs=epochs, ref_wcs=ref_wcs, shape=shape,
        versions=sorted({f.version for f in frames if f.version}),
        timings={"search_s": round(t_search, 1), "download_s": round(t_download, 1),
                 "total_s": round(time.time() - t0, 1)},
    )


def track_points(marker, epochs, n: int = 25):
    """Predicted path across the visits (pixels), or None if it moves less than a pixel."""
    if not epochs:
        return None
    t0 = min(ep["mjd_start"] for ep in epochs) - 30
    t1 = max(ep["mjd_end"] for ep in epochs) + 30
    pts = [marker(t) for t in np.linspace(t0, t1, n)]
    if np.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 1.0:
        return None
    return pts


def epoch_title(ep, det, k, n):
    from astropy.time import Time

    date = Time(ep["mjd_mid"], format="mjd").iso[:10]
    return f"{date}   epoch {k + 1}/{n}\n{movie.detector_label(det)}   {ep['counts'].get(det, 0)} images"


# ----------------------------------------------------------------- save / load

PHOT_COLUMNS = ["mjd", "detector", "wavelength_um", "bandwidth_um", "flux_ujy", "err_ujy", "snr", "wing_ujy",
                "x", "y", "background", "inside", "hard_flag", "soft_flag", "saturated", "blend", "flag_bits",
                "ra", "dec", "url"]


def json_safe(obj):
    """Replace NaN and infinity by None so the files are valid JSON (null)."""
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return float(obj) if np.isfinite(obj) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def save(result: RunResult, outdir: str) -> dict:
    """Write result.json, photometry.csv, epoch stacks (npz) and GIFs to outdir."""
    import csv

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "photometry.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=PHOT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in result.rows:
            w.writerow({k: r.get(k) for k in PHOT_COLUMNS})

    stacks = {}
    for ep in result.epochs:
        for det, img in ep["stacks"].items():
            stacks[f"e{ep['index']}_d{det}"] = img.astype(np.float32)
    np.savez_compressed(os.path.join(outdir, "stacks.npz"), **stacks)

    gifs = {}
    for det in range(0, 7):
        pngs = movie.render_frames(result.epochs, det, result.marker_pixels, epoch_title,
                                   track=track_points(result.marker_pixels, result.epochs))
        if pngs:
            name = f"movie_d{det}.gif"
            with open(os.path.join(outdir, name), "wb") as fh:
                fh.write(movie.frames_to_gif(pngs))
            gifs[str(det)] = name

    summary = {
        "target": result.target.to_dict(),
        "size_deg": result.size_deg,
        "n_found": result.n_found,
        "n_used": result.n_used,
        "n_clean": len(result.clean_rows()),
        "n_failures": len(result.failures),
        "fit": result.fit.as_dict(),
        "epochs": [
            {k: ep[k] for k in ("index", "mjd_start", "mjd_end", "mjd_mid", "n_frames")}
            | {"counts": {str(d): c for d, c in ep["counts"].items()}}
            for ep in result.epochs
        ],
        "ref_wcs": {"crval": list(map(float, result.ref_wcs.wcs.crval)),
                    "crpix": list(map(float, result.ref_wcs.wcs.crpix)),
                    "cdelt": list(map(float, result.ref_wcs.wcs.cdelt)),
                    "shape": list(result.shape)},
        "gifs": gifs,
        "versions": result.versions,
        "collections": list(spherex.COLLECTIONS),
        "timings": result.timings,
        "generated_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
    }
    with open(os.path.join(outdir, "result.json"), "w") as fh:
        json.dump(json_safe(summary), fh, indent=2, allow_nan=False)
    return summary


def load(outdir: str) -> dict | None:
    path = os.path.join(outdir, "result.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        summary = json.load(fh)
    rows = []
    csv_path = os.path.join(outdir, "photometry.csv")
    if os.path.exists(csv_path):
        import csv

        with open(csv_path) as fh:
            for r in csv.DictReader(fh):
                for k in ("mjd", "wavelength_um", "bandwidth_um", "flux_ujy", "err_ujy", "snr", "wing_ujy", "x", "y",
                          "background", "ra", "dec"):
                    try:
                        r[k] = float(r.get(k))
                    except (TypeError, ValueError):
                        r[k] = float("nan")
                for k in ("inside", "hard_flag", "soft_flag", "saturated", "blend"):
                    r[k] = str(r.get(k)) == "True"
                r["detector"] = int(r["detector"])
                r["flag_bits"] = int(float(r["flag_bits"] or 0))
                rows.append(r)
    summary["rows"] = rows
    summary["dir"] = outdir
    return summary
