"""Does it change? Brightness from visit to visit.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.

Within one detector the wavelength changes from image to image (linear variable
filters), so raw fluxes mix colour and time. For each detector we fit the smooth
spectral shape (a quadratic in wavelength, in magnitudes) using all visits; what is
left over in each image is the brightness change at that moment.
For saturated stars the light in the wings of the star is used instead of the core.
"""

from __future__ import annotations

import numpy as np

MIN_POINTS_PER_DETECTOR = 8


def _robust_poly(x, y, deg=2, iters=3):
    keep = np.isfinite(x) & np.isfinite(y)
    coef = None
    for _ in range(iters):
        if keep.sum() <= deg + 2:
            break
        coef = np.polyfit(x[keep], y[keep], deg)
        res = y - np.polyval(coef, x)
        mad = 1.4826 * np.median(np.abs(res[keep] - np.median(res[keep])))
        if mad <= 0:
            break
        keep = keep & (np.abs(res) < 4 * mad)
    return coef


def light_curve(rows, epochs) -> dict:
    """Return per-image changes (mag) and per-visit medians, plus a verdict."""
    points = []
    methods = {}
    for det in range(1, 7):
        drows = [r for r in rows if int(r["detector"]) == det and r["inside"] and np.isfinite(r["wavelength_um"])]
        if not drows:
            continue
        sat = np.mean([bool(r.get("saturated")) for r in drows])
        key = "wing_ujy" if sat > 0.5 else "flux_ujy"
        use = [r for r in drows
               if np.isfinite(r.get(key, np.nan)) and r.get(key, 0) > 0
               and (key == "wing_ujy" or (not r["hard_flag"] and not r.get("blend")))]
        if len(use) < MIN_POINTS_PER_DETECTOR:
            continue
        lam = np.array([r["wavelength_um"] for r in use])
        mag = -2.5 * np.log10(np.array([r[key] for r in use]))
        coef = _robust_poly(lam, mag)
        if coef is None:
            continue
        res = mag - np.polyval(coef, lam)
        methods[det] = "wings" if key == "wing_ujy" else "aperture"
        for r, d in zip(use, res):
            points.append({"mjd": float(r["mjd"]), "detector": det, "dmag": float(d)})

    visits = []
    for ep in epochs:
        sel = [p["dmag"] for p in points if ep["mjd_start"] - 0.5 <= p["mjd"] <= ep["mjd_end"] + 0.5]
        if len(sel) >= 4:
            arr = np.array(sel)
            med = float(np.median(arr))
            err = float(1.2533 * 1.4826 * np.median(np.abs(arr - med)) / np.sqrt(arr.size))
            visits.append({"mjd": ep["mjd_mid"], "dmag": med, "err": max(err, 0.005), "n": int(arr.size)})

    verdict = {"variable": False, "amplitude_mag": None, "significance": None, "text": ""}
    if len(visits) >= 2:
        d = np.array([v["dmag"] for v in visits])
        e = np.array([v["err"] for v in visits])
        amp = float(d.max() - d.min())
        noise = float(np.sqrt(e[d.argmax()] ** 2 + e[d.argmin()] ** 2))
        sig = amp / noise if noise > 0 else float("inf")
        verdict.update(amplitude_mag=amp, significance=sig)
        pct = (10 ** (0.4 * amp) - 1) * 100
        if amp > 0.05 and sig > 5:
            verdict["variable"] = True
            verdict["text"] = (f"Yes. Between visits its brightness changed by {amp:.2f} magnitudes "
                               f"(about {pct:.0f} %), {sig:.0f} times larger than the measurement noise.")
        else:
            verdict["text"] = (f"No clear change: visits agree within {amp:.2f} magnitudes "
                               f"(about {pct:.0f} %), compared with a noise of {noise:.3f} magnitudes.")
    else:
        verdict["text"] = "Fewer than two usable visits, so changes cannot be measured yet."
    return {"points": points, "visits": visits, "verdict": verdict, "methods": methods}
