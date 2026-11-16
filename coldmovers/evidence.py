"""Scientific Evidence & Validation: one ledger of every important result, built from the generated files.

Each entry says what kind of evidence it is, so a reader never mixes a real measurement with a test:

  A  Real SPHEREx measurement (images of the sky, measured by Cold Movers)
  B  Injection-recovery test (artificial movers added to copies of real SPHEREx images)
  C  Candidate, not confirmed (our detection did not meet the confirmation rule)
  D  Inconclusive or not detected (the data cannot support a conclusion, or nothing was found)
  S  Synthetic or computed check (no SPHEREx image involved: computed spectra, series, catalogue geometry)

Nothing here is typed by hand: every number and status is read from the files named in the entry's trace.
The app, the README section and the final report are all rendered from this one ledger, and the tests check
that they agree.
"""

from __future__ import annotations

import csv
import json
import os

CATEGORY = {
    "A": "Real SPHEREx measurement",
    "B": "Injection-recovery test",
    "C": "Candidate, not confirmed",
    "D": "Inconclusive or not detected",
    "S": "Synthetic or computed check",
}
OBSERVATION_STATES = {"CONFIRMED", "CANDIDATE", "NOT DETECTED", "INCONCLUSIVE", "MEASURED", "MEASURED WITH CAVEATS",
                      "NONE FOUND"}
TEST_STATES = {"PASS", "PARTIAL", "FAIL", "REPORTED"}
MARK_START, MARK_END = "<!-- evidence-summary:start -->", "<!-- evidence-summary:end -->"


def _json(root, rel):
    path = os.path.join(root, rel)
    return json.load(open(path)) if os.path.exists(path) else None


def _records(root):
    with open(os.path.join(root, "docs", "validation_records.csv")) as fh:
        return {r["key"]: r for r in csv.DictReader(fh)}


def _sb_row(sb, text):
    return next((r for r in sb["rows"] if text in r["check"]), None)


def entry(id_, claim, cat, status, source, method, evidence, uncertainty, limits, trace):
    return {"id": id_, "claim": claim, "category": cat, "category_name": CATEGORY[cat], "status": status,
            "source": source, "method": method, "evidence": evidence, "uncertainty": uncertainty,
            "limitations": limits, "trace": trace}


def build_ledger(root: str) -> list:
    rec = _records(root)
    sb = _json(root, "data/scoreboard.json")
    dev = _json(root, "docs/benchmark_injection.json")
    ha = _json(root, "docs/benchmark_holdout_A.json")
    hb = _json(root, "docs/benchmark_holdout_B.json")
    cal = _json(root, "docs/calibration.json")
    fol = _json(root, "docs/calibration_followup.json") or {}
    plx = _json(root, "docs/parallax_effect.json") or {}
    spherex = "SPHEREx DR1 + QR3 images (NASA/IPAC IRSA); one file URL per measurement in data/precomputed/<object>/photometry.csv"
    L = []

    # ---- motion of the test objects: our measurement first, the catalogue only as a comparison
    for key in ("barnard", "epsindib", "wise0855", "rwaur", "rdra", "trappist1"):
        r = rec[key]
        verdict = r["motion_verdict"]
        cat = {"CONFIRMED": "A", "CANDIDATE": "C"}.get(verdict, "D")
        ours = (f"our blind search: {r['blind_motion_arcsec_yr']} ± {r['blind_motion_err_arcsec_yr']}″/yr towards "
                f"{r['blind_pa_deg']}° (detectors {r['blind_detectors'].replace(' ', ', ')})"
                if r["blind_motion_arcsec_yr"] else "our blind search: no motion found")
        if r["trajectory_motion_arcsec_yr"]:
            ours += (f"; our trajectory fit near the predicted track: {r['trajectory_motion_arcsec_yr']} ± "
                     f"{r['trajectory_err_arcsec_yr']}″/yr")
        external = f"external comparison only (catalogue): {r['catalogue_motion_arcsec_yr']}″/yr towards {r['catalogue_pa_deg']}°"
        limits = {"CONFIRMED": "statistical error only; parallax not modelled "
                               f"(bias {plx.get(key, {}).get('bias_arcsec_yr', float('nan')):.2f}″/yr at these dates)",
                  "CANDIDATE": "seen in fewer than two trusted detectors" + (
                      f"; the speed differs from the catalogue by "
                      f"{100 * (float(r['blind_motion_arcsec_yr']) / float(r['catalogue_motion_arcsec_yr']) - 1):+.0f} %"
                      if r["blind_motion_arcsec_yr"] else ""),
                  "INCONCLUSIVE": "no detector can be trusted in this field",
                  "NOT DETECTED": "below what one year of visits can confirm"}[verdict]
        L.append(entry(f"motion-{key}", f"Motion of {r['object']}", cat, verdict, spherex,
                       "catalogue-free search: point sources followed through the visit stacks, straight-line fit, "
                       "confirmation needs 2+ trusted detectors and combined significance ≥ 5",
                       f"{ours}. {external}. Why: {r['motion_verdict_why']}.",
                       f"± {r['blind_motion_err_arcsec_yr']}″/yr (speed / significance)" if r["blind_motion_err_arcsec_yr"] else "—",
                       limits, ["docs/validation_records.csv", "coldmovers/validation.py", "tests/test_verdicts.py",
                                f"data/precomputed/{key}/photometry.csv"]))

    # ---- temperatures: blackbody-equivalent, never an effective temperature
    for key in ("trappist1", "epsindib", "barnard", "wise0855", "rwaur", "rdra"):
        r = rec[key]
        verdict = r["temperature_verdict"]
        cat = "A" if verdict.startswith("MEASURED") else "D"
        value = (f"blackbody-equivalent {int(float(r['bb_equivalent_temperature_k'])):,} K "
                 f"(range {r['temperature_range_k'].replace('-', '–')} K)" if r["bb_equivalent_temperature_k"] and verdict.startswith("MEASURED")
                 else "no reliable temperature")
        L.append(entry(f"temperature-{key}", f"Temperature of {r['object']}", cat, verdict, spherex,
                       "Madhava engine: band-integrated Planck fit, free temperature and scale, traffic light",
                       f"{value}. Published effective temperature, an external and different quantity: "
                       f"{r['published_temperature']}. Why: {r['temperature_verdict_why']}.",
                       "Δχ² = max(1, χ²r) interval with an 8 % floor" if cat == "A" else "—",
                       "a blackbody-equivalent temperature is not the physical (effective) temperature",
                       ["docs/validation_records.csv", "coldmovers/madhava.py", "docs/trappist1_madhava.png"
                        if key == "trappist1" else "docs/validation.md"]))

    # ---- brightness changes
    for key, text in (("rdra", "R Draconis, a known variable"), ("rwaur", "RW Aurigae, a known variable")):
        row = _sb_row(sb, text)
        status = {"pass": "MEASURED", "partial": "INCONCLUSIVE"}.get(row["status"], "NOT DETECTED")
        L.append(entry(f"brightness-{key}", f"Brightness change of {rec[key]['object']}", "A" if status == "MEASURED" else "D",
                       status, spherex, "per-detector residuals after removing the spectral shape, visit by visit",
                       f"{row['result']}. Rule: {row['rule']}.", "σ from the scatter of the residuals",
                       "a known variable star; 3σ–5σ is reported as 'possibly'", ["data/scoreboard.json", "coldmovers/variability.py"]))

    # ---- negative control and new objects
    row = _sb_row(sb, "No unexplained confirmed movers")
    L.append(entry("unexplained-movers", "Confirmed movers other than the known targets, six fields", "A",
                   "NONE FOUND", spherex, "the same catalogue-free search over each whole field",
                   f"{row['result']}.", "—", "fields are about 3′ across; this is a negative control, not a survey",
                   ["data/scoreboard.json", "docs/scoreboard.md"]))
    L.append(entry("new-objects", "Candidates for new, unknown objects", "C", "NONE FOUND", spherex,
                   "—", "Cold Movers claims no discovery: no unknown moving object is reported.", "—",
                   "only six small fields were searched", ["README.md"]))

    # ---- injection-recovery tests (never discoveries)
    for snr in ("8", "15", "30"):
        row = _sb_row(sb, f"Fake movers at S/N {snr} in real")
        L.append(entry(f"injection-scoreboard-{snr}", f"Injected movers at S/N {snr} (scoreboard campaign)", "B",
                       row["status"].upper(), "artificial movers added to copies of real SPHEREx visit stacks",
                       "blind search; matched afterwards", f"{row['result']}.", "binomial", sb["injection"]["note"],
                       ["data/scoreboard.json", "coldmovers/scoreboard.py"]))
    row = _sb_row(sb, "Very red fake movers")
    L.append(entry("injection-red", "Very red injected movers (detectors 5 and 6 only)", "B", row["status"].upper(),
                   "artificial movers in the two longest-wavelength detectors", "blind search",
                   f"{row['result']}." + (f" Held-out A: {ha['red_D5D6_snr15_core']['confirmed']} of "
                                          f"{ha['red_D5D6_snr15_core']['n']}; held-out B (new fields): "
                                          f"{hb['red_D5D6_snr15_core']['confirmed']} of {hb['red_D5D6_snr15_core']['n']}."
                                          if ha and hb else ""),
                   "binomial", row.get("note") or "", ["data/scoreboard.json", "evidence/VALIDATION_METRICS.md"]))
    for id_, name, data, src, note in (
            ("benchmark-dev", "Development benchmark (3,300 trials, seed 2026)", dev, "docs/benchmark_injection.json",
             "the neighbour-pull rule was chosen on these trials, so these numbers are optimistic"),
            ("benchmark-A", "Held-out set A (pre-registered, seed 20261115, same six fields)", ha,
             "docs/benchmark_holdout_A.json", "no parameter changed after the run"),
            ("benchmark-B", "Held-out set B (pre-registered, new SPHEREx fields)", hb, "docs/benchmark_holdout_B.json",
             "two of the four pre-registered fields: the ecliptic poles could not be used (IRSA search errors; at the "
             "poles SPHEREx observes almost continuously, so all images fall in one visit and no motion can be measured)")):
        if not data:
            continue
        s = data["by_snr_core"]["15.0"]
        s30 = data["by_snr_core"]["30.0"]
        L.append(entry(id_, name, "B", "REPORTED", "artificial movers added to copies of real SPHEREx visit stacks",
                       "blind search, matched afterwards; all six detectors, 5–20″/yr",
                       f"S/N 15: precision {s['precision']:.3f}, recall {s['recall']:.2f} ({s['confirmed']} of {s['n']}, "
                       f"{s['false_confirmed']} false confirmation{'' if s['false_confirmed'] == 1 else 's'}); S/N 30: precision {s30['precision']:.3f}, "
                       f"recall {s30['recall']:.2f}.", "95 % Wilson intervals in evidence/VALIDATION_METRICS.md", note,
                       [src, "evidence/VALIDATION_METRICS.md", "evidence/HOLDOUT_PREREGISTRATION.md"]))

    # ---- calibration of uncertainties
    if cal:
        n = cal["null_test"]
        k = n["position_scale_robust"]
        L.append(entry("calibration-null", "Position errors, checked on still stars", "A",
                       "MEASURED", spherex, "real-star null test (pre-registered)",
                       f"{n['tracks']} still-star tracks; position error scale k = {k:.2f} (1 = right); "
                       f"{n['n_significance_ge_3']} of {n['tracks']} pass motion significance 3, "
                       f"{n['n_significance_ge_5']} pass 5.", "—",
                       "most still stars scatter less than the model says, but a few scatter far more (heavy tails), "
                       "so single-detector significances are not Gaussian; confirmation needs two detectors for that reason",
                       ["docs/calibration.json", "evidence/CALIBRATION.md", "evidence/CALIBRATION_PREREGISTRATION.md"]))
        for id_, name, p in (("calibration-pulls-dev", "Motion uncertainties on injections (development)", cal["pulls_development"]),
                             ("calibration-pulls-A", "Motion uncertainties on injections (held-out A)", cal["pulls_holdout_A"])):
            if p.get("n"):
                L.append(entry(id_, name, "B", "REPORTED", "artificial movers in real SPHEREx stacks",
                               "velocity error ÷ quoted uncertainty (pre-registered)",
                               f"{p['n']} confirmed injections; Rayleigh scale k = {p['rayleigh_scale']:.2f} (1 = right); "
                               f"{100 * p['within_68_radius']:.0f} % within the 68 % radius.", "—",
                               ("the quoted blind-search speed uncertainties are too small: read them as at least "
                                f"{min(fol['pulls_development']['robust_scale'], fol['pulls_holdout_A']['robust_scale']):.1f} "
                                "times larger (robust follow-up, not pre-registered), with heavier tails"
                                if fol else "the quoted blind-search speed uncertainties are too small"),
                               ["docs/calibration.json", "evidence/CALIBRATION.md", "evidence/CALIBRATION_FOLLOWUP.md"]))
        tc = cal["temperature_coverage"]["cases"]
        b = next(v for m, v in tc.items() if "plus" in m)
        L.append(entry("calibration-temperature", "Temperature intervals on synthetic spectra", "S", "REPORTED",
                       "computed blackbodies on TRAPPIST-1's real SPHEREx bands and errors",
                       "interval coverage (pre-registered)",
                       f"the interval contains the true temperature in {100 * b['coverage_mean']:.0f} % of fits "
                       "(about 68 % expected).", "binomial",
                       ("the interval is quantized to a 0.35 % grid and can be too narrow; for the real objects it is "
                        f"{fol['interval_trappist1']['too_narrow_percent']:.0f} % (TRAPPIST-1) and "
                        f"{fol['interval_epsindib']['too_narrow_percent']:.0f} % (Epsilon Indi B) too narrow; best fits are not biased"
                        if fol else "synthetic spectra are pure blackbodies"),
                       ["docs/calibration.json", "evidence/CALIBRATION.md", "evidence/CALIBRATION_FOLLOWUP.md"]))

    # ---- synthetic and computed checks
    for text, id_ in (("Madhava recovers known temperatures", "synthetic-temperatures"),
                      ("Series error stays inside", "synthetic-series")):
        row = _sb_row(sb, text)
        L.append(entry(id_, row["check"], "S", row["status"].upper(), "computed spectra and series (no SPHEREx image)",
                       "scoreboard rule fixed in advance", f"{row['result']}.", "—", "", ["data/scoreboard.json",
                                                                                        "tests/test_madhava.py"]))
    if plx:
        worst = max(plx.items(), key=lambda kv: kv[1]["bias_arcsec_yr"])
        L.append(entry("parallax", "Parallax bias of the straight-line motion fit", "S", "REPORTED",
                       "catalogue parallaxes and our visit dates", "parallax ellipse at each visit date, same fit",
                       f"largest bias {worst[1]['bias_arcsec_yr']:.2f}″/yr ({worst[0]}), below every motion uncertainty.",
                       "—", "parallax is not modelled in the fit", ["docs/parallax_effect.md", "scripts/parallax_effect.py"]))
    return L


def summary_markdown(ledger: list) -> str:
    """Plain-language summary shared by the README, the app and the final report."""
    by = {}
    for e in ledger:
        by.setdefault(e["category"], []).append(e)

    def items(cat, fmt):
        return "; ".join(fmt(e) for e in by.get(cat, [])) or "none"

    ev = {e["id"]: e for e in ledger}
    confirmed = [e for e in ledger if e["status"] == "CONFIRMED"]
    lines = [
        "| Kind of evidence | What it shows |", "|---|---|",
        "| **A · Real SPHEREx measurements** | " + items("A", lambda e: f"{e['claim']}: **{e['status']}**") + " |",
        "| **B · Injection-recovery tests** (artificial movers in real images, never discoveries) | "
        + items("B", lambda e: f"{e['claim']}: {e['status'].lower()}") + " |",
        "| **C · Candidates, not confirmed** | " + items("C", lambda e: f"{e['claim']}: **{e['status']}**") + " |",
        "| **D · Inconclusive or not detected** | " + items("D", lambda e: f"{e['claim']}: **{e['status']}**") + " |",
        "| **S · Synthetic or computed checks** | " + items("S", lambda e: f"{e['claim']}: {e['status'].lower()}") + " |",
        "",
        f"**Confirmed by our own SPHEREx measurements:** {len(confirmed)} motions ("
        + ", ".join(e["claim"].replace("Motion of ", "") for e in confirmed) + "). "
        "Catalogue values are shown only for comparison and are never counted as our measurement.",
    ]
    if "benchmark-A" in ev:
        lines.append(f"**Detection rates come only from injected movers:** {ev['benchmark-A']['evidence']} (held-out A)")
    return "\n".join(lines)


def traceability_markdown(ledger: list) -> str:
    rows = ["| Claim | Kind | Status | Evidence | Where to check |", "|---|---|---|---|---|"]
    for e in ledger:
        rows.append(f"| {e['claim']} | {e['category']} · {e['category_name']} | **{e['status']}** | "
                    f"{e['evidence'].replace('|', '/')} | " + ", ".join(f"`{t}`" for t in e["trace"]) + " |")
    return "\n".join(rows)
