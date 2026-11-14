"""Targets: the five challenge objects, name lookup and proper-motion propagation.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.

Positions move: Barnard's Star travels about 10.4 arcsec per year, so a position
from the year 2000 is ~270 arcsec (44 SPHEREx pixels) off by 2026. Every frame is
therefore measured at the position propagated to that frame's own date.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

MJD_J2000 = 51544.5  # MJD of epoch J2000.0
DAYS_PER_JULIAN_YEAR = 365.25
MAS_PER_DEG = 3.6e6


def mjd_to_year(mjd):
    return 2000.0 + (np.asarray(mjd, dtype=float) - MJD_J2000) / DAYS_PER_JULIAN_YEAR


def year_to_mjd(year):
    return MJD_J2000 + (np.asarray(year, dtype=float) - 2000.0) * DAYS_PER_JULIAN_YEAR


@dataclass
class Target:
    key: str
    name: str
    ra_deg: float
    dec_deg: float
    pmra_masyr: float = 0.0  # mu_alpha * cos(delta)
    pmdec_masyr: float = 0.0
    parallax_mas: float | None = None
    ref_epoch: float = 2000.0  # Julian year at which ra/dec are valid
    source: str = "user input"
    note: str = ""

    def position_at(self, mjd):
        """(ra, dec) in degrees at the given MJD, linear proper-motion propagation.

        Over a few decades this is accurate to far better than one SPHEREx pixel
        (6.15 arcsec) for every object in the challenge.
        """
        dt = mjd_to_year(mjd) - self.ref_epoch
        dec = self.dec_deg + self.pmdec_masyr * dt / MAS_PER_DEG
        ra = self.ra_deg + self.pmra_masyr * dt / MAS_PER_DEG / np.cos(np.radians(self.dec_deg))
        return np.mod(ra, 360.0), dec

    @property
    def total_pm_arcsec_per_year(self) -> float:
        return float(np.hypot(self.pmra_masyr, self.pmdec_masyr) / 1000.0)

    @property
    def distance_pc(self) -> float | None:
        if self.parallax_mas and self.parallax_mas > 0:
            return 1000.0 / self.parallax_mas
        return None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Target":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


# The five objects named in the challenge brief. These starting values are used
# only if SIMBAD cannot be reached; precomputed results record the values used.
SHOWCASE = {
    "barnard": Target(
        key="barnard", name="Barnard's Star", ra_deg=269.4520833, dec_deg=4.6933889,
        pmra_masyr=-801.551, pmdec_masyr=10362.394, parallax_mas=546.976,
        source="fallback (Gaia DR3 values)",
        note="Red dwarf with the largest proper motion of any star.",
    ),
    "epsindib": Target(
        key="epsindib", name="Epsilon Indi B", ra_deg=331.0438, dec_deg=-56.7827,
        pmra_masyr=3966.7, pmdec_masyr=-2536.2, parallax_mas=274.8,
        source="fallback (motion of Epsilon Indi A, Gaia DR3)",
        note="Pair of T-type brown dwarfs orbiting the star Epsilon Indi.",
    ),
    "wise0855": Target(
        key="wise0855", name="WISE 0855-0714", ra_deg=133.7951292, dec_deg=-7.2451472,
        pmra_masyr=-8123.7, pmdec_masyr=673.9, parallax_mas=439.0, ref_epoch=2010.5,
        source="fallback (challenge brief position; literature motion)",
        note="The coldest known brown dwarf, near the temperature of the North Pole.",
    ),
    "rwaur": Target(
        key="rwaur", name="RW Aurigae", ra_deg=76.9565, dec_deg=30.4014,
        source="fallback",
        note="Young star still surrounded by its dusty planet-forming disk.",
    ),
    "rdra": Target(
        key="rdra", name="R Draconis", ra_deg=248.1675, dec_deg=66.7550,
        source="fallback",
        note="Pulsating red giant (Mira variable) that brightens and fades over months.",
    ),
}

# Extra objects beyond the challenge brief. Starting values (SIMBAD, epoch J2000) are refined
# with Gaia DR3 astrometry before any computation.
EXTRAS = {
    "trappist1": Target(
        key="trappist1", name="TRAPPIST-1", ra_deg=346.6223667, dec_deg=-5.0414000,
        pmra_masyr=930.9, pmdec_masyr=-479.4, parallax_mas=80.2,
        source="starting values (SIMBAD J2000), refined with Gaia DR3",
        note="Ultracool red dwarf with seven Earth-sized planets.",
    ),
}

# Every example the app offers: the challenge objects first, then the extras.
ALL_EXAMPLES = {**SHOWCASE, **EXTRAS}

SIMBAD_IDS = {
    "barnard": "Barnard's star",
    "epsindib": "eps Ind B",
    "wise0855": "WISE J085510.83-071442.5",
    "rwaur": "RW Aur",
    "rdra": "R Dra",
}


def _col(table, *names):
    lower = {c.lower(): c for c in table.colnames}
    for n in names:
        if n.lower() in lower:
            return table[lower[n.lower()]]
    return None


def _num(value):
    try:
        v = float(value)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


SESAME_MIRRORS = (
    "https://cds.unistra.fr/cgi-bin/nph-sesame/-ox/S?",
    "https://vizier.cfa.harvard.edu/viz-bin/nph-sesame/-ox/S?",
)


class ServiceDown(RuntimeError):
    """The name services (SIMBAD and Sesame) did not answer."""


def resolve_simbad(name: str, key: str | None = None) -> Target:
    """Look up a name in SIMBAD; if its TAP service fails, ask the Sesame resolver (two mirrors).

    Raises LookupError when the name is unknown and ServiceDown when no service answers.
    """
    try:
        return _resolve_simbad_tap(name, key)
    except LookupError:
        raise
    except Exception:
        return resolve_sesame(name, key)


def resolve_sesame(name: str, key: str | None = None) -> Target:
    """CDS Sesame name resolver (SIMBAD data): position, proper motion and parallax."""
    import urllib.parse
    import xml.etree.ElementTree as ET

    import requests

    root, last = None, None
    for base_url in SESAME_MIRRORS:  # CDS (France) first, then its mirror at Harvard (USA)
        try:
            resp = requests.get(base_url + urllib.parse.quote(name), timeout=20)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            break
        except Exception as exc:
            last = exc
    if root is None:
        raise ServiceDown(f"name resolvers unreachable ({last})")
    res = next((r for r in root.iter("Resolver") if r.find("jradeg") is not None), None)
    if res is None:
        raise LookupError(f"SIMBAD does not know '{name}'.")

    def val(path):
        el = res.find(path)
        return _num(el.text) if el is not None and el.text else None

    base = SHOWCASE.get(key or "")
    oname = res.find("oname")
    label = oname.text.strip() if oname is not None and oname.text else name
    ref = res.find("refPos")
    src = "SIMBAD via Sesame" + (f" (position: {ref.text.strip()})" if ref is not None and ref.text else "")
    return Target(
        key=key or label.replace(" ", "_").lower(),
        name=base.name if base else label,
        ra_deg=float(val("jradeg")), dec_deg=float(val("jdedeg")),
        pmra_masyr=val("pm/pmRA") or 0.0, pmdec_masyr=val("pm/pmDE") or 0.0,
        parallax_mas=val("plx/v"), ref_epoch=2000.0, source=src,
        note=base.note if base else "",
    )


def _resolve_simbad_tap(name: str, key: str | None = None) -> Target:
    from astroquery.simbad import Simbad

    simbad = Simbad()
    simbad.add_votable_fields("pmra", "pmdec", "plx_value")
    table = simbad.query_object(name)
    if table is None or len(table) == 0:
        raise LookupError(f"SIMBAD does not know '{name}'.")
    row = table[0]
    ra = _num(_col(table, "ra", "RA_d")[0])
    dec = _num(_col(table, "dec", "DEC_d")[0])
    if ra is None or dec is None:
        from astropy.coordinates import SkyCoord
        import astropy.units as u

        c = SkyCoord(str(_col(table, "RA")[0]), str(_col(table, "DEC")[0]), unit=(u.hourangle, u.deg))
        ra, dec = c.ra.deg, c.dec.deg
    pmra = _num(_col(table, "pmra", "PMRA")[0]) or 0.0
    pmdec = _num(_col(table, "pmdec", "PMDEC")[0]) or 0.0
    plx_col = _col(table, "plx_value", "PLX_VALUE")
    plx = _num(plx_col[0]) if plx_col is not None else None
    main_id = _col(table, "main_id", "MAIN_ID")
    coo_bib = _col(table, "coo_bibcode", "COO_BIBCODE")
    label = str(main_id[0]) if main_id is not None else name
    src = "SIMBAD"
    if coo_bib is not None and str(coo_bib[0]).strip():
        src += f" (position: {str(coo_bib[0]).strip()})"
    base = SHOWCASE.get(key or "")
    return Target(
        key=key or label.replace(" ", "_").lower(),
        name=base.name if base else label,
        ra_deg=float(ra), dec_deg=float(dec), pmra_masyr=float(pmra), pmdec_masyr=float(pmdec),
        parallax_mas=plx, ref_epoch=2000.0, source=src,
        note=base.note if base else "",
    )


def gaia_parallax(target: Target, radius_arcsec: float = 4.0):
    """Gaia DR3 parallax of the brightest source at the target's 2016.0 position.

    Returns (parallax_mas, parallax_error_mas, source_id) or None. Used to replace
    old catalogue parallaxes (for example Hipparcos values for variable binaries).
    """
    from astroquery.gaia import Gaia

    ra, dec = target.position_at(year_to_mjd(2016.0))
    query = f"""
    SELECT TOP 3 source_id, parallax, parallax_error, phot_g_mean_mag
    FROM gaiadr3.gaia_source
    WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {float(ra)}, {float(dec)}, {radius_arcsec / 3600.0}))
      AND parallax IS NOT NULL
    ORDER BY phot_g_mean_mag ASC
    """
    table = Gaia.launch_job(query).get_results()
    if len(table) == 0:
        return None
    row = table[0]
    plx, err = float(row["parallax"]), float(row["parallax_error"])
    if not (np.isfinite(plx) and plx > 0 and err > 0 and plx / err > 10):
        return None
    return plx, err, int(row["source_id"])


def parse_coordinates(text: str):
    """Parse 'RA Dec' in degrees or sexagesimal. Returns (ra_deg, dec_deg)."""
    text = text.strip().replace(",", " ")
    parts = text.split()
    if len(parts) == 2:
        try:
            return float(parts[0]) % 360.0, float(parts[1])
        except ValueError:
            pass
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    c = SkyCoord(text, unit=(u.hourangle, u.deg), frame="icrs")
    return float(c.ra.deg), float(c.dec.deg)


def refine_with_gaia(target: Target, radius_arcsec: float = 6.0) -> Target:
    """Replace position, proper motion and parallax by Gaia DR3 values (epoch 2016.0).

    The Gaia source is the brightest one within radius_arcsec of the target's predicted
    2016.0 position. Raises LookupError if there is none.
    """
    from astroquery.gaia import Gaia

    ra, dec = target.position_at(year_to_mjd(2016.0))
    query = f"""
    SELECT TOP 3 source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag
    FROM gaiadr3.gaia_source
    WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {float(ra)}, {float(dec)}, {radius_arcsec / 3600.0}))
      AND pmra IS NOT NULL
    ORDER BY phot_g_mean_mag ASC
    """
    table = Gaia.launch_job(query).get_results()
    if len(table) == 0:
        raise LookupError(f"no Gaia DR3 source within {radius_arcsec} arcsec")
    row = table[0]
    return Target(
        key=target.key, name=target.name, ra_deg=float(row["ra"]), dec_deg=float(row["dec"]),
        pmra_masyr=float(row["pmra"]), pmdec_masyr=float(row["pmdec"]), parallax_mas=float(row["parallax"]),
        ref_epoch=2016.0, source=f"Gaia DR3 {int(row['source_id'])}", note=target.note,
    )
