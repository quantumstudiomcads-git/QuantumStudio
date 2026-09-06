"""Pure numerical helpers for E5D Eliashberg convergence and Tc studies."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

import numpy as np


class EliashbergAnalysisError(ValueError):
    pass


def _spectrum(frequency, alpha2f):
    w = np.asarray(frequency, dtype=float)
    a = np.asarray(alpha2f, dtype=float)
    if w.ndim != 1 or a.ndim != 1 or w.shape != a.shape or len(w) < 2:
        raise EliashbergAnalysisError("frequency and alpha2F must be equal one-dimensional arrays.")
    if not np.all(np.isfinite(w)) or not np.all(np.isfinite(a)) or np.any(w < 0) or np.any(np.diff(w) < 0):
        raise EliashbergAnalysisError("frequency and alpha2F must be finite and ordered.")
    return w, a


def lambda_integral(frequency, alpha2f):
    from .epw import integrate_lambda
    return integrate_lambda(*_spectrum(frequency, alpha2f))


def cumulative_lambda(frequency, alpha2f):
    w, a = _spectrum(frequency, alpha2f)
    integrand = np.divide(a, w, out=np.zeros_like(a), where=w != 0)
    result = np.zeros_like(w)
    result[1:] = np.cumsum(0.5 * (integrand[1:] + integrand[:-1]) * np.diff(w)) * 2.0
    return result


def omega_log(frequency, alpha2f):
    w, a = _spectrum(frequency, alpha2f)
    lam = lambda_integral(w, a)
    if lam <= 0:
        raise EliashbergAnalysisError("omega_log requires positive lambda.")
    positive = w > 0
    integrand = np.zeros_like(a)
    integrand[positive] = a[positive] / w[positive] * np.log(w[positive])
    return float(np.exp(2.0 * np.trapezoid(integrand, w) / lam))


def omega_2(frequency, alpha2f):
    """Return the Allen-Dynes square-root second moment."""
    w, a = _spectrum(frequency, alpha2f)
    lam = lambda_integral(w, a)
    if lam <= 0:
        raise EliashbergAnalysisError("omega_2 requires positive lambda.")
    return float(np.sqrt(2.0 * np.trapezoid(a * w, w) / lam))


def relative_change(old, new):
    old, new = float(old), float(new)
    scale = max(abs(old), abs(new), np.finfo(float).tiny)
    return abs(new - old) / scale


def is_converged(old, new, tolerance):
    if tolerance < 0:
        raise EliashbergAnalysisError("convergence tolerance must be non-negative.")
    return relative_change(old, new) <= tolerance


def mcmillan_tc(lambda_ep, omega_log_value, mu_star=0.10):
    """Original McMillan form using omega_log as the supplied characteristic scale."""
    lam, omega, mu = float(lambda_ep), float(omega_log_value), float(mu_star)
    if lam <= 0 or omega <= 0 or not 0 <= mu < 1:
        raise EliashbergAnalysisError("invalid McMillan parameters.")
    denominator = lam - mu * (1.0 + 0.62 * lam)
    if denominator <= 0:
        raise EliashbergAnalysisError("McMillan denominator is non-positive.")
    # omega_log is in the same energy unit as the spectrum; convert meV to K.
    omega_K = omega * 11.60451812
    return omega_K / 1.45 * math.exp(-1.04 * (1.0 + lam) / denominator)


def allen_dynes_factors(lambda_ep, omega_log_value, omega_2_value, mu_star=0.10):
    lam, omega_log_value, omega_2_value, mu = map(float, (lambda_ep, omega_log_value, omega_2_value, mu_star))
    if lam <= 0 or omega_log_value <= 0 or omega_2_value <= 0 or not 0 <= mu < 1:
        raise EliashbergAnalysisError("invalid Allen-Dynes parameters.")
    f1 = (1.0 + (lam / (2.46 * (1.0 + 3.8 * mu))) ** 1.5) ** (1.0 / 3.0)
    ratio = omega_2_value / omega_log_value
    f2 = 1.0 + ((ratio - 1.0) * lam * lam) / (lam * lam + (1.82 * (1.0 + 6.3 * mu) * ratio) ** 2)
    return f1, f2


def allen_dynes_tc(lambda_ep, omega_log_value, omega_2_value, mu_star=0.10):
    f1, f2 = allen_dynes_factors(lambda_ep, omega_log_value, omega_2_value, mu_star)
    lam, omega, mu = float(lambda_ep), float(omega_log_value), float(mu_star)
    denominator = lam - mu * (1.0 + 0.62 * lam)
    if denominator <= 0:
        raise EliashbergAnalysisError("Allen-Dynes denominator is non-positive.")
    omega_K = omega * 11.60451812
    return f1 * f2 * omega_K / 1.2 * math.exp(-1.04 * (1.0 + lam) / denominator)


@dataclass(frozen=True)
class MuStarAssumption:
    value: float = 0.10
    source: str = "USER/MODEL_ASSUMPTION"

    def __post_init__(self):
        if not 0 <= float(self.value) < 1:
            raise EliashbergAnalysisError("mu_star must be in [0, 1).")


def transition_temperature(temperatures, criterion, *, target=1.0):
    """Linearly interpolate one bounded transition bracket."""
    t = np.asarray(temperatures, dtype=float)
    y = np.asarray(criterion, dtype=float)
    if t.ndim != 1 or y.shape != t.shape or len(t) < 2 or np.any(np.diff(t) <= 0):
        raise EliashbergAnalysisError("temperature scan must be ordered and paired.")
    crossings = []
    for i in range(len(t) - 1):
        a, b = y[i] - target, y[i + 1] - target
        if a == 0:
            crossings.append((t[i], t[i]))
        elif a * b < 0:
            crossings.append((t[i], t[i + 1]))
    if len(crossings) != 1:
        raise EliashbergAnalysisError("temperature scan has no unique transition bracket.")
    lo, hi = crossings[0]
    if lo == hi:
        return float(lo), (float(lo), float(hi))
    i = int(np.where(t == lo)[0][0])
    tc = lo + (target - y[i]) * (hi - lo) / (y[i + 1] - y[i])
    return float(tc), (float(lo), float(hi))
