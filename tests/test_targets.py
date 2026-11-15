"""Tests for proper-motion propagation."""

import numpy as np
import pytest

from coldmovers.targets import SHOWCASE, mjd_to_year, year_to_mjd


def test_epoch_conversion_round_trip():
    assert mjd_to_year(51544.5) == pytest.approx(2000.0)
    assert year_to_mjd(mjd_to_year(60900.0)) == pytest.approx(60900.0)


def test_barnard_moves_about_ten_arcsec_per_year():
    star = SHOWCASE["barnard"]
    ra1, dec1 = star.position_at(year_to_mjd(2025.0))
    ra2, dec2 = star.position_at(year_to_mjd(2026.0))
    shift = np.hypot((ra2 - ra1) * np.cos(np.radians(dec1)), dec2 - dec1) * 3600
    assert shift == pytest.approx(10.39, abs=0.05)
    assert star.total_pm_arcsec_per_year == pytest.approx(10.39, abs=0.05)


def test_barnard_has_moved_far_since_2000():
    star = SHOWCASE["barnard"]
    ra, dec = star.position_at(year_to_mjd(2026.0))
    shift = np.hypot((ra - star.ra_deg) * np.cos(np.radians(dec)), dec - star.dec_deg) * 3600
    assert shift > 250  # more than 40 SPHEREx pixels: propagation is essential


def test_distance_from_parallax():
    assert SHOWCASE["barnard"].distance_pc == pytest.approx(1.828, abs=0.01)


def test_json_safe_writes_null_for_nan():
    import json

    from coldmovers.pipeline import json_safe

    text = json.dumps(json_safe({"t": float("nan"), "x": [1.0, float("inf")], "n": np.int64(3)}), allow_nan=False)
    assert text == '{"t": null, "x": [1.0, null], "n": 3}'
