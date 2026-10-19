"""File-backed repository: the in-memory repository, saved to a JSON file after every write.

State survives a restart (docs/01: "refreshing preserves committed state"); `reset_to_seed`
restores the canonical seed and overwrites the file. All methods are serialized with a lock so
the web server's threads can share one repository.
"""
import json
import os
import tempfile
import threading

from labsync_core.values import iso, to_dt
from labsync_tools.memory_repo import DEFAULT_SEED_DIR, SCENARIO_NOW, InMemoryRepository

DEFAULT_STATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "var", "labsync_state.json")
FORMAT = "labsync-state-v1"


class FileRepository(InMemoryRepository):
    def __init__(self, path=DEFAULT_STATE, seed_dir=DEFAULT_SEED_DIR, now=SCENARIO_NOW):
        self.path = path
        self._lock = threading.RLock()
        self._loading = True
        super().__init__(seed_dir=seed_dir, now=now)  # loads the seed (reset_to_seed below skips saving)
        self._loading = False
        if os.path.exists(path):
            self._load()
        else:
            self._save()

    # ---- persistence
    def _state(self):
        return {"format": FORMAT, "data": self._data, "clock": iso(self._clock), "counter": self._counter,
                "writes": self._writes, "empty_calendar": self.empty_calendar}

    def _save(self):
        if self._loading:
            return
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".labsync_state.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self._state(), fh)  # keep insertion order: tools list records in that order
        os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written file

    def _load(self):
        with open(self.path, encoding="utf-8") as fh:
            state = json.load(fh)
        if state.get("format") != FORMAT:
            raise ValueError("%s is not a LabSync state file" % self.path)
        self._data = state["data"]
        self._clock = to_dt(state["clock"])
        self._counter = state["counter"]
        self._writes = state["writes"]
        self.empty_calendar = state.get("empty_calendar", False)

    # ---- Repository protocol, locked and saved
    def reset_to_seed(self, empty_calendar=None):
        with self._lock:
            super().reset_to_seed(empty_calendar)
            self._save()

    def now(self):
        with self._lock:
            return super().now()  # saved with the next write; a lost tick only shifts timestamps

    def next_id(self, prefix):
        with self._lock:
            value = super().next_id(prefix)
            self._save()  # ids must never repeat after a restart
            return value

    def list_records(self, kind):
        with self._lock:
            return super().list_records(kind)

    def get_record(self, kind, record_id):
        with self._lock:
            return super().get_record(kind, record_id)

    def save_record(self, kind, record):
        with self._lock:
            out = super().save_record(kind, record)
            self._save()
            return out

    def apply_write(self, write):
        with self._lock:
            try:
                super().apply_write(write)
            finally:
                self._save()

    def transaction(self):
        """Hold the lock across several calls (one tool call from the web server)."""
        return self._lock
