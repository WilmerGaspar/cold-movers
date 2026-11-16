"""Cold Movers web app.

Run: streamlit run app.py
"""

from __future__ import annotations

import io
import json
import os

import numpy as np
import streamlit as st

from coldmovers import __version__ as APP_VERSION
from coldmovers import assistant, checks, madhava, movers, movie, pipeline, variability
from coldmovers.references import PUBLISHED
from coldmovers.targets import ALL_EXAMPLES, SHOWCASE, ServiceDown, Target, parse_coordinates, resolve_simbad

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
    "trappist1": ("extra: temperature check",
                  "not one of the challenge objects. A faint, unsaturated cool star (host of seven Earth-sized "
                  "planets) that tests the temperature engine against a published value; its motion, about 1″ a "
                  "year, is too small to see in one year of SPHEREx."),
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


def section_failed(name, exc):
    """Show a short notice instead of letting one failing part take the whole page down."""
    note_problem(name, exc)
    st.warning(f"This part ({name}) could not be shown right now ({type(exc).__name__}). "
               "The rest of the page works; please try another object or reload.")


def note_problem(name, exc):
    """Keep the page alive, but never fail silently: log it (server log) and list it in the page footer."""
    import logging

    logging.getLogger("coldmovers").warning("%s failed: %s: %s", name, type(exc).__name__, exc, exc_info=exc)
    st.session_state.setdefault("_problems", []).append(f"{name} ({type(exc).__name__})")


# ------------------------------------------------------------------ inputs


def read_query_params():
    qp = st.query_params
    if "object" in qp and qp["object"] in ALL_EXAMPLES:
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
st.session_state["_problems"] = []  # filled by note_problem during this run
st.title("Cold Movers")
st.markdown(
    "**Cold Movers lets anyone explore SPHEREx observations, follow changes between visits, and see explicitly "
    "when the data do not support a reliable conclusion.** Pick an object or type sky coordinates: we fetch every "
    "SPHEREx image of that spot from NASA's archive, play the visits as a movie so anything that moves stands out, "
    "and fit its infrared light with a blackbody to estimate how cold it is (a blackbody-equivalent "
    "temperature, with an uncertainty and a warning when it should not be trusted)."
)
st.caption(f"Team Cold Movers (Honduras) · NASA Space Apps 2026 · version {APP_VERSION} · "
           "Not an official NASA product.")


@st.cache_data(show_spinner=False)
def validation_table():
    from coldmovers import validation

    return validation.validate(PRECOMPUTED)


def validation_summary(vt_all) -> str:
    """Sentences computed from the validation table (never typed by hand)."""
    vt = [v for v in vt_all if not v.get("extra")]
    extra = ""
    for v in vt_all:
        if v.get("extra") and v["temperature"] and v.get("published_k"):
            diff = 100.0 * (v["temperature"] - v["published_k"]) / v["published_k"]
            extra += (f" <br><b>Extra check, {v['name']}</b> (unsaturated, not in the brief): blackbody-equivalent "
                      f"{v['temperature']:,.0f} K vs {v['published_k']:,} K published ({diff:+.0f} %).")
    movers = [v for v in vt if v["pm_arcsec_yr"] >= 0.5]
    good = [v for v in movers if v["moved_measured"] is not None
            and abs(v["moved_measured"] - v["moved_predicted"]) < 2.0]
    worst = max((abs(v["moved_measured"] - v["moved_predicted"]) for v in good), default=0.0)
    temp_ok = [v for v in vt if v["light"] in ("green", "yellow")]
    bright = [v for v in vt if "too_bright" in v["reasons"]]
    images = sum(v["images"] for v in vt)
    return (f"<b>{images:,} SPHEREx images, {len(vt)} objects.</b> Motion recovered for <b>{len(good)} of "
            f"{len(movers)}</b> fast-moving objects, within {worst:.1f}″ of the catalogue prediction. "
            f"A blackbody-equivalent temperature could be measured for <b>{len(temp_ok)} of {len(vt)}</b>; <b>{len(bright)}</b> are too "
            "bright for SPHEREx, and the app says so instead of inventing a number." + extra)


g1, g2 = st.columns([1, 1])
with g1:
    st.markdown(
        "<div class='cm-card'><b>How to read this page in 60 seconds</b><ol style='margin:6px 0 0 0'>"
        "<li>Pick an object below; each one demonstrates something different.</li>"
        "<li><a href='#at-a-glance'>At a glance</a>: does it move, how cold is it, is it real; each answer can be "
        "audited in one click.</li>"
        "<li><a href='#the-sky'>The movie</a>: the circle and arrow show where it should be on each date; watch "
        "whether a dot follows them while the background stays still. <a href='#movers'>Section 2</a> finds "
        "what moves with no catalogue at all.</li>"
        "<li><a href='#is-it-real'>Is it real?</a> and the traffic light: where the data cannot support a "
        "conclusion, the app says why.</li></ol></div>",
        unsafe_allow_html=True,
    )
with g2:
    try:
        vt_top = validation_table()
    except Exception as _exc:
        note_problem("validation summary", _exc)
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


@st.cache_data(show_spinner=False)
def load_scoreboard():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "scoreboard.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


try:
    sb = load_scoreboard()
    if sb:
        c = sb["counts"]
        n_all = c["pass"] + c["partial"] + c["fail"]
        st.markdown(
            "<div class='cm-card' style='margin-top:10px'><b>Validation scoreboard: known objects, injected movers, fixed rules</b> "
            f"<span style='margin-left:8px'>🟢 <b>{c['pass']}</b> pass · 🟡 <b>{c['partial']}</b> partial · "
            f"🔴 <b>{c['fail']}</b> fail</span> <span class='cm-muted'>out of {n_all} checks</span>"
            "<div class='cm-muted' style='margin-top:4px'>Positive controls (known movers, known temperatures, known "
            "variables), negative controls (stars that do not move, objects SPHEREx cannot measure), synthetic "
            "spectra, and fake movers injected into real SPHEREx images. Pass rules were fixed before the results; "
            "partial and failed checks are shown too.</div>"
            "<div style='margin-top:6px'><b>Tests, not discoveries:</b> every result on this site is a test on known "
            "objects. Cold Movers claims no discovery; the same tools run on any coordinates you type.</div></div>",
            unsafe_allow_html=True,
        )
        with st.expander("See every check, its result and its rule"):
            import html as _html

            icon = {"pass": "🟢", "partial": "🟡", "fail": "🔴"}
            st.markdown(
                "".join(
                    "<div style='padding:7px 0; border-bottom:1px solid #232b40'>"
                    f"<b>{icon[r['status']]} {_html.escape(r['check'])}</b> "
                    f"<span class='cm-muted'>· {_html.escape(r['category'])} · {r['status']}</span>"
                    f"<div style='margin-top:2px'>{_html.escape(r['result'])}</div>"
                    f"<div class='cm-muted' style='font-size:0.85em'>Rule: {_html.escape(r['rule'])}</div></div>"
                    for r in sb["rows"]),
                unsafe_allow_html=True)
            for r in sb["rows"]:
                if r.get("note"):
                    st.caption(f"**{r['check']}.** {r['note']}")
            st.caption(f"Injected movers: {sb['injection']['note']} Fields used: "
                       f"{', '.join(sb['injection']['fields_used'])}. Computed on GitHub Actions with the app's own "
                       f"code (version {sb['app_version']}, {sb['generated_utc']} UTC).")
except Exception as _exc:
    note_problem("validation scoreboard", _exc)
REPO = "https://github.com/WilmerGaspar/cold-movers/blob/main/"


@st.cache_data(show_spinner=False)
def load_doc_json(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", name)
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def _wilson(k, n, z=1.96):
    if not n:
        return float("nan"), float("nan")
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - h), min(1.0, c + h)


def _metric_row(label, s):
    tp, n, fp = s["confirmed"], s["n"], s["false_confirmed"]
    r_lo, r_hi = _wilson(tp, n)
    p_lo, p_hi = _wilson(tp, tp + fp)
    prec = f"{s['precision']:.3f} ({p_lo:.2f}–{p_hi:.2f})" if tp + fp else "—"
    return (f"| {label} | {n} | {tp} | {n - tp} | {fp} | {prec} | {s['recall']:.2f} ({r_lo:.2f}–{r_hi:.2f}) | "
            f"{s['f1']:.2f} |")


def evaluator_summary(vt, sb):
    """The science on one page, written from the generated result files (no number is typed here)."""
    dev = load_doc_json("benchmark_injection.json")
    hold_a = load_doc_json("benchmark_holdout_A.json")
    hold_b = load_doc_json("benchmark_holdout_B.json")
    plx = load_doc_json("parallax_effect.json") or {}
    images = sum(v["images"] for v in vt)
    out = [
        "**1 · The problem.** Find objects that move across the sky in SPHEREx's repeated observations, measure "
        "how cold they look, and say clearly when the data cannot support a conclusion. Every result here is a "
        "test on known objects: Cold Movers claims no discovery.",
        f"**2 · Real data.** {images:,} SPHEREx spectral images (Data Release 1 + Quick Release 3, NASA/IPAC IRSA, "
        "[doi:10.26131/IRSA678](https://doi.org/10.26131/IRSA678)) of six objects. Every measurement keeps the URL "
        "of its original SPHEREx file (the `url` column of each CSV download). Fake movers used for testing are "
        "added to copies of these images and are always labelled as injections, never shown as observations.",
        "**3 · How it detects.** In each detector's visit stacks, point sources are found (6σ peaks), followed to "
        "the nearest source in the other visits and fitted with a straight line. No catalogue position or motion "
        "is used.",
        "**4 · How it validates.** A mover is CONFIRMED only when two or more of SPHEREx's six simultaneous "
        "detectors show the same motion with a combined significance of 5 or more, in detectors whose still stars "
        "line up, and no more significant mover passes within 4 px (its light could pull the centroid). Otherwise it "
        "is a CANDIDATE, or INCONCLUSIVE when the detectors cannot be trusted. Temperatures get a traffic light; a "
        "red light means INCONCLUSIVE.",
        "**5 · Results on the test objects** (generated by the app's own code):",
        "",
        "| Object | Motion verdict | Found with no catalogue | Catalogue | Temperature verdict | Published |",
        "|---|---|---|---|---|---|",
    ]
    for v in vt:
        free = (f"{v['free_rate']:.2f}″/yr, {v['free_pa']:.0f}°" if v.get("free_rate") else "—")
        temp = f" ({v['temperature']:,.0f} K)" if v["temperature"] and v["light"] != "red" else ""
        out.append(f"| {v['name']} | **{v['motion_verdict']}** | {free} | {v['catalogue_rate']:.2f}″/yr, "
                   f"{v['catalogue_pa']:.0f}° | {v['temperature_verdict']}{temp} | {v['published'].split(';')[0]} |")
    out += ["", "**6 · Detection metrics** (S/N 15, all six detectors, 5–20″/yr; 95 % intervals in brackets). "
            "TP: an injected mover confirmed within 1.5 px of where it was. FN: an injected mover not confirmed. "
            "FP: a confirmed mover that was not injected and was not there before. Precision = TP / (TP + FP); "
            "recall = TP / injections; F1 is their harmonic mean.", "",
            "| Set | Injections | TP | FN | FP | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|---|"]
    if dev:
        out.append(_metric_row("Development (3,300 trials; the neighbour-pull rule was chosen on it)",
                               dev["by_snr_core"]["15.0"]))
    if hold_a:
        out.append(_metric_row("Held-out A (new seed, spots and motions; same six fields)", hold_a["headline_snr15_core"]))
    if hold_b and hold_b.get("trials"):
        out.append(_metric_row(f"Held-out B ({sum(1 for f in hold_b['fields'].values() if 'visits' in f)} new SPHEREx "
                               "fields, never used before)", hold_b["headline_snr15_core"]))
    red = next((r for r in (sb or {}).get("rows", []) if "Very red" in r["check"]), None)
    worst_plx = max((p["bias_arcsec_yr"] for p in plx.values()), default=None)
    out += ["", "**7 · Limits.** "
            + (f"Very red movers seen only by the two longest-wavelength detectors: {red['result'].split(';')[0]}. "
               if red else "")
            + "Recall is lower next to stars and in crowded spots, and very low at S/N 5; speeds below about 3″/yr "
              "cannot be confirmed with a year of visits. A blackbody-equivalent temperature is not a true "
              "(effective) temperature. Parallax is not modelled"
            + (f" (its bias on these objects' fitted motion is at most {worst_plx:.2f}″/yr)" if worst_plx is not None
               else "")
            + ". Saturated stars give no temperature. The search does not find every moving object.",
            "", "**8 · Reproduce.** `pip install -r requirements.txt`, then `python -m pytest -q`, "
            "`python scripts/scoreboard.py`, `python scripts/benchmark_injection.py`, "
            "`python scripts/benchmark_holdout.py`. Details: "
            f"[README]({REPO}README.md), [held-out pre-registration]({REPO}evidence/HOLDOUT_PREREGISTRATION.md), "
            f"[final validation report]({REPO}evidence/FINAL_VALIDATION_REPORT.md), "
            f"[evidence records]({REPO}docs/validation_records.md)."]
    return "\n".join(out)


@st.cache_data(show_spinner=False)
def evidence_ledger():
    from coldmovers import evidence

    return evidence.build_ledger(os.path.dirname(os.path.abspath(__file__)))


def evidence_blocks(ledger):
    """Six short blocks for evaluators, all written from the evidence ledger."""
    def lines(entries, fmt):
        return "".join(f"<li>{fmt(e)}</li>" for e in entries) or "<li>none</li>"

    def short(e):
        return e["evidence"].split(". ")[0]

    measured = [e for e in ledger if e["category"] == "A"]
    simulated = [e for e in ledger if e["category"] in ("B", "S")]
    confirmed = [e for e in ledger if e["status"] == "CONFIRMED"]
    candidates = [e for e in ledger if e["category"] == "C"]
    undemonstrated = [e for e in ledger if e["category"] == "D"]
    limits = [f"<b>{e['claim']}</b>: {e['limitations']}" for e in ledger
              if e["limitations"] and e["id"] in ("injection-red", "benchmark-dev", "benchmark-B", "parallax",
                                                  "calibration-null", "calibration-pulls-A",
                                                  "calibration-temperature", "temperature-trappist1")]
    card = "<div class='cm-card' style='margin-top:6px'><b>{}</b><ul style='margin:4px 0 0 0'>{}</ul></div>"
    left = (card.format("✅ What was measured in real SPHEREx images (A)",
                        lines(measured, lambda e: f"{e['claim']}: <b>{e['status']}</b>"))
            + card.format("🟢 What was confirmed by our own measurements",
                          lines(confirmed, lambda e: f"{e['claim']}: {short(e)}"))
            + card.format("🟡 What is still a candidate (C)",
                          lines(candidates, lambda e: f"{e['claim']}: <b>{e['status']}</b>")))
    right = (card.format("🧪 What was simulated: injection tests (B) and synthetic checks (S), never discoveries",
                         lines(simulated, lambda e: f"{e['claim']} ({e['category']})"))
             + card.format("⚪ What could not be shown (D)",
                           lines(undemonstrated, lambda e: f"{e['claim']}: <b>{e['status']}</b>"))
             + card.format("⚠️ Known scientific limits", "".join(f"<li>{x}</li>" for x in limits)))
    return left, right


try:
    _ledger = evidence_ledger()
    st.markdown("#### Scientific evidence & validation: what is real, what is a test, what is still a candidate")
    _l, _r = st.columns(2)
    _left, _right = evidence_blocks(_ledger)
    _l.markdown(_left, unsafe_allow_html=True)
    _r.markdown(_right, unsafe_allow_html=True)
    with st.expander("🔗 Traceability: every claim, its kind of evidence, its status and where to check it"):
        from coldmovers import evidence as _evidence

        st.markdown(_evidence.traceability_markdown(_ledger))
        st.caption("Generated from the result files by coldmovers/evidence.py; the README and the final report show "
                   "the same summary, and automated tests check that they agree.")
except Exception as _exc:
    note_problem("evidence ledger", _exc)
try:
    with st.expander("🔬 For evaluators: the science on one page (data, method, validation, results, limits)"):
        st.markdown(evaluator_summary(vt_top, sb if "sb" in dir() else None))
except Exception as _exc:
    note_problem("evaluator summary", _exc)
with st.expander("📖 Words used on this page (glossary)"):
    st.markdown(
        "- **SPHEREx**: a NASA space telescope, launched in March 2025, that covers the entire sky twice a year, "
        "measuring each point in 102 infrared wavelength bands from 0.75 to 5 µm.\n"
        "- **Visit**: SPHEREx comes back to the same patch of sky about every six months. All images from one pass "
        "are stacked into one frame of the movie.\n"
        "- **Detectors D1 to D6**: SPHEREx has six detector arrays, each for a range of infrared colours, from "
        "0.75 µm (D1) to 5 µm (D6).\n"
        "- **Arcsecond (″)**: 1/3600 of a degree. A 2 cm coin seen from 4 km away spans about one arcsecond; one "
        "SPHEREx pixel spans 6.15″.\n"
        "- **mas/yr**: thousandths of an arcsecond per year, how catalogues give the speed of a star across the sky.\n"
        "- **Blackbody-equivalent temperature**: the temperature of an ideal glowing object (a blackbody) whose "
        "infrared colours match the measured ones. Stars and brown dwarfs are not perfect blackbodies, so it is not "
        "their true surface temperature.\n"
        "- **Traffic light**: green, one blackbody describes the light well; yellow, usable but one blackbody does "
        "not describe it well; red, SPHEREx cannot give a reliable temperature here (too bright, too cold, too faint "
        "or too few colours), so no number is presented as reliable.\n"
        "- **S/N (signal-to-noise)**: how many times brighter a source is than the noise around it.\n"
        "- **σ (sigma)**: how many times larger a change is than its uncertainty; above 5σ is a strong result.\n"
        "- **Magnitude**: the astronomers' brightness scale; a change of 0.1 magnitudes is about 10 %.\n"
        "- **Found without catalogue / confirmed / candidate**: motion found only from the SPHEREx images, without "
        "knowing where to look. Confirmed when at least two of the six detectors see the same motion and no more "
        "significant mover passes within 4 pixels of it (whose light could pull its measured position); otherwise it stays a "
        "candidate. Nothing is ever called a discovery."
    )
st.write("")

tab_obj, tab_coords, tab_name = st.tabs(["Challenge objects", "Coordinates", "Name"])
request = None

with tab_obj:
    # Challenge objects, then extras that have reviewed, precomputed results.
    keys = list(SHOWCASE) + [k for k in ALL_EXAMPLES if k not in SHOWCASE
                             and os.path.exists(os.path.join(PRECOMPUTED, k, "result.json"))]
    # The choice lives in session state with a fixed key: if its default followed the URL, Streamlit would
    # treat the selector as a new widget after every change and drop every other click.
    if "object_choice" not in st.session_state:
        st.session_state["object_choice"] = initial["key"] if initial["mode"] == "object" else keys[0]
    choice = st.radio(
        "Object", keys, key="object_choice", horizontal=True,
        format_func=lambda k: f"{ALL_EXAMPLES[k].name} · {DEMO[k][0]}", label_visibility="collapsed",
    )
    st.caption(f"{ALL_EXAMPLES[choice].note} **What it demonstrates:** {DEMO[choice][1]}")
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
        tgt = ALL_EXAMPLES[request["key"]]
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

try:
    fit = pipeline.fit_rows(rows)
except Exception as _exc:
    note_problem("temperature fit", _exc)
    fit = madhava.FitResult(temperature=float('nan'), t_low=float('nan'), t_high=float('nan'), scale=0.0,
                            chi2=float('nan'), dof=0, n_points=0, light='red', reasons=['not_enough_signal'])
try:
    real = checks.run_checks(rows, epochs, view["stacks"], marker) if view.get("stacks") else None
except Exception as _exc:
    note_problem("consistency checks", _exc)
    real = None
try:
    found = movers.search_all(epochs, view["stacks"]) if view.get("stacks") else None
except Exception as _exc:
    note_problem("mover search", _exc)
    found = None
try:
    lc = variability.light_curve(rows, epochs)
except Exception as _exc:
    note_problem("brightness check", _exc)
    lc = {"points": [], "visits": [], "methods": {},
          "verdict": {"variable": False, "amplitude_mag": None, "significance": None,
                      "text": "The brightness check could not run for this object."}}
STATUS_ICON = {"pass": "🟢", "warn": "🟡", "fail": "🔴"}


try:
    def summary_card(title, big, small, color="#232b40", icon=""):
        return (f"<div class='cm-card' style='border-left:5px solid {color}; min-height:128px'>"
                f"<div class='cm-muted'><span style='font-size:1.25rem; margin-right:6px'>{icon}</span>{title}</div>"
                f"<div class='cm-big' style='font-size:1.7rem'>{big}</div>"
                f"<div class='cm-muted' style='margin-top:4px'>{small}</div></div>")


    try:
        from coldmovers.validation import free_motion_from

        FREE = free_motion_from(found, epochs, marker)
    except Exception as _exc:
        note_problem("catalogue-free motion of the target", _exc)
        FREE = None
    FREE_NOTE = (f". Without the catalogue the app finds it moving {FREE['rate_arcsec_yr']:.1f}″/yr "
                 f"({'confirmed' if FREE['confirmed'] else 'candidate'}; see section 2)") if FREE else ""
    s1, s2, s3 = st.columns(3)
    motion = real.get("motion") if real else None
    if motion and target.total_pm_arcsec_per_year >= 0.5:
        moved_as = motion["measured_px"] * checks.PIXEL_ARCSEC
        s1.markdown(summary_card(
            "Does it move?", f"Yes · {moved_as:.1f}″",
            f"between the first and last visit, {assistant.coin_phrase(moved_as)}. Measured in the SPHEREx images "
            f"(centroids near the predicted track); the catalogue predicts "
            f"{motion['predicted_px'] * checks.PIXEL_ARCSEC:.1f}″" + FREE_NOTE, "#2fbf71", icon="🧭"),
            unsafe_allow_html=True)
    elif target.total_pm_arcsec_per_year < 0.5:
        s1.markdown(summary_card(
            "Does it move?", "Too slowly to see",
            f"{target.total_pm_arcsec_per_year * 1000:.0f} milliarcsec per year: far below one SPHEREx pixel "
            "over these visits", icon="🧭"), unsafe_allow_html=True)
    else:
        s1.markdown(summary_card("Does it move?", "Not measured", "not enough clear detections to follow it",
                                 icon="🧭"), unsafe_allow_html=True)

    if np.isfinite(fit.temperature) and fit.light != "red":
        big_t, small_t = f"{fit.temperature:,.0f} K", madhava.REASON_TEXT.get(fit.reasons[0], "") if fit.reasons else ""
    else:
        big_t = "Too bright to measure" if "too_bright" in fit.reasons else "Not reliable"
        small_t = madhava.REASON_TEXT.get(fit.reasons[0], "") if fit.reasons else ""
    small_t = small_t.split(". ")[0].rstrip(".") + "." if small_t else ""
    if fit.light == "red" and {"too_bright", "narrow_coverage", "only_long_wavelengths"} & set(fit.reasons):
        # A limit of the instrument, not a failure of the app: say so on the card itself.
        small_t = "<b>Instrument limit, not an app error.</b> " + small_t.replace(" um", " µm")
    s2.markdown(summary_card(f"How cold? (blackbody-equivalent) · {LIGHT_WORDS[fit.light]}", big_t, small_t,
                             LIGHT_COLORS[fit.light], icon="🌡️"), unsafe_allow_html=True)

    if real:
        n_pass = sum(c["status"] == "pass" for c in real["checks"])
        icons = " ".join(f"{STATUS_ICON[c['status']]} {c['name']}" for c in real["checks"])
        color = "#2fbf71" if n_pass == len(real["checks"]) else ("#f2c94c" if n_pass >= 2 else "#eb5757")
        s3.markdown(summary_card("Is it real?", f"{n_pass} of {len(real['checks'])} checks pass", icons, color,
                                 icon="🔍"), unsafe_allow_html=True)

    try:
        bullets = assistant.explain(target, fit, real, FREE, lc["verdict"], epochs)
        st.markdown(
            "<div class='cm-card' style='margin-top:10px'><div style='font-weight:600; margin-bottom:6px'>"
            "🧭 What am I looking at? In plain words</div>"
            + "".join(f"<div style='margin:4px 0'>{icon} {text}</div>" for icon, text in bullets)
            + "<div class='cm-muted' style='margin-top:6px'>Every sentence is written from the measurements on this "
              "page; nothing is added by hand.</div></div>",
            unsafe_allow_html=True,
        )
    except Exception as _exc:
        note_problem("plain-words panel", _exc)

    with st.expander("How were these three answers calculated? (audit trail)"):
        from astropy.time import Time

        def visit_file(mjd):
            """A small cutout of one original SPHEREx image of this visit, served by NASA/IPAC IRSA."""
            ep_rows = [r for r in rows if r.get("url") and abs(r["mjd"] - mjd) < 30 and r["inside"]]
            if not ep_rows:
                return None
            r = min(ep_rows, key=lambda r: abs(r["mjd"] - mjd))
            return f"{r['url']}?center={r['ra']:.6f},{r['dec']:.6f}d&size=0.05"

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
                    "Original SPHEREx image (IRSA)": visit_file(p["mjd"]),
                } for p in real["positions"]]), use_container_width=True, hide_index=True,
                    column_config={"Original SPHEREx image (IRSA)": st.column_config.LinkColumn(
                        display_text="download FITS cutout")})
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
                + (f"- **Result (blackbody-equivalent):** {fit.temperature:,.0f} K, interval {fit.t_low:,.0f}–{fit.t_high:,.0f} K "
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
except Exception as _section_error:  # keep the rest of the page alive
    section_failed('the summary', _section_error)

# ------------------------------------------------------------------ sky movie
try:

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
            "for \"Planet X\": a blink comparator flipped between two plates of one star field, exposed days apart, "
            "and the planet was the dot that jumped. Cold Movers is a "
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
        view_mode = st.radio("View", ["Movie", "Difference from the first visit", "Sum of all visits"],
                             horizontal=True,
                             key="view_mode",
                             help="Difference: things that did not change cancel out; moving or varying things remain.")
        show_diff = view_mode == "Difference from the first visit"
        show_sum = view_mode == "Sum of all visits"
        layers_on = st.pills("Visual assistant", list(assistant.LAYERS), selection_mode="multi",
                             default=list(assistant.LAYERS), key="layers_on") or []
        layers = assistant.layers_for(real, found, layers_on)
        diff_k = None
        usable_det = [ep for ep in epochs if det in view["stacks"].get(ep["index"], {})] if view.get("stacks") else []
        if show_diff and len(usable_det) >= 2:
            diff_k = st.select_slider(
                "Visit to compare with the first one", options=list(range(1, len(usable_det))),
                value=len(usable_det) - 1,
                format_func=lambda k: f"{assistant.mjd_to_date(usable_det[k]['mjd_mid'])} (visit {k + 1})")
        st.markdown(
            f"<span class='cm-muted'>Field of view {view['size_deg'] * 60:.1f} arcmin · SPHEREx pixels are 6.15 arcsec. "
            f"<a href='https://simbad.cds.unistra.fr/simbad/sim-coo?Coord={target.ra_deg}+{target.dec_deg}"
            f"&Radius=2&Radius.unit=arcmin' target='_blank'>SIMBAD</a> · "
            f"<a href='https://byw.tools/wiseview#ra={target.ra_deg}&dec={target.dec_deg}&size=176&band=3' "
            f"target='_blank'>Open in WiseView (WISE)</a></span>",
            unsafe_allow_html=True,
        )


    @st.cache_data(show_spinner=False, max_entries=48)
    def gif_for(cache_key: str, det: int, layers_key: str, _epochs, _stacks, _layers):
        eps = [dict(ep, stacks=_stacks.get(ep["index"], {}),
                    counts={int(k): v for k, v in ep["counts"].items()}) for ep in _epochs]
        pngs = movie.render_frames(eps, det, marker, pipeline.epoch_title, track=pipeline.track_points(marker, _epochs),
                                   layers=_layers)
        return movie.frames_to_gif(pngs, 800)


    def eps_with_stacks():
        return [dict(ep, stacks=view["stacks"].get(ep["index"], {}),
                     counts={int(k): v for k, v in ep["counts"].items()}) for ep in epochs]


    with left:
        if not view.get("stacks"):
            st.warning("No images could be aligned for this position.")
        elif show_sum:
            png = movie.render_sum(eps_with_stacks(), det, marker, track=pipeline.track_points(marker, epochs),
                                   layers=layers, title=f"Sum of all {len(usable_det)} visits · "
                                                        f"{movie.detector_label(det)}")
            if png is None:
                st.info("No visits to add up for this detector.")
            else:
                st.image(png, use_container_width=True)
                st.caption("All visits added together: faint sources that stay still become clearer, while anything "
                           "that moves is smeared into a short streak or a row of dots along its path.")
        elif show_diff:
            if diff_k is None:
                st.info("Only one visit so far for this detector, so there is nothing to subtract yet.")
            else:
                png = movie.render_difference(
                    eps_with_stacks(), det, diff_k, marker, track=pipeline.track_points(marker, epochs), layers=layers,
                    title=(f"{assistant.mjd_to_date(usable_det[diff_k]['mjd_mid'])} minus "
                           f"{assistant.mjd_to_date(usable_det[0]['mjd_mid'])} · {movie.detector_label(det)}\n"
                           "red = brighter now, blue = brighter then"))
                st.image(png, use_container_width=True)
                st.caption("Blue circle: predicted position at the first visit; orange: at the chosen visit. A real "
                           "mover leaves a blue spot where it was and a red spot where it is now.")
        else:
            key = f"{target.key}-{target.ra_deg:.5f}-{target.dec_deg:.5f}-{view.get('dir')}-{view['size_deg']}-{len(epochs)}"
            gif_file = view.get("gifs", {}).get(str(det)) if view.get("dir") else None
            all_layers = set(layers_on) == set(assistant.LAYERS)
            if all_layers and gif_file and os.path.exists(os.path.join(view["dir"], gif_file)):
                with open(os.path.join(view["dir"], gif_file), "rb") as fh:
                    gif = fh.read()  # frozen GIFs are rendered with every assistant layer on
            else:
                with st.spinner("Drawing the movie"):
                    gif = gif_for(key, det, ",".join(sorted(layers_on)), epochs, view["stacks"], layers)
            st.image(gif, use_container_width=True)
            st.caption("**Orange circle**: where the catalogue says the object is on that date (dashed: its path). "
                       "**Cyan +**: the position measured in that visit; **cyan arrow**: the measured motion since "
                       "the first visit, drawn ×N longer so a pixel or two can be seen. **Dotted ring**: the "
                       "\"Is it real?\" checks (green all pass, yellow some, red few). **Squares #**: other sources "
                       "that move, found without any catalogue (green confirmed, yellow candidate), with their "
                       "fitted trajectory so far as a dotted line.")
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

        return atlas.gaia_field_timed(ra, dec, radius)


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
except Exception as _section_error:  # keep the rest of the page alive
    section_failed('the sky movie', _section_error)

# ------------------------------------------------------------------ movers in the field
try:
    st.markdown("<div id='movers'></div>", unsafe_allow_html=True)
    st.markdown("### 2 · What moves in this field? Found without any catalogue")
    st.caption(
        "Every point source in every visit is detected and followed from visit to visit; a straight-line motion "
        "is fitted to its positions. No catalogue, proper motion or expected position is used. Because SPHEREx "
        "images its six detectors at the same moments, a real mover must show the same motion in at least two "
        "detectors to be called confirmed; one detector alone gives only a candidate."
    )
    if view.get("stacks") and found is not None:
        from astropy.time import Time

        cands = found["candidates"]
        first_mjd = min(ep["mjd_mid"] for ep in epochs)
        last_mjd = max(ep["mjd_mid"] for ep in epochs)
        tx, ty = marker(first_mjd)

        @st.cache_data(show_spinner=False, max_entries=32)
        def gaia_for_movers(ra, dec, radius):
            from coldmovers import atlas

            return atlas.gaia_field_timed(ra, dec, radius)

        gaia_note = {}
        if cands:
            try:
                from coldmovers import atlas

                ra_c, dec_c = ref_wcs.wcs_pix2world(float(tx), float(ty), 0)
                gstars = atlas.stars_at_year(
                    [g for g in gaia_for_movers(round(float(ra_c), 5), round(float(dec_c), 5),
                                                round(view["size_deg"] * 0.75, 4))],
                    2000.0 + (first_mjd - 51544.5) / 365.25)
                for i, c in enumerate(cands):
                    # The same object must sit at the same place AND move the same way: a stationary
                    # Gaia star next to a fast mover (WISE 0855 passing a background star) is not it.
                    best, nearby_static = None, False
                    for g in gstars:
                        gx, gy = ref_wcs.wcs_world2pix(g["ra"], g["dec"], 0)
                        d = float(np.hypot(gx - c["x"], gy - c["y"]))
                        if d > 2.0:
                            continue
                        g_rate = float(np.hypot(g["pmra"], g["pmdec"]) / 1000.0)
                        if abs(g_rate - c["rate_arcsec_yr"]) <= max(1.0, 0.3 * c["rate_arcsec_yr"]):
                            if best is None or d < best[0]:
                                best = (d, g, g_rate)
                        else:
                            nearby_static = True
                    if best:
                        gaia_note[i] = f"Gaia DR3 star moving the same way: {best[2]:.2f}″/yr"
                    elif nearby_static:
                        gaia_note[i] = ("no Gaia DR3 star moves like this; the Gaia star next to it does not move, so "
                                        "it is a different object (this mover is too faint or too red for Gaia)")
                    else:
                        gaia_note[i] = ("no Gaia DR3 counterpart (too faint or too red for Gaia, like a cold "
                                        "brown dwarf, or not a star)")
            except Exception as exc:
                gaia_note = {}
                st.caption(f"The ESA Gaia archive is not answering right now ({type(exc).__name__}), so the check "
                           "against Gaia DR3 stars is skipped; the motion measured in the SPHEREx images is not "
                           "affected. It is tried again in a few minutes.")

        mv_left, mv_right = st.columns([3, 2])
        with mv_left:
            import matplotlib.pyplot as plt

            det_show = cands[0]["detectors"][0] if cands else 0
            last_ep = max((ep for ep in epochs if det_show in view["stacks"].get(ep["index"], {})),
                          key=lambda ep: ep["mjd_mid"], default=None)
            if last_ep is not None:
                img = view["stacks"][last_ep["index"]][det_show]
                v = img[np.isfinite(img)]
                lo, hi = (np.percentile(v, [5, 99.7]) if v.size else (0, 1))
                fig, ax = plt.subplots(figsize=(4.4, 4.6), dpi=110, facecolor="#0b0f1a")
                ax.imshow(np.nan_to_num(np.arcsinh(np.clip((img - lo) / max(hi - lo, 1e-9), 0, None) * 10)),
                          origin="lower", cmap="gray", interpolation="nearest")
                for i, c in enumerate(cands[:6]):
                    col = "#2fbf71" if c["confirmed"] else "#f2c94c"
                    span = (last_mjd - first_mjd) / 365.25
                    ex, ey = c["x"] + c["vx_px_yr"] * span * 3, c["y"] + c["vy_px_yr"] * span * 3
                    ax.annotate("", xy=(ex, ey), xytext=(c["x"], c["y"]),
                                arrowprops=dict(arrowstyle="-|>", color=col, lw=1.8))
                    ax.text(c["x"] - 2.2, c["y"] - 2.2, f"#{i + 1}", color=col, fontsize=9, weight="bold")
                ax.add_patch(plt.Circle((tx, ty), 3.0, fill=False, color="#ff5a36", lw=1.2, ls="--"))
                ax.set_xticks([])
                ax.set_yticks([])
                ax.set_title(f"Last visit, {movie.detector_label(det_show)}\narrows: motion found, drawn 3× longer",
                             color="#e8ecf4", fontsize=8)
                fig.text(0.99, 0.005, movie.WATERMARK, ha="right", va="bottom", fontsize=6, color="#8a93a6")
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)
        with mv_right:
            if not cands:
                st.markdown("<div class='cm-card'>Nothing in this field moves measurably between the visits.</div>",
                            unsafe_allow_html=True)
            for i, c in enumerate(cands[:6]):
                is_target = bool(np.hypot(c["x"] - tx, c["y"] - ty) <= 2.0)
                n_det = len(c["detectors"])
                head = (f"🟢 Confirmed: {n_det} of 6 detectors see the same motion" if c["confirmed"]
                        else f"🟡 Candidate: passes within {movers.BLEND_PX:.0f} px of a faster mover, whose "
                             "light can pull its measured position" if c.get("pulled_by_neighbour")
                        else f"🟡 Candidate: {n_det} of 6 detectors")
                chips = []
                for d in range(1, 7):
                    info = found["per_detector"].get(d, {})
                    if d in c["detectors"]:
                        chips.append(f"<span style='color:#2fbf71; font-weight:700'>D{d} ✓</span>")
                    elif not info.get("reliable", False) and info.get("n_sources"):
                        chips.append(f"<span class='cm-muted' title='field not trusted in this detector'>D{d} ?</span>")
                    else:
                        chips.append(f"<span class='cm-muted'>D{d} ·</span>")
                each = " · ".join(f"D{m['detector']} {m['rate_arcsec_yr']:.2f}″/yr" for m in c.get("members", []))
                agree = (f"; the detectors agree within {c['rate_spread_arcsec_yr']:.2f}″/yr"
                         if len(c.get("members", [])) > 1 else "")
                cat = ""
                if is_target and target.total_pm_arcsec_per_year > 0:
                    cat_pa = float(np.degrees(np.arctan2(target.pmra_masyr, target.pmdec_masyr)) % 360)
                    cat = (f"<br>This is <b>{target.name}</b>. Catalogue: {target.total_pm_arcsec_per_year:.2f}″/yr "
                           f"towards {cat_pa:.0f}°.")
                st.markdown(
                    f"<div class='cm-card' style='margin-bottom:8px'><b>#{i + 1} · {head}</b><br>"
                    f"<div style='margin:4px 0; letter-spacing:0.5px'>{'&nbsp; '.join(chips)}</div>"
                    f"{c['rate_arcsec_yr']:.2f}″ per year towards {c['pa_deg']:.0f}° (east of north) · "
                    f"{c['significance']:.1f}σ combined"
                    f"<div class='cm-muted' style='margin-top:2px'>Each detector on its own: {each}{agree}. The "
                    f"combined value weights each detector by its significance.</div>"
                    f"{cat}<div class='cm-muted' style='margin-top:4px'>{gaia_note.get(i, '')}</div></div>",
                    unsafe_allow_html=True,
                )
            unreliable = [str(d) for d, x in found["per_detector"].items() if not x["reliable"] and x["n_sources"]]
            st.caption(
                "✓ sees the motion · · does not see it · ? field not trusted. "
                "Detectors whose field could not be trusted (saturated halos, moving ghosts): "
                + (", ".join(unreliable) if unreliable else "none") + ". Visits from "
                + f"{Time(first_mjd, format='mjd').iso[:10]} to {Time(last_mjd, format='mjd').iso[:10]}."
            )
            if cands:
                import pandas as pd

                out_rows = []
                for i, c in enumerate(cands):
                    ra_m, dec_m = ref_wcs.wcs_pix2world(float(c["x"]), float(c["y"]), 0)
                    out_rows.append({
                        "id": f"#{i + 1}", "status": "confirmed" if c["confirmed"] else "candidate",
                        "detectors": " ".join(map(str, c["detectors"])), "n_detectors": len(c["detectors"]),
                        "rate_arcsec_per_yr": round(c["rate_arcsec_yr"], 3),
                        "direction_deg_east_of_north": round(c["pa_deg"], 1),
                        "detector_rate_spread_arcsec_per_yr": round(c.get("rate_spread_arcsec_yr", 0.0), 3),
                        "significance_sigma": round(c["significance"], 1),
                        "ra_deg": round(float(ra_m), 6), "dec_deg": round(float(dec_m), 6),
                        "position_date": Time(c["t0_mjd"], format="mjd").iso[:10],
                        "is_the_target": bool(np.hypot(c["x"] - tx, c["y"] - ty) <= 2.0),
                        "pulled_by_neighbour": bool(c.get("pulled_by_neighbour", False)),
                        "gaia_check": gaia_note.get(i, "not checked"),
                        "open_in_cold_movers": (f"https://cold-movers.streamlit.app/?ra={float(ra_m):.5f}"
                                                f"&dec={float(dec_m):.5f}"),
                    })
                st.download_button(
                    "Download the movers found (CSV)", pd.DataFrame(out_rows).to_csv(index=False).encode(),
                    file_name=f"coldmovers_movers_{target.key}.csv", mime="text/csv",
                    help="Position on the first visit, motion, detectors and the Gaia check, for use in other tools.")
    else:
        st.caption("No aligned images, so the search cannot run.")
except Exception as _section_error:  # keep the rest of the page alive
    section_failed("the mover search", _section_error)

# ------------------------------------------------------------------ trajectory
try:
    traj = (assistant.trajectory_fit(real["positions"], target.pmra_masyr, target.pmdec_masyr)
            if real and real.get("positions") and target.total_pm_arcsec_per_year >= 0.5 else None)
    if traj:
        from plotly.subplots import make_subplots
        import plotly.graph_objects as go

        st.markdown(f"#### 📈 Trajectory of {target.name}: position versus time")
        figt = make_subplots(rows=1, cols=2, subplot_titles=("East offset (″)", "North offset (″)"))
        for col, key in ((1, "east"), (2, "north")):
            figt.add_trace(go.Scatter(x=traj["pred_dates"], y=traj[f"pred_{key}"], mode="lines",
                                      line=dict(color="#ff5a36", dash="dash"), name="catalogue prediction",
                                      showlegend=col == 1), row=1, col=col)
            figt.add_trace(go.Scatter(x=traj["dates"], y=traj[f"fit_{key}"], mode="lines",
                                      line=dict(color="#38d9f5"), name="straight-line fit to SPHEREx",
                                      showlegend=col == 1), row=1, col=col)
            figt.add_trace(go.Scatter(x=traj["dates"], y=traj[key], mode="markers",
                                      error_y=dict(type="data", array=traj["err"], visible=True, color="#38d9f5"),
                                      marker=dict(color="#38d9f5", size=9), name="measured position (±1σ)",
                                      showlegend=col == 1), row=1, col=col)
        figt.update_layout(template="plotly_dark", height=330, margin=dict(l=10, r=10, t=40, b=10),
                           legend=dict(orientation="h", y=-0.18), paper_bgcolor="rgba(0,0,0,0)",
                           plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(figt, use_container_width=True)
        dsig = abs(traj["rate"] - traj["catalogue_rate"]) / traj["rate_err"] if traj["rate_err"] > 0 else float("nan")
        chi = (f"reduced χ² {traj['chi2_red']:.2f}" + (" (the points follow a straight line within their errors)"
                                                        if traj["chi2_red"] <= 2 else
                                                        " (more scatter than the error bars; the uncertainty "
                                                        "below has been enlarged to match)")
               if np.isfinite(traj["chi2_red"]) else "two visits only, so a straight line always fits")
        signif = ("" if traj["rate"] >= 3 * traj["rate_err"] else
                  " The motion is smaller than three times its uncertainty: over these visits SPHEREx alone "
                  "cannot measure it significantly, and the app says so.")
        st.markdown(
            f"<div class='cm-card'>Measured from {traj['n']} visits in the SPHEREx images: "
            f"<b>{traj['rate']:.2f} ± {traj['rate_err']:.2f}″ per year towards {traj['pa']:.0f}° ± "
            f"{traj['pa_err']:.0f}°</b>. Catalogue: {traj['catalogue_rate']:.2f}″ per year towards "
            f"{traj['catalogue_pa']:.0f}°, a difference of {dsig:.1f}σ. {chi.capitalize()}.{signif}"
            "<div class='cm-muted' style='margin-top:4px'>Each point is a position measured within 2.5 pixels of the "
            "predicted track (so this uses the catalogue to know where to look, unlike section 2). Error bars "
            "combine the alignment between visits (0.12 px) and the centroid noise (PSF width divided by S/N). "
            "Offsets are from the predicted position at the first visit.</div></div>",
            unsafe_allow_html=True)
except Exception as _section_error:
    section_failed("the trajectory", _section_error)

# ------------------------------------------------------------------ spectrum + Madhava
try:

    st.markdown("### 3 · Its light, and how cold it is")

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
        series_html = ""
        if np.isfinite(fit.temperature) and clean:
            try:
                rep = madhava.series_report([r["wavelength_um"] for r in clean], [r["bandwidth_um"] for r in clean],
                                            fit.temperature)
                if np.isfinite(rep["max_rel_bound"]):
                    ex = max(int(np.ceil(np.log10(max(rep["max_rel_bound"], 1e-300)))), -15)
                    terms = f"{rep['terms']} terms + Madhava correction · " if rep["terms"] else ""
                    series_html = (f"<div class='cm-muted' style='margin-top:4px'>Series: {terms}error below "
                                   f"10<sup>{ex}</sup>, guaranteed</div>")
            except Exception as _exc:
                note_problem("series error bound", _exc)
                series_html = ""
        st.markdown(
            f"<div class='cm-card'><div class='cm-muted'>Blackbody-equivalent temperature</div>{temp_html}"
            f"<div style='margin-top:10px'><span class='cm-light' style='background:{LIGHT_COLORS[light]}'></span>"
            f"<b>{LIGHT_WORDS[light]}</b></div><ul style='margin:6px 0 0 0; padding-left:18px'>{reasons}</ul>"
            f"<div class='cm-muted' style='margin-top:8px'>{fit.n_points} clean measurements"
            + (f" · reduced chi² {fit.chi2_red:.2f}" if np.isfinite(fit.chi2_red) else "") + "</div>"
            + series_html + "</div>",
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
            st.markdown(
                "**Madhava's correction.** Madhava did not simply cut his series for π short: he added a correction "
                "term that estimates the part left out. The engine does the same. After N terms it adds the rest of "
                "the series in closed form. That rest is trapped between two limits we can prove (the ratio of "
                "consecutive terms grows but stays below e<sup>−x</sup>), so every band model carries a guaranteed "
                "bound on its series error. With the same number of terms, the error is 5 to 40 times smaller than "
                "simply cutting the series.",
                unsafe_allow_html=True,
            )
except Exception as _section_error:  # keep the rest of the page alive
    section_failed('the spectrum and temperature', _section_error)

# ------------------------------------------------------------------ does it change?
try:

    st.markdown("### 4 · Does it change? Brightness visit by visit")
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
except Exception as _section_error:  # keep the rest of the page alive
    section_failed('the brightness check', _section_error)

# ------------------------------------------------------------------ is it real?
try:

    st.markdown("<div id='is-it-real'></div>", unsafe_allow_html=True)
    st.markdown("### 5 · Is it real, or a ghost in the detector?")
    st.caption("Consistency checks: they tell you whether the data hang together, not whether a discovery is "
               "confirmed.")
    if real:
        cols = st.columns(len(real["checks"]))
        for col, chk in zip(cols, real["checks"]):
            col.markdown(
                f"<div class='cm-card'><b>{STATUS_ICON[chk['status']]} {chk['name']}</b>"
                f"<div style='margin-top:6px'>{chk['text']}</div></div>",
                unsafe_allow_html=True,
            )
        st.caption("Indicators of consistency, not confirmation. Positions are measured by centroiding near the "
                   "catalogue prediction, so the motion check tests agreement with the catalogue; fitting the motion "
                   "freely from the images is a next step. A real discovery needs follow-up by astronomers.")
    else:
        st.caption("No aligned images, so the checks cannot run.")
except Exception as _section_error:  # keep the rest of the page alive
    section_failed('the consistency checks', _section_error)

# ------------------------------------------------------------------ human scale
try:

    st.markdown("### 6 · On a human scale")
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
except Exception as _section_error:  # keep the rest of the page alive
    section_failed('the human-scale cards', _section_error)

# ------------------------------------------------------------------ data
try:

    st.markdown("### 7 · The data")
    if rows:
        import pandas as pd

        df = pd.DataFrame(rows)
        show = ["mjd", "detector", "wavelength_um", "bandwidth_um", "flux_ujy", "err_ujy", "snr", "hard_flag",
                "soft_flag", "url"]
        df = df[[c for c in show if c in df.columns]]
        with st.expander(f"All {len(df)} measurements"):
            st.dataframe(df, use_container_width=True, height=300,
                         column_config={"url": st.column_config.LinkColumn("original SPHEREx file (IRSA)")})
            st.caption("Every row links to the original SPHEREx image at NASA/IPAC IRSA from which it was measured.")
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
                "Object": v["name"] + (" (extra)" if v.get("extra") else ""),
                "SPHEREx images": v["images"],
                "Visits": v["visits"],
                "Moved (measured)": f"{v['moved_measured']:.1f}\"" if v["moved_measured"] is not None else "—",
                "Moved (catalogue)": f"{v['moved_predicted']:.1f}\"" if v["moved_predicted"] is not None else "—",
                "Found with no catalogue": (f"{v['free_rate']:.2f}\"/yr, {v['free_pa']:.0f}° ({v['free_status']})"
                                           if v.get("free_rate") else "—"),
                "Catalogue motion": f"{v['catalogue_rate']:.2f}\"/yr, {v['catalogue_pa']:.0f}°",
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
except Exception as _section_error:  # keep the rest of the page alive
    section_failed('the data table', _section_error)

st.divider()
st.markdown(
    "<div class='cm-muted'>Cold Movers · NASA Space Apps Challenge 2026 · team from Honduras. "
    "Open source (MIT): <a href='https://github.com/WilmerGaspar/cold-movers' target='_blank'>GitHub</a>.<br>"
    "This publication makes use of data products from the Spectro-Photometer for the History of the Universe, "
    "Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory "
    "and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration. "
    "This research has made use of the NASA/IPAC Infrared Science Archive; of data from the ESA mission Gaia, "
    "processed by the Gaia DPAC; and of the SIMBAD database and the Sesame name resolver (CDS, Strasbourg). "
    "Aladin Lite and WiseView are only linked as external pages. Full list with licences: "
    "<a href='https://github.com/WilmerGaspar/cold-movers/blob/main/DATA_AND_RESOURCES.md' target='_blank'>"
    "DATA_AND_RESOURCES.md</a>.<br>"
    "How we built it, including AI use: see the README. Not an official NASA product.</div>",
    unsafe_allow_html=True,
)
if st.session_state.get("_problems"):
    st.caption("Parts that could not run on this page (logged for the team): "
               + "; ".join(dict.fromkeys(st.session_state["_problems"])))
