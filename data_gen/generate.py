"""Generate the deterministic `imaging_tuesday_v1` synthetic CSVs.

Usage:  python -m data_gen.generate [--out DIR]

Outputs export-style CSVs (instrument bookings shaped like an iLab-style
export, a room-scheduling export, a purchasing export) plus reference tables.
Column names are our own invention; real iLab export formats are unverified.
"""
import argparse
import csv
import json
import os
import random
from datetime import datetime, timedelta

from . import reference as ref
from . import schedule as sched
from .scenario import (DEMO_WEEK_MONDAY, HISTORY_WEEK_MONDAYS, PROVENANCE, RANDOM_SEED, SCENARIO_ID,
                       SCENARIO_NOW, STAFFED_HOURS_PER_WEEK, TZ, TZ_NAME, CANONICAL_REQUEST,
                       iso_local, iso_utc, local_dt, week_days)

DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "out")

BOOKING_COLUMNS = ["booking_id", "resource_id", "resource_name", "resource_type", "lab_id", "lab_name", "user_id",
                   "start_local", "end_local", "start_utc", "end_utc", "session_hours", "status", "flexible",
                   "version", "week_start", "provenance"]
ROOM_COLUMNS = ["reservation_id", "room_id", "room_name", "lab_id", "user_id", "start_local", "end_local",
                "start_utc", "end_utc", "status", "purpose", "provenance"]
PURCHASING_COLUMNS = ["order_id", "line_id", "lab_id", "requester_id", "sku_id", "vendor_id", "quantity",
                      "unit_price_usd", "shipping_usd", "state", "created_local", "need_by_date", "ship_to",
                      "funding_hint_id", "provenance"]
DEMAND_COLUMNS = ["week_start", "resource_id", "requested_hours", "booked_hours", "staffed_hours",
                  "maintenance_hours", "provenance"]

# Seeded purchasing export. The Patel anti-GFP order is the planted pooling partner;
# Moreno's 2 packs are created by the lab flow, not seeded. Others are decoys.
PURCHASE_ORDERS = [
    # order_id, lab, requester, sku, qty, state, created, need_by, ship_to, funding_hint
    ("po_patel_antigfp", "lab_patel", "patel_mgr", "ANTI_GFP_100", 3, "awaiting_lab_approval",
     "2026-10-26 14:00", "2026-11-04", "north_bio_receiving", ""),
    # Decoy: same SKU tier would apply, but ships to a different location -> not poolable.
    ("po_patel_tips", "lab_patel", "jordan_patel", "TIPS_200", 4, "awaiting_fund_approval",
     "2026-10-23 11:00", "2026-11-06", "north_bio_receiving", ""),
    ("po_rivera_tips", "lab_rivera", "riley_rivera", "TIPS_200", 6, "awaiting_lab_approval",
     "2026-10-27 09:30", "2026-11-06", "south_annex_receiving", ""),
    # Decoy: single lab, nothing to pool with in the window.
    ("po_chen_dapi", "lab_chen", "chen_owner", "DAPI_1ML", 1, "awaiting_lab_approval",
     "2026-10-27 15:00", "2026-11-05", "north_bio_receiving", ""),
    # Decoy: same SKU as Chen but outside the 7-day window and already approved (locked).
    ("po_rivera_dapi", "lab_rivera", "rivera_mgr", "DAPI_1ML", 1, "approved_request",
     "2026-09-30 10:00", "2026-10-09", "north_bio_receiving", ""),
    ("po_rivera_dnakit", "lab_rivera", "rivera_mgr", "DNA_KIT", 2, "awaiting_fund_approval",
     "2026-10-22 13:00", "2026-11-09", "north_bio_receiving", "fh_rivera_award_end"),
    ("po_rivera_plates", "lab_rivera", "riley_rivera", "PCR_PLATES", 3, "approved_request",
     "2026-10-20 10:00", "2026-10-28", "north_bio_receiving", ""),
]


def _index(rows, key):
    return {row[key]: row for row in rows}


LABS = _index(ref.LABS, "lab_id")
PERSONS = _index(ref.PERSONS, "person_id")
INSTRUMENTS = _index(ref.INSTRUMENTS, "instrument_id")
ROOMS = _index(ref.ROOMS, "room_id")
SKUS = _index(ref.SUPPLY_SKUS, "sku_id")


def qualified_users(required):
    return sorted(p["person_id"] for p in ref.PERSONS
                  if p["lab_id"] and set(required) <= set(p["qualifications"]))


def _maintenance_blocks():
    blocks = {}
    for mw in ref.MAINTENANCE_WINDOWS:
        start = datetime.fromisoformat(mw["start_local"])
        end = datetime.fromisoformat(mw["end_local"])
        blocks.setdefault(mw["resource_id"], {})[start.date()] = (start.hour * 60 + start.minute,
                                                                    end.hour * 60 + end.minute)
    return blocks


def _status_for(start_dt):
    return "completed" if start_dt < SCENARIO_NOW else "confirmed"


def _booking_row(inst_id, day, start_min, end_min, user_id, flexible, booking_id, monday):
    inst = INSTRUMENTS[inst_id]
    lab_id = PERSONS[user_id]["lab_id"]
    start = local_dt(day, sched.hhmm(start_min))
    end = local_dt(day, sched.hhmm(end_min))
    if booking_id is None:
        booking_id = "bk_%s_%s_%s" % (inst_id, day.strftime("%Y%m%d"), sched.hhmm(start_min).replace(":", ""))
    return {
        "booking_id": booking_id, "resource_id": inst_id, "resource_name": inst["name"],
        "resource_type": "instrument", "lab_id": lab_id, "lab_name": LABS[lab_id]["name"], "user_id": user_id,
        "start_local": iso_local(start), "end_local": iso_local(end),
        "start_utc": iso_utc(start), "end_utc": iso_utc(end),
        "session_hours": (end_min - start_min) / 60, "status": _status_for(start),
        "flexible": flexible, "version": 1, "week_start": monday.isoformat(), "provenance": PROVENANCE,
    }


def build_bookings(rng):
    blocks = _maintenance_blocks()
    history = sched.history_targets(rng)
    rows = []
    for inst_id in sorted(INSTRUMENTS):
        inst = INSTRUMENTS[inst_id]
        users = qualified_users(inst["required_qualifications"])
        weeks = [(m, history[inst_id][i]) for i, m in enumerate(HISTORY_WEEK_MONDAYS)]
        for monday, hours in weeks:
            for day, s, e in sched.filler_week(rng, monday, hours, inst["buffer_minutes"], blocks.get(inst_id)):
                rows.append(_booking_row(inst_id, day, s, e, rng.choice(users), rng.random() < 0.25, None, monday))
        if inst_id in sched.DEMO_FIXED_INSTRUMENT_SESSIONS:
            for day, s, e, user, flexible, booking_id in sched.demo_fixed(inst_id):
                rows.append(_booking_row(inst_id, day, s, e, user, flexible, booking_id, DEMO_WEEK_MONDAY))
        else:
            hours = sched.DEMO_FILLER_INSTRUMENT_HOURS[inst_id]
            for day, s, e in sched.filler_week(rng, DEMO_WEEK_MONDAY, hours, inst["buffer_minutes"], blocks.get(inst_id)):
                rows.append(_booking_row(inst_id, day, s, e, rng.choice(users), rng.random() < 0.25, None,
                                         DEMO_WEEK_MONDAY))
    rows.sort(key=lambda r: (r["start_utc"], r["resource_id"]))
    return rows, history


def build_room_reservations(rng):
    rows = []
    users = qualified_users(["wet_prep"])

    def add(room_id, day, s, e, user, purpose):
        start = local_dt(day, sched.hhmm(s))
        end = local_dt(day, sched.hhmm(e))
        rows.append({
            "reservation_id": "rr_%s_%s_%s" % (room_id, day.strftime("%Y%m%d"), sched.hhmm(s).replace(":", "")),
            "room_id": room_id, "room_name": ROOMS[room_id]["name"], "lab_id": PERSONS[user]["lab_id"],
            "user_id": user, "start_local": iso_local(start), "end_local": iso_local(end),
            "start_utc": iso_utc(start), "end_utc": iso_utc(end), "status": _status_for(start),
            "purpose": purpose, "provenance": PROVENANCE,
        })

    for room_id in sorted(ROOMS):
        room = ROOMS[room_id]
        for offset, start, end, user, purpose in sched.DEMO_FIXED_ROOM_SESSIONS.get(room_id, []):
            add(room_id, week_days(DEMO_WEEK_MONDAY)[offset], sched._mins(start), sched._mins(end), user, purpose)
        sessions = sched.filler_week(rng, DEMO_WEEK_MONDAY, sched.DEMO_FILLER_ROOM_HOURS[room_id],
                                     room["buffer_minutes"], skip_days=sched.ROOM_FILLER_SKIP_DAYS.get(room_id, ()))
        for day, s, e in sessions:
            add(room_id, day, s, e, rng.choice(users), "General use")
    rows.sort(key=lambda r: (r["start_utc"], r["room_id"]))
    return rows


def build_purchasing():
    rows = []
    for order_id, lab, requester, sku_id, qty, state, created, need_by, ship_to, fh in PURCHASE_ORDERS:
        sku = SKUS[sku_id]
        created_dt = datetime.strptime(created, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        rows.append({
            "order_id": order_id, "line_id": order_id + "_l1", "lab_id": lab, "requester_id": requester,
            "sku_id": sku_id, "vendor_id": sku["vendor_id"], "quantity": qty,
            "unit_price_usd": sku["base_price_usd"], "shipping_usd": sku["shipping_per_order_usd"],
            "state": state, "created_local": iso_local(created_dt), "need_by_date": need_by,
            "ship_to": ship_to, "funding_hint_id": fh, "provenance": PROVENANCE,
        })
    return rows


def build_weekly_demand(rng, bookings, history):
    """History weeks only: requested (latent) vs booked hours, computed from booking rows."""
    booked = {}
    for b in bookings:
        key = (b["week_start"], b["resource_id"])
        booked[key] = booked.get(key, 0) + b["session_hours"]
    rows = []
    for inst_id in sorted(INSTRUMENTS):
        unmet = sched.unmet_hours(rng, inst_id)
        for i, monday in enumerate(HISTORY_WEEK_MONDAYS):
            hours = booked.get((monday.isoformat(), inst_id), 0)
            assert hours == history[inst_id][i], (inst_id, monday, hours)
            rows.append({
                "week_start": monday.isoformat(), "resource_id": inst_id,
                "requested_hours": hours + unmet[i], "booked_hours": hours,
                "staffed_hours": STAFFED_HOURS_PER_WEEK, "maintenance_hours": 0, "provenance": PROVENANCE,
            })
    return rows


def _flatten(rows):
    out = []
    for row in rows:
        flat = {}
        for key, value in row.items():
            if isinstance(value, list):
                value = ";".join(value)
            elif isinstance(value, bool):
                value = "true" if value else "false"
            elif isinstance(value, float) and value.is_integer():
                value = int(value)
            flat[key] = value
        out.append(flat)
    return out


def write_csv(path, rows, columns=None):
    rows = _flatten(rows)
    columns = columns or list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate(out_dir=DEFAULT_OUT):
    """Write every CSV plus scenario.json into `out_dir`. Returns the file names."""
    rng = random.Random(RANDOM_SEED)
    os.makedirs(out_dir, exist_ok=True)
    bookings, history = build_bookings(rng)
    rooms = build_room_reservations(rng)
    demand = build_weekly_demand(rng, bookings, history)
    tables = {
        "ilab_style_instrument_bookings.csv": (bookings, BOOKING_COLUMNS),
        "room_schedule_export.csv": (rooms, ROOM_COLUMNS),
        "purchasing_export.csv": (build_purchasing(), PURCHASING_COLUMNS),
        "weekly_instrument_demand.csv": (demand, DEMAND_COLUMNS),
        "departments.csv": (ref.DEPARTMENTS, None),
        "labs.csv": (ref.LABS, None),
        "persons.csv": (ref.PERSONS, None),
        "instruments.csv": (ref.INSTRUMENTS, None),
        "rooms.csv": (ref.ROOMS, None),
        "vendors.csv": (ref.VENDORS, None),
        "supply_skus.csv": (ref.SUPPLY_SKUS, None),
        "stock.csv": (ref.STOCK, None),
        "maintenance_windows.csv": (ref.MAINTENANCE_WINDOWS, None),
        "funding_hints.csv": (ref.FUNDING_HINTS, None),
        "policies.csv": (ref.POLICIES, None),
    }
    for name, (rows, columns) in tables.items():
        write_csv(os.path.join(out_dir, name), rows, columns)
    scenario = {
        "scenario_id": SCENARIO_ID, "random_seed": RANDOM_SEED, "timezone": TZ_NAME,
        "scenario_now_local": iso_local(SCENARIO_NOW), "demo_week_start": DEMO_WEEK_MONDAY.isoformat(),
        "history_week_starts": [m.isoformat() for m in HISTORY_WEEK_MONDAYS],
        "staffed_hours_per_week": STAFFED_HOURS_PER_WEEK, "staffed_window_local": ["09:00", "17:00"],
        "canonical_request": {"lab_id": "lab_moreno", "requester_id": "morgan", "text": CANONICAL_REQUEST},
        "synthetic": True,
        "note": "All records are synthetic demo data. Column names are not real iLab export formats.",
    }
    with open(os.path.join(out_dir, "scenario.json"), "w", encoding="utf-8") as fh:
        json.dump(scenario, fh, indent=2)
        fh.write("\n")
    return sorted(list(tables) + ["scenario.json"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=DEFAULT_OUT, help="output directory (default: data_gen/out)")
    args = parser.parse_args()
    for name in generate(args.out):
        print(os.path.join(args.out, name))


if __name__ == "__main__":
    main()
