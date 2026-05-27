"""Internal audit engine.

The :mod:`auditor` package contains the pure-Python implementation of the
OpenAPI quality checks. It is independent of Hermes — every public symbol
uses ordinary Python types and raises ordinary Python exceptions. The
Hermes-facing wrapper in :mod:`hermes_openapi_auditor.tools` is responsible
for translating to/from the Hermes handler protocol.
"""

from __future__ import annotations
