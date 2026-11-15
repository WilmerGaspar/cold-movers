from coldmovers.validation import motion_verdict, temperature_verdict


def test_confirmed_needs_the_search_to_confirm():
    free = {"confirmed": True, "detectors": [5, 6], "significance": 9.1}
    assert motion_verdict(free, 2, 10.4, 1.07)[0] == "CONFIRMED"


def test_one_detector_or_a_pulled_centroid_is_only_a_candidate():
    assert motion_verdict({"confirmed": False, "detectors": [5], "significance": 6.0}, 5, 8.2, 1.0)[0] == "CANDIDATE"
    pulled = {"confirmed": False, "detectors": [2, 3], "significance": 7.0, "pulled_by_neighbour": True}
    verdict, why = motion_verdict(pulled, 5, 8.2, 1.0)
    assert verdict == "CANDIDATE" and "pull" in why


def test_untrusted_field_is_inconclusive_never_confirmed():
    assert motion_verdict(None, 0, 0.02, 1.0)[0] == "INCONCLUSIVE"
    assert motion_verdict(None, 1, 10.0, 1.0)[0] == "INCONCLUSIVE"


def test_not_detected_says_whether_that_was_expected():
    verdict, why = motion_verdict(None, 6, 1.05, 1.0)
    assert verdict == "NOT DETECTED" and "as expected" in why
    verdict, why = motion_verdict(None, 6, 10.0, 1.0)
    assert verdict == "NOT DETECTED" and "miss" in why


def test_temperature_verdicts():
    assert temperature_verdict("green")[0] == "MEASURED"
    assert temperature_verdict("yellow")[0] == "MEASURED WITH CAVEATS"
    assert temperature_verdict("red")[0] == "INCONCLUSIVE"


def test_one_pixel_scale_everywhere():
    # The sky grid (movie, spherex) and the measurements (checks, movers, assistant) must use the same scale.
    from coldmovers import checks, spherex

    assert checks.PIXEL_ARCSEC == spherex.PIXEL_ARCSEC == 6.15


def test_flux_unit_conversion():
    # 1 MJy/sr over a solid angle of 1e-12 sr is 1 microjansky.
    from coldmovers import photometry

    assert photometry.UJY_PER_MJY * 1e-12 == 1.0
