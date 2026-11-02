"""Ingestion pipeline: turn raw error text into clean, deduplicated records.

Planned responsibility (Phases 1 and 3): parsers for captured errors, Stack Overflow Q&A and
GitHub issues; secret redaction (only redacted text is ever stored or embedded); normalization
(strip paths, usernames, line numbers, addresses, UUIDs, timestamps, temp names); fingerprinting
(exception type, message template, user vs library frames); content hashing, deduplication with
occurrence counts, and incremental update / delete handling.
"""
