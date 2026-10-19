"""File-backed repository: state survives a restart; reset restores the seed."""
import copy
import json

from labsync_app.store import FileRepository
from labsync_tools import tools as T
from labsync_tools.memory_repo import InMemoryRepository

from tests.tools.helpers import CANONICAL_GOAL, authorize_owner_move


def test_committed_state_survives_restart(tmp_path):
    path = str(tmp_path / "state.json")
    repo = FileRepository(path)
    _, proposal_id = authorize_owner_move(repo, copy.deepcopy(CANONICAL_GOAL))
    receipt = T.booking_commit_approved(repo, "morgan", proposal_id, "k")["receipt"]
    reopened = FileRepository(path)
    assert reopened.get_record("Booking", "bk_chen_confocal")["start_local"] == "2026-11-03T13:30:00-06:00"
    assert reopened.get_record("CommitReceipt", "k")["receipt"] == receipt
    assert reopened.list_records("AuditEvent") == repo.list_records("AuditEvent")
    again = T.booking_commit_approved(reopened, "morgan", proposal_id, "k")
    assert again["replayed"] and again["receipt"] == receipt  # idempotent across restarts
    assert reopened.next_id("x") not in {a["approval_id"] for a in reopened.list_records("Approval")}


def test_ids_never_repeat_after_restart(tmp_path):
    path = str(tmp_path / "state.json")
    first = FileRepository(path).next_id("plan")
    assert FileRepository(path).next_id("plan") != first


def test_reset_restores_seed_and_overwrites_file(tmp_path):
    path = str(tmp_path / "state.json")
    repo = FileRepository(path)
    authorize_owner_move(repo, copy.deepcopy(CANONICAL_GOAL))
    repo.reset_to_seed()
    fresh = InMemoryRepository()
    reopened = FileRepository(path)
    for kind in ("Booking", "Approval", "ReservationProposal", "AuditEvent"):
        assert reopened.list_records(kind) == fresh.list_records(kind)


def test_rejects_a_foreign_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"format": "something-else"}))
    try:
        FileRepository(str(path))
    except ValueError as exc:
        assert "not a LabSync state file" in str(exc)
    else:
        raise AssertionError("expected ValueError")
