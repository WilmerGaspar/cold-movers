"""Cold Movers web app.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.
Run: streamlit run app.py
"""

from __future__ import annotations

import io
import json
import os

import numpy as np
import streamlit as st

from coldmovers import checks, madhava, movie, pipeline, variability
from coldmovers.references import PUBLISHED
from coldmovers.targets import SHOWCASE, ServiceDown, Target, parse_coordinates, resolve_simbad

st.set_page_config(page_title="Cold Movers", page_icon="🛰️", layout="wide")

HERE = os.path.dirname(os.path.abspath(__file__))
PRECOMPUTED = os.path.join(HERE, "data", "precomputed")
LIGHT_COLORS = {"green": "#2fbf71", "yellow": "#f2c94c", "red": "#eb5757"}
LIGHT_WORDS = {"green": "Trust it", "yellow": "Read with care", "red": "No reliable temperature"}
DET_COLORS = {1: "#5b8def", 2: "#41b6c4", 3: "#7fcd8b", 4: "#f2c94c", 5: "#f2994a", 6: "#eb5757"}
LIGHT_YEARS_PER_PC = 3.26156
MOON_DIAMETER_ARCSEC = 1865.0
LIVE_TIME_BUDGET_S = 240  # a live search keeps what arrived after 4 minutes
# What each challenge object demonstrates (short label, longer explanation).
DEMO = {
    "barnard": ("fast motion",
                "the fastest-moving star in the sky crossing SPHEREx's field over a year. It is too bright for "
                "SPHEREx's detectors, so it shows motion, not a reliable temperature."),
    "epsindib": ("motion + temperature",
                 "a pair of nearby brown dwarfs: motion and a full temperature fit, flagged yellow because "
                 "methane and water bands make it unlike a single blackbody."),
    "wise0855": ("faint cold mover",
                 "the coldest known brown dwarf, visible only beyond 3.8 µm, passing a background star that the "
                 "checks detect and remove."),
    "rwaur": ("young star, disk",
              "a young star with a dusty disk; it saturates SPHEREx beyond 1.1 µm, so it tests the brightness "
              "check between visits (measured from the star's wings) and the limits of the temperature fit."),
    "rdra": ("pulsating giant",
             "a pulsating red giant (Mira variable); it saturates SPHEREx, so it tests the brightness check "
             "between visits from the star's wings."),
}

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; max-width: 1200px;}
    .cm-card {background:#151b2b; border-radius:14px; padding:16px 18px; border:1px solid #232b40;}
    .cm-big {font-size:2.2rem; font-weight:700; line-height:1.1;}
    .cm-light {display:inline-block; width:14px; height:14px; border-radius:50%; margin-right:8px; vertical-align:middle;}
    .cm-muted {color:#9aa4b8; font-size:0.92rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ inputs


def read_query_params():
    qp = st.query_params
    if "object" in qp and qp["object"] in SHOWCASE:
        return {"mode": "object", "key": qp["object"]}
    if "ra" in qp and "dec" in qp:
        try:
            return {
                "mode": "coords", "ra": float(qp["ra"]), "dec": float(qp["dec"]),
                "pmra": float(qp.get("pmra", 0)), "pmdec": float(qp.get("pmdec", 0)),
                "epoch": float(qp.get("epoch", 2000.0)), "size": float(qp.get("size", 3.0)),
            }
        except ValueError:
            pass
    return {"mode": "object", "key": "barnard"}


initial = read_query_params()

# Automatic browser translation rewrites the page under Streamlit and breaks it (removeChild errors).
# Mark the page "do not translate"; the text is in English as Space Apps requires.
import streamlit.components.v1 as _components  # noqa: E402

_components.html(
    """<script>
    try {
      const d = window.parent.document;
      d.documentElement.setAttribute('translate', 'no');
      d.documentElement.classList.add('notranslate');
      if (!d.querySelector('meta[name="google"]')) {
        const m = d.createElement('meta'); m.name = 'google'; m.content = 'notranslate'; d.head.appendChild(m);
      }
    } catch (e) {}
    </script>""",
    height=0,
)
st.title("Cold Movers")
st.markdown(
    "**Cold Movers lets anyone explore SPHEREx observations, follow changes between visits, and see explicitly "
    "when the data do not support a reliable conclusion.** Pick an object or type sky coordinates: we fetch every "
    "SPHEREx image of that spot from NASA's archive, play the visits as a movie so anything that moves stands out, "
    "and fit its infrared light to estimate how cold it is."
)
st.caption("Team Cold Movers (Honduras) · NASA Space Apps 2026 · built with AI-assisted code (Claude, Anthropic); "
           "see the AI note at the bottom. Not an official NASA product.")


@st.cache_data(show_spinner=False)
def validation_table():
    from coldmovers import validation

    return validation.validate(PRECOMPUTED)


def validation_summary(vt) -> str:
    """One sentence computed from the validation table (never typed by hand)."""
    movers = [v for v in vt if v["pm_arcsec_yr"] >= 0.5]
    good = [v for v in movers if v["moved_measured"] is not None
            and abs(v["moved_measured"] - v["moved_predicted"]) < 2.0]
    worst = max((abs(v["moved_measured"] - v["moved_predicted"]) for v in good), default=0.0)
    temp_ok = [v for v in vt if v["light"] in ("green", "yellow")]
    bright = [v for v in vt if "too_bright" in v["reasons"]]
    images = sum(v["images"] for v in vt)
    return (f"<b>{images:,} SPHEREx images, {len(vt)} objects.</b> Motion recovered for <b>{len(good)} of "
            f"{len(movers)}</b> fast-moving objects, within {worst:.1f}″ of the catalogue prediction. "
            f"A temperature could be measured for <b>{len(temp_ok)} of {len(vt)}</b>; <b>{len(bright)}</b> are too "
            "bright for SPHEREx, and the app says so instead of inventing a number.")


g1, g2 = st.columns([1, 1])
with g1:
    st.markdown(
        "<div class='cm-card'><b>How to read this page in 60 seconds</b><ol style='margin:6px 0 0 0'>"
        "<li>Pick an object below; each one demonstrates something different.</li>"
        "<li><a href='#at-a-glance'>At a glance</a>: does it move, how cold is it, is it real; each answer can be "
        "audited in one click.</li>"
        "<li><a href='#the-sky'>The movie</a>: the circle and arrow show where it should be on each date; watch "
        "whether a dot follows them while the background stays still.</li>"
        "<li><a href='#is-it-real'>Is it real?</a> and the traffic light: where the data cannot support a "
        "conclusion, the app says why.</li></ol></div>",
        unsafe_allow_html=True,
    )
with g2:
    try:
        vt_top = validation_table()
    except Exception:
        vt_top = []
    if vt_top:
        st.markdown(f"<div class='cm-card'><b>Tested on the five challenge objects</b>"
                    f"<div style='margin-top:6px'>{validation_summary(vt_top)}</div></div>",
                    unsafe_allow_html=True)
    st.markdown(
        "<div class='cm-card' style='margin-top:10px'><b>Intended use</b> <span class='cm-muted'>(not yet tested "
        "with users)</span><div style='margin-top:4px'>Citizen scientists checking whether a SPHEREx source moves; "
        "teachers showing motion, light and uncertainty with real NASA data; astronomers taking a quick, traceable "
        "first look at any position.</div></div>",
        unsafe_allow_html=True,
    )
st.write("")

tab_obj, tab_coords, tab_name = st.tabs(["Challenge objects", "Coordinates", "Name"])
request = None

with tab_obj:
    keys = list(SHOWCASE)
    # The choice lives in session state with a fixed key: if its default followed the URL, Streamlit would
    # treat the selector as a new widget after every change and drop every other click.
    if "object_choice" not in st.session_state:
        st.session_state["object_choice"] = initial["key"] if initial["mode"] == "object" else keys[0]
    choice = st.radio(
        "Object", keys, key="object_choice", horizontal=True,
        format_func=lambda k: f"{SHOWCASE[k].name} · {DEMO[k][0]}", label_visibility="collapsed",
    )
    st.caption(f"{SHOWCASE[choice].note} **What it demonstrates:** {DEMO[choice][1]}")
    prev = st.session_state.get("request")
    if (
        st.button("Show", key="show_obj", type="primary")
        or (initial["mode"] == "object" and prev is None)
        or (prev is not None and prev["mode"] == "object" and prev["key"] != choice)
    ):
        request = {"mode": "object", "key": choice}

with tab_coords:
    c1, c2 = st.columns(2)
    # Defaults from the shared link are set once; fixed keys keep the widgets stable afterwards.
    if "ra_txt" not in st.session_state:
        coords_link = initial["mode"] == "coords"
        st.session_state.update({
            "ra_txt": f"{initial['ra']:.6f}" if coords_link else "",
            "dec_txt": f"{initial['dec']:.6f}" if coords_link else "",
            "pmra_in": float(initial.get("pmra", 0.0)),
            "pmdec_in": float(initial.get("pmdec", 0.0)),
            "epoch_in": float(initial.get("epoch", 2000.0)),
            "size_in": float(np.clip(initial.get("size", 3.0), 2.0, 8.0)),
        })
    ra_txt = c1.text_input("RA (degrees or 08h55m10.8s)", key="ra_txt", placeholder="133.79513")
    dec_txt = c2.text_input("Dec (degrees or -07d14m42.5s)", key="dec_txt", placeholder="-7.24515")
    with st.expander("Motion and field of view"):
        d1, d2, d3, d4 = st.columns(4)
        pmra = d1.number_input("pmRA* (mas/yr)", key="pmra_in")
        pmdec = d2.number_input("pmDec (mas/yr)", key="pmdec_in")
        epoch = d3.number_input("Epoch of RA/Dec (year)", key="epoch_in")
        size_arcmin = d4.slider("Field of view (arcmin)", 2.0, 8.0, step=0.5, key="size_in")
        max_frames = st.slider("Maximum images to download", 40, 400, 150, 10,
                               help="More images give a better spectrum but take longer.")
    if st.button("Search SPHEREx", key="go_coords", type="primary") or (
        initial["mode"] == "coords" and "request" not in st.session_state
    ):
        try:
            ra, dec = parse_coordinates(f"{ra_txt} {dec_txt}")
            request = {"mode": "coords", "ra": ra, "dec": dec, "pmra": pmra, "pmdec": pmdec,
                       "epoch": epoch, "size": size_arcmin, "max_frames": max_frames}
        except Exception as exc:
            st.error(f"Could not read those coordinates: {exc}")

with tab_name:
    name = st.text_input("Any object name known to SIMBAD", placeholder="e.g. Luhman 16, GJ 1001, TRAPPIST-1")
    st.caption("Position, proper motion and parallax come from SIMBAD (CDS, Strasbourg).")
    if st.button("Search SPHEREx", key="go_name", type="primary") and name.strip():
        request = {"mode": "name", "name": name.strip(), "size": 3.0, "max_frames": 150}

if request is not None:
    st.session_state["request"] = request
request = st.session_state.get("request")


# ------------------------------------------------------------------ data loading


@st.cache_data(show_spinner=False)
def load_precomputed(key: str):
    data = pipeline.load(os.path.join(PRECOMPUTED, key))
    if data is None:
        return None
    npz_path = os.path.join(PRECOMPUTED, key, "stacks.npz")
    stacks = {}
    if os.path.exists(npz_path):
        with np.load(npz_path) as npz:
            for name in npz.files:
                e, d = name[1:].split("_d")
                stacks.setdefault(int(e), {})[int(d)] = npz[name]
    data["stacks"] = stacks
    return data


def live_run(target_json: str, size_deg: float, max_frames: int):
    """Run the pipeline once per session and parameter set (results kept in the session)."""
    cache = st.session_state.setdefault("live_cache", {})
    key = json.dumps([target_json, round(size_deg, 4), int(max_frames)])
    if key in cache:
        return cache[key]
    target = Target.from_dict(json.loads(target_json))
    bar = st.progress(0.0, text="Starting")

    def progress(stage, frac):
        bar.progress(min(max(frac, 0.0), 1.0), text=stage)

    result = pipeline.run(target, size_deg=size_deg, max_frames=max_frames, workers=8, progress=progress,
                          time_budget_s=LIVE_TIME_BUDGET_S)
    bar.empty()
    if len(cache) > 4:
        cache.pop(next(iter(cache)))
    cache[key] = result
    return result


def view_from_result(result: pipeline.RunResult) -> dict:
    stacks = {ep["index"]: ep["stacks"] for ep in result.epochs}
    return {
        "target": result.target.to_dict(), "rows": result.rows, "n_found": result.n_found,
        "n_used": result.n_used, "epochs": [{k: v for k, v in ep.items() if k != "stacks"} for ep in result.epochs],
        "stacks": stacks, "versions": result.versions, "timings": result.timings, "size_deg": result.size_deg,
        "ref": {"crval": list(result.ref_wcs.wcs.crval), "crpix": list(result.ref_wcs.wcs.crpix),
                "cdelt": list(result.ref_wcs.wcs.cdelt), "shape": list(result.shape)},
        "gifs": {}, "dir": None, "live": True,
    }


def make_target(req) -> Target:
    if req["mode"] == "name":
        return resolve_simbad(req["name"])
    return Target(key="custom", name=f"RA {req['ra']:.5f}, Dec {req['dec']:+.5f}", ra_deg=req["ra"],
                  dec_deg=req["dec"], pmra_masyr=req["pmra"], pmdec_masyr=req["pmdec"],
                  ref_epoch=req["epoch"], source="user input")


if request is None:
    st.stop()

view = None
if request["mode"] == "object":
    view = load_precomputed(request["key"])
    if view is None:
        st.info("Results for this object are still being computed on our server. Showing a live search instead.")
        tgt = SHOWCASE[request["key"]]
        with st.status(f"Searching SPHEREx for {tgt.name}", expanded=True):
            view = view_from_result(live_run(json.dumps(tgt.to_dict()), pipeline.DEFAULT_SIZE_DEG, 150))
    st.query_params.clear()
    st.query_params["object"] = request["key"]
else:
    try:
        tgt = make_target(request)
    except Exception as exc:
        if isinstance(exc, ServiceDown):
            st.error("The star-name service (SIMBAD, CDS Strasbourg) is not answering right now. "
                     "Please use the Coordinates tab, or pick one of the challenge objects.")
        elif isinstance(exc, LookupError):
            st.error(f"SIMBAD does not know the name '{request.get('name', '')}'. Check the spelling or use "
                     "the Coordinates tab.")
        else:
            st.error("The name lookup failed. Please use the Coordinates tab.")
        st.stop()
    st.query_params.clear()
    st.query_params.update({"ra": f"{tgt.ra_deg:.6f}", "dec": f"{tgt.dec_deg:.6f}", "size": str(request["size"]),
                            "pmra": f"{tgt.pmra_masyr:.2f}", "pmdec": f"{tgt.pmdec_masyr:.2f}",
                            "epoch": f"{tgt.ref_epoch:.2f}"})
    try:
        view = view_from_result(live_run(json.dumps(tgt.to_dict()), request["size"] / 60.0, request["max_frames"]))
    except Exception as exc:
        st.error(f"The SPHEREx search failed: {exc}. IRSA may be busy; please try again in a minute.")
        st.stop()

target = Target.from_dict(view["target"])
rows = view["rows"]
epochs = view["epochs"]


def ref_wcs_from(ref):
    from astropy.wcs import WCS

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval, w.wcs.crpix, w.wcs.cdelt = ref["crval"], ref["crpix"], ref["cdelt"]
    return w


ref_wcs = ref_wcs_from(view["ref_wcs"] if "ref_wcs" in view else view["ref"])


def marker(mjd):
    ra, dec = target.position_at(mjd)
    x, y = ref_wcs.wcs_world2pix(ra, dec, 0)
    return float(x), float(y)


# ------------------------------------------------------------------ header metrics

st.subheader(target.name)
if view.get("stacks"):
    checks.mark_blends(rows, epochs, view["stacks"], marker)
clean = pipeline.clean_rows(rows)
mjds = [r["mjd"] for r in rows]
m1, m2, m3, m4 = st.columns(4)
m1.metric("SPHEREx images found", view["n_found"])
m2.metric("Images used", view["n_used"], help="Spread evenly in time when there are more than the limit.")
m3.metric("Epochs (visits)", len(epochs))
if mjds:
    from astropy.time import Time

    months = (max(mjds) - min(mjds)) / 30.44
    m4.metric("Time span", f"{months:.0f} months",
              help=f"From {Time(min(mjds), format='mjd').iso[:10]} to {Time(max(mjds), format='mjd').iso[:10]}")
st.caption(
    f"Position from {target.source}. Proper motion {target.pmra_masyr:.0f}, {target.pmdec_masyr:.0f} mas/yr "
    f"({target.total_pm_arcsec_per_year:.2f} arcsec/yr). Data: SPHEREx DR1 + QR3 via NASA/IPAC IRSA"
    + (f", pipeline version {', '.join(view['versions'])}" if view.get("versions") else "") + "."
)

# ------------------------------------------------------------------ verdict at a glance

st.markdown("<div id='at-a-glance'></div>", unsafe_allow_html=True)

fit = pipeline.fit_rows(rows)
real = checks.run_checks(rows, epochs, view["stacks"], marker) if view.get("stacks") else None
lc = variability.light_curve(rows, epochs)
STATUS_ICON = {"pass": "🟢", "warn": "🟡", "fail": "🔴"}


def summary_card(title, big, small, color="#232b40"):
    return (f"<div class='cm-card' style='border-left:5px solid {color}; min-height:128px'>"
            f"<div class='cm-muted'>{title}</div><div class='cm-big' style='font-size:1.7rem'>{big}</div>"
            f"<div class='cm-muted' style='margin-top:4px'>{small}</div></div>")


s1, s2, s3 = st.columns(3)
motion = real.get("motion") if real else None
if motion and target.total_pm_arcsec_per_year >= 0.5:
    s1.markdown(summary_card(
        "Does it move?", f"Yes · {motion['measured_px'] * checks.PIXEL_ARCSEC:.1f}″",
        f"measured between the first and last SPHEREx visit; the catalogue predicts "
        f"{motion['predicted_px'] * checks.PIXEL_ARCSEC:.1f}″", "#2fbf71"), unsafe_allow_html=True)
elif target.total_pm_arcsec_per_year < 0.5:
    s1.markdown(summary_card(
        "Does it move?", "Too slowly to see",
        f"{target.total_pm_arcsec_per_year * 1000:.0f} milliarcsec per year: far below one SPHEREx pixel "
        "over these visits"), unsafe_allow_html=True)
else:
    s1.markdown(summary_card("Does it move?", "Not measured", "not enough clear detections to follow it"),
                unsafe_allow_html=True)

if np.isfinite(fit.temperature) and fit.light != "red":
    big_t, small_t = f"{fit.temperature:,.0f} K", madhava.REASON_TEXT.get(fit.reasons[0], "") if fit.reasons else ""
else:
    big_t = "Too bright to measure" if "too_bright" in fit.reasons else "Not reliable"
    small_t = madhava.REASON_TEXT.get(fit.reasons[0], "") if fit.reasons else ""
s2.markdown(summary_card(f"How cold? · {LIGHT_WORDS[fit.light]}", big_t, small_t.split(". ")[0].rstrip(".") + ".",
                         LIGHT_COLORS[fit.light]), unsafe_allow_html=True)

if real:
    n_pass = sum(c["status"] == "pass" for c in real["checks"])
    icons = " ".join(f"{STATUS_ICON[c['status']]} {c['name']}" for c in real["checks"])
    color = "#2fbf71" if n_pass == len(real["checks"]) else ("#f2c94c" if n_pass >= 2 else "#eb5757")
    s3.markdown(summary_card("Is it real?", f"{n_pass} of {len(real['checks'])} checks pass", icons, color),
                unsafe_allow_html=True)

with st.expander("How were these three answers calculated? (audit trail)"):
    from astropy.time import Time

    a_mot, a_temp, a_real = st.tabs(["Motion", "Temperature", "Is it real?"])
    with a_mot:
        if real and real.get("positions"):
            import pandas as pd

            st.dataframe(pd.DataFrame([{
                "Visit (date)": Time(p["mjd"], format="mjd").iso[:10],
                "Predicted x, y (px)": f"{p['pred_x']:.2f}, {p['pred_y']:.2f}",
                "Measured x, y (px)": (f"{p['x']:.2f}, {p['y']:.2f}" if np.isfinite(p["x"]) else "—"),
                "Offset (arcsec)": (round(float(np.hypot(p["x"] - p["pred_x"], p["y"] - p["pred_y"]))
                                    * checks.PIXEL_ARCSEC, 1) if np.isfinite(p["x"]) else None),
                "Peak S/N": round(float(p["snr"]), 1) if np.isfinite(p["snr"]) else None,
                "Used": "yes" if p["detected"] else "no (S/N < 5 or too far)",
            } for p in real["positions"]]), use_container_width=True, hide_index=True)
            st.caption(f"Positions are flux-weighted centroids in the visit stacks of detector {real['detector']} "
                       "(the one where the target is brightest and not blended). Predicted positions come from "
                       f"{target.source}, propagated with the proper motion to each visit. 1 px = 6.15 arcsec.")
        else:
            st.caption("No aligned images, so positions could not be measured.")
    with a_temp:
        inside = [r for r in rows if r["inside"]]
        n_sat = sum(bool(r.get("saturated")) for r in inside)
        n_flag = sum(r["hard_flag"] and not r.get("saturated") for r in inside)
        n_blend = sum(bool(r.get("blend")) and not r["hard_flag"] for r in inside)
        n_out = len(rows) - len(inside)
        lam_used = [r["wavelength_um"] for r in clean]
        st.markdown(
            f"- **Used in the fit:** {fit.n_points} measurements"
            + (f", from {min(lam_used):.2f} to {max(lam_used):.2f} µm" if lam_used else "") + "\n"
            f"- **Left out:** {n_sat} saturated, {n_flag} with other SPHEREx quality flags, {n_blend} blended with a "
            f"neighbour, {n_out} with the target outside the cutout\n"
            f"- **Model:** one blackbody integrated exactly over each band; free temperature and scale; errors = "
            f"measurement error plus an 8 % systematic floor\n"
            + (f"- **Result:** {fit.temperature:,.0f} K, interval {fit.t_low:,.0f}–{fit.t_high:,.0f} K "
               f"(where χ² rises by max(1, χ²/dof) = {max(1.0, fit.chi2_red):.1f}); reduced χ² {fit.chi2_red:.2f}\n"
               if np.isfinite(fit.temperature) else "- **Result:** no temperature\n")
            + f"- **Traffic light:** {LIGHT_WORDS[fit.light]}: "
            + "; ".join(madhava.REASON_TEXT.get(r, r) for r in fit.reasons)
        )
        pub = PUBLISHED.get(target.key)
        if pub:
            st.caption(f"Published value for comparison: {pub['text']} ({pub['ref']}).")
    with a_real:
        if real:
            for c in real["checks"]:
                st.markdown(f"{STATUS_ICON[c['status']]} **{c['name']}**: {c['text']}")
        else:
            st.caption("No aligned images, so the checks cannot run.")

# ------------------------------------------------------------------ sky movie

st.markdown("<div id='the-sky'></div>", unsafe_allow_html=True)
st.markdown("### 1 · The sky, visit by visit")
left, right = st.columns([3, 2])
with right:
    st.markdown(
        "Each frame stacks every SPHEREx image of one detector taken during one visit, all aligned on the "
        "same patch of sky. The orange circle is where the object should be on that date and the dashed arrow "
        "is its predicted path, from 2.5 years before the first visit to 2.5 years after the last. **If a dot follows the circle while the background stays still, you are "
        "watching real motion across the sky.**"
    )
    st.markdown(
        "<span class='cm-muted'>In 1930 Clyde Tombaugh found Pluto at Lowell Observatory, during the search "
        "for \"Planet X\", by blinking two photographs of the same sky taken days apart. Cold Movers is a "
        "digital blink comparator for SPHEREx. Cold brown dwarfs like WISE 0855 are invisible to the eye: only "
        "infrared light and their motion give them away.</span>",
        unsafe_allow_html=True,
    )
    available = sorted({d for ep in view["stacks"].values() for d in ep}) if view.get("stacks") else []
    # Start on the detector where the target is brightest and not blended (WISE 0855: the
    # long-wavelength one); "All detectors" for saturated stars.
    best = checks.best_detector(rows)
    options = available or [0]
    det = st.radio("Detector", options, index=options.index(best) if best in options else 0,
                   format_func=movie.detector_label)
    show_diff = st.toggle("Show difference (last visit minus first)", value=False,
                          help="Things that did not change cancel out; moving or varying things remain.")
    st.markdown(
        f"<span class='cm-muted'>Field of view {view['size_deg'] * 60:.1f} arcmin · SPHEREx pixels are 6.15 arcsec. "
        f"<a href='https://simbad.cds.unistra.fr/simbad/sim-coo?Coord={target.ra_deg}+{target.dec_deg}"
        f"&Radius=2&Radius.unit=arcmin' target='_blank'>SIMBAD</a> · "
        f"<a href='https://byw.tools/wiseview#ra={target.ra_deg}&dec={target.dec_deg}&size=176&band=3' "
        f"target='_blank'>Open in WiseView (WISE)</a></span>",
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False, max_entries=24)
def gif_for(cache_key: str, det: int, _epochs, _stacks):
    eps = [dict(ep, stacks=_stacks.get(ep["index"], {}),
                counts={int(k): v for k, v in ep["counts"].items()}) for ep in _epochs]
    pngs = movie.render_frames(eps, det, marker, pipeline.epoch_title, track=pipeline.track_points(marker, _epochs))
    return movie.frames_to_gif(pngs, 800)


with left:
    if not view.get("stacks"):
        st.warning("No images could be aligned for this position.")
    elif show_diff:
        usable = [ep for ep in epochs if det in view["stacks"].get(ep["index"], {})]
        if len(usable) < 2:
            st.info("Only one visit so far for this detector, so there is nothing to subtract yet.")
        else:
            import matplotlib.pyplot as plt

            diff = view["stacks"][usable[-1]["index"]][det] - view["stacks"][usable[0]["index"]][det]
            v = np.nanpercentile(np.abs(diff), 99) or 1.0  # relative to each visit's sky level
            fig, ax = plt.subplots(figsize=(4.2, 4.4), dpi=110)
            ax.imshow(np.nan_to_num(diff), origin="lower", cmap="RdBu_r", vmin=-v, vmax=v, interpolation="nearest")
            path = pipeline.track_points(marker, epochs)
            if path:
                ax.plot(*zip(*path), ls="--", color="#555555", lw=1.0)
            for ep, col in ((usable[0], "#5b8def"), (usable[-1], "#eb5757")):
                px, py = marker(ep["mjd_mid"])
                ax.add_patch(plt.Circle((px, py), 3.0, fill=False, color=col, lw=1.5))
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title("Last visit minus first: red = brighter now, blue = was there before", fontsize=8)
            fig.tight_layout()
            fig.text(0.99, 0.005, movie.WATERMARK, ha="right", va="bottom", fontsize=6, color="#8a93a6")
            st.pyplot(fig, use_container_width=True)
    else:
        key = f"{target.key}-{target.ra_deg:.5f}-{target.dec_deg:.5f}-{view.get('dir')}-{view['size_deg']}-{len(epochs)}"
        gif_file = view.get("gifs", {}).get(str(det)) if view.get("dir") else None
        if gif_file and os.path.exists(os.path.join(view["dir"], gif_file)):
            with open(os.path.join(view["dir"], gif_file), "rb") as fh:
                gif = fh.read()
        else:
            gif = gif_for(key, det, epochs, view["stacks"])
        st.image(gif, use_container_width=True)
        st.download_button("Download this movie (GIF)", gif, file_name=f"coldmovers_{target.key}_d{det}.gif",
                           mime="image/gif")

if mjds:
    ra_now, dec_now = target.position_at(float(np.median(mjds)))
else:
    ra_now, dec_now = target.ra_deg, target.dec_deg
ra_2010, dec_2010 = target.position_at(55400.0)  # WISE survey, mid-2010
atlas_fov = max(view["size_deg"] * 1.6, 0.06)
atlas_link = (f"https://aladin.cds.unistra.fr/AladinLite/?target={float(ra_now):.6f}%20{float(dec_now):+.6f}"
              f"&fov={atlas_fov:.3f}&survey=P%2FallWISE%2Fcolor")


@st.cache_data(show_spinner=False, max_entries=32)
def gaia_stars(ra, dec, radius):
    from coldmovers import atlas

    return atlas.gaia_field(ra, dec, radius)


if st.toggle("Overlay Gaia DR3 stars and their motion on the SPHEREx image", value=False) and view.get("stacks"):
    from astropy.time import Time

    from coldmovers import atlas

    # The visit with the most images gives the cleanest picture.
    best_ep = max(epochs, key=lambda ep: ep["n_frames"])
    stack = view["stacks"].get(best_ep["index"], {}).get(0)
    if stack is None:
        stack = next(iter(view["stacks"].get(best_ep["index"], {}).values()), None)
    year_ep = 2000.0 + (best_ep["mjd_mid"] - 51544.5) / 365.25
    ra_ep, dec_ep = target.position_at(best_ep["mjd_mid"])
    try:
        with st.spinner("Asking the ESA Gaia archive for the stars in this field"):
            stars = gaia_stars(round(float(ra_ep), 5), round(float(dec_ep), 5), round(view["size_deg"] * 0.75, 4))
            # Crowded Milky Way fields hold hundreds of faint Gaia stars that one SPHEREx visit cannot see;
            # keep the brighter ones (G <= 18) so the picture stays readable.
            stars = [s_ for s_ in stars if 0 < s_["g"] <= 18.0]
        png, n_shown = atlas.render_on_spherex(
            stack, lambda r, d: tuple(float(v) for v in ref_wcs.wcs_world2pix(r, d, 0)), stars, year_ep,
            marker(best_ep["mjd_mid"]),
            title=f"{target.name} · SPHEREx visit of {Time(best_ep['mjd_mid'], format='mjd').iso[:10]} + Gaia DR3",
        )
        a1, a2 = st.columns([3, 2])
        a1.image(png, use_container_width=True)
        a2.markdown(
            f"**What you see.** The SPHEREx image of one visit (all detectors). Blue squares are the {n_shown} "
            "Gaia DR3 stars brighter than G = 18 in this field, moved to the date of the visit with their own proper motion; arrows show "
            "where that motion takes them in 20 years. The orange circle is our object. A star whose square sits "
            "on a SPHEREx dot confirms the alignment; a dot with no Gaia square is either too red or too faint for "
            "Gaia (like a cold brown dwarf) or not a star."
        )
        a2.markdown(f"[Explore the wider sky in Aladin Lite (CDS)]({atlas_link})")
    except Exception as exc:
        st.info(f"The ESA Gaia archive did not answer ({type(exc).__name__}). Please try again in a minute.")

# ------------------------------------------------------------------ spectrum + Madhava

st.markdown("### 2 · Its light, and how cold it is")

c_plot, c_card = st.columns([3, 2])
with c_plot:
    import plotly.graph_objects as go

    figp = go.Figure()
    for d in range(1, 7):
        pts = [r for r in clean if r["detector"] == d]
        if not pts:
            continue
        figp.add_trace(go.Scatter(
            x=[r["wavelength_um"] for r in pts], y=[r["flux_ujy"] for r in pts], mode="markers",
            name=f"D{d}", marker=dict(size=6, color=DET_COLORS[d], opacity=0.85),
            error_y=dict(type="data", array=[r["err_ujy"] for r in pts], thickness=1, width=0, color=DET_COLORS[d]),
            hovertemplate="%{x:.3f} um<br>%{y:.1f} uJy<extra>D" + str(d) + "</extra>",
        ))
    flagged = [r for r in rows if r["inside"] and r["hard_flag"] and np.isfinite(r["wavelength_um"])
               and np.isfinite(r["flux_ujy"])]
    if flagged:
        figp.add_trace(go.Scatter(
            x=[r["wavelength_um"] for r in flagged], y=[r["flux_ujy"] for r in flagged], mode="markers",
            name="flagged (not used)", marker=dict(size=6, color="#6b7280", symbol="x"),
        ))
    blended = [r for r in rows if r["inside"] and not r["hard_flag"] and r.get("blend")
               and np.isfinite(r["wavelength_um"]) and np.isfinite(r["flux_ujy"])]
    if blended:
        figp.add_trace(go.Scatter(
            x=[r["wavelength_um"] for r in blended], y=[r["flux_ujy"] for r in blended], mode="markers",
            name="neighbour blended (not used)", marker=dict(size=6, color="#a78bfa", symbol="circle-open"),
        ))
    if np.isfinite(fit.temperature):
        grid = np.linspace(0.72, 5.05, 300)
        res_power = np.nanmedian([r["wavelength_um"] / r["bandwidth_um"] for r in clean]) if clean else 50
        model = fit.scale * madhava.band_model_fnu(grid, grid / res_power, fit.temperature)
        figp.add_trace(go.Scatter(x=grid, y=model, mode="lines", name=f"Madhava fit {fit.temperature:.0f} K",
                                  line=dict(color="#ffffff", width=2)))
    figp.update_layout(
        template="plotly_dark", height=420, margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="Wavelength (micrometres)", yaxis_title="Brightness (microjansky)",
        legend=dict(orientation="h", y=1.08), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(figp, use_container_width=True)
    if np.isfinite(fit.temperature) and clean:
        lam_c = np.array([r["wavelength_um"] for r in clean])
        f_c = np.array([r["flux_ujy"] for r in clean])
        e_c = np.array([r["err_ujy"] for r in clean])
        model_c = fit.scale * madhava.band_model_fnu(lam_c, [r["bandwidth_um"] for r in clean], fit.temperature)
        resid = (f_c - model_c) / np.sqrt(e_c**2 + (madhava.DEFAULT_ERROR_FLOOR * np.abs(f_c)) ** 2)
        figr = go.Figure()
        for d in range(1, 7):
            sel = np.array([r["detector"] == d for r in clean])
            if sel.any():
                figr.add_trace(go.Scatter(x=lam_c[sel], y=resid[sel], mode="markers", showlegend=False,
                                          marker=dict(size=5, color=DET_COLORS[d], opacity=0.85)))
        for yv, dash in ((0, "solid"), (3, "dot"), (-3, "dot")):
            figr.add_hline(y=yv, line=dict(color="#6b7280", width=1, dash=dash))
        figr.update_layout(
            template="plotly_dark", height=200, margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="Wavelength (micrometres)", yaxis_title="(data − fit) / error",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(figr, use_container_width=True)
        st.caption("Residuals: points beyond the dotted lines (±3) show where one blackbody fails. In cool "
                   "atmospheres that happens at water bands (1.4, 1.9, 2.7 µm), methane bands (1.6, 2.2, 3.3 µm) "
                   "and carbon monoxide or dioxide (4.3–4.7 µm).")

with c_card:
    light = fit.light
    if np.isfinite(fit.temperature) and light == "red":
        temp_html = ("<div class='cm-big'>Not reliable</div>"
                     f"<div class='cm-muted'>The curve fit gives about {fit.temperature:,.0f} K, but read the "
                     "reasons below before trusting it.</div>")
    elif np.isfinite(fit.temperature):
        temp_html = (f"<div class='cm-big'>{fit.temperature:,.0f} K</div>"
                     f"<div class='cm-muted'>range {fit.t_low:,.0f} – {fit.t_high:,.0f} K · "
                     f"about {fit.temperature - 273.15:,.0f} °C</div>")
    else:
        temp_html = "<div class='cm-big'>—</div>"
    reasons = "".join(f"<li>{madhava.REASON_TEXT.get(r, r)}</li>" for r in fit.reasons)
    st.markdown(
        f"<div class='cm-card'><div class='cm-muted'>Blackbody-equivalent temperature</div>{temp_html}"
        f"<div style='margin-top:10px'><span class='cm-light' style='background:{LIGHT_COLORS[light]}'></span>"
        f"<b>{LIGHT_WORDS[light]}</b></div><ul style='margin:6px 0 0 0; padding-left:18px'>{reasons}</ul>"
        f"<div class='cm-muted' style='margin-top:8px'>{fit.n_points} clean measurements"
        + (f" · reduced chi² {fit.chi2_red:.2f}" if np.isfinite(fit.chi2_red) else "") + "</div></div>",
        unsafe_allow_html=True,
    )
    pub = PUBLISHED.get(target.key)
    if pub:
        st.markdown(
            f"<div class='cm-card' style='margin-top:10px'><div class='cm-muted'>Published value, for comparison</div>"
            f"{pub['text']}<div class='cm-muted' style='margin-top:4px'>{pub['ref']}</div></div>",
            unsafe_allow_html=True,
        )
    with st.expander("How the Madhava engine works"):
        st.markdown(
            "SPHEREx splits light into 102 colour bands. A hot object shines mostly at short wavelengths, a cold "
            "one at long wavelengths (Wien's law). We fit Planck's law for a perfect thermal emitter to every "
            "measurement. Because each SPHEREx band is wide, we integrate the curve over each band exactly, "
            "using the series for the fraction of blackbody energy below a wavelength:"
        )
        st.latex(r"F(0\to\lambda)=\frac{15}{\pi^4}\sum_{n=1}^{\infty} e^{-nx}\left(\frac{x^3}{n}+\frac{3x^2}{n^2}"
                 r"+\frac{6x}{n^3}+\frac{6}{n^4}\right),\quad x=\frac{hc}{\lambda k T}")
        st.markdown(
            "Infinite series, pioneered by Madhava of Sangamagrama in India about 600 years ago, let us integrate "
            "Planck's law exactly over each band; the engine is named in his honour. This particular series is "
            "standard physics (Widger & Woodall 1976), not our invention. The result is a *blackbody-equivalent* "
            "temperature: brown dwarfs and young stars are not perfect blackbodies, so the traffic light tells you "
            "when one curve does not describe the light."
        )

# ------------------------------------------------------------------ does it change?

st.markdown("### 3 · Does it change? Brightness visit by visit")
v_plot, v_text = st.columns([3, 2])
with v_text:
    st.markdown(f"<div class='cm-card'>{lc['verdict']['text']}</div>", unsafe_allow_html=True)
    if any("wings" in m for m in lc["methods"].values()):
        st.caption("Its core saturates SPHEREx, so we follow the light in the wings of the star (3-6 pixels "
                   "from the centre), which rises and falls with the total brightness.")
    st.caption("For each detector we remove the smooth change of brightness with wavelength, so what remains "
               "is the change in time. Lower magnitude means brighter.")
with v_plot:
    if lc["points"]:
        import plotly.graph_objects as go
        from astropy.time import Time

        figv = go.Figure()
        for d in sorted({p["detector"] for p in lc["points"]}):
            pts = [p for p in lc["points"] if p["detector"] == d]
            figv.add_trace(go.Scatter(
                x=Time([p["mjd"] for p in pts], format="mjd").to_datetime(), y=[p["dmag"] for p in pts],
                mode="markers", name=f"D{d}", marker=dict(size=5, color=DET_COLORS[d], opacity=0.55),
            ))
        if lc["visits"]:
            figv.add_trace(go.Scatter(
                x=Time([v["mjd"] for v in lc["visits"]], format="mjd").to_datetime(),
                y=[v["dmag"] for v in lc["visits"]], mode="lines+markers", name="visit median",
                error_y=dict(type="data", array=[v["err"] for v in lc["visits"]]),
                line=dict(color="#ffffff", width=2), marker=dict(size=10),
            ))
        figv.update_layout(
            template="plotly_dark", height=340, margin=dict(l=10, r=10, t=30, b=10),
            yaxis=dict(title="Change (magnitudes)", autorange="reversed"), xaxis_title="Date",
            legend=dict(orientation="h", y=1.1), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(figv, use_container_width=True)
    else:
        st.caption("Not enough usable measurements to follow its brightness.")

# ------------------------------------------------------------------ is it real?

st.markdown("<div id='is-it-real'></div>", unsafe_allow_html=True)
st.markdown("### 4 · Is it real, or a ghost in the detector?")
if real:
    cols = st.columns(len(real["checks"]))
    for col, chk in zip(cols, real["checks"]):
        col.markdown(
            f"<div class='cm-card'><b>{STATUS_ICON[chk['status']]} {chk['name']}</b>"
            f"<div style='margin-top:6px'>{chk['text']}</div></div>",
            unsafe_allow_html=True,
        )
    st.caption("These are signals, not proof. A real discovery needs follow-up by astronomers.")
else:
    st.caption("No aligned images, so the checks cannot run.")

# ------------------------------------------------------------------ human scale

st.markdown("### 5 · On a human scale")
h1, h2 = st.columns(2)
with h1:
    if target.distance_pc:
        ly = target.distance_pc * LIGHT_YEARS_PER_PC
        obs_year = float(np.median([2000.0 + (m - 51544.5) / 365.25 for m in mjds])) if mjds else 2026.0
        left = obs_year - ly
        when = f"around {left:.0f}" if left >= 1 else f"around {abs(left) + 1:.0f} BC"
        st.markdown(
            f"<div class='cm-card'><div class='cm-muted'>Light from the past</div>"
            f"<div class='cm-big'>It left {when}</div>"
            f"The light SPHEREx caught had been travelling for about {ly:,.1f} years "
            f"({target.distance_pc:,.1f} parsecs). Looking at the sky is looking at the past."
            f"<div class='cm-muted' style='margin-top:4px'>Distance from the parallax "
            f"({target.parallax_mas:.2f} mas).</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("No parallax available for this position, so its distance is unknown here.")
with h2:
    if target.total_pm_arcsec_per_year > 0.05:
        age = st.slider("Your age (years)", 1, 100, 30)
        moved = target.total_pm_arcsec_per_year * age
        st.markdown(
            f"<div class='cm-card'><div class='cm-muted'>How far it moved during your life</div>"
            f"<div class='cm-big'>{moved:,.0f} arcsec</div>"
            f"That is {moved / MOON_DIAMETER_ARCSEC:.2f} times the width of the full Moon, or "
            f"{moved / 6.15:,.0f} SPHEREx pixels.</div>",
            unsafe_allow_html=True,
        )

# ------------------------------------------------------------------ data

st.markdown("### 6 · The data")
if rows:
    import pandas as pd

    df = pd.DataFrame(rows)
    show = ["mjd", "detector", "wavelength_um", "bandwidth_um", "flux_ujy", "err_ujy", "snr", "hard_flag",
            "soft_flag", "url"]
    df = df[[c for c in show if c in df.columns]]
    with st.expander(f"All {len(df)} measurements"):
        st.dataframe(df, use_container_width=True, height=300)
    st.download_button("Download measurements (CSV)", df.to_csv(index=False).encode(),
                       file_name=f"coldmovers_{target.key}.csv", mime="text/csv")


with st.expander("How well does it work? Validation table for the five challenge objects"):
    vt = vt_top
    if not vt:
        st.caption("Validation unavailable right now.")
    if vt:
        import pandas as pd

        light_word = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
        st.dataframe(pd.DataFrame([{
            "Object": v["name"],
            "SPHEREx images": v["images"],
            "Visits": v["visits"],
            "Moved (measured)": f"{v['moved_measured']:.1f}\"" if v["moved_measured"] is not None else "—",
            "Moved (catalogue)": f"{v['moved_predicted']:.1f}\"" if v["moved_predicted"] is not None else "—",
            "Madhava": (f"{light_word[v['light']]} {v['temperature']:,.0f} K"
                        if v["temperature"] and v["light"] != "red" else f"{light_word[v['light']]} not reliable"),
            "Why": "; ".join(madhava.REASON_TEXT.get(r, r).split(":")[0].split(".")[0] for r in v["reasons"]),
            "Published": v["published"],
        } for v in vt]), use_container_width=True, hide_index=True)
        st.caption(
            "Motion: the target's position measured by centroiding each visit, compared with the catalogue proper "
            "motion between the first and last visit. A reliable tool must also say when it cannot measure: three "
            "of the five objects are bright enough to saturate SPHEREx, and the app says so instead of inventing a "
            "number."
        )

st.divider()
st.markdown(
    "<div class='cm-muted'>Cold Movers · NASA Space Apps Challenge 2026 · team from Honduras. "
    "Open source (MIT): <a href='https://github.com/WilmerGaspar/cold-movers' target='_blank'>GitHub</a>.<br>"
    "This publication makes use of data products from the Spectro-Photometer for the History of the Universe, "
    "Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory "
    "and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration. "
    "This research has made use of the NASA/IPAC Infrared Science Archive; of data from the ESA mission Gaia, "
    "processed by the Gaia DPAC; of the SIMBAD database, VizieR and Aladin Lite (CDS, Strasbourg); and of WISE images "
    "(UCLA, JPL/Caltech, NASA). Full list with licences: "
    "<a href='https://github.com/WilmerGaspar/cold-movers/blob/main/DATA_AND_RESOURCES.md' target='_blank'>"
    "DATA_AND_RESOURCES.md</a>.<br>"
    "Built with AI assistance (Claude, Anthropic) under the team's direction. Not an official NASA product.</div>",
    unsafe_allow_html=True,
)
