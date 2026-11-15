"""Validation table: how Cold Movers does on the five challenge objects.

For each precomputed object: the motion measured in the SPHEREx images versus the
catalogue prediction, the Madhava result and the published temperature.
"""

from __future__ import annotations

import os

import numpy as np

from . import assistant, variability, checks, movers, pipeline
from .references import PUBLISHED
from .targets import ALL_EXAMPLES, EXTRAS, Target


def load_stacks(outdir: str) -> dict:
    stacks = {}
    path = os.path.join(outdir, "stacks.npz")
    if os.path.exists(path):
        with np.load(path) as npz:
            for name in npz.files:
                e, d = name[1:].split("_d")
                stacks.setdefault(int(e), {})[int(d)] = npz[name]
    return stacks


def marker_for(target: Target, ref: dict):
    from astropy.wcs import WCS

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval, w.wcs.crpix, w.wcs.cdelt = ref["crval"], ref["crpix"], ref["cdelt"]

    def marker(mjd):
        ra, dec = target.position_at(mjd)
        x, y = w.wcs_world2pix(ra, dec, 0)
        return float(x), float(y)

    return marker


def validate(precomputed_dir: str) -> list:
    table = []
    for key in ALL_EXAMPLES:
        outdir = os.path.join(precomputed_dir, key)
        view = pipeline.load(outdir)
        if view is None:
            continue
        target = Target.from_dict(view["target"])
        stacks = load_stacks(outdir)
        marker = marker_for(target, view["ref_wcs"])
        rows = view["rows"]
        checks.mark_blends(rows, view["epochs"], stacks, marker)
        real = checks.run_checks(rows, view["epochs"], stacks, marker)
        fit = pipeline.fit_rows(rows)
        motion = real.get("motion")
        free = free_motion_of_target(view["epochs"], stacks, marker)
        table.append({
            "key": key,
            "name": target.name,
            "images": view["n_used"],
            "visits": len(view["epochs"]),
            "pm_arcsec_yr": target.total_pm_arcsec_per_year,
            "moved_measured": motion["measured_px"] * checks.PIXEL_ARCSEC if motion else None,
            "moved_predicted": motion["predicted_px"] * checks.PIXEL_ARCSEC if motion else None,
            "seen": next(c["status"] for c in real["checks"] if c["name"] == "Seen again"),
            "temperature": fit.temperature if np.isfinite(fit.temperature) else None,
            "light": fit.light,
            "reasons": fit.reasons,
            "published": PUBLISHED.get(key, {}).get("text", ""),
            "published_k": PUBLISHED.get(key, {}).get("teff_k"),
            "extra": key in EXTRAS,
            "catalogue_rate": target.total_pm_arcsec_per_year,
            "catalogue_pa": catalogue_pa(target),
            "free_rate": free["rate_arcsec_yr"] if free else None,
            "free_pa": free["pa_deg"] if free else None,
            "free_status": ("confirmed" if free["confirmed"] else "candidate") if free else None,
            "free_detectors": free["detectors"] if free else [],
            # evidence record fields (docs/validation_records.*)
            "free_significance": free["significance"] if free else None,
            "free_rate_err": (free["rate_arcsec_yr"] / free["significance"]) if free and free["significance"] else None,
            "trajectory": (assistant.trajectory_fit(real["positions"], target.pmra_masyr, target.pmdec_masyr)
                           if real.get("positions") and target.total_pm_arcsec_per_year >= 0.5 else None),
            "t_low": fit.t_low if np.isfinite(fit.t_low) else None,
            "t_high": fit.t_high if np.isfinite(fit.t_high) else None,
            "brightness": variability.light_curve(rows, view["epochs"])["verdict"],
            "n_files": len({r.get("url") for r in rows if r.get("url")}),
            "detectors_used": sorted({int(r["detector"]) for r in rows}),
            "first_date": assistant.mjd_to_date(min(ep["mjd_mid"] for ep in view["epochs"])),
            "last_date": assistant.mjd_to_date(max(ep["mjd_mid"] for ep in view["epochs"])),
            "checks": {c["name"]: c["status"] for c in real["checks"]},
            "position_source": getattr(target, "source", ""),
        })
    return table


def catalogue_pa(target) -> float:
    """Position angle (degrees east of north) of the catalogue proper motion."""
    return float(np.degrees(np.arctan2(target.pmra_masyr, target.pmdec_masyr)) % 360)


def free_motion_of_target(epochs, stacks, marker, radius_px: float = 2.0):
    """The catalogue-free mover found at the target's first-visit position, if any."""
    return free_motion_from(movers.search_all(epochs, stacks), epochs, marker, radius_px)


def free_motion_from(found, epochs, marker, radius_px: float = 2.0):
    """Same as free_motion_of_target, from a search that has already run."""
    if not epochs or not found:
        return None
    x0, y0 = marker(min(ep["mjd_mid"] for ep in epochs))
    near = [c for c in found["candidates"] if np.hypot(c["x"] - x0, c["y"] - y0) <= radius_px]
    return near[0] if near else None
