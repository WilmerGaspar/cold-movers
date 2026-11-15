"""Are Cold Movers' uncertainties honest? Three pre-registered tests (evidence/CALIBRATION_PREREGISTRATION.md).

1. Real-star null test. Stars in the six frozen SPHEREx fields barely move (far below one pixel a year), so
   their measured positions should scatter only as the position error model says (0.12 px alignment plus
   0.9 px / S/N centroiding, per axis), and their "motion significance" should rarely pass the thresholds.
   Real data, no simulation.
2. Injection pulls. For injected movers that were confirmed, the velocity error divided by the quoted
   uncertainty (speed / significance) should follow a Rayleigh distribution of scale 1. Estimated on the
   development set (seed 2026), checked on held-out set A (seed 20261115).
3. Temperature interval coverage. Synthetic blackbodies observed with TRAPPIST-1's real SPHEREx bands and
   errors; the Madhava interval should contain the true temperature about 68 % of the time when the noise
   matches what the fit assumes.

Usage: python scripts/calibration.py --dev-trials DEV.jsonl --holdout-trials A.jsonl [--smoke]
Writes docs/calibration.json and evidence/CALIBRATION.md.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from coldmovers import __version__, madhava, movers, pipeline, validation  # noqa: E402
from coldmovers.targets import Target  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE = os.path.join(ROOT, "data", "precomputed")
RAYLEIGH_68, RAYLEIGH_95 = math.sqrt(-2 * math.log(1 - 0.6827)), math.sqrt(-2 * math.log(1 - 0.9545))
CAL_LO, CAL_HI = 0.8, 1.25  # pre-registered: "calibrated" if the error scale k lies here


def tan_pixel(ra, dec, ref):
    """Pixel (0-based) of (ra, dec) on the reference grid: gnomonic projection, no rotation (as validation.marker_for)."""
    a, d = math.radians(ra), math.radians(dec)
    a0, d0 = (math.radians(v) for v in ref["crval"])
    cosc = math.sin(d0) * math.sin(d) + math.cos(d0) * math.cos(d) * math.cos(a - a0)
    xi = math.degrees(math.cos(d) * math.sin(a - a0) / cosc)
    eta = math.degrees((math.cos(d0) * math.sin(d) - math.sin(d0) * math.cos(d) * math.cos(a - a0)) / cosc)
    return ref["crpix"][0] - 1 + xi / ref["cdelt"][0], ref["crpix"][1] - 1 + eta / ref["cdelt"][1]


def sigma_pos(snr):
    return math.hypot(movers.SYS_ALIGN_PX, movers.PSF_SIGMA_PX / max(snr, 1.0))


def null_test():
    """Still stars in trusted detectors of the six frozen fields (the target itself excluded)."""
    z_axis, sig, per_field = [], [], {}
    for key in sorted(os.listdir(PRE)):
        outdir = os.path.join(PRE, key)
        view = pipeline.load(outdir) if os.path.isdir(outdir) else None
        if not view:
            continue
        epochs, stacks = view["epochs"], validation.load_stacks(outdir)
        target = Target.from_dict(view["target"])
        t_first = min(ep["mjd_mid"] for ep in epochs)
        tx, ty = tan_pixel(*target.position_at(t_first), view["ref_wcs"])
        n_tracks = n_points = 0
        for det in (1, 2, 3, 4, 5, 6):
            r = movers.search(epochs, stacks, det)
            if not r["reliable"]:
                continue
            for tr in r["sources"]:
                if math.hypot(tr["x"] - tx, tr["y"] - ty) <= 3.0:
                    continue  # the target (a real mover) is not a still star
                sig.append(tr["significance"])
                n_tracks += 1
                pts = np.array(tr["points"])
                n = len(pts)
                if n < 3:
                    continue
                t = pts[:, 0]
                lev = 1.0 / n + (t - t.mean()) ** 2 / np.sum((t - t.mean()) ** 2)
                s = sigma_pos(tr["snr"])
                for axis in (1, 2):
                    resid = pts[:, axis] - np.polyval(np.polyfit(t, pts[:, axis], 1), t)
                    z_axis.extend((resid / (s * np.sqrt(1.0 - lev))).tolist())
                    n_points += n
        per_field[key] = {"tracks": n_tracks, "residuals": n_points}
    z = np.array(z_axis)
    sig = np.array(sig)
    k_robust = float(1.4826 * np.median(np.abs(z - np.median(z)))) if z.size else float("nan")
    k_rms = float(np.sqrt(np.mean(z ** 2))) if z.size else float("nan")
    rayleigh_k = float(np.sqrt(np.mean(sig ** 2) / 2.0)) if sig.size else float("nan")
    return {
        "per_field": per_field, "residuals": int(z.size), "tracks": int(sig.size),
        "position_scale_robust": k_robust, "position_scale_rms": k_rms,
        "within_1sigma": float(np.mean(np.abs(z) < 1)) if z.size else float("nan"),
        "within_2sigma": float(np.mean(np.abs(z) < 2)) if z.size else float("nan"),
        "significance_median": float(np.median(sig)) if sig.size else float("nan"),
        "significance_rayleigh_scale": rayleigh_k,
        "frac_significance_ge_3": float(np.mean(sig >= 3)) if sig.size else float("nan"),
        "frac_significance_ge_5": float(np.mean(sig >= 5)) if sig.size else float("nan"),
        "n_significance_ge_3": int(np.sum(sig >= 3)), "n_significance_ge_5": int(np.sum(sig >= 5)),
        "expected_if_calibrated": {"within_1sigma": 0.6827, "within_2sigma": 0.9545,
                                   "frac_significance_ge_3": math.exp(-4.5), "frac_significance_ge_5": math.exp(-12.5),
                                   "note": "significance uses the first-to-last shift uncertainty sqrt(2) x sigma_pos, "
                                           "larger than the slope uncertainty when there are more than two visits, "
                                           "so a calibrated position model gives fewer threshold crossings than this"},
    }


def pulls(path):
    """Velocity error over quoted uncertainty for confirmed injections (all six detectors)."""
    zs = []
    with open(path) as fh:
        for line in fh:
            t = json.loads(line)
            if not t.get("confirmed") or t.get("set") != "all six" or not t.get("significance"):
                continue
            rm, rt = t["rate_measured"], t["rate"]
            dpa = math.radians(t["pa_err"])
            dv = math.sqrt(max(rm * rm + rt * rt - 2 * rm * rt * math.cos(dpa), 0.0))
            zs.append(dv / (rm / t["significance"]))
    z = np.array(zs)
    if not z.size:
        return {"n": 0}
    k = float(np.sqrt(np.mean(z ** 2) / 2.0))
    return {"n": int(z.size), "rayleigh_scale": k, "median_pull": float(np.median(z)),
            "within_68_radius": float(np.mean(z < RAYLEIGH_68)), "within_95_radius": float(np.mean(z < RAYLEIGH_95)),
            "expected_if_calibrated": {"rayleigh_scale": 1.0, "within_68_radius": 0.6827, "within_95_radius": 0.9545}}


def coverage(n_per_t, seed=20261116):
    """Synthetic blackbodies with TRAPPIST-1's real clean SPHEREx bands and relative errors."""
    view = pipeline.load(os.path.join(PRE, "trappist1"))
    good = pipeline.clean_rows(view["rows"])
    lam = np.array([r["wavelength_um"] for r in good])
    bw = np.array([r["bandwidth_um"] for r in good])
    rel = np.array([r["err_ujy"] / abs(r["flux_ujy"]) for r in good])
    rng = np.random.default_rng(seed)
    out = {"points_per_spectrum": int(lam.size), "spectra_per_temperature": n_per_t, "seed": seed, "cases": {}}
    for mode in ("measurement errors only", "measurement errors plus the 8 % floor the fit assumes"):
        res = {}
        for temp in (800.0, 1200.0, 1800.0, 2500.0, 3200.0):
            model = madhava.band_model_fnu(lam, bw, temp)
            model = model / np.median(model) * 1000.0
            sig = rel * model
            if mode.startswith("measurement errors plus"):
                sig = np.hypot(sig, madhava.DEFAULT_ERROR_FLOOR * model)
            inside = green = 0
            for _ in range(n_per_t):
                f = model + rng.normal(0.0, sig)
                fit = madhava.fit_temperature(lam, bw, f, rel * np.abs(f))
                inside += bool(fit.t_low <= temp <= fit.t_high)
                green += fit.light == "green"
            res[f"{temp:.0f}"] = {"coverage": inside / n_per_t, "green": green / n_per_t}
        total = sum(v["coverage"] for v in res.values()) / len(res)
        out["cases"][mode] = {"by_temperature": res, "coverage_mean": total}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-trials", required=True)
    ap.add_argument("--holdout-trials", required=True)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "calibration.json"))
    args = ap.parse_args()
    result = {"code_version": __version__, "preregistration": "evidence/CALIBRATION_PREREGISTRATION.md",
              "null_test": null_test(), "pulls_development": pulls(args.dev_trials),
              "pulls_holdout_A": pulls(args.holdout_trials), "temperature_coverage": coverage(3 if args.smoke else 60)}
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=1)
    if not args.smoke:
        write_report(result)
    print(json.dumps(result, indent=1))


def verdict(k):
    if not k == k:
        return "not measured"
    return "calibrated" if CAL_LO <= k <= CAL_HI else ("uncertainties too small" if k > CAL_HI else "uncertainties too large (conservative)")


def write_report(r):
    n, pd, ph, tc = r["null_test"], r["pulls_development"], r["pulls_holdout_A"], r["temperature_coverage"]
    exp = n["expected_if_calibrated"]
    L = ["# Calibration of uncertainties (generated by `scripts/calibration.py`)", "",
         "Pre-registered in [CALIBRATION_PREREGISTRATION.md](CALIBRATION_PREREGISTRATION.md) before any of these "
         f"numbers were computed. Code version {r['code_version']}. A scale *k* of 1 means the quoted uncertainties "
         f"are right; the pre-registered band for \"calibrated\" is {CAL_LO}–{CAL_HI}.", "",
         "## 1. Real-star null test (real SPHEREx data, no simulation)", "",
         f"{n['tracks']} still-star tracks in trusted detectors of the six frozen fields (targets excluded); "
         f"{n['residuals']} position residuals from tracks with three or more visits.", "",
         "| Quantity | Measured | If the error model is right |", "|---|---|---|",
         f"| Position error scale *k* (robust, 1.4826 × MAD) | **{n['position_scale_robust']:.2f}** ({verdict(n['position_scale_robust'])}) | 1.00 |",
         f"| Position error scale *k* (RMS, sensitive to outliers) | {n['position_scale_rms']:.2f} | 1.00 |",
         f"| Residuals within 1σ | {100 * n['within_1sigma']:.1f} % | {100 * exp['within_1sigma']:.1f} % |",
         f"| Residuals within 2σ | {100 * n['within_2sigma']:.1f} % | {100 * exp['within_2sigma']:.1f} % |",
         f"| Still stars with motion significance ≥ 3 (candidate level) | {n['n_significance_ge_3']} of {n['tracks']} "
         f"({100 * n['frac_significance_ge_3']:.1f} %) | at most {100 * exp['frac_significance_ge_3']:.1f} % |",
         f"| Still stars with motion significance ≥ 5 (one detector's share of a confirmation) | {n['n_significance_ge_5']} of "
         f"{n['tracks']} ({100 * n['frac_significance_ge_5']:.2f} %) | at most {100 * exp['frac_significance_ge_5']:.4f} % |",
         "", f"Tracks per field: " + ", ".join(f"{k} {v['tracks']}" for k, v in n["per_field"].items()) + ".", "",
         "## 2. Injection pulls (velocity error ÷ quoted uncertainty, confirmed injections)", "",
         "| Set | Confirmed injections | Rayleigh scale *k* | Within the 68 % radius | Within the 95 % radius |",
         "|---|---|---|---|---|"]
    for name, p in (("Development (seed 2026): estimate", pd), ("Held-out A (seed 20261115): check", ph)):
        if p.get("n"):
            L.append(f"| {name} | {p['n']} | **{p['rayleigh_scale']:.2f}** ({verdict(p['rayleigh_scale'])}) | "
                     f"{100 * p['within_68_radius']:.1f} % | {100 * p['within_95_radius']:.1f} % |")
    L += ["", "Expected if calibrated: *k* = 1.00, 68.3 % and 95.4 %.", "",
          "## 3. Temperature interval coverage (synthetic spectra on TRAPPIST-1's real SPHEREx bands)", "",
          f"{tc['spectra_per_temperature']} spectra per temperature, {tc['points_per_spectrum']} points each, seed "
          f"{tc['seed']}. The fit always adds an 8 % floor to the quoted errors.", "",
          "| Noise put into the synthetic spectra | " + " | ".join(f"{t} K" for t in tc["cases"][next(iter(tc["cases"]))]["by_temperature"])
          + " | Mean coverage | Expected |", "|---|" + "---|" * 7]
    for mode, c in tc["cases"].items():
        exp_txt = "≈ 68 %" if "plus" in mode else "above 68 % (the floor makes the interval conservative)"
        L.append(f"| {mode} | " + " | ".join(f"{100 * v['coverage']:.0f} %" for v in c["by_temperature"].values())
                 + f" | **{100 * c['coverage_mean']:.0f} %** | {exp_txt} |")
    L.append("")
    with open(os.path.join(ROOT, "evidence", "CALIBRATION.md"), "w") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    main()
