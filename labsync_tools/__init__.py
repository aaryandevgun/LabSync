"""LabSync agent tools: JSON in, JSON out, thin wrappers over labsync_core.

Data access goes through `repository.Repository`; `memory_repo.InMemoryRepository`
is the local implementation, and C3 Code writes the C3-backed one.
"""
