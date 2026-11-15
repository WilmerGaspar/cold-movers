"""Validation scoreboard: positive controls, negative controls, synthetic tests, injected movers.

The pass rules are written here, before the results are known, and every result is shown,
including the partial and failed ones. Statuses: "pass", "partial", "fail".
"""

from __future__ import annotations

import math

import numpy as np

from . import madhava, movers
from .checks import PIXEL_ARCSEC

RATE_TOL = 0.10  # relative error allowed on a catalogue-free rate
PA_TOL_DEG = 10.0  # direction error allowed
TEMP_TOL = 0.10  # relative difference allowed against a published temperature
RECOVER_PASS = 0.80  # fraction of injected movers that must be recovered as confirmed
RECOVER_PARTIAL = 0.50
MATCH_PX = 1.5  # an injected mover counts as found within this distance of where it was put


def row(category, check, status, result, rule, note=""):
    return {"category": category, "check": check, "status": status, "result": result, "rule": rule, "note": note}


def _pa_diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


# ------------------------------------------------------------------ real data


def motion_control(v):
    """A catalogue-free detection of a known fast mover, compared with its catalogue motion."""
    rule = (f"pass: confirmed (2+ detectors) with rate within {RATE_TOL:.0%} and direction within "
            f"{PA_TOL_DEG:.0f}° of the catalogue; partial: found but not both; fail: not found")
    if not v.get("free_rate"):
        return row("Positive control · motion", f"{v['name']} found without any catalogue", "fail",
                   "not found", rule)
    err = (v["free_rate"] - v["catalogue_rate"]) / v["catalogue_rate"]
    dpa = _pa_diff(v["free_pa"], v["catalogue_pa"])
    ok = v["free_status"] == "confirmed" and abs(err) <= RATE_TOL and dpa <= PA_TOL_DEG
    n = len(v["free_detectors"])
    result = (f"{v['free_rate']:.2f}″/yr towards {v['free_pa']:.0f}° vs catalogue {v['catalogue_rate']:.2f}″/yr, "
              f"{v['catalogue_pa']:.0f}° ({err:+.0%}, {dpa:.0f}° off); {v['free_status']}, {n} detector"
              + ("s" if n != 1 else ""))
    return row("Positive control · motion", f"{v['name']} found without any catalogue",
               "pass" if ok else "partial", result, rule)


def track_control(vrows):
    fast = [v for v in vrows if v["pm_arcsec_yr"] >= 0.5 and v["moved_measured"] is not None]
    rule = "pass: every fast mover's measured shift is within 1 SPHEREx pixel (6.15″) of the catalogue shift"
    good = [v for v in fast if abs(v["moved_measured"] - v["moved_predicted"]) <= PIXEL_ARCSEC]
    result = "; ".join(f"{v['name']} {v['moved_measured']:.1f}″ vs {v['moved_predicted']:.1f}″" for v in fast)
    status = "pass" if fast and len(good) == len(fast) else ("partial" if good else "fail")
    return row("Positive control · motion", "Shift between first and last visit agrees with the catalogue",
               status, result, rule)


def temperature_control(v):
    rule = (f"pass: blackbody-equivalent within {TEMP_TOL:.0%} of the published effective temperature; partial: "
            "outside but flagged yellow or red; fail: outside and green")
    name = f"{v['name']} temperature vs published"
    if v["temperature"] is None:
        return row("Positive control · temperature", name, "fail", "no temperature", rule)
    lo, hi = v["published_range_k"]
    t = v["temperature"]
    inside = lo * (1 - TEMP_TOL) <= t <= hi * (1 + TEMP_TOL)
    status = "pass" if inside else ("fail" if v["light"] == "green" else "partial")
    pub = f"{lo:,.0f}–{hi:,.0f} K"
    if inside:
        ref = v.get("published_k") or 0.5 * (lo + hi)
        diff = f"{(t - ref) / ref:+.0%} from {ref:,.0f} K"
    else:
        edge = hi if t > hi else lo
        diff = f"{(t - edge) / edge:+.0%} beyond the published range"
    result = f"{t:,.0f} K vs {pub} ({diff}); light {v['light']}"
    return row("Positive control · temperature", name, status, result, rule)


def variability_control(name, verdict):
    rule = "pass: 'Yes' (change above 5σ); partial: 'Possibly' (3–5σ); fail: 'No clear change'"
    text = verdict.get("text", "")
    status = "pass" if text.startswith("Yes") else ("partial" if text.startswith("Possibly") else "fail")
    amp, sig = verdict.get("amplitude_mag"), verdict.get("significance")
    result = (f"{amp:.2f} mag between visits, {sig:.1f}σ" if amp is not None and sig is not None else text)
    return row("Positive control · brightness", f"{name}, a known variable, is seen to change", status, result,
               rule)


def still_control(v, n_confirmed_field):
    rule = "pass: no mover reported at the star (its catalogue motion is far below one pixel)"
    status = "pass" if not v.get("free_rate") else "fail"
    result = ("no mover at the star" if status == "pass" else f"reported {v['free_rate']:.2f}″/yr") + \
        f"; confirmed movers elsewhere in the field: {n_confirmed_field}"
    return row("Negative control · motion", f"{v['name']} (does not move) gives no false mover", status, result,
               rule)


def refusal_control(v, why):
    rule = "pass: red light, so no temperature is presented as reliable"
    status = "pass" if v["light"] == "red" else "fail"
    return row("Negative control · temperature", f"{v['name']} ({why}) gets a red light", status,
               f"light {v['light']}: " + "; ".join(madhava.REASON_TEXT.get(r, r).split(".")[0] for r in v["reasons"]),
               rule)


# ------------------------------------------------------------------ synthetic


def synthetic_temperatures(temps=(600.0, 900.0, 1500.0, 2500.0, 3500.0), seeds=5, noise=0.03):
    lam = np.geomspace(0.75, 5.0, 102)
    bw = lam / 60.0
    worst, all_green, n = 0.0, True, 0
    for temp in temps:
        for seed in range(seeds):
            rng = np.random.default_rng(1000 + seed)
            true = madhava.band_model_fnu(lam, bw, temp)
            true = true / true.max() * 1000.0
            err = noise * true + 1.0
            res = madhava.fit_temperature(lam, bw, true + rng.normal(0, err), err)
            worst = max(worst, abs(res.temperature - temp) / temp)
            all_green &= res.light == "green"
            n += 1
    rule = "pass: every synthetic blackbody (600–3500 K, 3 % noise) recovered within 5 % and green"
    status = "pass" if worst <= 0.05 and all_green else ("partial" if worst <= 0.10 else "fail")
    return row("Synthetic", "Madhava recovers known temperatures", status,
               f"{n} spectra; worst error {worst:.1%}; " + ("all green" if all_green else "not all green"), rule)


def series_bound_check():
    xs = np.array([0.5, 0.7, 1.0, 2.0, 5.0, 10.0, 30.0])
    exact = np.array([madhava._SCALE * math.fsum(math.exp(-k * x) * (x**3 / k + 3 * x * x / k**2 + 6 * x / k**3
                                                                       + 6 / k**4) for k in range(1, 4000))
                      for x in xs])
    ok, parts = True, []
    for tol in (1e-4, 1e-8, 1e-15):  # cut the series early on purpose, then at full precision
        value, bound, n = madhava._large_x_with_bound(xs, tol=tol)
        err = np.abs(value - exact)
        ok &= bool(np.all(err <= bound + 4 * np.spacing(value)))
        parts.append(f"{n} terms: error {err.max():.1e} ≤ bound {bound.max():.1e}" if tol > 1e-15 else
                     f"full precision ({n} terms): error {err.max():.1e}, at the level of computer rounding")
    return row("Synthetic", "Series error stays inside Madhava's guaranteed bound", "pass" if ok else "fail",
               "; ".join(parts), "pass: the difference from the exactly summed series is within the bound (plus rounding) at every test point")


# ------------------------------------------------------------------ injected movers


def _gauss(shape, x, y, amp, sigma=movers.PSF_SIGMA_PX):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma**2))


def _quiet_spots(stacks, epochs, rng, n, margin=7.0, clearance=5.0):
    """Random positions away from the edges and from every source seen in the first visit."""
    first = min(epochs, key=lambda ep: ep["mjd_mid"])
    imgs = [im for d, im in stacks[first["index"]].items() if d != 0]
    shape = imgs[0].shape
    sources = [s for im in imgs for s in movers.detect(im, snr=4.0)]
    spots, tries = [], 0
    while len(spots) < n and tries < 5000:
        tries += 1
        x = rng.uniform(margin, shape[1] - 1 - margin)
        y = rng.uniform(margin, shape[0] - 1 - margin)
        if all(math.hypot(x - s[0], y - s[1]) > clearance for s in sources) and \
                all(math.hypot(x - p[0], y - p[1]) > 2 * clearance for p in spots):
            spots.append((x, y))
    return spots


def inject_and_search(epochs, stacks, x0, y0, rate_arcsec_yr, pa_deg, snr, detectors=(1, 2, 3, 4, 5, 6)):
    """Add one moving point source to copies of the real stacks, run the search, report what it found."""
    t0 = min(ep["mjd_mid"] for ep in epochs)
    vx = -rate_arcsec_yr * math.sin(math.radians(pa_deg)) / PIXEL_ARCSEC  # x grows to the west
    vy = rate_arcsec_yr * math.cos(math.radians(pa_deg)) / PIXEL_ARCSEC
    new = {}
    for ep in epochs:
        t = (ep["mjd_mid"] - t0) / 365.25
        new[ep["index"]] = {}
        for d, img in stacks.get(ep["index"], {}).items():
            if d in detectors:
                _, sd = movers._noise(img)
                img = img + _gauss(img.shape, x0 + vx * t, y0 + vy * t, snr * sd)
            new[ep["index"]][d] = img
    found = movers.search_all(epochs, new)
    best = None
    for c in found["candidates"]:
        dt = (c["t0_mjd"] - t0) / 365.25
        d = math.hypot(c["x"] - (x0 + vx * dt), c["y"] - (y0 + vy * dt))
        if d <= MATCH_PX and (best is None or d < best[0]):
            best = (d, c)
    if best is None:
        return {"found": False, "confirmed": False}
    c = best[1]
    return {"found": True, "confirmed": bool(c["confirmed"]), "n_detectors": len(c["detectors"]),
            "rate_err": (c["rate_arcsec_yr"] - rate_arcsec_yr) / rate_arcsec_yr,
            "pa_err": _pa_diff(c["pa_deg"], pa_deg)}


def injection_campaign(fields, rates=(5.0, 10.0, 20.0), pas=(30.0, 120.0, 210.0, 300.0), snrs=(8.0, 15.0, 30.0),
                       red_snr=15.0, seed=7, spots_per_field=4):
    """fields: {name: (epochs, stacks)}. Returns (rows, details)."""
    rng = np.random.default_rng(seed)
    results = {s: [] for s in snrs}
    red = []
    used = []
    for name, (epochs, stacks) in fields.items():
        base = movers.search_all(epochs, stacks)
        if sum(x["reliable"] for d, x in base["per_detector"].items()) < 4:
            continue  # fields spoiled by saturated halos are left out, and named
        used.append(name)
        # Each fake mover is injected alone, so a quiet spot can be reused for every speed and direction.
        for (x0, y0) in _quiet_spots(stacks, epochs, rng, spots_per_field):
            for rate in rates:
                for pa in pas:
                    for s in snrs:
                        r = inject_and_search(epochs, stacks, x0, y0, rate, pa, s)
                        results[s].append(dict(r, field=name, rate=rate))
                    r = inject_and_search(epochs, stacks, x0, y0, rate, pa, red_snr, detectors=(5, 6))
                    red.append(dict(r, field=name, rate=rate))

    def summary(res):
        conf = [r for r in res if r["confirmed"]]
        frac = len(conf) / len(res) if res else 0.0
        med = float(np.median([abs(r["rate_err"]) for r in conf])) if conf else float("nan")
        pa = float(np.median([r["pa_err"] for r in conf])) if conf else float("nan")
        return frac, med, pa, len(conf), len(res)

    def status(frac, med):
        if frac >= RECOVER_PASS and np.isfinite(med) and med <= RATE_TOL:
            return "pass"
        return "partial" if frac >= RECOVER_PARTIAL else "fail"

    rows = []
    rule = (f"pass: at least {RECOVER_PASS:.0%} recovered as confirmed, median rate error ≤ {RATE_TOL:.0%}; "
            f"partial: at least {RECOVER_PARTIAL:.0%}")
    for s in snrs:
        frac, med, pa, nc, n = summary(results[s])
        rates_txt = ", ".join(f"{r:.0f}″/yr {sum(x['confirmed'] for x in results[s] if x['rate'] == r)}/"
                              f"{sum(x['rate'] == r for x in results[s])}" for r in rates)
        rows.append(row("Synthetic · injected movers", f"Fake movers at S/N {s:.0f} in real SPHEREx images",
                        status(frac, med),
                        (f"{nc} of {n} confirmed ({frac:.0%}); median rate error {med:.1%}, direction {pa:.0f}°"
                         if nc else f"0 of {n} confirmed") + f"; by speed: {rates_txt}", rule))
    frac, med, pa, nc, n = summary(red)
    by_field = ", ".join(f"{f} {sum(r['confirmed'] for r in red if r['field'] == f)}/"
                         f"{sum(r['field'] == f for r in red)}" for f in used)
    rows.append(row("Synthetic · injected movers",
                    f"Very red fake movers (only the two longest-wavelength detectors), S/N {red_snr:.0f}",
                    status(frac, med),
                    (f"{nc} of {n} confirmed ({frac:.0%}); median rate error {med:.1%}" if nc
                     else f"0 of {n} confirmed") + f"; by field: {by_field}", rule,
                    note=("Diagnosis: a detector is trusted only if its still stars line up between visits. At the "
                          "longest wavelengths these fields hold only one to three stars. When one of them is a real "
                          "mover (Epsilon Indi B or WISE 0855 themselves) or the halo of a saturated star (RW "
                          "Aurigae), the rule distrusts the whole detector, so a second mover cannot be confirmed; "
                          "in the richer TRAPPIST-1 field most are. Making this rule work in sparse fields is our "
                          "first next step.")))
    details = {"fields_used": used, "rates_arcsec_yr": list(rates), "pa_deg": list(pas), "snrs": list(snrs),
               "note": "Gaussian point sources (sigma 0.9 px) added to the frozen visit stacks, same S/N in every "
                       "detector used; one fake mover at a time, at random quiet spots, in fields where at least "
                       "four detectors line up well."}
    return rows, details


def counts(rows):
    return {s: sum(r["status"] == s for r in rows) for s in ("pass", "partial", "fail")}


# ------------------------------------------------------------------ blind benchmark


def _spots_near_sources(stacks, epochs, rng, n, margin=7.0, near=(2.5, 4.0)):
    """Random positions 2.5-4 px from a source seen in the first visit (crowded conditions)."""
    first = min(epochs, key=lambda ep: ep["mjd_mid"])
    imgs = [im for d, im in stacks[first["index"]].items() if d != 0]
    shape = imgs[0].shape
    sources = [s for im in imgs for s in movers.detect(im, snr=6.0)]
    spots, tries = [], 0
    while sources and len(spots) < n and tries < 5000:
        tries += 1
        sx, sy = sources[rng.integers(len(sources))][:2]
        r, a = rng.uniform(*near), rng.uniform(0, 2 * math.pi)
        x, y = sx + r * math.cos(a), sy + r * math.sin(a)
        if margin <= x <= shape[1] - 1 - margin and margin <= y <= shape[0] - 1 - margin:
            spots.append((x, y))
    return spots


def blind_trial(epochs, stacks, baseline, x0, y0, rate_arcsec_yr, pa_deg, snr, detectors=(1, 2, 3, 4, 5, 6)):
    """One injected mover, a blind search, and every confirmed mover the search reports.

    The search never sees (x0, y0) or the motion: matching happens afterwards. Confirmed movers
    that match neither the injection nor a mover already present before injecting (baseline)
    are counted as false positives of this trial.
    """
    t0 = min(ep["mjd_mid"] for ep in epochs)
    vx = -rate_arcsec_yr * math.sin(math.radians(pa_deg)) / PIXEL_ARCSEC
    vy = rate_arcsec_yr * math.cos(math.radians(pa_deg)) / PIXEL_ARCSEC
    new = {}
    for ep in epochs:
        t = (ep["mjd_mid"] - t0) / 365.25
        new[ep["index"]] = {}
        for d, img in stacks.get(ep["index"], {}).items():
            if d in detectors:
                _, sd = movers._noise(img)
                img = img + _gauss(img.shape, x0 + vx * t, y0 + vy * t, snr * sd)
            new[ep["index"]][d] = img
    found = movers.search_all(epochs, new)
    hit, fps, fp_xy = None, 0, []
    for c in found["candidates"]:
        dt = (c["t0_mjd"] - t0) / 365.25
        d_inj = math.hypot(c["x"] - (x0 + vx * dt), c["y"] - (y0 + vy * dt))
        if d_inj <= MATCH_PX and (hit is None or d_inj < hit[0]):
            hit = (d_inj, c)
            continue
        if c["confirmed"] and not any(math.hypot(c["x"] - b["x"], c["y"] - b["y"]) <= 2.0 for b in baseline):
            fps += 1
            fp_xy.append((round(float(c["x"]), 1), round(float(c["y"]), 1)))
    out = {"found": hit is not None, "confirmed": bool(hit and hit[1]["confirmed"]), "false_confirmed": fps,
           "false_positions": fp_xy}  # where each false confirmation sat (first visit, pixels)
    if hit:
        c = hit[1]
        out.update(rate_err=(c["rate_arcsec_yr"] - rate_arcsec_yr) / rate_arcsec_yr,
                   pa_err=_pa_diff(c["pa_deg"], pa_deg), n_detectors=len(c["detectors"]),
                   # for the calibration of uncertainties (scripts/calibration.py); no decision uses them
                   rate_measured=float(c["rate_arcsec_yr"]), pa_measured=float(c["pa_deg"]),
                   significance=float(c["significance"]))
    return out


def summarize_trials(trials):
    """Recall, precision, F1 and errors for a list of blind trials (confirmed movers only)."""
    n = len(trials)
    tp = sum(t["confirmed"] for t in trials)
    cand = sum(t["found"] and not t["confirmed"] for t in trials)
    fp = sum(t["false_confirmed"] for t in trials)
    recall = tp / n if n else float("nan")
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    f1 = (2 * precision * recall / (precision + recall)) if tp else 0.0
    rate_err = [abs(t["rate_err"]) for t in trials if t["confirmed"]]
    pa_err = [t["pa_err"] for t in trials if t["confirmed"]]
    return {"n": n, "confirmed": tp, "candidate_only": cand, "missed": n - tp - cand, "false_confirmed": fp,
            "recall": recall, "precision": precision, "f1": f1,
            "false_confirmed_per_trial": fp / n if n else float("nan"),
            "rate_err_median": float(np.median(rate_err)) if rate_err else float("nan"),
            "rate_err_p84": float(np.percentile(rate_err, 84)) if rate_err else float("nan"),
            "pa_err_median": float(np.median(pa_err)) if pa_err else float("nan")}
