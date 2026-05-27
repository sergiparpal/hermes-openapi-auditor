"""Tool schemas — the OpenAI function-calling shapes the LLM reads.

Schemas live in their own module per the official Hermes plugin convention.
"""

from __future__ import annotations

from typing import Any

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
                "enum": ["public", "internal", "agent-consumed"],
                "default": "agent-consumed",
                "description": (
                    "Audit profile. 'public' is strictest; 'internal' relaxes "
                    "cosmetic issues; 'agent-consumed' prioritizes signals that "
                    "matter for LLM function calling."
                ),
            },
            "severity_threshold": {
                "type": "string",
                "enum": ["info", "warning", "error"],
                "default": "warning",
                "description": "Minimum severity to include in the output.",
            },
            "format": {
                "type": "string",
                "enum": ["json", "markdown"],
                "default": "json",
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
