"""Sky atlas image: AllWISE background, Gaia DR3 stars with motion arrows, our object.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.

The background comes from the CDS hips2fits service (AllWISE colour survey, 2010).
Gaia DR3 stars are queried from the ESA Gaia archive; each star is drawn at its
2010 position (the WISE epoch) with an arrow showing where its proper motion takes
it in 20 years. Everything is drawn on the server, so no browser plug-in is needed.
"""

from __future__ import annotations

import io

import numpy as np

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
    resp = requests.get(HIPS2FITS, params=params, timeout=40)
    resp.raise_for_status()
    img = np.array(Image.open(io.BytesIO(resp.content)).convert("RGB"))
    return img[::-1]  # first row at the bottom, like the sky coordinates


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
    fig.text(0.99, 0.005, "Cold Movers · AI-assisted code (Claude)", ha="right", va="bottom", fontsize=6,
             color="#8a93a6")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#0b0f1a")
    plt.close(fig)
    return buf.getvalue()
