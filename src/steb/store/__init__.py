"""Persistence layer: records, metadata, and search indexes kept in sync.

Planned responsibility (Phases 1, 3 and 4): the SQLite store as source of truth for error records,
fixes and metadata; the BM25 index and the vector index; and the sync logic that keeps all three
consistent across inserts, updates (e.g. unresolved -> resolved) and deletes.
"""
