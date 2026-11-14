"""Validation table: how Cold Movers does on the five challenge objects.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.

For each precomputed object: the motion measured in the SPHEREx images versus the
catalogue prediction, the Madhava result and the published temperature.
"""

from __future__ import annotations

import os

import numpy as np

from . import checks, pipeline
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
        })
    return table
