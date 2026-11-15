"""Headless smoke test of the Streamlit app (runs on GitHub Actions).

Loads the app once per challenge object and reports any exception.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamlit.testing.v1 import AppTest  # noqa: E402

from coldmovers.targets import ALL_EXAMPLES  # noqa: E402

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
failed = 0

# The challenge gives WISE 0855 as "08h55m10.831s, -7d14m42.53s": every way a judge might paste it must work.
from coldmovers.targets import parse_coordinates  # noqa: E402

WISE_RA, WISE_DEC = 133.7951292, -7.2451472
for text in ("08h55m10.831s -7d14m42.53s", "08h55m10.831s, -7d14m42.53s", "08:55:10.831 -07:14:42.53",
             "8 55 10.831 -7 14 42.53", "133.7951292 -7.2451472", "133.7951292, -7.2451472"):
    try:
        ra, dec = parse_coordinates(text)
        ok = abs(ra - WISE_RA) < 1e-5 and abs(dec - WISE_DEC) < 1e-5
    except Exception as exc:
        ok, ra, dec = False, exc, ""
    print(f"coordinates {text!r}: {'OK' if ok else 'FAILED'} -> {ra} {dec}")
    failed += 0 if ok else 1
for key in ALL_EXAMPLES:
    try:
        at = AppTest.from_file(APP, default_timeout=300)
        try:
            at.query_params["object"] = key
        except Exception:
            print(f"{key}: (query params not supported by this AppTest; testing the default object)")
        at.run()
        if at.exception:
            failed += 1
            print(f"{key}: EXCEPTION")
            for e in at.exception:
                print("   ", e.value)
                print("   ", "\n    ".join(str(s) for s in e.stack_trace[-12:]))
        else:
            heads = [m.value for m in at.markdown if str(m.value).startswith("###")]
            if len(heads) < 6:
                failed += 1
                print(f"{key}: MISSING SECTIONS, only {len(heads)} found")
            broken = [w.value for w in at.warning if "could not be shown" in str(w.value)]
            broken += [c.value for c in at.caption if "Parts that could not run" in str(c.value)]
            if broken:
                failed += 1
                print(f"{key}: SECTION FAILED: {broken}")
            if not any("What am I looking at?" in str(m.value) for m in at.markdown):
                failed += 1
                print(f"{key}: the plain-words panel is missing")
            # Difference view with every assistant layer on
            at.radio(key="view_mode").set_value("Difference from the first visit").run()
            if at.exception or any("could not be shown" in str(w.value) for w in at.warning):
                failed += 1
                print(f"{key}: DIFFERENCE VIEW FAILED {[e.value for e in at.exception]}")
            at.radio(key="view_mode").set_value("Sum of all visits").run()
            if at.exception or any("could not be shown" in str(w.value) for w in at.warning):
                failed += 1
                print(f"{key}: SUM VIEW FAILED {[e.value for e in at.exception]}")
            print(f"{key}: OK  sections={heads}  errors={[e.value for e in at.error]}  warnings={[w.value for w in at.warning]}")
    except Exception:
        failed += 1
        print(f"{key}: CRASH\n{traceback.format_exc()}")
print("SMOKE", "FAILED" if failed else "PASSED")
sys.exit(1 if failed else 0)
