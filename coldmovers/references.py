"""Published temperatures of the five challenge objects, used to check our results.

These are effective temperatures from detailed spectral modelling. A blackbody fit
to 0.75-5 um photometry is not expected to match them exactly for objects with
deep molecular bands or dusty disks; the comparison shows how far one can trust it.
"""

PUBLISHED = {
    "barnard": {
        "teff_k": 3231, "low_k": 3210, "high_k": 3252,
        "text": "3231 ± 21 K (M4 red dwarf)",
        "ref": "Jahandar et al. 2024, ApJ (SPIRou high-resolution spectroscopy), arXiv:2310.12125",
    },
    "epsindib": {
        "teff_k": 1150, "low_k": 880, "high_k": 1340,
        "text": "Ba ≈ 1300–1340 K (T1), Bb ≈ 880–940 K (T6); SPHEREx sees the pair blended",
        "ref": "King et al. 2010, A&A, arXiv:0911.3143",
    },
    "wise0855": {
        "teff_k": 285, "low_k": 265, "high_k": 285,
        "text": "≈ 285 K (Y dwarf, coldest known brown dwarf)",
        "ref": "Luhman et al. 2024, AJ (JWST/NIRSpec), arXiv:2311.17316",
    },
    "rwaur": {
        "teff_k": None, "low_k": None, "high_k": None,
        "text": "K-type young star; its dusty disk adds extra infrared light",
        "ref": "SIMBAD spectral classification; disk: Rodriguez et al. 2013, arXiv:1308.2017",
    },
    "trappist1": {
        "teff_k": 2566, "low_k": 2540, "high_k": 2592,
        "text": "2566 ± 26 K (M8 dwarf with seven planets)",
        "ref": "Agol et al. 2021, Planetary Science Journal (via the NASA Exoplanet Archive)",
    },
    "rdra": {
        "teff_k": None, "low_k": None, "high_k": None,
        "text": "Mira variable (M-type giant): brightness and temperature change over its cycle",
        "ref": "SIMBAD / AAVSO Variable Star Index",
    },
}
