"""Field mover search: which sources in the field move, measured without any catalogue.

Every visit stack (all images of one visit, aligned on the same sky grid) is searched
for point sources. Each source of the first visit is followed to the nearest source in
the other visits, and a straight-line motion is fitted to its positions over time.
The motion of the stationary stars sets the noise floor (how well the images line up),
so a source is ranked by how many times its motion exceeds that floor.

No proper motion, catalogue or prior position is used: this is the independent check
that complements "Consistent with catalogue motion". Gaia DR3 is consulted only
afterwards, to say which movers are already known.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import maximum_filter

from .checks import PIXEL_ARCSEC, centroid

DETECT_SNR = 6.0  # peak height in units of the robust noise
MATCH_RADIUS_PX = 4.0  # a source may move at most this far between first and last visit
EDGE_PX = 3
MIN_SIGNIFICANCE = 5.0  # combined significance for a confirmed mover
CANDIDATE_SIGNIFICANCE = 3.0  # per detector
MIN_SHIFT_PX = 0.5
SYS_ALIGN_PX = 0.12  # per-visit alignment uncertainty (static stars line up to ~0.1-0.2 px)
PSF_SIGMA_PX = 0.9  # SPHEREx point-spread function width (sigma) in pixels, roughly
MAX_FIELD_MEDIAN_SHIFT_PX = 0.5  # beyond this the field is too disturbed to trust
MAX_FIT_RMS_PX = 0.6
# Neighbour pull: when two movers come within this distance of each other in some visit, the
# light of one can pull the measured centroid of the other. Found with the blind injection
# benchmark: a fake mover passing 2-4 px from a still star made the star itself look like a
# confirmed mover. The less significant of the pair (a pulled centroid gives a small shift
# for its uncertainty) is therefore kept as a candidate, never confirmed.
BLEND_PX = 4.0  # a real mover follows a straight line


def _noise(image):
    v = image[np.isfinite(image)]
    if v.size < 20:
        return np.nan, np.nan
    med = np.median(v)
    return float(med), float(1.4826 * np.median(np.abs(v - med)))


def detect(image, snr: float = DETECT_SNR, edge: int = EDGE_PX):
    """Point sources in a stack: list of (x, y, peak_snr), refined by centroiding."""
    med, sd = _noise(image)
    if not np.isfinite(sd) or sd <= 0:
        return []
    img = np.nan_to_num(image - med, nan=0.0)
    peaks = (img == maximum_filter(img, size=3)) & (img > snr * sd)
    ny, nx = img.shape
    out = []
    for y, x in zip(*np.nonzero(peaks)):
        if x < edge or y < edge or x > nx - 1 - edge or y > ny - 1 - edge:
            continue
        cx, cy, s = centroid(image, float(x), float(y), half=2, iterations=2)
        if np.isfinite(cx) and np.hypot(cx - x, cy - y) < 1.5:
            out.append((cx, cy, float(img[y, x] / sd)))
    # merge duplicates closer than 1.5 px (keep the brighter)
    out.sort(key=lambda s: -s[2])
    merged = []
    for s in out:
        if all(np.hypot(s[0] - m[0], s[1] - m[1]) > 1.5 for m in merged):
            merged.append(s)
    return merged


def search(epochs, stacks, det: int = 0) -> dict:
    """Follow every source of the first usable visit through the others and fit its motion.

    epochs: list of dicts with index and mjd_mid; stacks: {epoch_index: {det: image}}.
    Returns {"sources": [...], "floor_px": float, "n_visits": int, "span_years": float}.
    """
    usable = [ep for ep in epochs if det in stacks.get(ep["index"], {})]
    usable.sort(key=lambda ep: ep["mjd_mid"])
    if len(usable) < 2:
        return {"sources": [], "floor_px": float("nan"), "reliable": False, "n_visits": len(usable),
                "span_years": 0.0, "detector": det}
    found = {ep["index"]: detect(stacks[ep["index"]][det]) for ep in usable}
    first = usable[0]
    t0 = first["mjd_mid"]
    years = {ep["index"]: (ep["mjd_mid"] - t0) / 365.25 for ep in usable}
    span = years[usable[-1]["index"]]

    def nearest_other(cands, j):
        others = [np.hypot(c[0] - cands[j][0], c[1] - cands[j][1]) for k, c in enumerate(cands) if k != j]
        return float(min(others)) if others else float("inf")

    tracks = []
    first_found = found[first["index"]]
    for i0, (x0, y0, s0) in enumerate(first_found):
        pts = [(0.0, x0, y0)]
        neighbour = nearest_other(first_found, i0)
        for ep in usable[1:]:
            cands = found[ep["index"]]
            if not cands:
                continue
            # predict from the motion so far (none yet for the second visit)
            if len(pts) >= 2:
                t = np.array([p[0] for p in pts])
                vx = np.polyfit(t, [p[1] for p in pts], 1)[0]
                vy = np.polyfit(t, [p[2] for p in pts], 1)[0]
                px, py = x0 + vx * years[ep["index"]], y0 + vy * years[ep["index"]]
            else:
                px, py = x0, y0
            d = [np.hypot(c[0] - px, c[1] - py) for c in cands]
            j = int(np.argmin(d))
            if d[j] <= MATCH_RADIUS_PX:
                pts.append((years[ep["index"]], cands[j][0], cands[j][1]))
                neighbour = min(neighbour, nearest_other(cands, j))
        if len(pts) < 2:
            continue
        t = np.array([p[0] for p in pts])
        xs = np.array([p[1] for p in pts])
        ys = np.array([p[2] for p in pts])
        if t.max() - t.min() <= 0:
            continue
        vx = float(np.polyfit(t, xs, 1)[0])
        vy = float(np.polyfit(t, ys, 1)[0])
        tracks.append({"x": float(x0), "y": float(y0), "snr": s0, "n_visits": len(pts), "t0_mjd": float(t0),
                       "t_span": float(t.max() - t.min()),
                       "vx_px_yr": vx, "vy_px_yr": vy,
                       "shift_px": float(np.hypot(vx, vy) * (t.max() - t.min())),
                       "min_neighbour_px": neighbour,
                       "points": [(float(a), float(b), float(c)) for a, b, c in pts]})

    # Uncertainty of each position: a centroiding term that shrinks with brightness plus a
    # systematic alignment term, per visit. The shift between first and last visit then has
    # sqrt(2) times that uncertainty.
    for tr in tracks:
        sigma_pos = float(np.hypot(SYS_ALIGN_PX, PSF_SIGMA_PX / max(tr["snr"], 1.0)))
        tr["sigma_shift_px"] = float(np.sqrt(2.0) * sigma_pos)
        tr["significance"] = float(tr["shift_px"] / tr["sigma_shift_px"])
        tr["rate_arcsec_yr"] = float(np.hypot(tr["vx_px_yr"], tr["vy_px_yr"]) * PIXEL_ARCSEC)
        # position angle east of north; x grows to the west on the sky grid (RA decreases)
        tr["pa_deg"] = float(np.degrees(np.arctan2(-tr["vx_px_yr"], tr["vy_px_yr"])) % 360)
        pts = np.array(tr["points"])
        if len(pts) >= 3:
            fx = np.polyval(np.polyfit(pts[:, 0], pts[:, 1], 1), pts[:, 0])
            fy = np.polyval(np.polyfit(pts[:, 0], pts[:, 2], 1), pts[:, 0])
            tr["fit_rms_px"] = float(np.sqrt(np.mean((pts[:, 1] - fx) ** 2 + (pts[:, 2] - fy) ** 2)))
        else:
            tr["fit_rms_px"] = 0.0

    # Field quality: most sources do not move measurably, so their typical apparent shift
    # tells how well the visits line up. Saturated halos and moving ghosts spoil it.
    shifts = np.sort(np.array([tr["shift_px"] for tr in tracks]))
    # The fastest source is left out (it may be the very mover we look for).
    floor = float(np.median(shifts[:-1])) if shifts.size >= 2 else float("nan")
    reliable = bool(shifts.size >= 2 and floor <= MAX_FIELD_MEDIAN_SHIFT_PX)
    need = min(3, len(usable))
    for tr in tracks:
        tr["mover"] = bool(reliable and tr["significance"] >= MIN_SIGNIFICANCE and tr["shift_px"] >= MIN_SHIFT_PX
                           and tr["n_visits"] >= need and tr["fit_rms_px"] <= MAX_FIT_RMS_PX)
    tracks.sort(key=lambda tr: -tr["significance"])
    return {"sources": tracks, "floor_px": floor, "reliable": reliable, "n_visits": len(usable),
            "span_years": float(span), "detector": det}


def search_all(epochs, stacks) -> dict:
    """Search every detector and keep only motion confirmed by two or more of them.

    SPHEREx images all six detectors at the same moments, so a real mover shows the same
    position and velocity in each detector where it is visible; detector artifacts and
    saturated halos do not. A detection counts if its field is reliable and its motion is
    at least 3 sigma; detections within 1.5 px (first visit) with velocities agreeing within
    1 px/yr are grouped. Combined significance = sqrt(sum of squares).
    """
    per_det = {}
    dets = []
    for det in (1, 2, 3, 4, 5, 6):
        r = search(epochs, stacks, det)
        per_det[det] = {"reliable": r["reliable"], "floor_px": r["floor_px"], "n_sources": len(r["sources"]),
                        "n_visits": r["n_visits"]}
        if not r["reliable"]:
            continue
        for tr in r["sources"]:
            if tr["significance"] >= CANDIDATE_SIGNIFICANCE and tr["shift_px"] >= MIN_SHIFT_PX \
                    and tr["fit_rms_px"] <= MAX_FIT_RMS_PX and tr["n_visits"] >= min(3, r["n_visits"]):
                dets.append(dict(tr, detector=det, span_years=r["span_years"]))
    groups = []
    for d in sorted(dets, key=lambda d: -d["significance"]):
        for g in groups:
            ref = g[0]
            if (np.hypot(d["x"] - ref["x"], d["y"] - ref["y"]) <= 1.5
                    and np.hypot(d["vx_px_yr"] - ref["vx_px_yr"], d["vy_px_yr"] - ref["vy_px_yr"]) <= 1.0
                    and all(m["detector"] != d["detector"] for m in g)):
                g.append(d)
                break
        else:
            groups.append([d])
    candidates = []
    for g in groups:
        w = np.array([m["significance"] ** 2 for m in g])
        vx = float(np.average([m["vx_px_yr"] for m in g], weights=w))
        vy = float(np.average([m["vy_px_yr"] for m in g], weights=w))
        sig = float(np.sqrt(w.sum()))
        members = sorted(({"detector": m["detector"], "rate_arcsec_yr": m["rate_arcsec_yr"], "pa_deg": m["pa_deg"],
                           "significance": m["significance"], "n_visits": m["n_visits"]} for m in g),
                         key=lambda m: m["detector"])
        rates = np.array([m["rate_arcsec_yr"] for m in members])
        candidates.append({
            "x": g[0]["x"], "y": g[0]["y"], "t0_mjd": g[0]["t0_mjd"], "detectors": sorted(m["detector"] for m in g),
            "members": members,
            # how well the detectors agree with each other (0 when only one detector sees it)
            "rate_spread_arcsec_yr": float(rates.max() - rates.min()) if rates.size > 1 else 0.0,
            "significance": sig, "vx_px_yr": vx, "vy_px_yr": vy,
            "rate_arcsec_yr": float(np.hypot(vx, vy) * PIXEL_ARCSEC),
            "pa_deg": float(np.degrees(np.arctan2(-vx, vy)) % 360),
            "shift_px": float(np.hypot(vx, vy) * g[0]["span_years"]),
            "min_neighbour_px": float(min(m.get("min_neighbour_px", float("inf")) for m in g)),
            "pulled_by_neighbour": False,
            "confirmed": len(g) >= 2 and sig >= MIN_SIGNIFICANCE,
            "points": g[0]["points"],
        })
    # Neighbour pull: compare every pair of movers at the visit times.
    times = sorted(ep["mjd_mid"] for ep in epochs)
    for a in candidates:
        for b in candidates:
            if a is b or b["significance"] <= a["significance"]:
                continue
            dmin = min(np.hypot((a["x"] + a["vx_px_yr"] * (t - a["t0_mjd"]) / 365.25)
                                - (b["x"] + b["vx_px_yr"] * (t - b["t0_mjd"]) / 365.25),
                                (a["y"] + a["vy_px_yr"] * (t - a["t0_mjd"]) / 365.25)
                                - (b["y"] + b["vy_px_yr"] * (t - b["t0_mjd"]) / 365.25)) for t in times)
            if dmin < BLEND_PX:
                a["pulled_by_neighbour"] = True
                a["confirmed"] = False
    candidates.sort(key=lambda c: (not c["confirmed"], -c["significance"]))
    usable = [ep for ep in epochs if any(ep["index"] in stacks for _ in [0])]
    return {"candidates": candidates, "per_detector": per_det, "n_visits": len(usable)}
