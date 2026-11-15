"""Forced aperture photometry on SPHEREx cutouts.

For each image the target position is propagated to that image's date, converted
to a pixel with the image's own WCS, and the flux is summed in a circular aperture
after removing the local background measured in a ring around it. Pixels with
serious FLAGS bits are excluded; any flagged pixel in the aperture is reported.

Units: SPHEREx images are surface brightness in MJy/sr; multiplying by the pixel
solid angle gives MJy, reported here in microjansky (uJy).
An aperture of 2.5 pixels (~15 arcsec) does not capture all the light of the
point-spread function; because the temperature fit has a free scale, a constant
aperture loss does not change the temperature.
"""

from __future__ import annotations

import numpy as np

from .spherex import FLAG_NAMES, HARD_MASK, SAT_MASK, SOFT_MASK

R_APERTURE = 2.5
R_IN = 5.0
R_OUT = 9.0
UJY_PER_MJY = 1e12


def _robust_stats(values: np.ndarray):
    v = values[np.isfinite(values)]
    if v.size < 5:
        return np.nan, np.nan
    for _ in range(3):
        med = np.median(v)
        mad = 1.4826 * np.median(np.abs(v - med))
        if mad <= 0:
            break
        keep = np.abs(v - med) < 3 * mad
        if keep.all():
            break
        v = v[keep]
    med = np.median(v)
    mad = 1.4826 * np.median(np.abs(v - med))
    return float(med), float(mad)


def flag_names(bits: int) -> list:
    return [name for b, name in FLAG_NAMES.items() if bits & (1 << b)]


def measure(image, variance, flags, x, y, pixel_sr, r_ap=R_APERTURE, r_in=R_IN, r_out=R_OUT) -> dict:
    """Aperture flux (uJy) at pixel (x, y). Returns a dict with flux, error and quality."""
    ny, nx = image.shape
    out = {
        "x": float(x), "y": float(y), "flux_ujy": np.nan, "err_ujy": np.nan,
        "background": np.nan, "hard_flag": True, "soft_flag": False, "saturated": False, "flag_bits": 0,
        "inside": False, "n_ap": 0, "wing_ujy": np.nan, "wing2_ujy": np.nan,
    }
    if not (np.isfinite(x) and np.isfinite(y)):
        return out
    if x < r_ap or y < r_ap or x > nx - 1 - r_ap or y > ny - 1 - r_ap:
        return out
    out["inside"] = True

    yy, xx = np.indices(image.shape)
    rr = np.hypot(xx - x, yy - y)
    ap = rr <= r_ap
    ring = (rr >= r_in) & (rr <= r_out)

    flags = np.asarray(flags, dtype=np.int64)
    finite = np.isfinite(image)
    hard = ((flags & HARD_MASK) != 0) | ~finite
    ap_bits = int(np.bitwise_or.reduce(flags[ap])) if ap.any() else 0
    out["flag_bits"] = ap_bits
    out["hard_flag"] = bool(np.any(hard & ap))
    out["soft_flag"] = bool(ap_bits & SOFT_MASK)
    out["saturated"] = bool(ap_bits & SAT_MASK)

    ring_ok = ring & ~hard & ((flags & SOFT_MASK) == 0)
    if ring_ok.sum() < 8:
        ring_ok = ring & ~hard
    bkg, bkg_sd = _robust_stats(image[ring_ok])
    out["background"] = bkg
    out["wing_ujy"] = _wing_flux(image, rr, hard, pixel_sr)
    out["wing2_ujy"] = _wing_flux(image, rr, hard, pixel_sr, WING2_IN, WING2_OUT, FAR2_IN, FAR2_OUT)
    if not np.isfinite(bkg):
        return out

    use = ap & ~hard
    n_ap = int(use.sum())
    out["n_ap"] = n_ap
    if n_ap < 0.6 * ap.sum():
        out["hard_flag"] = True
        return out

    # A few masked aperture pixels: scale the sum of the good ones up to the full aperture.
    # The same factor multiplies the noise of those pixels, so the variance gets it squared.
    scale = ap.sum() / n_ap
    signal = np.sum(image[use] - bkg) * scale
    var = np.nansum(np.asarray(variance)[use])
    if not np.isfinite(var) or var <= 0:
        var = n_ap * bkg_sd**2
    var = var * scale**2 + ap.sum() ** 2 * bkg_sd**2 / max(ring_ok.sum(), 1)
    out["flux_ujy"] = float(signal * pixel_sr * UJY_PER_MJY)
    out["err_ujy"] = float(np.sqrt(var) * pixel_sr * UJY_PER_MJY)
    return out


WING_IN, WING_OUT = 3.0, 6.0
FAR_IN, FAR_OUT = 10.0, 14.0
# Outer ring for the brightest stars, whose saturation and blooming reach past 6 px.
WING2_IN, WING2_OUT = 6.0, 10.0
FAR2_IN, FAR2_OUT = 13.0, 17.0


def _wing_flux(image, rr, hard, pixel_sr, r_in=WING_IN, r_out=WING_OUT, far_in=FAR_IN, far_out=FAR_OUT) -> float:
    """Light in the wings of the star (3-6 px), with the sky measured further out (10-14 px).

    Saturation only affects the core, and at a fixed wavelength the wings are a fixed
    fraction of the total light, so wing flux tracks brightness changes of very
    bright (saturated) stars from one visit to the next. Returns uJy or NaN.
    """
    wing = (rr >= r_in) & (rr <= r_out)
    far = (rr >= far_in) & (rr <= far_out) & ~hard
    good = wing & ~hard
    if far.sum() < 12 or good.sum() < 0.5 * wing.sum():
        return float("nan")
    sky, _ = _robust_stats(image[far])
    if not np.isfinite(sky):
        return float("nan")
    return float(np.sum(image[good] - sky) * wing.sum() / good.sum() * pixel_sr * UJY_PER_MJY)


def measure_frame(frame, ra_deg: float, dec_deg: float) -> dict:
    """Photometry of one SPHEREx Frame at a sky position, plus wavelength and date."""
    x, y = frame.wcs.world_to_pixel_values(ra_deg, dec_deg)
    x, y = float(x), float(y)
    res = measure(frame.image, frame.variance, frame.flags, x, y, frame.pixel_sr)
    wl, bw = frame.wavelength_at(x, y)
    res.update({
        "mjd": frame.mjd, "detector": frame.detector, "wavelength_um": wl, "bandwidth_um": bw,
        "ra": ra_deg, "dec": dec_deg, "url": frame.url,
    })
    res["snr"] = res["flux_ujy"] / res["err_ujy"] if res["err_ujy"] and res["err_ujy"] > 0 else np.nan
    return res
