"""Tests for the validation scoreboard rules."""

import numpy as np

from coldmovers import scoreboard


def v(**kw):
    base = {"name": "X", "free_rate": 10.0, "free_pa": 355.0, "free_status": "confirmed", "free_detectors": [5, 6],
            "catalogue_rate": 10.4, "catalogue_pa": 356.0, "temperature": 2464.0, "light": "yellow",
            "published_range_k": (2540, 2592), "published_k": 2566, "reasons": []}
    base.update(kw)
    return base


def test_motion_rules():
    assert scoreboard.motion_control(v())["status"] == "pass"
    assert scoreboard.motion_control(v(free_status="candidate"))["status"] == "partial"
    assert scoreboard.motion_control(v(free_rate=8.0))["status"] == "partial"  # 23 % off
    assert scoreboard.motion_control(v(free_pa=20.0))["status"] == "partial"  # 24 degrees off, across north
    assert scoreboard.motion_control(v(free_rate=None))["status"] == "fail"


def test_temperature_rules():
    assert scoreboard.temperature_control(v())["status"] == "pass"
    far = v(temperature=1874.0, published_range_k=(880, 1340))
    assert scoreboard.temperature_control(far)["status"] == "partial"
    assert scoreboard.temperature_control(dict(far, light="green"))["status"] == "fail"


def test_variability_rules():
    assert scoreboard.variability_control("R", {"text": "Yes. ...", "amplitude_mag": 0.5, "significance": 10})["status"] == "pass"
    assert scoreboard.variability_control("R", {"text": "Possibly. ...", "amplitude_mag": 0.2, "significance": 4})["status"] == "partial"
    assert scoreboard.variability_control("R", {"text": "No clear change", "amplitude_mag": 0.01, "significance": 1})["status"] == "fail"


def test_injected_mover_is_recovered_in_a_clean_field():
    rng = np.random.default_rng(0)
    epochs = [{"index": i, "mjd_mid": 60800.0 + 182.6 * i} for i in range(3)]
    stacks = {i: {d: rng.normal(0, 1, (41, 41)) for d in (2, 3, 4)} for i in range(3)}
    for i in range(3):
        for d in (2, 3, 4):  # a few still stars so the field can be trusted
            for (x, y) in [(8, 8), (32, 9), (9, 31), (31, 32)]:
                stacks[i][d] += scoreboard._gauss((41, 41), x, y, 40.0)
    out = scoreboard.inject_and_search(epochs, stacks, 20.0, 20.0, 10.0, 120.0, 20.0, detectors=(2, 3, 4))
    assert out["found"] and out["confirmed"]
    assert abs(out["rate_err"]) < 0.15 and out["pa_err"] < 10


def test_counts():
    rows = [scoreboard.row("a", "b", s, "", "") for s in ("pass", "pass", "partial", "fail")]
    assert scoreboard.counts(rows) == {"pass": 2, "partial": 1, "fail": 1}
