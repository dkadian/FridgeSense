"""Data access. Every function takes an open sqlite3 connection as its first
argument so callers own the transaction boundary and tests can use :memory:."""
from . import events, items, users  # noqa: F401
