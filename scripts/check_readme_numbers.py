"""Check that the numbers quoted in README.md are the numbers the code produced.

Every expected string below is built from a generated file (scoreboard, validation table, evidence records,
benchmarks) or from running the code, never typed by hand. Prints a table; exit code 1 on any mismatch.
"""

import csv
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
readme = open(os.path.join(ROOT, "README.md")).read()
results, bad = [], 0


def expect(what, text, source):
    global bad
    ok = text in readme
    bad += not ok
    results.append((what, text, source, "OK" if ok else "NOT IN README"))


sb = json.load(open(os.path.join(ROOT, "data", "scoreboard.json")))
c = sb["counts"]
expect("Scoreboard counts", f"{c['pass']} pass · {c['partial']} partial · {c['fail']} fail ({sum(c.values())} checks)",
       "data/scoreboard.json")
for row in sb["rows"]:
    m = re.match(r"(\d+) of (\d+) confirmed \((\d+)%\)", row["result"])
    if m and "Very red" in row["check"]:
        expect("Red movers confirmed", f"confirmed in {m.group(3)} % of cases", "data/scoreboard.json")
    elif m:
        snr = re.search(r"S/N (\d+)", row["check"]).group(1)
        expect(f"Injected movers at S/N {snr}", f"{m.group(3)} %", "data/scoreboard.json")
        if snr == "15":
            med = re.search(r"median rate error ([\d.]+)%, direction (\d+)°", row["result"])
            expect("S/N 15 median errors", f"median rate error {med.group(1)} %, direction {med.group(2)}°",
                   "data/scoreboard.json")

# Validation table: each object's row in the README must carry the generated values.
val = {}
for line in open(os.path.join(ROOT, "docs", "validation.md")):
    cells = [x.strip() for x in line.strip().strip("|").split("|")]
    if len(cells) == 7 and cells[0] not in ("Object", "---"):
        val[cells[0].replace(" *(extra)*", "")] = cells
readme_rows = {}
for line in readme.splitlines():
    cells = [x.strip() for x in line.strip().strip("|").split("|")]
    if len(cells) == 7:
        readme_rows[cells[0].replace(" *(extra)*", "").replace("−", "-")] = cells
for name, cells in val.items():
    row = readme_rows.get(name.replace("−", "-"))
    if row is None:
        bad += 1
        results.append((f"{name}: validation row", "(row)", "docs/validation.md", "NOT IN README"))
        continue
    for i, label in ((1, "images / visits"), (2, "moved"), (4, "catalogue motion")):
        want = cells[i].split(",")[0]
        ok = want in row[i]
        bad += not ok
        results.append((f"{name}: {label}", want, "docs/validation.md", "OK" if ok else f"README has {row[i]!r}"))
    m = re.match(r"([\d.]+″/yr towards \d+°)", cells[3])
    if m:
        ok = m.group(1) in row[3]
        bad += not ok
        results.append((f"{name}: found with no catalogue", m.group(1), "docs/validation.md",
                        "OK" if ok else f"README has {row[3]!r}"))
    t = re.search(r"([\d,]+ K)", cells[5])
    if t:
        ok = t.group(1) in row[5]
        bad += not ok
        results.append((f"{name}: temperature", t.group(1), "docs/validation.md", "OK" if ok else f"README has {row[5]!r}"))

expect("Total SPHEREx images", f"{sum(int(c[1].split('/')[0]) for c in val.values()):,} images", "docs/validation.md")
rec = {r["key"]: r for r in csv.DictReader(open(os.path.join(ROOT, "docs", "validation_records.csv")))}
for r in rec.values():
    if r.get("motion_verdict"):
        name = r["object"].replace("-", "−") if "WISE" in r["object"] else r["object"]
        expect(f"{r['object']}: verdicts", f"| {name}{' *(extra)*' if r['key'] == 'trappist1' else ''} | "
               f"**{r['motion_verdict']}**", "docs/validation_records.csv")
        row = next((ln for ln in readme.splitlines() if ln.startswith(f"| {name}") and "**" + r["motion_verdict"] in ln), "")
        ok = f"**{r['temperature_verdict']}**" in row
        bad += not ok
        results.append((f"{r['object']}: temperature verdict", r["temperature_verdict"], "docs/validation_records.csv",
                        "OK" if ok else "NOT IN README"))
b = rec["barnard"]
expect("Barnard's Star trajectory", f"{b['trajectory_motion_arcsec_yr']} ± {b['trajectory_err_arcsec_yr']}″ per year",
       "docs/validation_records.csv")
expect("Barnard's Star trajectory χ²", f"reduced χ² of {b['trajectory_chi2_red']}", "docs/validation_records.csv")

before = json.load(open(os.path.join(ROOT, "docs", "benchmark_injection_before.json")))["by_snr_core"]["15.0"]
after = json.load(open(os.path.join(ROOT, "docs", "benchmark_injection.json")))["by_snr_core"]["15.0"]
expect("Benchmark precision before", f"precision {before['precision']:.2f}", "docs/benchmark_injection_before.json")
expect("Benchmark precision after", f"precision {after['precision']:.2f}", "docs/benchmark_injection.json")
expect("Benchmark recall", f"recall {before['recall']:.2f} → {after['recall']:.2f}", "benchmark JSON files")
trials = json.load(open(os.path.join(ROOT, "docs", "benchmark_injection.json")))["trials"]
expect("Benchmark size", f"{trials:,} trials", "docs/benchmark_injection.json")
holdout = os.path.join(ROOT, "docs", "benchmark_holdout_A.json")
if os.path.exists(holdout):
    h = json.load(open(holdout))["headline_snr15_core"]
    expect("Held-out precision (set A)", f"precision {h['precision']:.2f}", "docs/benchmark_holdout_A.json")
    expect("Held-out recall (set A)", f"recall {h['recall']:.2f}", "docs/benchmark_holdout_A.json")
    h30 = json.load(open(holdout))["by_snr_core"]["30.0"]
    expect("Held-out precision at S/N 30 (set A)", f"precision {h30['precision']:.2f} at S/N 30", "docs/benchmark_holdout_A.json")

holdout_b = os.path.join(ROOT, "docs", "benchmark_holdout_B.json")
if os.path.exists(holdout_b):
    hb = json.load(open(holdout_b))
    expect("Held-out recall (set B)", f"recall was higher, {hb['headline_snr15_core']['recall']:.2f} at S/N 15",
           "docs/benchmark_holdout_B.json")
    expect("Very red movers (set B)", f"confirmed in {100 * hb['red_D5D6_snr15_core']['recall']:.0f} % of cases",
           "docs/benchmark_holdout_B.json")
    for k in ("8.0", "15.0", "30.0"):
        sb_ = hb["by_snr_core"][k]
        expect(f"Set B row, S/N {k}", f"| {sb_['n']} | {sb_['confirmed']} | {sb_['n'] - sb_['confirmed']} | "
               f"{sb_['false_confirmed']} | {sb_['precision']:.2f} (", "docs/benchmark_holdout_B.json")
cal_path, fol_path = os.path.join(ROOT, "docs", "calibration.json"), os.path.join(ROOT, "docs", "calibration_followup.json")
if os.path.exists(cal_path) and os.path.exists(fol_path):
    cal, fol = json.load(open(cal_path)), json.load(open(fol_path))
    k = min(fol["pulls_development"]["robust_scale"], fol["pulls_holdout_A"]["robust_scale"])
    expect("Blind-search uncertainty scale", f"at least {k:.1f} times larger", "docs/calibration_followup.json")
    expect("Still stars", f"On {cal['null_test']['tracks']} real still stars", "docs/calibration.json")
    tc = [v for m, v in cal["temperature_coverage"]["cases"].items() if "plus" in m][0]
    expect("Temperature coverage", f"{100 * tc['coverage_mean']:.0f} % of precise synthetic fits", "docs/calibration.json")
    expect("Interval too narrow (TRAPPIST-1)", f"{fol['interval_trappist1']['too_narrow_percent']:.0f} % (TRAPPIST-1)",
           "docs/calibration_followup.json")
out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "madhava_correction_check.py")],
                     capture_output=True, text=True).stdout
m = re.search(r"(\d+)× to (\d+)×", out)
expect("Madhava correction improvement", f"{m.group(1)} to {m.group(2)} times smaller", "scripts/madhava_correction_check.py")
n_tests = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", os.path.join(ROOT, "tests")],
                         capture_output=True, text=True, cwd=ROOT).stdout
m = re.search(r"(\d+) tests? collected", n_tests)
if m:
    expect("Number of automated tests", f"{m.group(1)} automated tests", "pytest --collect-only")

print("| Claim | Expected text | From | Result |\n|---|---|---|---|")
for r in results:
    print("| " + " | ".join(str(x).replace("|", "\\|") for x in r) + " |")
print(f"\n{len(results) - bad} of {len(results)} README numbers match the generated results.")
sys.exit(1 if bad else 0)
