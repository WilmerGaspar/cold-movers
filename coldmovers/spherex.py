"""SPHEREx data access through NASA/IPAC IRSA.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.

Search: IRSA Simple Image Access v2 (SIA2) on the DR1 and QR3 Wide collections,
following IRSA's tutorial "Introduction to SPHEREx Spectral Images"; TAP on the
spherex.artifact / spherex.plane tables is used as a fallback.
Download: IRSA's cutout service (append ?center=RA,DEC&size=DEG to the image URL),
so only a small square around the target is transferred.
Each cutout keeps the SPHEREx layers IMAGE (MJy/sr), FLAGS, VARIANCE, ZODI, EPSF and
WCS-WAVE; the wavelength at any pixel comes from the "W" world coordinate system.

Data: SPHEREx DR1 (doi:10.26131/IRSA678) and Quick Release 3, NASA/JPL-Caltech/IPAC.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

IRSA = "https://irsa.ipac.caltech.edu"
COLLECTIONS = ("spherex_dr1", "spherex_qr3")
PIXEL_ARCSEC = 6.15
CACHE_DIR = os.environ.get("COLDMOVERS_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "coldmovers"))

# Approximate wavelength range of each SPHEREx detector [micrometre]
DETECTOR_RANGE_UM = {
    1: (0.75, 1.09),
    2: (1.10, 1.62),
    3: (1.63, 2.41),
    4: (2.42, 3.82),
    5: (3.83, 4.41),
    6: (4.42, 5.00),
}

# FLAGS bits (from the MSKN/MSKD keywords of the FLAGS layer)
FLAG_NAMES = {
    0: "TRANSIENT", 1: "OVERFLOW", 2: "SUR_ERROR", 6: "NONFUNC", 7: "DICHROIC",
    9: "MISSING_DATA", 10: "HOT", 11: "COLD", 12: "FULLSAMPLE", 14: "PHANMISS",
    15: "NONLINEAR", 17: "PERSIST", 19: "OUTLIER", 20: "CROSSTALK", 21: "SOURCE",
    22: "GHOST", 23: "GHOST_FPA", 24: "GHOST_EXT", 25: "STREAK", 26: "BLOOM",
    27: "SNOWBALL", 28: "HALO",
}
# Pixels with these bits are not used for photometry.
HARD_BITS = (1, 2, 6, 9, 10, 11, 15, 17, 19, 25, 26, 27, 28)
# These bits do not remove the pixel but are reported as possible contamination.
SOFT_BITS = (0, 7, 14, 20, 22, 23, 24)
HARD_MASK = int(sum(1 << b for b in HARD_BITS))
SOFT_MASK = int(sum(1 << b for b in SOFT_BITS))
# Saturation: the detector overflowed (very bright sources such as Barnard's Star).
SAT_MASK = int((1 << 1) | (1 << 2))
# For the movie only dead or missing pixels are hidden; saturated cores are drawn white.
MOVIE_MASK = int((1 << 6) | (1 << 9))


def _quiet():
    logging.getLogger("astropy").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", module="astropy")
    warnings.filterwarnings("ignore", message=".*SIP.*")
    warnings.filterwarnings("ignore", message=".*datfix.*")


def detector_from_name(name) -> int:
    match = re.search(r"D([1-6])", str(name))
    return int(match.group(1)) if match else 0


# --------------------------------------------------------------------------- search


def _table_to_rows(table, url_col, time_col, band_col, obs_col=None, collection=""):
    rows = []
    cols = {c.lower(): c for c in table.colnames}

    def get(row, name):
        c = cols.get(name.lower()) if name else None
        return row[c] if c else None

    for row in table:
        url = str(get(row, url_col))
        if not url or url == "None":
            continue
        if url.startswith("/") or not url.startswith("http"):
            url = f"{IRSA}/{url.lstrip('/')}"
        try:
            mjd = float(get(row, time_col))
        except (TypeError, ValueError):
            continue
        band = get(row, band_col)
        det = detector_from_name(band) or detector_from_name(url)
        rows.append({
            "url": url.split("?")[0],
            "mjd": mjd,
            "detector": det,
            "obs_id": str(get(row, obs_col)) if obs_col else "",
            "collection": collection,
        })
    return rows


def search_images(ra_deg: float, dec_deg: float, collections=COLLECTIONS, attempts: int = 6):
    """List SPHEREx spectral images covering a sky position, sorted by time.

    Returns a list of dicts: url, mjd, detector (1-6), obs_id, collection.
    IRSA sometimes answers 502/503 for a moment, so the search is retried.
    """
    last = None
    for attempt in range(attempts):
        try:
            return _search_once(ra_deg, dec_deg, collections)
        except RuntimeError as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(min(10 * (attempt + 1), 45))
    raise last


def _search_once(ra_deg: float, dec_deg: float, collections=COLLECTIONS):
    _quiet()
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    coord = SkyCoord(ra_deg, dec_deg, unit="deg", frame="icrs")
    rows, errors = [], []
    try:
        from astroquery.ipac.irsa import Irsa

        for coll in collections:
            table = Irsa.query_sia(pos=(coord, 1 * u.arcsec), collection=coll)
            if hasattr(table, "to_table"):
                table = table.to_table()
            rows += _table_to_rows(table, "access_url", "t_min", "energy_bandpassname", "obs_id", coll)
    except Exception as exc:  # fall back to TAP
        errors.append(f"SIA: {exc}")
        rows = []
    if not rows:
        try:
            rows = _search_tap(ra_deg, dec_deg)
        except Exception as exc:
            errors.append(f"TAP: {exc}")
    if not rows and errors:
        raise RuntimeError("IRSA search failed: " + " | ".join(errors))

    seen, unique = set(), []
    for r in sorted(rows, key=lambda r: r["mjd"]):
        if r["url"] in seen or r["detector"] == 0:
            continue
        seen.add(r["url"])
        unique.append(r)
    return unique


def _search_tap(ra_deg, dec_deg):
    from astroquery.ipac.irsa import Irsa

    query = f"""
    SELECT a.uri, p.time_bounds_lower, p.energy_bandpassname
    FROM spherex.artifact a
    JOIN spherex.plane p ON a.planeid = p.planeid
    WHERE 1 = CONTAINS(POINT('ICRS', {ra_deg}, {dec_deg}), p.poly)
    ORDER BY p.time_bounds_lower
    """
    table = Irsa.query_tap(query).to_table()
    return _table_to_rows(table, "uri", "time_bounds_lower", "energy_bandpassname", None, "tap")


def select_spread(rows, max_frames: int):
    """Keep at most max_frames images, spread evenly in time (keeps all epochs)."""
    if max_frames is None or len(rows) <= max_frames:
        return list(rows)
    idx = np.unique(np.linspace(0, len(rows) - 1, max_frames).round().astype(int))
    return [rows[i] for i in idx]


# ------------------------------------------------------------------------- cutouts


@dataclass
class Frame:
    url: str
    mjd: float
    detector: int
    image: np.ndarray
    variance: np.ndarray
    flags: np.ndarray
    wcs: object
    pixel_sr: float
    spectral_wcs: object = None
    version: str = ""
    meta: dict = field(default_factory=dict)

    def wavelength_at(self, x: float, y: float):
        """Central wavelength and bandwidth (micrometre) at pixel (x, y)."""
        if self.spectral_wcs is None:
            return np.nan, np.nan
        try:
            wl, bw = self.spectral_wcs.pixel_to_world(x, y)
            return float(wl.to_value("um")), float(bw.to_value("um"))
        except Exception:
            try:
                wl, bw = self.spectral_wcs.wcs_pix2world(x, y, 0)
                return float(wl) * 1e6, float(bw) * 1e6  # SI metres -> micrometre
            except Exception:
                return np.nan, np.nan


def cutout_url(url: str, ra_deg: float, dec_deg: float, size_deg: float) -> str:
    return f"{url}?center={ra_deg:.6f},{dec_deg:.6f}d&size={size_deg:.4f}"


def _cache_path(key: str) -> str:
    h = hashlib.sha1(key.encode()).hexdigest()
    return os.path.join(CACHE_DIR, h[:2], h + ".fits")


def fetch_bytes(url: str, retries: int = 6, timeout: float = 90.0) -> bytes:
    import requests

    path = _cache_path(url)
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read()
    last = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "ColdMovers/0.1 (NASA Space Apps 2026)"})
            if resp.status_code in (429, 502, 503, 504):
                # IRSA is busy: wait longer each time before trying again.
                last = RuntimeError(f"HTTP {resp.status_code}")
                time.sleep(4 * (attempt + 1) + np.random.uniform(0, 2))
                continue
            resp.raise_for_status()
            data = resp.content
            if not data.startswith(b"SIMPLE"):
                raise ValueError("response is not a FITS file")
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(data)
            except OSError:
                pass
            return data
        except Exception as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"download failed: {last}")


def parse_cutout(data: bytes, row: dict) -> Frame:
    _quiet()
    from astropy.io import fits
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_area

    with fits.open(io.BytesIO(data), memmap=False) as hdul:
        img_hdu = hdul["IMAGE"] if "IMAGE" in hdul else hdul[1]
        header = img_hdu.header
        image = np.array(img_hdu.data, dtype=np.float32)
        flags = np.array(hdul["FLAGS"].data, dtype=np.int64) if "FLAGS" in hdul else np.zeros(image.shape, np.int64)
        variance = (
            np.array(hdul["VARIANCE"].data, dtype=np.float32) if "VARIANCE" in hdul else np.full(image.shape, np.nan, np.float32)
        )
        wcs = WCS(header)
        try:
            spectral = WCS(header, fobj=hdul, key="W")
            spectral.sip = None
        except Exception:
            spectral = None
        pixel_deg2 = proj_plane_pixel_area(wcs.celestial)
        version = str(hdul[0].header.get("VERSION", "")) if len(hdul) else ""
        meta = {k: header.get(k) for k in ("DATE", "MJD-AVG", "MJD-BEG", "DETECTOR", "BUNIT") if k in header}
    return Frame(
        url=row["url"], mjd=float(row["mjd"]), detector=int(row["detector"]),
        image=image, variance=variance, flags=flags, wcs=wcs if wcs.naxis == 2 else wcs.celestial,
        pixel_sr=float(pixel_deg2) * (np.pi / 180.0) ** 2, spectral_wcs=spectral,
        version=version, meta=meta,
    )


def download_frames(rows, center_for_row, size_deg: float, workers: int = 6, progress=None):
    """Download and parse cutouts in parallel.

    center_for_row(row) -> (ra, dec) gives the cutout centre for each image.
    progress(done, total) is called as downloads finish.
    Returns (frames, failures).
    """
    frames, failures = [], []
    total = len(rows)

    def job(row):
        ra, dec = center_for_row(row)
        data = fetch_bytes(cutout_url(row["url"], ra, dec, size_deg))
        return parse_cutout(data, row)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(job, r): r for r in rows}
        for done, fut in enumerate(as_completed(futures), start=1):
            try:
                frames.append(fut.result())
            except Exception as exc:
                failures.append({"url": futures[fut]["url"], "error": str(exc)[:200]})
            if progress:
                progress(done, total)
    frames.sort(key=lambda f: f.mjd)
    return frames, failures
