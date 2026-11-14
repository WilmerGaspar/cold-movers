"""Sky movie: align SPHEREx cutouts by their WCS, stack them by epoch, animate.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.

Why stack by detector and epoch?
SPHEREx uses linear variable filters: the wavelength changes across each detector,
so consecutive raw images of the same spot are taken at different wavelengths and
the sky "changes colour" from frame to frame. Averaging all images of one detector
taken during one visit (an epoch) gives a broadband image per detector, the sum
per detector suggested in the challenge brief. Blinking those epoch images, all on
the same sky grid, makes real motion visible, in the spirit of WiseView.
"""

from __future__ import annotations

import io

import numpy as np
from scipy.ndimage import map_coordinates

from .spherex import DETECTOR_RANGE_UM, HARD_MASK, PIXEL_ARCSEC

EPOCH_GAP_DAYS = 20.0


def make_reference_wcs(ra_deg: float, dec_deg: float, size_deg: float, pixel_arcsec: float = PIXEL_ARCSEC):
    from astropy.wcs import WCS

    n = int(np.ceil(size_deg * 3600.0 / pixel_arcsec))
    n += (n + 1) % 2  # odd, so the target sits on the central pixel
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra_deg, dec_deg]
    w.wcs.crpix = [(n + 1) / 2.0, (n + 1) / 2.0]
    w.wcs.cdelt = [-pixel_arcsec / 3600.0, pixel_arcsec / 3600.0]
    return w, (n, n)


def reproject_frame(frame, ref_wcs, shape) -> np.ndarray:
    """Resample a frame onto the reference grid (bilinear); bad pixels become NaN."""
    ny, nx = shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    ra, dec = ref_wcs.wcs_pix2world(xx.ravel(), yy.ravel(), 0)
    x_in, y_in = frame.wcs.world_to_pixel_values(ra, dec)
    img = np.array(frame.image, dtype=float)
    bad = (np.asarray(frame.flags, dtype=np.int64) & HARD_MASK) != 0
    img[bad] = np.nan
    finite = np.isfinite(img)
    med = np.nanmedian(img) if finite.any() else 0.0
    filled = np.where(finite, img - med, 0.0)
    weight = finite.astype(float)
    coords = np.vstack([np.asarray(y_in), np.asarray(x_in)])
    val = map_coordinates(filled, coords, order=1, mode="constant", cval=0.0)
    wgt = map_coordinates(weight, coords, order=1, mode="constant", cval=0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(wgt > 0.5, val / wgt, np.nan)
    return out.reshape(shape)


def group_epochs(mjds, gap_days: float = EPOCH_GAP_DAYS):
    """Label sorted dates into epochs separated by gaps longer than gap_days."""
    mjds = np.asarray(mjds, dtype=float)
    order = np.argsort(mjds)
    labels = np.empty(mjds.size, dtype=int)
    current = 0
    for k, i in enumerate(order):
        if k > 0 and mjds[i] - mjds[order[k - 1]] > gap_days:
            current += 1
        labels[i] = current
    return labels


def build_epoch_stacks(frames, ref_wcs, shape, gap_days: float = EPOCH_GAP_DAYS):
    """Return a list of epoch dicts with a stacked image per detector."""
    if not frames:
        return []
    labels = group_epochs([f.mjd for f in frames], gap_days)
    epochs = []
    for e in range(labels.max() + 1):
        members = [f for f, lab in zip(frames, labels) if lab == e]
        stacks, counts = {}, {}
        for det in range(1, 7):
            imgs = [reproject_frame(f, ref_wcs, shape) for f in members if f.detector == det]
            if imgs:
                with np.errstate(all="ignore"):
                    stacks[det] = np.nanmean(np.array(imgs), axis=0)
                counts[det] = len(imgs)
        if stacks:
            # "All detectors": each detector scaled by its own noise, then averaged.
            normed = []
            for img in stacks.values():
                v = img[np.isfinite(img)]
                sd = 1.4826 * np.median(np.abs(v - np.median(v))) if v.size else 1.0
                normed.append(img / (sd if sd > 0 else 1.0))
            with np.errstate(all="ignore"):
                stacks[0] = np.nanmean(np.array(normed), axis=0)
            counts[0] = sum(counts.values())
        mj = np.array([f.mjd for f in members])
        epochs.append({
            "index": e, "mjd_start": float(mj.min()), "mjd_end": float(mj.max()),
            "mjd_mid": float(np.median(mj)), "n_frames": len(members),
            "stacks": stacks, "counts": counts,
        })
    return epochs


def detector_label(det: int) -> str:
    if det == 0:
        return "All detectors (0.75-5.0 um)"
    lo, hi = DETECTOR_RANGE_UM[det]
    return f"Detector {det} ({lo:.2f}-{hi:.2f} um)"


def _stretch(images):
    vals = np.concatenate([im[np.isfinite(im)].ravel() for im in images if im is not None and np.isfinite(im).any()])
    if vals.size == 0:
        return 0.0, 1.0
    lo, hi = np.percentile(vals, [5, 99.7])
    return float(lo), float(hi if hi > lo else lo + 1)


def render_frames(epochs, det: int, marker_pixels=None, title_fn=None, dpi: int = 100):
    """Render one PNG (bytes) per epoch for a detector, with a common stretch."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    usable = [ep for ep in epochs if det in ep["stacks"]]
    if not usable:
        return []
    lo, hi = _stretch([ep["stacks"][det] for ep in usable])
    pngs = []
    for k, ep in enumerate(usable):
        img = ep["stacks"][det]
        norm = np.arcsinh(np.clip((img - lo) / (hi - lo), 0, None) * 10) / np.arcsinh(10)
        fig, ax = plt.subplots(figsize=(4.2, 4.6), dpi=dpi)
        ax.imshow(np.nan_to_num(norm, nan=0.0), origin="lower", cmap="gray", vmin=0, vmax=1, interpolation="nearest")
        if marker_pixels is not None:
            px, py = marker_pixels(ep["mjd_mid"])
            ax.add_patch(plt.Circle((px, py), 3.0, fill=False, color="#ff5a36", lw=1.5))
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(title_fn(ep, det, k, len(usable)) if title_fn else f"epoch {k + 1}", fontsize=9)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        pngs.append(buf.getvalue())
    return pngs


def frames_to_gif(pngs, ms_per_frame: int = 700) -> bytes:
    from PIL import Image

    if not pngs:
        return b""
    images = [Image.open(io.BytesIO(p)).convert("P", palette=Image.ADAPTIVE) for p in pngs]
    buf = io.BytesIO()
    images[0].save(buf, format="GIF", save_all=True, append_images=images[1:], duration=ms_per_frame, loop=0)
    return buf.getvalue()


def difference_image(epochs, det: int):
    """Last epoch minus first epoch for a detector (None if fewer than two)."""
    usable = [ep for ep in epochs if det in ep["stacks"]]
    if len(usable) < 2:
        return None
    return usable[-1]["stacks"][det] - usable[0]["stacks"][det]
