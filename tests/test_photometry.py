"""Tests for forced photometry. AI-assisted (Claude, Anthropic), reviewed by the team."""

import numpy as np
import pytest

from coldmovers import photometry
from coldmovers.spherex import HARD_MASK


def star_image(flux=1000.0, x0=15.3, y0=14.6, sigma=0.9, bkg=5.0, noise=0.0, seed=0):
    yy, xx = np.mgrid[0:31, 0:31]
    img = bkg + flux / (2 * np.pi * sigma**2) * np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * sigma**2))
    if noise:
        img = img + np.random.default_rng(seed).normal(0, noise, img.shape)
    return img


def test_recovers_flux_and_removes_background():
    img = star_image()
    var = np.full(img.shape, 0.01)
    flags = np.zeros(img.shape, dtype=np.int64)
    res = photometry.measure(img, var, flags, 15.3, 14.6, pixel_sr=1e-12)
    # Gaussian with sigma 0.9 px: 1 - exp(-2.5^2 / (2 * 0.9^2)) = 97.9 % lies within 2.5 px.
    expected = 1000.0 * (1 - np.exp(-(2.5**2) / (2 * 0.9**2)))
    assert res["flux_ujy"] == pytest.approx(expected, rel=0.015)
    assert res["background"] == pytest.approx(5.0, abs=1e-6)
    assert not res["hard_flag"]


def test_hard_flag_in_aperture_is_reported():
    img = star_image()
    flags = np.zeros(img.shape, dtype=np.int64)
    flags[15, 15] = 1 << 1  # OVERFLOW
    assert HARD_MASK & (1 << 1)
    res = photometry.measure(img, np.ones(img.shape), flags, 15.3, 14.6, pixel_sr=1e-12)
    assert res["hard_flag"]
    assert "OVERFLOW" in photometry.flag_names(res["flag_bits"])


def test_target_outside_image():
    img = star_image()
    res = photometry.measure(img, np.ones(img.shape), np.zeros(img.shape, int), 40.0, 3.0, pixel_sr=1e-12)
    assert not res["inside"]
    assert np.isnan(res["flux_ujy"])


def test_error_scales_with_noise():
    img = star_image(noise=2.0)
    res = photometry.measure(img, np.full(img.shape, 4.0), np.zeros(img.shape, int), 15.3, 14.6, pixel_sr=1e-12)
    assert 5 < res["err_ujy"] < 30


def test_error_grows_when_aperture_pixels_are_masked():
    img = star_image(noise=2.0)
    var = np.full(img.shape, 4.0)
    clean = photometry.measure(img, var, np.zeros(img.shape, dtype=np.int64), 15.3, 14.6, pixel_sr=1e-12)
    flags = np.zeros(img.shape, dtype=np.int64)
    flags[13, 13] = flags[13, 17] = flags[16, 13] = 1 << 10  # three HOT pixels at the aperture edge
    masked = photometry.measure(img, var, flags, 15.3, 14.6, pixel_sr=1e-12)
    assert masked["n_ap"] < clean["n_ap"]
    assert masked["err_ujy"] > clean["err_ujy"]
