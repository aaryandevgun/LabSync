"""Shared fixtures: the generated imaging_tuesday_v1 CSVs as lists of dicts."""
import csv
import os

import pytest

from data_gen.generate import DEFAULT_OUT

DEMO_WEEK = "2026-11-02"


def _read(name):
    with open(os.path.join(DEFAULT_OUT, name + ".csv"), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="session")
def seed():
    d = {name: _read(name) for name in [
        "ilab_style_instrument_bookings", "room_schedule_export", "purchasing_export", "weekly_instrument_demand",
        "persons", "instruments", "rooms", "supply_skus", "stock", "maintenance_windows", "policies", "labs"]}
    d["bookings"] = d.pop("ilab_style_instrument_bookings")
    d["room_bookings"] = d.pop("room_schedule_export")
    d["orders"] = d.pop("purchasing_export")
    d["demand"] = d.pop("weekly_instrument_demand")
    d["persons_by_id"] = {p["person_id"]: p for p in d["persons"]}
    d["instruments_by_id"] = {i["instrument_id"]: i for i in d["instruments"]}
    d["rooms_by_id"] = {r["room_id"]: r for r in d["rooms"]}
    d["skus_by_id"] = {s["sku_id"]: s for s in d["supply_skus"]}
    return d
