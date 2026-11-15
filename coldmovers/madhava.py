"""Madhava engine: blackbody-equivalent temperature from band-integrated Planck fits.

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


_SCALE = 15.0 / np.pi**4
# Bound for the Bernoulli expansion: the first term left out (k = 22), doubled. Successive
# terms shrink by at least (x / 2 pi)^2 < 0.007 for x < 0.5, so the doubling is generous.
_SMALL_TAIL_COEF = 2.0 * abs(float(bernoulli(22)[22])) / (25.0 * float(factorial(22)))


def _c(n, x, x2, x3):
    return x3 / n + 3.0 * x2 / n**2 + 6.0 * x / n**3 + 6.0 / n**4


def _large_x_with_bound(x: np.ndarray, tol: float = 1e-15, max_terms: int = 100000):
    """Sum N terms, then add a Madhava correction for everything that was left out.

    Madhava of Sangamagrama did not simply cut his series for pi: he added a correction
    term that estimates the part left out. We do the same here. Each term is
    t_n = exp(-n x) c_n with c_n = x^3/n + 3x^2/n^2 + 6x/n^3 + 6/n^4. Since c_n is a sum of
    log-convex functions of n, the ratio q_n = t_(n+1) / t_n grows with n and stays below
    exp(-x). The part left out after N terms, R_N, is therefore trapped:

        t_(N+1) / (1 - q_(N+1))  <=  R_N  <=  t_(N+1) / (1 - exp(-x))

    The correction is the midpoint of that interval, and half its width is a guaranteed
    bound on the truncation error. Returns (fraction, bound, number of terms summed).
    """
    x = np.asarray(x, dtype=float)
    x2, x3 = x * x, x * x * x
    em = np.exp(-x)
    one_minus_em = -np.expm1(-x)
    total = np.exp(-x) * _c(1, x, x2, x3)  # t_1
    c_next = _c(2, x, x2, x3)
    n = 1
    while True:
        nxt = np.exp(-(n + 1) * x) * c_next  # t_(n+1)
        c_after = _c(n + 2, x, x2, x3)
        lower = nxt / (1.0 - em * c_after / c_next)
        upper = nxt / one_minus_em
        bound = 0.5 * (upper - lower)
        if n >= max_terms or np.all(bound <= tol * total):
            break
        total += nxt
        c_next = c_after
        n += 1
    return _SCALE * (total + 0.5 * (lower + upper)), _SCALE * bound, n


def _fraction_large_x(x: np.ndarray, tol: float = 1e-15, max_terms: int = 100000) -> np.ndarray:
    """Series with Madhava's correction, accurate and fast for x >= ~0.5."""
    return _large_x_with_bound(x, tol, max_terms)[0]


def _fraction_small_x(x: np.ndarray) -> np.ndarray:
    """1 - (15/pi^4) * integral_0^x t^3/(e^t-1) dt, using Bernoulli numbers."""
    powers = x[..., None] ** (_K + 3)
    integral = np.sum(_COEF * powers, axis=-1)
    return 1.0 - _SCALE * integral


def fraction_with_bound(lam_um, temperature_k):
    """Blackbody fraction below lam, a guaranteed bound on its series error, and terms used.

    Returns (fraction, bound, terms): arrays of the broadcast shape, plus the largest
    number of series terms summed before Madhava's correction (0 if not needed).
    """
    lam = np.asarray(lam_um, dtype=float)
    temp = np.asarray(temperature_k, dtype=float)
    lam, temp = np.broadcast_arrays(lam, temp)
    with np.errstate(divide="ignore", over="ignore"):
        x = C2_UM_K / (lam * temp)
    out = np.empty(x.shape, dtype=float)
    bound = np.zeros(x.shape, dtype=float)
    terms = 0
    finite = np.isfinite(x)
    big = finite & (x >= _SMALL_X)
    small = finite & (x < _SMALL_X)
    if np.any(big):
        out[big], bound[big], terms = _large_x_with_bound(x[big])
    if np.any(small):
        out[small] = _fraction_small_x(x[small])
        bound[small] = _SCALE * _SMALL_TAIL_COEF * x[small] ** 25
    out[np.isposinf(x)] = 0.0  # lam -> 0 (or T -> 0): no energy below
    out[np.isnan(x)] = np.nan
    bound[np.isnan(x)] = np.nan
    return np.clip(out, 0.0, 1.0), bound, terms


def blackbody_fraction(lam_um, temperature_k) -> np.ndarray:
    """Fraction of blackbody energy emitted below wavelength lam (micrometre) at T (K)."""
    return fraction_with_bound(lam_um, temperature_k)[0]


def series_report(lam_um, bandwidth_um, temperature_k) -> dict:
    """How the series behaved for the bands of one fit.

    terms: most series terms summed before Madhava's correction.
    max_rel_bound: guaranteed truncation error of the band models, relative to their value.
    """
    lam = np.asarray(lam_um, dtype=float)
    half = 0.5 * np.asarray(bandwidth_um, dtype=float)
    f_hi, b_hi, n_hi = fraction_with_bound(lam + half, temperature_k)
    f_lo, b_lo, n_lo = fraction_with_bound(lam - half, temperature_k)
    diff = np.abs(f_hi - f_lo)
    ok = np.isfinite(diff) & (diff > 0)
    rel = (b_hi[ok] + b_lo[ok]) / diff[ok]
    return {"terms": int(max(n_hi, n_lo)),
            "max_rel_bound": float(np.max(rel)) if rel.size else float("nan")}


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


def _floor_reference(lam, f, window: int = 9) -> np.ndarray:
    """Flux used for the systematic floor: |f|, or the local running median if larger.

    With |f| alone, a point whose flux came out near zero (or negative after the
    background was removed) would get almost no floor and too much weight.
    """
    order = np.argsort(lam)
    fs = np.abs(f[order])
    half = window // 2
    local = np.array([np.median(fs[max(0, i - half): i + half + 1]) for i in range(fs.size)])
    ref = np.empty_like(fs)
    ref[order] = np.maximum(fs, local)
    return ref


def _contiguous_interval(grid, chi, t_best, level):
    """Lowest and highest grid temperature of the connected region around t_best
    where chi2 <= level (a second, separate minimum does not widen the interval)."""
    ok = chi <= level
    i0 = int(np.argmin(np.abs(grid - t_best)))
    if not ok[i0]:
        return float(t_best), float(t_best)
    lo = hi = i0
    while lo > 0 and ok[lo - 1]:
        lo -= 1
    while hi < grid.size - 1 and ok[hi + 1]:
        hi += 1
    return float(grid[lo]), float(grid[hi])


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

    sigma = np.sqrt(e**2 + (error_floor * _floor_reference(lam, f)) ** 2)
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
    t_low, t_high = _contiguous_interval(fine, chi_fine, t_best, chi_best + delta)

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
    "narrow_coverage": (
        "The usable measurements cover too narrow a range of wavelengths to pin down a temperature."
    ),
    "only_long_wavelengths": (
        "It only shows up beyond 3 um. That alone says it is very cold: anything warmer than about "
        "1000 K would also shine at shorter wavelengths."
    ),
    "partly_saturated":"Some wavelengths saturate the detector and were left out.",
    "neighbour_removed": (
        "A neighbouring source blended with the target in some images; those measurements were left out."
    ),
    "colder_than_range":"Colder than the fit can measure: almost all its light is beyond 5 um.",
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
