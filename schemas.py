"""Tool schemas — the OpenAI function-calling shapes the LLM reads.

Schemas live in their own module per the official Hermes plugin convention.

Enumerated values and defaults are derived from
:mod:`hermes_openapi_auditor.auditor.model` so the LLM-facing schema and
the runtime validator in :mod:`hermes_openapi_auditor.tools` cannot drift.
"""

from __future__ import annotations

from typing import Any

from .auditor.model import (
    DEFAULT_FORMAT,
    DEFAULT_PROFILE,
    DEFAULT_THRESHOLD,
    OUTPUT_FORMATS,
    PROFILE_NAMES,
    SEVERITY_LEVELS,
)

AUDIT_OPENAPI_SPEC: dict[str, Any] = {
    "name": "audit_openapi_spec",
    "description": (
        "Audit an OpenAPI/Swagger spec (2.0, 3.0, or 3.1) for quality issues. "
        "Returns a prioritized list of findings covering missing descriptions, "
        "ambiguous types, missing examples, overly permissive additionalProperties, "
        "and undocumented error codes. Use this whenever a user asks to review, "
        "lint, or check the quality of an OpenAPI/Swagger spec file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Absolute or relative path to the OpenAPI/Swagger file (.json, .yaml, or .yml)."
                ),
            },
            "profile": {
                "type": "string",
                "enum": list(PROFILE_NAMES),
                "default": DEFAULT_PROFILE,
                "description": (
                    "Audit profile. 'public' is strictest; 'internal' relaxes "
                    "cosmetic issues; 'agent-consumed' prioritizes signals that "
                    "matter for LLM function calling."
                ),
            },
            "severity_threshold": {
                "type": "string",
                "enum": list(SEVERITY_LEVELS),
                "default": DEFAULT_THRESHOLD,
                "description": "Minimum severity to include in the output.",
            },
            "format": {
                "type": "string",
                "enum": list(OUTPUT_FORMATS),
                "default": DEFAULT_FORMAT,
                "description": (
                    "Output format. 'json' returns a structured findings list "
                    "(best for agent iteration); 'markdown' returns a human-"
                    "readable report wrapped in a JSON envelope."
                ),
            },
        },
        "required": ["path"],
    },
}
