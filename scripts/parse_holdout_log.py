"""Rebuild docs/benchmark_holdout_<label>.json from the printed output of scripts/benchmark_holdout.py.

Used for held-out set B, which runs on GitHub Actions: its artifact cannot be downloaded from our environment,
but the job log can, and the script prints every summary it writes. The rebuilt file says where it came from
(run and job), and the fields the log does not print (candidates, direction errors) are left out, not guessed.

Usage: python scripts/parse_holdout_log.py LOGFILE --label B --source "GitHub Actions run N, job M"
"""

import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = re.compile(r"^\s+(?P<key>.+?)\s+n=\s*(?P<n>\d+) TP=\s*(?P<tp>\d+) FN=\s*(?P<fn>\d+) FP=\s*(?P<fp>\d+) "
                  r"\(distinct (?P<distinct>\d+)\) recall=(?P<recall>[\d.na]+) \[(?P<rlo>[\d.na]+)-(?P<rhi>[\d.na]+)\] "
                  r"precision=(?P<precision>[\d.na]+) \[(?P<plo>[\d.na]+)-(?P<phi>[\d.na]+)\] f1=(?P<f1>[\d.na]+) "
                  r"rate_err_med=(?P<err>[\d.na]+)\s*$")


def num(x):
    return float("nan") if x == "nan" else float(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--label", default="B")
    ap.add_argument("--source", required=True)
    ap.add_argument("--fetch-log", default=None, help="log of scripts/fetch_holdout_fields.py, to record missing fields")
    args = ap.parse_args()
    text = open(args.log).read()
    # The script first prints {label, trials, seconds, fields} as indented JSON.
    start = text.index("{")
    depth, end = 0, start
    for i, ch in enumerate(text[start:], start):
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            end = i + 1
            break
    out = json.loads(text[start:end])
    out["source"] = f"parsed from the printed output of scripts/benchmark_holdout.py ({args.source})"
    if args.fetch_log:
        missing = re.findall(r"^(\w+): FAILED \((.+?)\)\s*$", open(args.fetch_log).read(), re.M)
        out["missing_fields"] = {k: re.sub(r" for url: \S+", "", why) for k, why in missing}
    section = None
    for line in text[end:].splitlines():
        if line.startswith("== "):
            section = line[3:].strip()
            out[section] = {}
            continue
        m = LINE.match(line)
        if m and section:
            g = m.groupdict()
            out[section][g["key"].strip()] = {
                "n": int(g["n"]), "confirmed": int(g["tp"]), "false_negatives": int(g["fn"]),
                "false_confirmed": int(g["fp"]), "distinct_false_sources": int(g["distinct"]),
                "recall": num(g["recall"]), "recall_ci95": [num(g["rlo"]), num(g["rhi"])],
                "precision": num(g["precision"]), "precision_ci95": [num(g["plo"]), num(g["phi"])],
                "f1": num(g["f1"]), "rate_err_median": num(g["err"]), "candidate_only": None}
    for sec in ("headline_snr15_core", "red_D5D6_snr15_core"):
        if sec in out and list(out[sec]) == ["all"]:
            out[sec] = out[sec]["all"]
    path = os.path.join(ROOT, "docs", f"benchmark_holdout_{args.label}.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"wrote {path}: {out.get('trials')} trials, sections {[k for k in out if k.startswith(('by_', 'headline', 'red'))]}")


if __name__ == "__main__":
    main()
