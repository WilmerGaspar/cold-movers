"""'Is it real?' checks: can the universe be fooling us?

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.

Three independent checks, each reported as pass / warn / fail with the evidence:
  1. Seen again: the source is detected in more than one visit.
  2. Clean pixels: few measurements carry SPHEREx contamination flags
     (ghosts, crosstalk, persistence, ...).
  3. Moves as predicted: the measured position in every visit follows the
     catalogue proper motion (positions measured by centroiding the epoch stacks).
These are signals, not proof.
"""

from __future__ import annotations

import numpy as np

PIXEL_ARCSEC = 6.15


def centroid(image: np.ndarray, x0: float, y0: float, half: int = 3, iterations: int = 3):
    """Flux-weighted centroid near (x0, y0). Returns (x, y, peak_snr) or NaNs."""
    if image is None:
        return np.nan, np.nan, np.nan
    ny, nx = image.shape
    x, y = float(x0), float(y0)
    finite = image[np.isfinite(image)]
    if finite.size < 20:
        return np.nan, np.nan, np.nan
    med = np.median(finite)
    noise = 1.4826 * np.median(np.abs(finite - med)) or np.nan
    for _ in range(iterations):
        xi, yi = int(round(x)), int(round(y))
        x1, x2 = max(xi - half, 0), min(xi + half + 1, nx)
        y1, y2 = max(yi - half, 0), min(yi + half + 1, ny)
        if x2 - x1 < 3 or y2 - y1 < 3:
            return np.nan, np.nan, np.nan
        box = image[y1:y2, x1:x2] - med
        box = np.where(np.isfinite(box) & (box > 0), box, 0.0)
        total = box.sum()
        if total <= 0:
            return np.nan, np.nan, np.nan
        yy, xx = np.mgrid[y1:y2, x1:x2]
        x, y = float((box * xx).sum() / total), float((box * yy).sum() / total)
    xi, yi = int(round(x)), int(round(y))
    peak = image[min(max(yi, 0), ny - 1), min(max(xi, 0), nx - 1)] - med
    return x, y, float(peak / noise) if np.isfinite(noise) and noise > 0 else np.nan


def best_detector(rows) -> int:
    """Detector where the target has the highest median S/N."""
    best, best_snr = 0, -np.inf
    for d in range(1, 7):
        snr = [r["snr"] for r in rows if r["detector"] == d and r["inside"] and not r["hard_flag"]
               and np.isfinite(r.get("snr", np.nan))]
        if snr and np.median(snr) > best_snr:
            best, best_snr = d, float(np.median(snr))
    return best


def run_checks(rows, epochs, stacks, marker) -> dict:
    """rows: photometry dicts; epochs: list of epoch dicts; stacks: {epoch_index: {det: image}};
    marker(mjd) -> predicted (x, y) on the stack grid."""
    out = {"checks": []}
    det = best_detector(rows)
    out["detector"] = det

    # 1. Seen again --------------------------------------------------------
    seen, positions = 0, []
    for ep in epochs:
        img = stacks.get(ep["index"], {}).get(det)
        px, py = marker(ep["mjd_mid"])
        x, y, snr = centroid(img, px, py)
        detected = np.isfinite(snr) and snr >= 5 and np.isfinite(x) and np.hypot(x - px, y - py) < 2.5
        seen += int(detected)
        positions.append({"mjd": ep["mjd_mid"], "pred_x": px, "pred_y": py, "x": x, "y": y, "snr": snr,
                          "detected": bool(detected)})
    n_ep = len(epochs)
    if n_ep >= 2 and seen >= 2:
        status, msg = "pass", f"Detected in {seen} of {n_ep} visits (detector {det})."
    elif seen == 1:
        status, msg = "warn", (f"Detected in only 1 of {n_ep} visits. A one-time detection can be a cosmic ray, "
                               "an asteroid passing by, or a real flare.")
    else:
        status, msg = "fail", "Not clearly detected at the expected position in any visit."
    out["checks"].append({"name": "Seen again", "status": status, "text": msg})
    out["positions"] = positions

    # 2. Clean pixels --------------------------------------------------------
    inside = [r for r in rows if r["inside"]]
    if inside:
        hard = sum(r["hard_flag"] for r in inside)
        soft = sum(bool(r["soft_flag"]) and not r["hard_flag"] for r in inside)
        frac = (hard + soft) / len(inside)
        if frac < 0.2:
            status = "pass"
        elif frac < 0.5:
            status = "warn"
        else:
            status = "fail"
        msg = (f"{len(inside) - hard - soft} of {len(inside)} measurements are free of SPHEREx quality flags; "
               f"{hard} were excluded (saturation, hot pixels, artifacts) and {soft} carry possible "
               "contamination (ghosts, crosstalk).")
    else:
        status, msg = "fail", "The target never fell inside a usable image."
    out["checks"].append({"name": "Clean pixels", "status": status, "text": msg})

    # 3. Moves as predicted ---------------------------------------------------
    det_pos = [p for p in positions if p["detected"]]
    if len(det_pos) >= 2:
        resid = np.array([np.hypot(p["x"] - p["pred_x"], p["y"] - p["pred_y"]) for p in det_pos])
        first, last = det_pos[0], det_pos[-1]
        pred_shift = np.hypot(last["pred_x"] - first["pred_x"], last["pred_y"] - first["pred_y"])
        meas_shift = np.hypot(last["x"] - first["x"], last["y"] - first["y"])
        rms = float(np.sqrt(np.mean(resid**2)))
        out["motion"] = {"predicted_px": float(pred_shift), "measured_px": float(meas_shift), "rms_px": rms}
        if rms < 1.0:
            status = "pass"
            msg = (f"Measured positions follow the catalogue motion within {rms * PIXEL_ARCSEC:.1f} arcsec. "
                   f"Between the first and last visit it moved {meas_shift * PIXEL_ARCSEC:.1f} arcsec "
                   f"(predicted {pred_shift * PIXEL_ARCSEC:.1f}).")
        else:
            status = "warn"
            msg = (f"Positions differ from the prediction by {rms * PIXEL_ARCSEC:.1f} arcsec on average: "
                   "check for a neighbour, a wrong catalogue motion, or a different object.")
    else:
        status, msg = "warn", "Not enough detections to test the motion."
    out["checks"].append({"name": "Moves as predicted", "status": status, "text": msg})
    return out
