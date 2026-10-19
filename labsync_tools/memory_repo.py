"""In-memory Repository loaded from the data_gen CSVs. Local test bed and demo backup."""
import copy
import csv
import os
from datetime import timedelta

from labsync_core.values import as_bool, as_num, iso, to_dt

from .repository import ID_FIELDS, CommitWriteError

DEFAULT_SEED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_gen", "out")

SEED_FILES = {
    "Department": "departments.csv", "Lab": "labs.csv", "Person": "persons.csv", "Instrument": "instruments.csv",
    "Room": "rooms.csv", "Vendor": "vendors.csv", "SupplySku": "supply_skus.csv", "Stock": "stock.csv",
    "MaintenanceWindow": "maintenance_windows.csv", "FundingHint": "funding_hints.csv", "Policy": "policies.csv",
    "WeeklyDemand": "weekly_instrument_demand.csv", "Booking": "ilab_style_instrument_bookings.csv",
    "RoomReservation": "room_schedule_export.csv", "OrderProposal": "purchasing_export.csv",
}
SCENARIO_NOW = "2026-10-28T10:00:00-05:00"
CALENDAR_KINDS = ("Booking", "RoomReservation")


def _load_seed(seed_dir):
    data = {kind: {} for kind in ID_FIELDS}
    for kind, name in SEED_FILES.items():
        with open(os.path.join(seed_dir, name), newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if kind == "WeeklyDemand":
                    row["demand_id"] = "%s_%s" % (row["resource_id"], row["week_start"])
                if kind == "RoomReservation":
                    row["resource_id"] = row["room_id"]
                if kind in ("Booking", "RoomReservation"):  # typed like the rows commit writes
                    row["version"] = int(as_num(row.get("version"), 1))
                    if "flexible" in row:
                        row["flexible"] = as_bool(row["flexible"])
                data[kind][row[ID_FIELDS[kind]]] = row
    return data


class InMemoryRepository:
    """Dict-backed Repository with a deterministic clock and ids.

    `fail_on_write` (a write index, 0-based, counted across the repository's life) makes
    `apply_write` raise, to exercise partial-commit compensation in tests.
    """

    def __init__(self, seed_dir=DEFAULT_SEED_DIR, now=SCENARIO_NOW):
        self._seed_dir = seed_dir
        self._start = now
        self.empty_calendar = False
        self.reset_to_seed()

    def reset_to_seed(self, empty_calendar=None):
        """Restore the exact canonical seed (docs/03 demo reset). `empty_calendar` drops every seeded
        instrument booking and room reservation (people, instruments, stock and orders stay), for a
        simple booking demo; it sticks for later resets until changed."""
        if empty_calendar is not None:
            self.empty_calendar = bool(empty_calendar)
        self._data = _load_seed(self._seed_dir)
        if self.empty_calendar:
            for kind in CALENDAR_KINDS:
                self._data[kind] = {}
        self._clock = to_dt(self._start)
        self._counter = 0
        self._writes = 0
        self.fail_on_write = None

    # ---- Repository protocol ----
    def now(self):
        self._clock += timedelta(seconds=1)  # strictly increasing timestamps keep audit order stable
        return iso(self._clock)

    def next_id(self, prefix):
        self._counter += 1
        return "%s_%04d" % (prefix, self._counter)

    def list_records(self, kind):
        return [copy.deepcopy(r) for r in self._data[kind].values()]

    def get_record(self, kind, record_id):
        row = self._data[kind].get(record_id)
        return copy.deepcopy(row) if row is not None else None

    def save_record(self, kind, record):
        record = copy.deepcopy(record)
        self._data[kind][record[ID_FIELDS[kind]]] = record
        return copy.deepcopy(record)

    def apply_write(self, write):
        index = self._writes
        self._writes += 1
        if self.fail_on_write is not None and index == self.fail_on_write:
            raise CommitWriteError("injected failure on write %d" % index)
        kind = write.get("entity", "Booking")
        table = self._data[kind]
        if write["op"] == "update":
            row = table.get(write["id"])
            if row is None or as_num(row.get("version"), 1) != write["expected_version"]:
                raise CommitWriteError("version mismatch on %s" % write["id"])
            row.update(copy.deepcopy(write["after"]))
        elif write["op"] == "create":
            if write["id"] in table:
                raise CommitWriteError("duplicate id %s" % write["id"])
            row = copy.deepcopy(write["after"])
            row[ID_FIELDS[kind]] = write["id"]
            if kind == "RoomReservation":
                row["room_id"] = row["resource_id"]
            table[write["id"]] = row
        elif write["op"] == "delete":
            table.pop(write["id"], None)
        else:
            raise CommitWriteError("unknown op %s" % write["op"])
