"""The offline mock's keyword fallback for typed requests (not a model; see labsync_app/mock_parse.py)."""
from labsync_app.mock_parse import parse

NOW = "2026-10-28T10:00:00-05:00"  # Wednesday


def p(text):
    return parse(text, "morgan", "lab_moreno", NOW)


def test_instrument_day_time_duration():
    g = p("I need the confocal on Thursday at 2pm for 2 hours")
    assert (g["desiredStart"], g["preferredEnd"]) == ("2026-10-29T14:00:00-05:00", "2026-10-29T16:00:00-05:00")
    assert g["steps"][0]["requiredCapabilities"] == ["confocal_imaging"] and g["steps"][0]["durationMinutes"] == 120


def test_dst_offset_weekday_window_and_supplies():
    g = p("widefield Tuesday afternoon 2 hours for GFP, plus 2 packs of anti-GFP")
    assert (g["desiredStart"], g["preferredEnd"]) == ("2026-11-03T13:00:00-06:00", "2026-11-03T17:00:00-06:00")
    assert g["steps"][0]["requiredCapabilities"] == ["gfp_imaging", "widefield_imaging"]
    assert g["supplies"] == [{"skuId": "ANTI_GFP_100", "quantity": 2, "source": "stated"}]


def test_prep_room_dependency_and_rounding():
    g = p("confocal 100 minutes friday 9am-1pm with prep room")
    assert [s["kind"] for s in g["steps"]] == ["prep_room", "instrument"]
    assert g["steps"][1]["dependsOn"] == ["prep"] and g["steps"][1]["durationMinutes"] == 105


def test_missing_facts_are_listed_not_guessed():
    g = p("confocal next week")
    assert g["desiredStart"] is None and set(g["missingInformation"]) == {"instrument duration", "desiredStart"}
    assert "date is in the past" in p("confocal yesterday 1 hour")["missingInformation"]
    assert p("confocal tuesday 9-10am for 3 hours")["missingInformation"]


def test_supplies_only_and_nothing_recognised():
    assert p("3 boxes of coverslips")["supplies"] == [{"skuId": "COVERSLIP_24", "quantity": 3, "source": "stated"}]
    assert p("3 boxes of coverslips")["steps"] == []
    assert p("hello there") is None
