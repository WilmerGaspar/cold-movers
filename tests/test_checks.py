"""Tests for the 'Is it real?' checks. AI-assisted (Claude, Anthropic), reviewed by the team."""

import numpy as np
import pytest

from coldmovers import checks


def blob(x0, y0, flux=500.0, n=31, noise=1.0, seed=0):
    yy, xx = np.mgrid[0:n, 0:n]
    img = flux / (2 * np.pi) * np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / 2.0)
    return img + np.random.default_rng(seed).normal(0, noise, (n, n))


def test_centroid_finds_offset_star():
    x, y, snr = checks.centroid(blob(16.4, 14.2), 15, 15)
    assert x == pytest.approx(16.4, abs=0.15)
    assert y == pytest.approx(14.2, abs=0.15)
    assert snr > 20


def test_moving_star_passes_all_checks():
    epochs, stacks = [], {}
    track = {0: (14.0, 15.0), 1: (15.0, 15.0), 2: (16.0, 15.0)}
    for i, (x, y) in track.items():
        epochs.append({"index": i, "mjd_mid": 60800.0 + 180 * i})
        stacks[i] = {3: blob(x, y, seed=i)}

    def marker(mjd):
        i = int(round((mjd - 60800.0) / 180))
        return track[i]

    rows = [{"detector": 3, "inside": True, "hard_flag": False, "soft_flag": False, "snr": 30.0}] * 20
    out = checks.run_checks(rows, epochs, stacks, marker)
    status = {c["name"]: c["status"] for c in out["checks"]}
    assert status == {"Seen again": "pass", "Clean pixels": "pass", "Moves as predicted": "pass"}


def test_single_detection_warns():
    epochs = [{"index": 0, "mjd_mid": 60800.0}, {"index": 1, "mjd_mid": 60980.0}]
    stacks = {0: {3: blob(15, 15)}, 1: {3: np.random.default_rng(5).normal(0, 1, (31, 31))}}
    rows = [{"detector": 3, "inside": True, "hard_flag": False, "soft_flag": False, "snr": 10.0}] * 5
    out = checks.run_checks(rows, epochs, stacks, lambda mjd: (15.0, 15.0))
    assert out["checks"][0]["status"] == "warn"
