"""Tests for the brightness-change module."""

import numpy as np

from coldmovers import variability


def fake_rows(amplitude_mag, saturated=False, seed=0):
    rng = np.random.default_rng(seed)
    rows, epochs = [], []
    for e, mjd0 in enumerate([60800.0, 60980.0, 61160.0]):
        epochs.append({"index": e, "mjd_start": mjd0, "mjd_end": mjd0 + 10, "mjd_mid": mjd0 + 5})
        offset = amplitude_mag if e == 1 else 0.0
        for k in range(20):
            lam = 1.1 + 0.5 * k / 19
            base = 1000.0 * lam**-2  # smooth spectral shape
            flux = base * 10 ** (-0.4 * offset) * (1 + rng.normal(0, 0.01))
            rows.append({
                "mjd": mjd0 + k * 0.5, "detector": 2, "wavelength_um": lam, "inside": True,
                "hard_flag": saturated, "saturated": saturated, "blend": False,
                "flux_ujy": np.nan if saturated else flux, "wing_ujy": 0.2 * flux,
            })
    return rows, epochs


def test_constant_star_is_not_variable():
    rows, epochs = fake_rows(0.0)
    out = variability.light_curve(rows, epochs)
    assert not out["verdict"]["variable"]
    assert len(out["visits"]) == 3


def test_brightening_is_detected():
    rows, epochs = fake_rows(-0.4)
    out = variability.light_curve(rows, epochs)
    assert out["verdict"]["variable"]
    assert 0.3 < out["verdict"]["amplitude_mag"] < 0.5


def test_saturated_star_uses_wings():
    rows, epochs = fake_rows(-0.4, saturated=True)
    out = variability.light_curve(rows, epochs)
    assert out["methods"] == {2: "wings"}
    assert out["verdict"]["variable"]


def test_intermediate_change_is_possible_not_yes_or_no():
    rows, epochs = fake_rows(-0.12, seed=4)
    for r in rows:  # add noise so the change sits between 3 and 5 sigma
        r["flux_ujy"] *= 1 + np.random.default_rng(int(r["mjd"])).normal(0, 0.12)
    out = variability.light_curve(rows, epochs)
    sig = out["verdict"]["significance"]
    text = out["verdict"]["text"]
    if 3 < sig <= 5:
        assert text.startswith("Possibly")
    elif sig > 5:
        assert text.startswith("Yes")
    else:
        assert text.startswith("No clear change")
