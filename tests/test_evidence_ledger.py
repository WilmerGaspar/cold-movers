"""The evidence ledger must never let a test or a weak detection pass as a confirmed observation."""

import csv
import os

import pytest

from coldmovers import evidence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def ledger():
    return evidence.build_ledger(ROOT)


@pytest.fixture(scope="module")
def records():
    with open(os.path.join(ROOT, "docs", "validation_records.csv")) as fh:
        return {r["key"]: r for r in csv.DictReader(fh)}


def test_confirmed_only_when_the_rule_is_met(ledger, records):
    for e in ledger:
        if e["status"] != "CONFIRMED":
            continue
        assert e["category"] == "A" and e["id"].startswith("motion-")
        r = records[e["id"].split("-", 1)[1]]
        significance = float(r["blind_motion_arcsec_yr"]) / float(r["blind_motion_err_arcsec_yr"])
        assert r["blind_status"] == "confirmed"
        assert len(r["blind_detectors"].split()) >= 2 and significance >= 5.0
        assert int(r["trusted_detectors"]) >= 2


def test_weak_detections_are_never_confirmed(ledger, records):
    status = {e["id"]: e["status"] for e in ledger}
    for key, r in records.items():
        weak = (not r["blind_motion_arcsec_yr"] or len(r["blind_detectors"].split()) < 2
                or r["blind_status"] != "confirmed")
        if weak:
            assert status[f"motion-{key}"] != "CONFIRMED", key


def test_injections_and_synthetic_checks_are_never_observations(ledger):
    for e in ledger:
        if e["category"] in ("B", "S"):
            assert e["status"] in evidence.TEST_STATES, e["id"]
        else:
            assert e["status"] in evidence.OBSERVATION_STATES, e["id"]
        assert e["category_name"] == evidence.CATEGORY[e["category"]]


def test_the_known_cases(ledger):
    ev = {e["id"]: e for e in ledger}
    assert ev["motion-wise0855"]["status"] == "CANDIDATE" and ev["motion-wise0855"]["category"] == "C"
    assert ev["motion-rdra"]["status"] == "INCONCLUSIVE" and ev["motion-rdra"]["category"] == "D"
    for key in ("barnard", "epsindib"):
        assert ev[f"motion-{key}"]["status"] == "CONFIRMED"
        assert "our blind search" in ev[f"motion-{key}"]["evidence"]
        assert "external comparison only" in ev[f"motion-{key}"]["evidence"]
    assert ev["new-objects"]["status"] == "NONE FOUND"
    for e in ledger:
        if e["id"].startswith("temperature-"):
            assert "different quantity" in e["evidence"]
            if e["status"].startswith("MEASURED"):
                assert "blackbody-equivalent" in e["evidence"]


def test_readme_sentence_matches_the_ledger(ledger):
    confirmed = [e for e in ledger if e["id"].startswith("motion-") and e["status"] == "CONFIRMED"]
    candidates = [e for e in ledger if e["id"].startswith("motion-") and e["status"] == "CANDIDATE"]
    readme = open(os.path.join(ROOT, "README.md")).read()
    assert len(confirmed) == 2 and len(candidates) == 1
    assert "motion of two known nearby objects" in readme and "a third one moving, but only as a **candidate**" in readme


def test_readme_report_and_ledger_agree(ledger):
    block = evidence.summary_markdown(ledger)
    for path in ("README.md", "evidence/FINAL_VALIDATION_REPORT.md"):
        text = open(os.path.join(ROOT, path)).read()
        a, b = text.index(evidence.MARK_START), text.index(evidence.MARK_END)
        assert text[a + len(evidence.MARK_START):b].strip() == block.strip(), path


def test_every_trace_exists(ledger):
    for e in ledger:
        for t in e["trace"]:
            assert os.path.exists(os.path.join(ROOT, t)), (e["id"], t)
