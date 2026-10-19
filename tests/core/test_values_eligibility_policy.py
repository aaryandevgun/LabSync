from datetime import date

import pytest

from labsync_core import eligibility, policy
from labsync_core.values import (add_business_days, as_bool, as_list, as_num, business_days_before, overlaps,
                                 to_dt, violates_buffer)

T = "2026-11-03T%s:00-06:00"


def test_half_open_intervals_touching_do_not_overlap():
    assert not overlaps(T % "10:00", T % "12:00", T % "12:00", T % "13:00")
    assert overlaps(T % "10:00", T % "12:00", T % "11:59", T % "13:00")


def test_buffer_applied_once_between_sessions():
    # T-SCHED-003: 10:00-13:00 then a 13:10 start violates the 15-min buffer; 13:15 is fine.
    assert violates_buffer(T % "10:00", T % "13:00", T % "13:10", T % "14:00", 15)
    assert not violates_buffer(T % "10:00", T % "13:00", T % "13:15", T % "14:00", 15)
    # Symmetric: the earlier session can come second in the call.
    assert not violates_buffer(T % "13:30", T % "15:30", T % "10:00", T % "13:00", 15)


def test_naive_datetimes_rejected_and_utc_z_accepted():
    with pytest.raises(ValueError):
        to_dt("2026-11-03T10:00:00")
    assert to_dt("2026-11-03T16:00:00Z") == to_dt(T % "10:00")


def test_csv_coercions():
    assert as_list("a;b") == ["a", "b"] and as_list("") == [] and as_list(["x"]) == ["x"]
    assert as_bool("true") and not as_bool("false") and as_bool(True)
    assert as_num("40") == 40 and as_num("0.25") == 0.25 and as_num("", 7) == 7


def test_business_days_skip_weekends():
    assert business_days_before(date(2026, 11, 2), 2) == date(2026, 10, 29)
    assert add_business_days(date(2026, 10, 29), 2) == date(2026, 11, 2)


def test_morgan_not_qualified_for_confocal_2(seed):
    morgan = seed["persons_by_id"]["morgan"]
    assert eligibility.check_qualifications(morgan, seed["instruments_by_id"]["confocal_1"])["eligible"]
    result = eligibility.check_qualifications(morgan, seed["instruments_by_id"]["confocal_2"])
    assert result == {"eligible": False, "missing": ["confocal_2_cert"], "code": "NOT_QUALIFIED"}


def test_equivalence_and_capabilities(seed):
    inst = seed["instruments_by_id"]
    assert eligibility.equivalent(inst["confocal_1"], inst["confocal_2"])
    assert not eligibility.equivalent(inst["confocal_1"], inst["microscope_wide_1"])
    assert eligibility.capability_match(inst["microscope_wide_1"], ["gfp_imaging", "confocal_imaging"]) == [
        "confocal_imaging"]


def test_policy_rows_override_defaults(seed):
    merged = policy.policy_map(seed["policies"])
    assert merged["score.weight.meets_preferred_window"] == 50
    assert policy.get([{"key": "pooling.window_days", "value": "3"}], "pooling.window_days") == 3
    assert policy.get({}, "scheduling.max_options") == 3
