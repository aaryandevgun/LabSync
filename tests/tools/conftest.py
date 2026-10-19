"""Fixtures for tool tests: a fresh in-memory repository and the canonical Moreno request."""
import copy

import pytest

from labsync_tools.memory_repo import InMemoryRepository

from .helpers import CANONICAL_GOAL


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def goal():
    return copy.deepcopy(CANONICAL_GOAL)
