"""Visual assistant and plain-language explanations ("What am I looking at?").

Everything drawn or said here comes from measurements the app has already made
(checks.run_checks, movers.search_all, the Madhava fit, the brightness check).
Nothing is decorative and nothing is guessed: when a measurement is missing, the
matching layer or sentence is simply left out.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from .checks import PIXEL_ARCSEC

LAYERS = ("Catalogue prediction", "Measured motion", "Checks highlight", "Movers found without catalogue")
WIEN_UM_K = 2897.771955
# A 2 cm coin seen from 4 km spans 0.02 / 4000 rad = 1.03 arcsec.
COIN_KM_PER_ARCSEC = 4.0


def coin_phrase(arcsec: float) -> str:
    """'the width of a 2 cm coin seen from 370 m away': an angle a person can picture."""
    if not np.isfinite(arcsec) or arcsec <= 0:
        return ""
    metres = 0.02 / (arcsec * np.pi / 648000.0)
    far = f"{metres / 1000:.1f} km" if metres >= 1000 else f"{round(metres, -1):.0f} m"
    return f"the width of a 2 cm coin seen from {far} away"


def mjd_to_date(mjd: float) -> str:
    return (datetime(1858, 11, 17) + timedelta(days=float(mjd))).strftime("%Y-%m-%d")


def trajectory_fit(positions, pmra_masyr: float = 0.0, pmdec_masyr: float = 0.0) -> dict | None:
    """Straight-line motion fitted to the measured positions, with uncertainties.

    Offsets are east and north of the first visit's predicted position, in arcsec (x grows to the
    west on the sky grid). Each point's error combines the alignment floor and the centroid noise
    (PSF width / S/N), the same model the mover search uses. When the scatter exceeds the error
    bars (reduced chi-square above 1), the slope errors are scaled up by its square root.
    Returns None with fewer than two detected visits.
    """
    from .movers import PSF_SIGMA_PX, SYS_ALIGN_PX

    pts = sorted((p for p in positions if p.get("detected")), key=lambda p: p["mjd"])
    if len(pts) < 2:
        return None
    first = min(positions, key=lambda p: p["mjd"])
    x0, y0, t0 = first["pred_x"], first["pred_y"], first["mjd"]

    def years(mjd):
        return (mjd - t0) / 365.25

    t = np.array([years(p["mjd"]) for p in pts])
    east = np.array([-(p["x"] - x0) * PIXEL_ARCSEC for p in pts])
    north = np.array([(p["y"] - y0) * PIXEL_ARCSEC for p in pts])
    err = np.array([np.hypot(SYS_ALIGN_PX, PSF_SIGMA_PX / max(float(p["snr"]), 1.0)) * PIXEL_ARCSEC for p in pts])
    w = 1.0 / err**2
    design = np.vstack([np.ones_like(t), t]).T
    cov = np.linalg.inv(design.T @ (design * w[:, None]))
    fits, chi2 = [], 0.0
    for y in (east, north):
        coef = cov @ (design.T @ (w * y))
        chi2 += float(np.sum(((y - design @ coef) / err) ** 2))
        fits.append(coef)
    dof = 2 * len(pts) - 4
    chi2_red = chi2 / dof if dof > 0 else float("nan")
    scale = float(np.sqrt(max(1.0, chi2_red))) if dof > 0 else 1.0
    s_v = float(np.sqrt(cov[1, 1])) * scale
    v_e, v_n = float(fits[0][1]), float(fits[1][1])
    rate = float(np.hypot(v_e, v_n))
    rate_err = s_v  # same error on both axes, so the error of the length is s_v too
    pa = float(np.degrees(np.arctan2(v_e, v_n)) % 360.0)
    pa_err = float(np.degrees(s_v / rate)) if rate > 0 else float("nan")
    return {
        "dates": [mjd_to_date(p["mjd"]) for p in pts], "t": t.tolist(), "east": east.tolist(),
        "north": north.tolist(), "err": err.tolist(),
        "fit_east": [float(fits[0][0] + fits[0][1] * tt) for tt in t],
        "fit_north": [float(fits[1][0] + fits[1][1] * tt) for tt in t],
        "pred_dates": [mjd_to_date(p["mjd"]) for p in sorted(positions, key=lambda p: p["mjd"])],
        "pred_east": [-(p["pred_x"] - x0) * PIXEL_ARCSEC for p in sorted(positions, key=lambda p: p["mjd"])],
        "pred_north": [(p["pred_y"] - y0) * PIXEL_ARCSEC for p in sorted(positions, key=lambda p: p["mjd"])],
        "rate": rate, "rate_err": rate_err, "pa": pa, "pa_err": pa_err, "chi2_red": chi2_red, "n": len(pts),
        "catalogue_rate": float(np.hypot(pmra_masyr, pmdec_masyr)) / 1000.0,
        "catalogue_pa": float(np.degrees(np.arctan2(pmra_masyr, pmdec_masyr)) % 360.0),
    }


def check_ring(real) -> dict | None:
    """Colour and label of the ring drawn around the target, from the 'Is it real?' checks."""
    if not real or not real.get("checks"):
        return None
    n = sum(c["status"] == "pass" for c in real["checks"])
    total = len(real["checks"])
    color = "#2fbf71" if n == total else ("#f2c94c" if n >= 2 else "#eb5757")
    return {"color": color, "label": f"{n}/{total} checks", "n_pass": n, "n_total": total}


def layers_for(real, found, show=LAYERS) -> dict:
    """Overlay data for movie.render_frames and movie.render_difference."""
    show = set(show)
    out = {"prediction": "Catalogue prediction" in show}
    if "Measured motion" in show and real and real.get("positions"):
        out["measured"] = [(float(p["mjd"]), float(p["x"]), float(p["y"])) for p in real["positions"]
                           if p["detected"]]
    if "Checks highlight" in show:
        out["ring"] = check_ring(real)
    if "Movers found without catalogue" in show and found:
        out["movers"] = [{"t0_mjd": c["t0_mjd"], "x": c["x"], "y": c["y"], "vx_px_yr": c["vx_px_yr"],
                          "vy_px_yr": c["vy_px_yr"], "confirmed": c["confirmed"], "label": f"#{i + 1}"}
                         for i, c in enumerate(found.get("candidates", [])[:6])]
    return out


def _first_sentence(text: str) -> str:
    text = text.replace(" um", " µm")
    return text.split(". ")[0].rstrip(".") + "."


def explain(target, fit, real, free, lc_verdict, epochs) -> list:
    """Short plain-language sentences about what the user sees, as (icon, text) pairs."""
    out = []
    mjds = [ep["mjd_mid"] for ep in epochs] if epochs else []
    motion = (real or {}).get("motion")
    pm = float(target.total_pm_arcsec_per_year)

    # 1. Motion ------------------------------------------------------------------
    if mjds and pm < 0.5:
        years = (max(mjds) - min(mjds)) / 365.25
        px = pm * years / PIXEL_ARCSEC
        frac = "less than a hundredth" if px < 0.01 else f"{px:.2f}"
        out.append(("🧭", f"It moves only {pm * 1000:.0f} thousandths of an arcsecond per year. Over these visits "
                          f"that is {frac} of a SPHEREx pixel, so in the movie it should stand still. That is "
                          "expected, not a failure."))
    elif motion:
        meas = motion["measured_px"] * PIXEL_ARCSEC
        pred = motion["predicted_px"] * PIXEL_ARCSEC
        out.append(("🧭", f"Between {mjd_to_date(min(mjds))} and {mjd_to_date(max(mjds))} it moved {meas:.1f} "
                          f"arcseconds in the SPHEREx images, about {meas / PIXEL_ARCSEC:.1f} pixels (the cyan "
                          f"arrow in the movie): {coin_phrase(meas)}. The catalogue predicts {pred:.1f}."))
    if free:
        n = len(free["detectors"])
        status = ("confirmed, because more than one detector sees the same motion" if free["confirmed"]
                  else "only a candidate, because a single detector sees it")
        out.append(("🔎", f"Without using any catalogue, the app found it moving {free['rate_arcsec_yr']:.2f} "
                          f"arcseconds per year in {n} of 6 detectors: {status}."))

    # 2. Light and temperature ---------------------------------------------------
    reasons = list(fit.reasons or [])
    if "only_long_wavelengths" in reasons:
        out.append(("🌡️", "It only shows up at wavelengths longer than 3 µm. Something that gives off almost no "
                           "shorter infrared light but glows at 3 to 5 µm is very cold: anything warmer than "
                           "about 1000 K would also shine at shorter wavelengths."))
    elif np.isfinite(fit.temperature) and fit.light != "red":
        peak = WIEN_UM_K / fit.temperature
        if "peak_beyond_5um" in reasons:
            where = "beyond 5 µm, past the longest SPHEREx wavelength, so the number is an extrapolation"
        elif "peak_below_0p75um" in reasons:
            where = "below 0.75 µm, before the shortest SPHEREx wavelength, so the number is an extrapolation"
        else:
            where = f"near {peak:.2f} µm"
        out.append(("🌡️", f"Its light peaks {where}. By Wien's law (peak × temperature ≈ 2,898 µm·K) one "
                           f"blackbody would be about {fit.temperature:,.0f} K ({fit.temperature - 273.15:,.0f} °C)."))

    # 3. Traffic light in plain words ----------------------------------------------
    if "too_bright" in reasons:
        light = ("Red light because the star is so bright that it overflows (saturates) the SPHEREx detector in "
                 "most images, so its brightness cannot be measured. "
                 + ("Its motion can still be seen." if pm >= 0.5 else "Its position can still be measured."))
    elif fit.light == "red":
        main = next((r for r in reasons if r not in ("neighbour_removed", "partly_saturated")),
                    reasons[0] if reasons else None)
        from .madhava import REASON_TEXT

        why = (_first_sentence(REASON_TEXT.get(main, "The data cannot give a reliable temperature")) if main
               else "The data cannot give a reliable temperature.")
        light = "Red light: " + why[0].lower() + why[1:]
        light += " The app shows no temperature rather than a wrong one."
    elif fit.light == "yellow":
        light = ("Yellow light: one smooth blackbody curve does not describe its light. That is normal for cool "
                 "stars and brown dwarfs, whose atmospheres absorb light at particular colours, so read the "
                 "number as a rough guide.")
    else:
        light = ("Green light: one blackbody curve describes its light within the errors, and the peak falls "
                 "inside the SPHEREx range.")
    if "neighbour_removed" in reasons:
        light += " Images where a neighbouring source blends with it were left out."
    out.append(({"red": "🔴", "yellow": "🟡", "green": "🟢"}[fit.light], light))

    # 4. Is it real? -----------------------------------------------------------------
    ring = check_ring(real)
    if ring:
        failed = [c["name"].lower() for c in real["checks"] if c["status"] != "pass"]
        text = f"It passes {ring['n_pass']} of {ring['n_total']} consistency checks (the coloured ring)"
        if failed:
            names = failed[0] if len(failed) == 1 else ", ".join(failed[:-1]) + " and " + failed[-1]
            text += f": {names} did not fully pass."
        else:
            text += "."
        text += " These checks test consistency; they are not a confirmation."
        out.append(("✅" if not failed else "⚠️", text))

    # 5. Brightness -------------------------------------------------------------------
    if lc_verdict and lc_verdict.get("text"):
        out.append(("💡", "Brightness from visit to visit: " + lc_verdict["text"]))
    return out
