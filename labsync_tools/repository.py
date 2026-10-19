"""The repository interface every LabSync tool uses for data access.

C3 Code implements this on C3 Types; `memory_repo.InMemoryRepository` is the
local implementation. Records are plain dicts keyed by the id field below.
Record kinds match the entity names in docs/05 (plus a few app records).
"""
from typing import Dict, List, Optional

try:  # Python 3.8+
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object

# kind -> id field. Reference kinds are seeded from data_gen/out; app kinds are written by tools.
ID_FIELDS = {
    # reference / seed
    "Department": "department_id", "Lab": "lab_id", "Person": "person_id", "Instrument": "instrument_id",
    "Room": "room_id", "Vendor": "vendor_id", "SupplySku": "sku_id", "Stock": "stock_id",
    "MaintenanceWindow": "maintenance_id", "FundingHint": "funding_hint_id", "Policy": "policy_id",
    "WeeklyDemand": "demand_id",
    # calendar
    "Booking": "booking_id", "RoomReservation": "reservation_id",
    # app records
    "ExperimentPlan": "plan_id", "ReservationProposal": "proposal_id", "Approval": "approval_id",
    "OrderProposal": "order_id", "DepartmentInsight": "insight_id", "ForecastRun": "forecast_run_id",
    "AuditEvent": "audit_id", "CommitReceipt": "idempotency_key", "Notification": "notification_id",
    "AgentRun": "run_id",
}


class CommitWriteError(Exception):
    """Raised by `apply_write` when a single write cannot be applied (e.g. version mismatch)."""


class Repository(Protocol):
    """Storage contract. Every method takes and returns JSON-serializable dicts."""

    def now(self) -> str:
        """Current time as an ISO 8601 string with offset (the scenario clock in the demo)."""

    def next_id(self, prefix: str) -> str:
        """A new unique id starting with `prefix` (deterministic in the demo)."""

    def list_records(self, kind: str) -> List[Dict]:
        """All records of `kind` (copies; callers may not mutate storage through them)."""

    def get_record(self, kind: str, record_id: str) -> Optional[Dict]:
        """One record by id, or None."""

    def save_record(self, kind: str, record: Dict) -> Dict:
        """Insert or replace a record (id taken from ID_FIELDS[kind]). Returns the stored copy."""

    def apply_write(self, write: Dict) -> None:
        """Apply one planned booking write from labsync_core.commit.plan_commit.

        write = {"op": "create"|"update"|"delete", "entity": "Booking"|"RoomReservation",
                 "id", "expected_version"?, "before", "after"}.
        Must reject an update whose stored version != expected_version (raise CommitWriteError).
        """

    def reset_to_seed(self, empty_calendar=None) -> None:
        """Demo sandbox only: restore the canonical `imaging_tuesday_v1` seed exactly (docs/03).
        empty_calendar=True drops the seeded bookings and room reservations; None keeps the last choice."""
