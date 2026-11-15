"""Sky atlas images: Gaia DR3 stars with motion arrows over a SPHEREx stack (primary,
no external image service needed) or over an AllWISE image from CDS (when CDS is up).

The background comes from the CDS hips2fits service (AllWISE colour survey, 2010).
Gaia DR3 stars are queried from the ESA Gaia archive; each star is drawn at its
2010 position (the WISE epoch) with an arrow showing where its proper motion takes
it in 20 years. Everything is drawn on the server, so no browser plug-in is needed.
"""

from __future__ import annotations

import io

import numpy as np

from .net import call_with_timeout  # noqa: F401  (re-exported)

HIPS2FITS = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits"
WISE_EPOCH = 2010.5
GAIA_EPOCH = 2016.0
ARROW_YEARS = 20.0


def fetch_allwise(ra_deg: float, dec_deg: float, fov_deg: float, size: int = 480) -> np.ndarray:
    """RGB image (rows from the bottom up) of the AllWISE colour survey around a position."""
    import requests
    from PIL import Image

    params = {
        "hips": "CDS/P/allWISE/color", "width": size, "height": size, "fov": fov_deg,
        "projection": "TAN", "coordsys": "icrs", "ra": ra_deg, "dec": dec_deg, "format": "jpg",
    }
    resp = requests.get(HIPS2FITS, params=params, timeout=15)
    resp.raise_for_status()
    img = np.array(Image.open(io.BytesIO(resp.content)).convert("RGB"))
    return img[::-1]  # first row at the bottom, like the sky coordinates


_GAIA_PAUSED_UNTIL = 0.0
GAIA_PAUSE_S = 300.0


def gaia_field_timed(ra_deg: float, dec_deg: float, radius_deg: float, timeout_s: float = 12.0,
                     max_rows: int = 400) -> list:
    """gaia_field with a time limit (TimeoutError instead of a frozen page).

    After one timeout the archive is not asked again for a few minutes, so every page
    stays fast while it is down.
    """
    import time

    global _GAIA_PAUSED_UNTIL
    if time.time() < _GAIA_PAUSED_UNTIL:
        raise TimeoutError("the ESA Gaia archive stopped answering a few minutes ago")
    try:
        return call_with_timeout(gaia_field, timeout_s, ra_deg, dec_deg, radius_deg, max_rows)
    except TimeoutError:
        _GAIA_PAUSED_UNTIL = time.time() + GAIA_PAUSE_S
        raise


def gaia_field(ra_deg: float, dec_deg: float, radius_deg: float, max_rows: int = 400) -> list:
    """Gaia DR3 sources in a circle: position (epoch 2016.0), proper motion, G magnitude."""
    from astroquery.gaia import Gaia

    query = f"""
    SELECT TOP {int(max_rows)} source_id, ra, dec, pmra, pmdec, phot_g_mean_mag
    FROM gaiadr3.gaia_source
    WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra_deg}, {dec_deg}, {radius_deg}))
    ORDER BY phot_g_mean_mag ASC
    """
    table = Gaia.launch_job(query).get_results()
    out = []
    for row in table:
        def val(name):
            v = row[name]
            try:
                f = float(v)
                return f if np.isfinite(f) else 0.0
            except (TypeError, ValueError):
                return 0.0
        out.append({"ra": val("ra"), "dec": val("dec"), "pmra": val("pmra"), "pmdec": val("pmdec"),
                    "g": val("phot_g_mean_mag")})
    return out


def render(ra_c, dec_c, fov_deg, image, stars, obj_now, obj_2010, title="", size_in=6.0) -> bytes:
    """Draw the atlas PNG. obj_now / obj_2010 are (ra, dec) of the target."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = image.shape[0]
    scale = n / fov_deg  # pixels per degree
    cosd = np.cos(np.radians(dec_c))

    def to_px(ra, dec):
        x = (n - 1) / 2.0 - (ra - ra_c) * cosd * scale  # east to the left
        y = (n - 1) / 2.0 + (dec - dec_c) * scale
        return x, y

    fig, ax = plt.subplots(figsize=(size_in, size_in + 0.5), dpi=100, facecolor="#0b0f1a")
    ax.imshow(image, origin="lower", interpolation="bilinear")
    for s in stars:
        dt = WISE_EPOCH - GAIA_EPOCH
        ra10 = s["ra"] + s["pmra"] * dt / 3.6e6 / cosd
        dec10 = s["dec"] + s["pmdec"] * dt / 3.6e6
        x, y = to_px(ra10, dec10)
        if not (0 <= x < n and 0 <= y < n):
            continue
        ax.plot(x, y, marker="s", ms=5, mfc="none", mec="#41b6c4", mew=0.9)
        pm = np.hypot(s["pmra"], s["pmdec"])
        if pm > 30:  # mas/yr: draw where it goes in ARROW_YEARS
            x2, y2 = to_px(ra10 + s["pmra"] * ARROW_YEARS / 3.6e6 / cosd, dec10 + s["pmdec"] * ARROW_YEARS / 3.6e6)
            ax.annotate("", xy=(x2, y2), xytext=(x, y),
                        arrowprops=dict(arrowstyle="-|>", color="#41b6c4", lw=1.0))
    for (ra, dec), label in ((obj_2010, "2010 (WISE)"), (obj_now, "now (SPHEREx)")):
        x, y = to_px(ra, dec)
        ax.add_patch(plt.Circle((x, y), n * 0.035, fill=False, color="#ff5a36", lw=1.8))
        ax.text(x + n * 0.045, y + n * 0.02, label, color="#ff5a36", fontsize=8, weight="bold")
    ax.set_xlim(0, n - 1)
    ax.set_ylim(0, n - 1)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#232b40")
    ax.set_title(title, color="#e8ecf4", fontsize=9)
    fig.text(0.01, 0.005, f"N up, E left · field {fov_deg * 60:.1f}′ · AllWISE via CDS hips2fits · Gaia DR3 (ESA)",
             ha="left", va="bottom", fontsize=6, color="#8a93a6")
    fig.text(0.99, 0.005, "Cold Movers", ha="right", va="bottom", fontsize=6,
             color="#8a93a6")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#0b0f1a")
    plt.close(fig)
    return buf.getvalue()


def stars_at_year(stars, year: float):
    """Gaia DR3 positions (epoch 2016.0) moved to another year with their proper motion."""
    out = []
    for s in stars:
        cosd = np.cos(np.radians(s["dec"]))
        dt = year - GAIA_EPOCH
        out.append(dict(s, ra=s["ra"] + s["pmra"] * dt / 3.6e6 / cosd, dec=s["dec"] + s["pmdec"] * dt / 3.6e6))
    return out


def render_on_spherex(image, to_px, stars, year: float, target_xy, title="", size_in=6.0):
    """Gaia DR3 stars (moved to `year`) with 20-year motion arrows, drawn on a SPHEREx stack.

    image: 2D stack on the movie grid; to_px(ra, dec) -> (x, y) on that grid.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    finite = image[np.isfinite(image)]
    lo, hi = (np.percentile(finite, [5, 99.7]) if finite.size else (0.0, 1.0))
    norm = np.arcsinh(np.clip((image - lo) / max(hi - lo, 1e-9), 0, None) * 10) / np.arcsinh(10)
    ny, nx = image.shape
    fig, ax = plt.subplots(figsize=(size_in, size_in + 0.5), dpi=100, facecolor="#0b0f1a")
    ax.imshow(np.nan_to_num(norm), origin="lower", cmap="gray", vmin=0, vmax=1, interpolation="nearest")
    shown = 0
    for s in stars_at_year(stars, year):
        x, y = to_px(s["ra"], s["dec"])
        if not (-0.5 <= x < nx - 0.5 and -0.5 <= y < ny - 0.5):
            continue
        shown += 1
        ax.plot(x, y, marker="s", ms=6, mfc="none", mec="#41b6c4", mew=0.9)
        if np.hypot(s["pmra"], s["pmdec"]) > 30:  # mas/yr
            cosd = np.cos(np.radians(s["dec"]))
            x2, y2 = to_px(s["ra"] + s["pmra"] * ARROW_YEARS / 3.6e6 / cosd,
                           s["dec"] + s["pmdec"] * ARROW_YEARS / 3.6e6)
            ax.annotate("", xy=(x2, y2), xytext=(x, y), arrowprops=dict(arrowstyle="-|>", color="#41b6c4", lw=1.1))
    if target_xy is not None:
        ax.add_patch(plt.Circle(target_xy, 3.0, fill=False, color="#ff5a36", lw=1.8))
    ax.set_xlim(-0.5, nx - 0.5)
    ax.set_ylim(-0.5, ny - 0.5)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#232b40")
    ax.set_title(title, color="#e8ecf4", fontsize=9)
    fig.text(0.01, 0.005, f"SPHEREx stack · Gaia DR3 (ESA) stars moved to {year:.1f} · arrows: 20 years of motion",
             ha="left", va="bottom", fontsize=6, color="#8a93a6")
    fig.text(0.99, 0.005, "Cold Movers", ha="right", va="bottom", fontsize=6,
             color="#8a93a6")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#0b0f1a")
    plt.close(fig)
    return buf.getvalue(), shown
