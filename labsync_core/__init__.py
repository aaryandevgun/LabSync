"""LabSync business logic: pure functions over plain Python data.

No C3 imports, no I/O, no LLM calls. Inputs are dicts (CSV-shaped rows work
directly: ISO timestamps, `;`-joined lists and "true"/"false" are accepted);
outputs are JSON-serializable dicts and lists.
"""
