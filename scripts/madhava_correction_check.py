"""How much Madhava's correction term improves the Planck band series (prints a table).

For each x = hc/(lambda k T) the series is summed with the same number of terms N twice:
cut off after N terms (plain truncation), and with the Madhava correction added for the rest.
Both are compared with the series summed to 4,000 terms with exact float summation (math.fsum).
Only points where the plain error is well above computer rounding are compared.
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coldmovers import madhava as m  # noqa: E402


def exact(x):
    return m._SCALE * math.fsum(math.exp(-k * x) * (x**3 / k + 3 * x * x / k**2 + 6 * x / k**3 + 6 / k**4)
                                for k in range(1, 4000))


xs = np.array([0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0])
print("| Requested tolerance | Terms N | x | Plain truncation error | Error with Madhava's correction | "
      "Guaranteed bound | Improvement |")
print("|---|---|---|---|---|---|---|")
ratios = []
inside = []
for tol in (1e-4, 1e-6, 1e-8):
    value, bound, n = m._large_x_with_bound(xs, tol=tol)
    n = int(np.max(n))
    plain = m._SCALE * sum(np.exp(-k * xs) * m._c(k, xs, xs**2, xs**3) for k in range(1, n + 1))
    ref = np.array([exact(x) for x in xs])
    for x, p, v, b, r in zip(xs, plain, value, bound, ref):
        ep, ev = abs(p - r), abs(v - r)
        if ep < 1e3 * np.spacing(r):  # both at rounding level: nothing to compare
            continue
        ratios.append(ep / max(ev, np.spacing(r)))
        inside.append(ev <= b + 4 * np.spacing(r))
        print(f"| {tol:g} | {n} | {x:g} | {ep:.1e} | {ev:.1e} | {b:.1e} | {ratios[-1]:.0f}× |")
print(f"\nImprovement over plain truncation with the same terms: {min(ratios):.0f}× to {max(ratios):.0f}× "
      f"({len(ratios)} comparisons); corrected error inside its guaranteed bound in {sum(inside)} of {len(inside)}.")
sys.exit(0 if all(inside) else 1)
