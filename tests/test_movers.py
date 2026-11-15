"""Tests for the catalogue-free mover search."""

import numpy as np

from coldmovers import movers


def star(img, x, y, flux):
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    img += flux / (2 * np.pi * 0.9**2) * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 0.9**2))


def field(t_years, mover_v=(0.0, 1.5), seed=0, jitter=0.0, with_mover=True):
    rng = np.random.default_rng(seed)
    img = rng.normal(0, 1, (31, 31))
    for (x, y) in [(6, 7), (24, 9), (8, 23), (22, 24)]:  # stationary stars
        star(img, x + rng.normal(0, jitter), y + rng.normal(0, jitter), 400)
    if with_mover:
        star(img, 15 + mover_v[0] * t_years, 12 + mover_v[1] * t_years, 400)
    return img


def epochs_and_stacks(dets=(2, 3), n=3, **kw):
    epochs, stacks = [], {}
    for i in range(n):
        epochs.append({"index": i, "mjd_mid": 60800.0 + 182.6 * i})
        stacks[i] = {d: field(0.5 * i, seed=10 * i + d, **kw) for d in dets}
    return epochs, stacks


def test_detects_point_sources():
    found = movers.detect(field(0.0))
    assert len(found) == 5


def test_mover_confirmed_in_two_detectors_with_right_rate():
    epochs, stacks = epochs_and_stacks()
    res = movers.search_all(epochs, stacks)
    top = res["candidates"][0]
    assert top["confirmed"] and top["detectors"] == [2, 3]
    assert abs(top["rate_arcsec_yr"] - 1.5 * 6.15) < 1.0
    assert abs(top["pa_deg"] - 0.0) < 10 or abs(top["pa_deg"] - 360.0) < 10  # moving north
    assert sum(c["confirmed"] for c in res["candidates"]) == 1  # stationary stars are not movers


def test_one_detector_is_only_a_candidate():
    epochs, stacks = epochs_and_stacks(dets=(5,))
    res = movers.search_all(epochs, stacks)
    assert res["candidates"] and not res["candidates"][0]["confirmed"]


def test_static_field_has_no_movers():
    epochs, stacks = epochs_and_stacks(with_mover=False)
    res = movers.search_all(epochs, stacks)
    assert not any(c["confirmed"] for c in res["candidates"])


def test_badly_aligned_field_is_not_trusted():
    epochs, stacks = epochs_and_stacks(jitter=1.5, with_mover=False)
    res = movers.search_all(epochs, stacks)
    assert not any(c["confirmed"] for c in res["candidates"])
