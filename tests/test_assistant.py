"""Tests for the visual assistant and the plain-language explanations."""

import numpy as np

from coldmovers import assistant, madhava, movie
from coldmovers.targets import Target


def fit(temp=float("nan"), light="red", reasons=()):
    return madhava.FitResult(temperature=temp, t_low=temp, t_high=temp, scale=1.0, chi2=1.0, dof=5, n_points=20,
                             light=light, reasons=list(reasons))


def real(statuses=("pass", "pass", "pass", "pass"), moved=(1.8, 1.8)):
    names = ["Seen again", "Clean pixels", "Consistent with catalogue motion", "No neighbour"]
    return {"checks": [{"name": n, "status": s, "text": ""} for n, s in zip(names, statuses)],
            "motion": {"measured_px": moved[0], "predicted_px": moved[1], "rms_px": 0.1},
            "positions": [{"mjd": 60800.0 + 100 * i, "x": 15.0, "y": 15.0 + 0.4 * i, "pred_x": 15.0,
                           "pred_y": 15.0 + 0.4 * i, "snr": 30.0, "detected": True} for i in range(3)],
            "detector": 2}


EPOCHS = [{"index": i, "mjd_mid": 60800.0 + 100 * i, "mjd_start": 60795.0 + 100 * i, "mjd_end": 60805.0 + 100 * i,
           "counts": {2: 5}} for i in range(3)]
FAST = Target("t", "Test star", 10.0, 10.0, pmra_masyr=0.0, pmdec_masyr=10000.0)
SLOW = Target("s", "Slow star", 10.0, 10.0, pmra_masyr=20.0, pmdec_masyr=5.0)


def test_check_ring_colours():
    assert assistant.check_ring(real())["color"] == "#2fbf71"
    assert assistant.check_ring(real(("pass", "warn", "pass", "pass")))["color"] == "#f2c94c"
    assert assistant.check_ring(real(("fail", "warn", "warn", "pass")))["color"] == "#eb5757"
    assert assistant.check_ring(None) is None


def test_layers_follow_the_choice():
    found = {"candidates": [{"t0_mjd": 60800.0, "x": 5.0, "y": 5.0, "vx_px_yr": 1.0, "vy_px_yr": 0.0,
                             "confirmed": True}]}
    all_on = assistant.layers_for(real(), found)
    assert all_on["prediction"] and len(all_on["measured"]) == 3 and all_on["ring"] and all_on["movers"]
    none = assistant.layers_for(real(), found, [])
    assert none == {"prediction": False}


def test_explain_saturated_fast_star():
    text = " ".join(t for _, t in assistant.explain(FAST, fit(reasons=["too_bright"]), real(), None,
                                                     {"text": "No clear change."}, EPOCHS))
    assert "saturates" in text and "motion can still be seen" in text
    assert "moved 11.1 arcseconds" in text  # 1.8 px x 6.15 arcsec/px


def test_explain_slow_star_should_stand_still():
    out = assistant.explain(SLOW, fit(2500.0, "green", ["clean_blackbody_fit"]), real(), None, None, EPOCHS)
    text = " ".join(t for _, t in out)
    assert "stand still" in text and "Green light" in text and "2,500 K" in text


def test_explain_only_long_wavelengths_says_cold_without_a_number():
    out = assistant.explain(FAST, fit(600.0, "red", ["narrow_coverage", "only_long_wavelengths"]),
                            real(("pass", "warn", "pass", "warn")), None, None, EPOCHS)
    text = " ".join(t for _, t in out)
    assert "very cold" in text and "600 K" not in text
    assert "clean pixels and no neighbour did not fully pass" in text


def test_frames_and_difference_render_with_layers():
    rng = np.random.default_rng(1)
    eps = [dict(ep, stacks={2: rng.normal(0, 1, (31, 31))}) for ep in EPOCHS]
    layers = assistant.layers_for(real(), {"candidates": [{"t0_mjd": 60800.0, "x": 5.0, "y": 5.0, "vx_px_yr": 1.0,
                                                           "vy_px_yr": 0.0, "confirmed": False}]})
    pngs = movie.render_frames(eps, 2, lambda mjd: (15.0, 15.0), layers=layers)
    assert len(pngs) == 3 and all(p[:4] == b"\x89PNG" for p in pngs)
    assert movie.render_difference(eps, 2, 2, lambda mjd: (15.0, 15.0), layers=layers)[:4] == b"\x89PNG"
    assert movie.render_difference(eps, 2, 0, lambda mjd: (15.0, 15.0)) is None
    assert movie.render_sum(eps, 2, lambda mjd: (15.0, 15.0), layers=layers)[:4] == b"\x89PNG"
    assert movie.render_sum(eps, 5) is None


def test_external_calls_cannot_freeze_the_page():
    import time

    import pytest

    from coldmovers import atlas

    assert atlas.call_with_timeout(lambda a, b: a + b, 2.0, 1, 2) == 3
    t = time.time()
    with pytest.raises(TimeoutError):
        atlas.call_with_timeout(time.sleep, 0.3, 5)
    assert time.time() - t < 2.0
    with pytest.raises(ValueError):
        atlas.call_with_timeout(lambda: int("x"), 2.0)


def test_gaia_pause_after_timeout(monkeypatch):
    import time

    import pytest

    from coldmovers import atlas

    calls = []
    monkeypatch.setattr(atlas, "gaia_field", lambda *a: calls.append(1) or time.sleep(1.0))
    monkeypatch.setattr(atlas, "_GAIA_PAUSED_UNTIL", 0.0)
    with pytest.raises(TimeoutError):
        atlas.gaia_field_timed(0.0, 0.0, 0.1, timeout_s=0.2)
    t = time.time()
    with pytest.raises(TimeoutError):  # paused: answers at once, without asking the archive
        atlas.gaia_field_timed(0.0, 0.0, 0.1, timeout_s=0.2)
    assert time.time() - t < 0.1 and len(calls) == 1
