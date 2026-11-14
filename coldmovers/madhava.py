"""Madhava engine: blackbody-equivalent temperature from band-integrated Planck fits.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.

Physics
-------
The fraction of blackbody energy emitted at wavelengths shorter than lam is

    F(0 -> lam, T) = (15 / pi^4) * sum_{n>=1} exp(-n x) (x^3/n + 3x^2/n^2 + 6x/n^3 + 6/n^4)

with x = h c / (lam k T)  (Widger & Woodall 1976, Bull. Amer. Meteor. Soc. 57, 1217).
For small x the complementary expansion based on Bernoulli numbers is used instead,
because the series above needs many terms there.

The mean spectral radiance inside a band [lam1, lam2] is then exact, not sampled:

    <B_lam> = (sigma T^4 / pi) * (F(0 -> lam2) - F(0 -> lam1)) / (lam2 - lam1)

SPHEREx bands are wide (spectral resolution R ~ 35-130), so integrating the Planck
curve over each band is more faithful than evaluating it at the band centre.

Name
----
"Madhava" is a homage to Madhava of Sangamagrama (c. 1340-1425), a pioneer of
infinite series. The series used here is standard textbook physics, not a new result.

Output
------
A *blackbody-equivalent* temperature with an uncertainty, the goodness of fit, and
a traffic light. It is NOT the effective temperature of a brown dwarf: their spectra
have deep molecular bands, so the light tells the user when the curve fits poorly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import bernoulli, factorial

# Physical constants (CODATA 2018)
C2_UM_K = 14387.768775039337  # second radiation constant h c / k  [micrometre * kelvin]
WIEN_B_UM_K = 2897.771955  # Wien displacement constant [micrometre * kelvin]
SIGMA_SB = 5.670374419e-8  # Stefan-Boltzmann constant [W m^-2 K^-4]

# SPHEREx wavelength coverage [micrometre]
SPHEREX_MIN_UM = 0.75
SPHEREX_MAX_UM = 5.0

# Temperatures whose Planck peak falls inside the SPHEREx coverage (about 580-3860 K).
PEAK_LOW_K = WIEN_B_UM_K / SPHEREX_MAX_UM
PEAK_HIGH_K = WIEN_B_UM_K / SPHEREX_MIN_UM

# Fit settings
DEFAULT_ERROR_FLOOR = 0.08  # conservative 8 % systematic floor added in quadrature
DEFAULT_T_MIN = 150.0
DEFAULT_T_MAX = 30000.0
CHI2_RED_YELLOW = 5.0  # above this the spectrum is not a single blackbody
MIN_POINTS = 6
MAX_REL_ERROR = 0.5

_SMALL_X = 0.5  # below this, use the Bernoulli expansion
_N_BERNOULLI = 20
_B = bernoulli(_N_BERNOULLI)
_K = np.arange(_N_BERNOULLI + 1)
# integral_0^x t^3/(e^t - 1) dt = sum_k B_k x^(k+3) / ((k+3) k!)
_COEF = np.where(_K == 1, -0.5, _B) / ((_K + 3) * factorial(_K))
_COEF[(_K % 2 == 1) & (_K > 1)] = 0.0


def _fraction_large_x(x: np.ndarray, tol: float = 1e-15, max_terms: int = 100000) -> np.ndarray:
    """Madhava-style series, accurate and fast for x >= ~0.5."""
    n_terms = int(min(max_terms, np.ceil(-np.log(tol) / max(np.min(x), 1e-12)) + 2))
    total = np.zeros_like(x)
    x2 = x * x
    x3 = x2 * x
    for n in range(1, n_terms + 1):
        term = np.exp(-n * x) * (x3 / n + 3.0 * x2 / n**2 + 6.0 * x / n**3 + 6.0 / n**4)
        total += term
        if np.all(term <= tol * total):
            break
    return 15.0 / np.pi**4 * total


def _fraction_small_x(x: np.ndarray) -> np.ndarray:
    """1 - (15/pi^4) * integral_0^x t^3/(e^t-1) dt, using Bernoulli numbers."""
    powers = x[..., None] ** (_K + 3)
    integral = np.sum(_COEF * powers, axis=-1)
    return 1.0 - 15.0 / np.pi**4 * integral


def blackbody_fraction(lam_um, temperature_k) -> np.ndarray:
    """Fraction of blackbody energy emitted below wavelength lam (micrometre) at T (K)."""
    lam = np.asarray(lam_um, dtype=float)
    temp = np.asarray(temperature_k, dtype=float)
    lam, temp = np.broadcast_arrays(lam, temp)
    with np.errstate(divide="ignore", over="ignore"):
        x = C2_UM_K / (lam * temp)
    out = np.empty(x.shape, dtype=float)
    big = x >= _SMALL_X
    if np.any(big):
        out[big] = _fraction_large_x(x[big])
    if np.any(~big):
        out[~big] = _fraction_small_x(x[~big])
    out[~np.isfinite(x)] = 1.0  # lam -> infinity
    return np.clip(out, 0.0, 1.0)


def planck_lambda(lam_um, temperature_k) -> np.ndarray:
    """Spectral radiance B_lambda in W m^-2 sr^-1 um^-1 (reference implementation)."""
    lam = np.asarray(lam_um, dtype=float)
    c1 = 1.191042972e8  # 2 h c^2 in W um^4 m^-2 sr^-1
    with np.errstate(over="ignore"):
        return c1 / lam**5 / np.expm1(C2_UM_K / (lam * temperature_k))


def band_mean_radiance(lam_lo_um, lam_hi_um, temperature_k) -> np.ndarray:
    """Exact mean of B_lambda over [lam_lo, lam_hi], in W m^-2 sr^-1 um^-1."""
    lo = np.asarray(lam_lo_um, dtype=float)
    hi = np.asarray(lam_hi_um, dtype=float)
    frac = blackbody_fraction(hi, temperature_k) - blackbody_fraction(lo, temperature_k)
    return SIGMA_SB * np.asarray(temperature_k, dtype=float) ** 4 / np.pi * frac / (hi - lo)


def band_model_fnu(lam_um, bandwidth_um, temperature_k) -> np.ndarray:
    """Shape of F_nu in each band (arbitrary units): <B_lambda> * lam_c^2."""
    lam = np.asarray(lam_um, dtype=float)
    half = 0.5 * np.asarray(bandwidth_um, dtype=float)
    return band_mean_radiance(lam - half, lam + half, temperature_k) * lam**2


@dataclass
class FitResult:
    temperature: float
    t_low: float
    t_high: float
    scale: float
    chi2: float
    dof: int
    n_points: int
    light: str  # "green", "yellow" or "red"
    reasons: list = field(default_factory=list)
    grid_t: np.ndarray | None = None
    grid_chi2: np.ndarray | None = None

    @property
    def chi2_red(self) -> float:
        return self.chi2 / self.dof if self.dof > 0 else float("nan")

    @property
    def error_minus(self) -> float:
        return self.temperature - self.t_low

    @property
    def error_plus(self) -> float:
        return self.t_high - self.temperature

    def as_dict(self) -> dict:
        return {
            "temperature_k": round(float(self.temperature), 1),
            "t_low_k": round(float(self.t_low), 1),
            "t_high_k": round(float(self.t_high), 1),
            "chi2_red": round(float(self.chi2_red), 3),
            "n_points": int(self.n_points),
            "light": self.light,
            "reasons": list(self.reasons),
        }


def _chi2_for(temp, lam, bw, flux, sigma):
    model = band_model_fnu(lam, bw, temp)
    w = 1.0 / sigma**2
    denom = np.sum(w * model * model)
    if denom <= 0 or not np.isfinite(denom):
        return np.inf, 0.0
    scale = max(np.sum(w * model * flux) / denom, 0.0)
    resid = (flux - scale * model) / sigma
    return float(np.sum(resid * resid)), float(scale)


def fit_temperature(
    lam_um,
    bandwidth_um,
    flux,
    flux_err,
    error_floor: float = DEFAULT_ERROR_FLOOR,
    t_min: float = DEFAULT_T_MIN,
    t_max: float = DEFAULT_T_MAX,
    n_grid: int = 400,
) -> FitResult:
    """Fit a band-integrated blackbody (free temperature and scale) to F_nu data.

    flux and flux_err can be in any F_nu unit (for example microjansky).
    The uncertainty interval is where chi2 rises by max(1, chi2_red) above the
    minimum (the usual inflation when the model does not fit perfectly).
    """
    lam = np.asarray(lam_um, dtype=float)
    bw = np.asarray(bandwidth_um, dtype=float)
    f = np.asarray(flux, dtype=float)
    e = np.asarray(flux_err, dtype=float)
    good = np.isfinite(lam) & np.isfinite(bw) & np.isfinite(f) & np.isfinite(e) & (e > 0) & (bw > 0)
    lam, bw, f, e = lam[good], bw[good], f[good], e[good]
    n = int(lam.size)

    if n < MIN_POINTS or np.sum(f / e > 3) < 3:
        return FitResult(
            temperature=float("nan"), t_low=float("nan"), t_high=float("nan"), scale=0.0,
            chi2=float("nan"), dof=max(n - 2, 0), n_points=n, light="red",
            reasons=["not_enough_signal"],
        )

    sigma = np.sqrt(e**2 + (error_floor * np.abs(f)) ** 2)
    grid = np.geomspace(t_min, t_max, n_grid)
    chi = np.array([_chi2_for(t, lam, bw, f, sigma)[0] for t in grid])
    i = int(np.nanargmin(chi))

    lo_t = grid[max(i - 1, 0)]
    hi_t = grid[min(i + 1, n_grid - 1)]
    if hi_t > lo_t:
        res = minimize_scalar(
            lambda lt: _chi2_for(np.exp(lt), lam, bw, f, sigma)[0],
            bounds=(np.log(lo_t), np.log(hi_t)), method="bounded",
        )
        t_best = float(np.exp(res.x))
    else:
        t_best = float(grid[i])
    chi_best, scale = _chi2_for(t_best, lam, bw, f, sigma)
    dof = max(n - 2, 1)
    chi2_red = chi_best / dof

    # Uncertainty from the chi2 profile on a fine grid around the minimum.
    delta = max(1.0, chi2_red)
    fine = np.geomspace(max(t_min, t_best / 4), min(t_max, t_best * 4), 800)
    chi_fine = np.array([_chi2_for(t, lam, bw, f, sigma)[0] for t in fine])
    inside = fine[chi_fine <= chi_best + delta]
    t_low = float(inside.min()) if inside.size else t_best
    t_high = float(inside.max()) if inside.size else t_best

    result = FitResult(
        temperature=t_best, t_low=t_low, t_high=t_high, scale=scale, chi2=chi_best,
        dof=dof, n_points=n, light="green", grid_t=grid, grid_chi2=chi,
    )
    result.light, result.reasons = traffic_light(result, t_min, t_max)
    return result


def traffic_light(result: FitResult, t_min: float = DEFAULT_T_MIN, t_max: float = DEFAULT_T_MAX):
    """Return ("green" | "yellow" | "red", [reason codes]).

    green : the Planck peak lies inside SPHEREx coverage (~580-3860 K) and one
            blackbody describes the spectrum within the errors.
    yellow: a temperature was measured, but the spectrum is not a single blackbody
            (molecular bands, a dusty disk, variability, blending), or the peak lies
            outside SPHEREx coverage so the value is an extrapolation.
    red   : no reliable temperature (too little signal, fit at the edge of the
            allowed range, or uncertainty larger than 50 %).
    """
    t = result.temperature
    if not np.isfinite(t):
        return "red", ["not_enough_signal"]
    reasons = []
    if t <= t_min * 1.05:
        reasons.append("colder_than_range")
    if t >= t_max * 0.95:
        reasons.append("hotter_than_range")
    if (result.t_high - result.t_low) / 2 > MAX_REL_ERROR * t:
        reasons.append("uncertainty_too_large")
    if reasons:
        return "red", reasons

    if result.chi2_red > CHI2_RED_YELLOW:
        reasons.append("not_a_single_blackbody")
    if t < PEAK_LOW_K:
        reasons.append("peak_beyond_5um")
    if t > PEAK_HIGH_K:
        reasons.append("peak_below_0p75um")
    return ("yellow", reasons) if reasons else ("green", ["clean_blackbody_fit"])


REASON_TEXT = {
    "not_enough_signal": "Not enough clean SPHEREx measurements to fit a temperature.",
    "too_bright": (
        "Too bright for SPHEREx: the star saturates the detector, so its brightness cannot be measured "
        "from these images. SPHEREx was built to see faint objects; compare with the published value."
    ),
    "colder_than_range": "Colder than the fit can measure: almost all its light is beyond 5 um.",
    "hotter_than_range": "Hotter than the fit can measure with SPHEREx bands.",
    "uncertainty_too_large": "The uncertainty is larger than half the value.",
    "not_a_single_blackbody": (
        "One blackbody does not describe this spectrum: expect molecular bands "
        "(water, methane, CO), a dusty disk, variability or a blended neighbour."
    ),
    "peak_beyond_5um": "Its Planck peak is beyond 5 um, so the temperature is an extrapolation.",
    "peak_below_0p75um": "Its Planck peak is below 0.75 um, so the temperature is an extrapolation.",
    "clean_blackbody_fit": "One blackbody fits the SPHEREx spectrum within the errors.",
}


def wien_peak_um(temperature_k: float) -> float:
    return WIEN_B_UM_K / temperature_k
