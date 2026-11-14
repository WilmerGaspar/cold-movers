"""Tests for the Madhava engine. AI-assisted (Claude, Anthropic), reviewed by the team."""

import numpy as np
import pytest
from scipy.integrate import quad

from coldmovers import madhava as m


def fraction_by_integration(lam_um, temp):
    """Reference: integrate B_lambda numerically and divide by sigma T^4 / pi."""
    total = m.SIGMA_SB * temp**4 / np.pi
    value, _ = quad(lambda lam: m.planck_lambda(lam, temp), 1e-3, lam_um, limit=500, points=[m.wien_peak_um(temp)] if m.wien_peak_um(temp) < lam_um else None)
    return value / total


def test_full_spectrum_is_one():
    assert m.blackbody_fraction(1e9, 300.0) == pytest.approx(1.0, abs=1e-12)
    assert m.blackbody_fraction(1e-3, 300.0) == pytest.approx(0.0, abs=1e-12)


def test_quarter_of_energy_below_wien_peak():
    # Classic result: about 25.0 % of blackbody energy lies below the peak wavelength.
    for temp in (300.0, 1000.0, 5772.0):
        assert m.blackbody_fraction(m.wien_peak_um(temp), temp) == pytest.approx(0.25005, abs=2e-4)


@pytest.mark.parametrize("temp", [150.0, 600.0, 1500.0, 3100.0, 10000.0, 30000.0])
@pytest.mark.parametrize("lam", [0.75, 1.5, 2.9, 5.0])
def test_series_matches_numerical_integration(lam, temp):
    assert m.blackbody_fraction(lam, temp) == pytest.approx(fraction_by_integration(lam, temp), abs=1e-8)


def test_both_series_agree_at_switch_point():
    x = np.array([m._SMALL_X * 0.999, m._SMALL_X * 1.001])
    a = m._fraction_large_x(x)
    b = m._fraction_small_x(x)
    assert np.allclose(a, b, atol=1e-12)


def test_fraction_is_monotonic():
    lam = np.linspace(0.3, 30, 500)
    frac = m.blackbody_fraction(lam, 900.0)
    assert np.all(np.diff(frac) > 0)


def test_narrow_band_equals_planck_at_centre():
    lam, temp = 2.0, 1200.0
    narrow = m.band_mean_radiance(lam - 1e-4, lam + 1e-4, temp)
    assert narrow == pytest.approx(m.planck_lambda(lam, temp), rel=1e-5)


def synthetic_spectrum(temp, noise=0.03, seed=1):
    rng = np.random.default_rng(seed)
    lam = np.geomspace(0.75, 5.0, 102)
    bw = lam / 60.0
    true = m.band_model_fnu(lam, bw, temp)
    true = true / true.max() * 1000.0
    err = noise * true + 1.0
    flux = true + rng.normal(0, err)
    return lam, bw, flux, err


@pytest.mark.parametrize("temp", [800.0, 1500.0, 3100.0])
def test_fit_recovers_temperature_and_is_green(temp):
    lam, bw, flux, err = synthetic_spectrum(temp)
    res = m.fit_temperature(lam, bw, flux, err)
    assert res.t_low <= temp <= res.t_high
    assert abs(res.temperature - temp) / temp < 0.05
    assert res.light == "green"


def test_molecular_absorption_turns_yellow():
    lam, bw, flux, err = synthetic_spectrum(1200.0, noise=0.01)
    # Carve deep water and methane-like absorption bands.
    for centre, width, depth in [(1.4, 0.1, 0.8), (1.9, 0.15, 0.8), (2.3, 0.15, 0.6), (3.3, 0.3, 0.9)]:
        flux = flux * (1 - depth * np.exp(-0.5 * ((lam - centre) / width) ** 2))
    res = m.fit_temperature(lam, bw, flux, err)
    assert res.light == "yellow"
    assert "not_a_single_blackbody" in res.reasons


def test_too_few_points_is_red():
    lam, bw, flux, err = synthetic_spectrum(2000.0)
    res = m.fit_temperature(lam[:4], bw[:4], flux[:4], err[:4])
    assert res.light == "red"


def test_pure_noise_is_red():
    rng = np.random.default_rng(3)
    lam = np.geomspace(0.75, 5.0, 60)
    res = m.fit_temperature(lam, lam / 60, rng.normal(0, 1, lam.size), np.ones(lam.size))
    assert res.light == "red"


def test_peak_outside_range_is_yellow():
    lam, bw, flux, err = synthetic_spectrum(6000.0, noise=0.02)
    res = m.fit_temperature(lam, bw, flux, err)
    assert res.light in ("yellow", "red")
    if res.light == "yellow":
        assert "peak_below_0p75um" in res.reasons


def test_limits_lambda_zero_and_infinity():
    # Reviewer's finding: lambda -> 0 must give 0 (no energy below), lambda -> inf gives 1.
    assert m.blackbody_fraction(0.0, 1000.0) == 0.0
    assert m.blackbody_fraction(np.inf, 1000.0) == pytest.approx(1.0)


def test_uncertainty_interval_ignores_a_separate_minimum():
    grid = np.linspace(100, 1000, 901)
    chi = np.minimum((grid - 300) ** 2 / 100.0, (grid - 800) ** 2 / 100.0 + 0.5)
    lo, hi = m._contiguous_interval(grid, chi, 300.0, level=1.0)
    assert lo == pytest.approx(290, abs=1) and hi == pytest.approx(310, abs=1)


def test_error_floor_does_not_vanish_for_faint_points():
    lam = np.linspace(1, 2, 21)
    f = np.full(21, 100.0)
    f[10] = 0.5  # a point that came out near zero
    ref = m._floor_reference(lam, f)
    assert ref[10] == pytest.approx(100.0)
    assert np.all(ref >= np.abs(f))
