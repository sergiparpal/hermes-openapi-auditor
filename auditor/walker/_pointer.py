"""Pointer utilities and null-safe coercions used by the walker.

RFC 6901 escapes plus a pair of "treat None like an empty container"
helpers that keep the rest of the walker pleasant to write.
"""

from __future__ import annotations

from typing import Any


def encode_pointer_segment(segment: Any) -> str:
    """RFC 6901 escape a single pointer segment.

    Accepts any value so the caller doesn't have to coerce YAML dict
    keys that PyYAML may have parsed as non-strings (e.g. bare ``on:``
    becomes ``True`` under YAML 1.1, bare ``42:`` becomes ``int``).
    """
    return str(segment).replace("~", "~0").replace("/", "~1")


def as_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` unchanged if it's a dict, else an empty dict.

    Used to make every traversal site null-safe in the common case where
    a YAML key is present but its value is ``null`` (e.g. ``paths:`` on a
    line by itself), which would otherwise crash ``.items()``.
    """
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Return ``value`` unchanged if it's a list, else an empty list."""
    return value if isinstance(value, list) else []
