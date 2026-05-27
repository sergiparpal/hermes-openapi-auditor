# Implementation Plan: `hermes-openapi-auditor`

> **Target executor:** Claude Code CLI (Sonnet, `/effort auto`, prefix complex steps with `think hard`).
> **Estimated effort:** 9–14 hours of focused work.
> **License:** MIT.
> **Python:** 3.11+.
> **Hermes Agent target version:** v0.14.0 (`v2026.5.16`, May 16, 2026) or later.

> **Revision 2 (post-verification against the official `build-a-hermes-plugin` guide):** the plugin contract was corrected in several places where Revision 1 had inferred details from secondary sources. The most consequential changes:
> - `plugin.yaml` has NO `category`, `license`, `homepage`, or `dependencies` fields. It declares `provides_tools` and `provides_hooks` lists instead.
> - The tool handler signature is `(args: dict, **kwargs) -> str` and MUST return a JSON string (never a dict, never raises). See §2.6.1.
> - File layout follows the official 4-file convention: `plugin.yaml`, `__init__.py`, `schemas.py`, `tools.py`.
> - Plugin discovery is automatic from `~/.hermes/plugins/`; there is no `plugins.enabled` allowlist.
> - Hermes target version updated from v0.13.0 to v0.14.0 (latest release).

---

## 0. Document conventions for the agent

- Every phase has explicit **deliverables**, **acceptance criteria**, and **commands to run** before moving on.
- Code samples in this plan are **reference patterns**, not literal copy-paste targets. Adapt as needed but preserve the contracts.
- When in doubt about a Hermes Agent API, **stop and consult** the official guide at https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin rather than guessing. The Hermes plugin surface evolves quickly (808 commits between v0.13.0 and v0.14.0); pin against the installed version.
- Do **not** run `claude init` in the project root. A bespoke `CLAUDE.md` will be added in Phase 7 and must not be overwritten.

---

## 1. Project overview

### 1.1 Goal

Build a Hermes Agent plugin that exposes a single tool, `audit_openapi_spec(path)`, which audits the quality of an OpenAPI/Swagger specification file and returns a prioritized list of quality findings. The plugin targets three OpenAPI versions: **Swagger 2.0**, **OpenAPI 3.0**, and **OpenAPI 3.1**.

### 1.2 Why this plugin exists

LLMs increasingly consume OpenAPI specs as input for function calling (deciding which endpoint to invoke and with what arguments). A spec that passes a classic linter (e.g. Spectral) can still be unusable for function calling because it lacks semantic signals (descriptions, examples, narrow enums, documented error codes). This plugin is **a linter oriented to agent consumption**, not a generic OpenAPI linter.

### 1.3 The five audit rules

| ID | Name | Severity default | Cross-version difficulty |
|---|---|---|---|
| `missing-descriptions` | Operations missing `summary`/`description` | warning | trivial |
| `ambiguous-types` | Parameters/schemas with loose typing | warning | **high** (nullable, type:file, polymorphism vary by version) |
| `missing-examples` | Request/response bodies without examples | warning | **high** (different mechanisms per version) |
| `additional-properties` | `additionalProperties: true` where a closed contract is expected | info | low (3.1 nuance with `unevaluatedProperties`) |
| `undocumented-errors` | Operations with no `4xx`/`5xx` responses | warning | trivial |

---

## 2. Hermes Agent plugin contract (hard requirements)

These are non-negotiable constraints imposed by the host framework. Violating any of them means the plugin will not load or will fail Hermes' quality bar.

### 2.1 Golden rule: do not modify the core

From Hermes' internal `AGENTS.md` (May 2026, Teknium):

> Plugins MUST NOT modify core files (`run_agent.py`, `cli.py`, `gateway/run.py`, `hermes_cli/main.py`, etc.). If a plugin needs a capability the framework doesn't expose, expand the generic plugin surface (new hook, new `ctx` method) — never hardcode plugin-specific logic into core.

For this plugin: **no core changes are required and none must be made.** All functionality fits cleanly within the existing `general` plugin category and the `ctx.register_tool` API.

### 2.2 Plugin discovery and location

Hermes discovers plugins from **three** sources (verified against the official architecture docs):

1. **User scope:** `~/.hermes/plugins/<plugin-name>/`
2. **Project scope:** `.hermes/plugins/<plugin-name>/` (relative to the current working directory)
3. **Pip entry points:** any installed Python package registering an entry point under the `hermes_agent.plugins` group

For this plugin:
- Local development/testing: drop or symlink the plugin into `~/.hermes/plugins/hermes-openapi-auditor/`.
- For pip-based distribution, add to `pyproject.toml`:
  ```toml
  [project.entry-points."hermes_agent.plugins"]
  hermes-openapi-auditor = "hermes_openapi_auditor"
  ```
- Plugin activation is **automatic on discovery**. The plugin appears in Hermes' tool list on next startup. There is no `plugins.enabled` allowlist to manage. (A user can disable a discovered plugin via `hermes plugins disable <name>` if needed.)

### 2.3 Required files

The plugin directory MUST contain at minimum:

| File | Purpose |
|---|---|
| `plugin.yaml` | Manifest declaring name, version, `provides_tools`, `provides_hooks`. See §4.2. |
| `__init__.py` | Entrypoint exposing a top-level `register(ctx)` function. See §4.3. |

The official "Build a Hermes Plugin" guide recommends a **4-file convention** that splits concerns cleanly. This plan follows it:

| File | Purpose |
|---|---|
| `plugin.yaml` | Manifest |
| `__init__.py` | `register()` — wires schemas to handlers |
| `schemas.py` | Tool schemas (the dicts the LLM reads) |
| `tools.py` | Tool handlers (the Python functions that run when called) |

This is a convention, not a hard requirement of the loader — but following it improves readability and matches the patterns used by every example in the official docs.

### 2.4 Plugin type (no `category` field exists)

The `category` field used in earlier drafts of this plan does **not** exist in the real `plugin.yaml` format. The official manifest has no such field. Plugin categorization works by directory placement:

- **General plugins** (tools, hooks, slash commands, CLI commands) — go directly under `plugins/<name>/`. This plugin is a general plugin.
- **Specialized plugin types** (memory providers, context engines, image-gen providers, model providers) — go under `plugins/<type>/<name>/` and implement specific ABCs.

Since `hermes-openapi-auditor` only registers a single tool, it is a **general plugin**, lives directly at `~/.hermes/plugins/hermes-openapi-auditor/`, and follows the build-a-plugin guide (not any of the specialized-type guides).

### 2.5 Entrypoint contract

The plugin's `__init__.py` MUST expose a top-level callable named `register` with this signature:

```python
def register(ctx) -> None:
    """Called once by Hermes' PluginManager at startup.

    `ctx` is a PluginContext instance. The exact import path of its type
    is not documented publicly; do not type-hint it strictly.
    """
```

Inside `register()`, the plugin invokes APIs on `ctx` to register tools, hooks, commands, etc. For this plugin, the only call is `ctx.register_tool(...)`.

### 2.6 Tool registration API

`ctx.register_tool` is called with these keyword arguments (verified against the official "Build a Hermes Plugin" guide):

```python
ctx.register_tool(
    name="audit_openapi_spec",     # tool name exposed to the LLM
    toolset="qa",                  # logical grouping (any string)
    schema=AUDIT_OPENAPI_SPEC,     # full OpenAI function-calling schema dict
    handler=audit_openapi_spec,    # the Python function backing the tool
)
```

Optional kwargs available (used in this plan only for `check_fn`):
- `check_fn: Callable | None` — returning False hides the tool from the model. Useful when an optional dependency is missing.
- `requires_env: list[str] | None` — Hermes will not load the plugin if any of these env vars are absent.

**The schema dict has this shape** (OpenAI function-calling style — `name`, `description`, and `parameters` are siblings inside the schema, NOT separate `register_tool` kwargs):

```python
AUDIT_OPENAPI_SPEC = {
    "name": "audit_openapi_spec",
    "description": "Audit an OpenAPI/Swagger spec for quality issues...",
    "parameters": {
        "type": "object",
        "properties": { ... },
        "required": ["path"],
    },
}
```

### 2.6.1 Handler contract (HARD REQUIREMENTS — verified from official docs)

These are listed as "Common mistakes" in the official build-a-plugin guide. Violating them will break the plugin.

| Rule | Requirement |
|---|---|
| **Signature** | `def handler(args: dict, **kwargs) -> str` — single positional `args` dict, plus `**kwargs` for forward compatibility. Do NOT unpack the schema's properties as named parameters. |
| **Return type** | Always a **JSON string** (use `json.dumps(...)`). Never a dict, never a Python object, never `None`. This applies to success AND error paths alike. |
| **Exceptions** | Handler MUST NOT raise. Catch every exception and return `json.dumps({"error": "..."})` instead. A raised exception will fail the tool call from the model's perspective. |
| **`**kwargs`** | Always accept `**kwargs`. Hermes may pass additional context in future versions; without `**kwargs` the plugin will break on upgrade. |

Example minimal handler shape:

```python
import json

def audit_openapi_spec(args: dict, **kwargs) -> str:
    try:
        path = args.get("path")
        if not path:
            return json.dumps({"error": "path argument is required"})
        # ... do the work ...
        return json.dumps({"version": "3.0", "findings": [...]})
    except Exception as e:
        return json.dumps({"error": f"audit failed: {e}"})
```

### 2.7 Dependencies policy

- Python dependencies are declared in **`pyproject.toml` only**. There is no `dependencies` field in the official `plugin.yaml` schema (a former draft of this plan included one — it was incorrect and has been removed).
- Prefer stdlib where possible. Acceptable external dependencies for this plugin: `PyYAML`, `jsonschema>=4.18`, `openapi-spec-validator>=0.7`, `jsonref>=1.1`.
- **No network calls during runtime.** The plugin audits local files only.
- If the plugin needed a secret (API key) at load time, the official mechanism is `requires_env:` in `plugin.yaml` (rich format supports `name`, `description`, `url`, `secret`). This plugin needs no secrets, so `requires_env:` is omitted.

### 2.8 Privilege and security expectations

- Plugins run with the same privileges as the Hermes agent itself. Operator review is the line of defense.
- The plugin reads the user-provided spec path. It MUST NOT read any other files, write outside `/tmp`, or make network calls. Operator trust is preserved by being narrow.

### 2.9 Version pinning (recommendation, not enforced)

Hermes is under heavy development. The catalog explicitly warns: "APIs stable today may change; pin version." Tested against **Hermes Agent v0.14.0** (release tag `v2026.5.16`, May 16, 2026 — the "Foundation Release"). Document this clearly in the README.

Notable in v0.14.0 that matters for plugin authors:
- `ctx.llm` shipped officially (#23194) — plugins can call any LLM via the active provider/credentials without manual client wiring. Not used by this plugin (audit is static), but worth knowing.
- `tool_override` flag added (#26759) — lets a plugin replace a built-in tool. Not used here.
- Hermes is now a real PyPI package: `pip install hermes-agent && hermes`.

> **Note:** The `requires_hermes_version` / `hermes_requires` field at plugin-manifest level was investigated in May 2026 (catalog Rev 8) and confirmed **not to exist** for plugins (it exists only for `profile_distribution`). Do not add such a field to `plugin.yaml`.

---

## 3. Functional requirements

### 3.1 The tool

A single tool with this contract:

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | string (required) | — | Absolute or relative path to an OpenAPI/Swagger file (`.json`, `.yaml`, `.yml`). |
| `profile` | enum: `public`, `internal`, `agent-consumed` | `agent-consumed` | Adjusts which rules fire and at what severity. |
| `severity_threshold` | enum: `info`, `warning`, `error` | `warning` | Minimum severity to include in output. |
| `format` | enum: `json`, `markdown` | `json` | Output format. JSON for agent iteration; markdown for human display. |

**Return shape (always a JSON string per Hermes' handler contract — see §2.6.1):**

When `format=json` (default), the JSON payload has this shape:

```json
{
  "version": "3.0",
  "source": "/path/to/spec.yaml",
  "findings": [
    {
      "rule_id": "missing-examples",
      "severity": "warning",
      "message": "Response 200 (application/json) of GET /pets has no example.",
      "path": "#/paths/~1pets/get/responses/200/content/application~1json",
      "operation": "GET /pets",
      "suggestion": "Add `example` or `examples` to the mediaType."
    }
  ]
}
```

When `format=markdown`, the JSON envelope wraps the markdown string:

```json
{"version": "3.0", "source": "/path/to/spec.yaml", "markdown": "## Findings\n\n..."}
```

On any error, the return value is always still a JSON string:

```json
{"error": "spec at '/path/to/spec.yaml' could not be parsed: ..."}
```

The handler must never return a dict, an object, or `None` — only a JSON-serialized string. The agent receives the string and parses it as needed.

### 3.2 Multi-version support

The plugin MUST correctly audit all three of:
- Swagger 2.0
- OpenAPI 3.0.x (any patch version)
- OpenAPI 3.1.x (any patch version)

Specs mixing fields from multiple versions (e.g. `swagger: "2.0"` alongside a `components` object) MUST be rejected with a clear error.

### 3.3 Profile semantics

| Profile | Intent |
|---|---|
| `public` | Strictest. Missing examples and descriptions are errors, not warnings. Use for public APIs. |
| `internal` | Relaxed. Cosmetic issues downgraded to info. Use for internal-only APIs. |
| `agent-consumed` (default) | Prioritizes signals that matter for LLM function calling. Missing descriptions and examples are warnings; ambiguous types are warnings; underdocumented errors are warnings. |

Profiles are implemented as a severity-override mapping. Defaults are embedded in code; the user can override via `~/.hermes/openapi-auditor.yaml`.

---

## 4. Technical architecture

### 4.1 Repository structure

```
hermes-openapi-auditor/
├── plugin.yaml
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE
├── __init__.py                       # register() entrypoint
├── schemas.py                        # tool schemas (what the LLM reads)
├── tools.py                          # tool handler(s): args:dict + **kwargs → JSON string
├── auditor/                          # internal implementation (not exposed to LLM)
│   ├── __init__.py
│   ├── detect.py                     # detect_version()
│   ├── loader.py                     # load_spec(): parse + validate + resolve refs
│   ├── model.py                      # dataclasses: Spec, Finding, Version
│   ├── walker.py                     # version-agnostic iterators
│   ├── runner.py                     # orchestration (called by tools.py wrapper)
│   ├── profiles.py                   # profile config + severity overrides
│   ├── rendering.py                  # markdown rendering
│   └── rules/
│       ├── __init__.py               # REGISTRY list
│       ├── missing_descriptions.py
│       ├── undocumented_errors.py
│       ├── additional_properties.py
│       ├── missing_examples.py
│       └── ambiguous_types.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── petstore-2.0.yaml         # download from OpenAPI Initiative
    │   ├── petstore-3.0.yaml
    │   ├── petstore-3.1.yaml
    │   ├── invalid-frankenstein.yaml # has both `swagger` and `components`
    │   ├── invalid-no-version.json
    │   └── synthetic/                # tiny minimal specs for per-rule unit tests
    │       ├── missing-examples-2.0.yaml
    │       ├── missing-examples-3.0.yaml
    │       └── ...
    ├── test_detect.py
    ├── test_loader.py
    ├── test_walker.py
    ├── test_handler.py               # tests the Hermes-facing tools.py wrapper
    ├── test_rules_missing_descriptions.py
    ├── test_rules_undocumented_errors.py
    ├── test_rules_additional_properties.py
    ├── test_rules_missing_examples.py
    ├── test_rules_ambiguous_types.py
    └── test_integration.py           # end-to-end against Petstore fixtures
```

Layout rationale (follows the official 4-file convention from §2.3):
- `schemas.py` holds the OpenAI function-calling schemas the LLM reads.
- `tools.py` holds the Hermes-facing handler(s) — they accept `args: dict, **kwargs` and return JSON strings. The handler is a thin wrapper that delegates to `auditor/runner.py`.
- `auditor/` is the internal implementation, free to use rich Python types (dataclasses, exceptions). It never touches Hermes APIs and is fully unit-testable in isolation.

### 4.2 `plugin.yaml` template

Use exactly the fields shown below. Earlier drafts of this plan included `category:`, `license:`, `homepage:`, and `dependencies:` — **all four are non-existent in the official manifest format and must NOT appear here.** They have been removed.

```yaml
name: hermes-openapi-auditor
version: 0.1.0
description: >
  Audits OpenAPI/Swagger specs (2.0, 3.0, 3.1) for quality issues that hurt
  both human readers and LLMs consuming the spec via function calling.
  Checks for missing descriptions, ambiguous types, missing examples,
  permissive additionalProperties, and undocumented error codes.
author: <your name>

# What this plugin registers. These lists are how Hermes describes the plugin
# in `/plugins` output and the loading banner.
provides_tools:
  - audit_openapi_spec
provides_hooks: []   # this plugin registers no hooks
```

The official documented optional field that is intentionally NOT used here:
- `requires_env:` — for plugins that need API keys. This plugin needs none.

Python dependencies (`PyYAML`, `jsonschema`, `openapi-spec-validator`, `jsonref`) go in `pyproject.toml`, NOT in `plugin.yaml`. Example `pyproject.toml` excerpt:

```toml
[project]
name = "hermes-openapi-auditor"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "PyYAML>=6.0",
    "jsonschema>=4.18",
    "openapi-spec-validator>=0.7",
    "jsonref>=1.1",
]

[project.optional-dependencies]
dev = ["pytest>=7", "pytest-cov", "ruff", "mypy"]

# For pip-based distribution (optional — directory install also works):
[project.entry-points."hermes_agent.plugins"]
hermes-openapi-auditor = "hermes_openapi_auditor"
```

### 4.3 The three top-level files: `schemas.py`, `tools.py`, `__init__.py`

Following the official 4-file convention. Each file has one job.

**`schemas.py`** — what the LLM reads:

```python
"""Tool schemas — what the LLM sees in its tool list."""

AUDIT_OPENAPI_SPEC = {
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
                    "Absolute or relative path to the OpenAPI/Swagger file "
                    "(.json, .yaml, or .yml)."
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
```

**`tools.py`** — the Hermes-facing handler. This is the file most likely to be wrong if you skip §2.6.1. The handler:
1. Takes `args: dict` and `**kwargs` — single dict, no unpacked params.
2. Returns a JSON string from every path, including errors.
3. Never raises.

```python
"""Tool handler — Hermes-facing entrypoint.

This is a thin wrapper that translates the Hermes handler protocol
(args dict in, JSON string out, no exceptions) to the internal
`auditor.runner.audit_openapi_spec(...)` API which uses normal Python types.
"""
from __future__ import annotations
import json

from .auditor.runner import audit_openapi_spec as _run_audit


def audit_openapi_spec(args: dict, **kwargs) -> str:
    """Hermes handler. Always returns a JSON string.

    Per Hermes plugin contract (see plan §2.6.1):
    - Signature: (args: dict, **kwargs) -> str
    - Return: JSON string on success AND error
    - Never raises
    """
    try:
        path = args.get("path")
        if not path:
            return json.dumps({"error": "'path' argument is required"})

        result = _run_audit(
            path=path,
            profile=args.get("profile", "agent-consumed"),
            severity_threshold=args.get("severity_threshold", "warning"),
            format=args.get("format", "json"),
        )
        # _run_audit returns a Python dict (or dict with 'markdown' key).
        # The handler's job is to serialize it.
        return json.dumps(result)
    except FileNotFoundError as e:
        return json.dumps({"error": f"file not found: {e}"})
    except Exception as e:
        # Catch-all: handler MUST NOT raise.
        return json.dumps({"error": f"audit failed: {type(e).__name__}: {e}"})
```

**`__init__.py`** — registration:

```python
"""hermes-openapi-auditor — plugin registration."""
from __future__ import annotations
import logging

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    """Called once by Hermes' PluginManager at startup.

    `ctx` is a PluginContext instance. Do not type-hint it strictly — the
    type is not publicly exported and may change between Hermes versions.
    """
    ctx.register_tool(
        name="audit_openapi_spec",
        toolset="qa",
        schema=schemas.AUDIT_OPENAPI_SPEC,
        handler=tools.audit_openapi_spec,
    )
    logger.debug("hermes-openapi-auditor registered: 1 tool (audit_openapi_spec)")
```

Note that `description` is NOT a separate kwarg to `register_tool` — it lives inside `schemas.AUDIT_OPENAPI_SPEC["description"]` as part of the OpenAI function-calling schema. The official examples all follow this pattern.

### 4.4 Multi-version dispatch pattern

**Decision:** rules are one file each, with internal dispatch by version. Do NOT create per-version subdirectories.

Rationale:
- Each rule's full version handling is visible in one file (easier to maintain).
- Adding a new OpenAPI version (e.g. future 3.2) means touching N rule files, not adding N new directories.
- Shared helpers within a rule stay co-located.

Pattern per rule:

```python
def check(spec, walker) -> list[Finding]:
    if spec.version == "2.0":
        return _check_v2(spec, walker)
    if spec.version == "3.0":
        return _check_v3_0(spec, walker)
    return _check_v3_1(spec, walker)
```

Rules that genuinely don't differ across versions (`missing_descriptions`, `undocumented_errors`) skip dispatch entirely and implement a single `check()` body that operates on the normalized walker output.

### 4.5 Reference rule: `missing_examples.py`

This is the **reference implementation** for the version-divergent pattern. Use it as the template for `ambiguous_types.py`.

```python
"""Rule: missing examples in request/response bodies and schemas.

Divergences by version:
- 2.0: `examples` (dict keyed by mime) in responses; `example` singular in schemas.
- 3.0: `example` or `examples` (named, plural) inside each mediaType object.
- 3.1: as 3.0 + `examples: [...]` array at schema level (JSON Schema 2020-12).
       An example declared ONLY at schema level still counts as present.
"""
from __future__ import annotations
from ..model import Finding, Spec

RULE_ID = "missing-examples"


def check(spec: Spec, walker) -> list[Finding]:
    if spec.version == "2.0":
        return _check_v2(spec, walker)
    if spec.version == "3.0":
        return _check_v3_0(spec, walker)
    return _check_v3_1(spec, walker)


def _check_v2(spec: Spec, walker) -> list[Finding]:
    findings: list[Finding] = []
    for path, verb, op, pointer in walker.iter_operations(spec):
        body_param = next(
            (p for p in op.get("parameters", []) if p.get("in") == "body"), None
        )
        if body_param is not None:
            schema = body_param.get("schema", {})
            if "example" not in schema:
                findings.append(Finding(
                    rule_id=RULE_ID,
                    severity="warning",
                    message=f"Request body of {verb.upper()} {path} has no `example`.",
                    path=f"{pointer}/parameters",
                    operation=f"{verb.upper()} {path}",
                    suggestion="Add `example` to the body parameter's schema.",
                ))

        for status, response in op.get("responses", {}).items():
            if not _is_success_or_error(status):
                continue
            schema = response.get("schema", {})
            if not schema:
                continue
            if not response.get("examples") and "example" not in schema:
                findings.append(Finding(
                    rule_id=RULE_ID,
                    severity="warning",
                    message=f"Response {status} of {verb.upper()} {path} has no example.",
                    path=f"{pointer}/responses/{status}",
                    operation=f"{verb.upper()} {path}",
                    suggestion="Add `examples` (per mime) or `example` on the schema.",
                ))
    return findings


def _check_v3_0(spec: Spec, walker) -> list[Finding]:
    findings: list[Finding] = []
    for path, verb, op, pointer in walker.iter_operations(spec):
        rb = op.get("requestBody")
        if rb is not None:
            for mime, media in rb.get("content", {}).items():
                if not _media_or_schema_has_example_v3_0(media):
                    findings.append(Finding(
                        rule_id=RULE_ID,
                        severity="warning",
                        message=f"Request body {mime} of {verb.upper()} {path} has no example.",
                        path=f"{pointer}/requestBody/content/{mime}",
                        operation=f"{verb.upper()} {path}",
                        suggestion="Add `example`/`examples` to the mediaType or `example` to the schema.",
                    ))
        for status, response in op.get("responses", {}).items():
            if not _is_success_or_error(status):
                continue
            for mime, media in response.get("content", {}).items():
                if not _media_or_schema_has_example_v3_0(media):
                    findings.append(Finding(
                        rule_id=RULE_ID,
                        severity="warning",
                        message=f"Response {status} ({mime}) of {verb.upper()} {path} has no example.",
                        path=f"{pointer}/responses/{status}/content/{mime}",
                        operation=f"{verb.upper()} {path}",
                        suggestion="Add `example`/`examples` to the mediaType or `example` to the schema.",
                    ))
    return findings


def _check_v3_1(spec: Spec, walker) -> list[Finding]:
    """Structurally same as 3.0, but schema-level `examples: [...]` array counts."""
    findings: list[Finding] = []
    for path, verb, op, pointer in walker.iter_operations(spec):
        rb = op.get("requestBody")
        if rb is not None:
            for mime, media in rb.get("content", {}).items():
                if not _media_or_schema_has_example_v3_1(media):
                    findings.append(Finding(
                        rule_id=RULE_ID,
                        severity="warning",
                        message=f"Request body {mime} of {verb.upper()} {path} has no example.",
                        path=f"{pointer}/requestBody/content/{mime}",
                        operation=f"{verb.upper()} {path}",
                        suggestion=(
                            "Add `example`/`examples` to mediaType, or `example`/`examples` "
                            "(array) to the schema."
                        ),
                    ))
        for status, response in op.get("responses", {}).items():
            if not _is_success_or_error(status):
                continue
            for mime, media in response.get("content", {}).items():
                if not _media_or_schema_has_example_v3_1(media):
                    findings.append(Finding(
                        rule_id=RULE_ID,
                        severity="warning",
                        message=f"Response {status} ({mime}) of {verb.upper()} {path} has no example.",
                        path=f"{pointer}/responses/{status}/content/{mime}",
                        operation=f"{verb.upper()} {path}",
                        suggestion=(
                            "Add `example`/`examples` to mediaType, or to the schema "
                            "(3.1 allows `examples: [...]` array on schemas)."
                        ),
                    ))
    return findings


def _media_or_schema_has_example_v3_0(media: dict) -> bool:
    if "example" in media or media.get("examples"):
        return True
    schema = media.get("schema", {})
    return "example" in schema


def _media_or_schema_has_example_v3_1(media: dict) -> bool:
    if "example" in media or media.get("examples"):
        return True
    schema = media.get("schema", {})
    if "example" in schema:
        return True
    schema_examples = schema.get("examples")
    return isinstance(schema_examples, list) and len(schema_examples) > 0


def _is_success_or_error(status: str) -> bool:
    if status == "default":
        return True
    if not status or not status[0].isdigit():
        return status.upper() in ("2XX", "4XX", "5XX")
    return status[0] in ("2", "4", "5")
```

---

## 5. Implementation phases

Each phase is a checkpoint. The agent should run the listed commands and verify acceptance criteria before proceeding.

### Phase 1: Project scaffolding (≈45 min)

**Deliverables:**
- Directory tree as in §4.1, with empty modules.
- `pyproject.toml` declaring the package, dev dependencies, AND the pip entry point under `hermes_agent.plugins` (see §4.2).
- `plugin.yaml` per §4.2 — note: NO `category`, `license`, `homepage`, or `dependencies` fields.
- `LICENSE` (MIT).
- Stub `schemas.py` with the `AUDIT_OPENAPI_SPEC` dict from §4.3.
- Stub `tools.py` with the handler signature `def audit_openapi_spec(args: dict, **kwargs) -> str` returning `json.dumps({"error": "not implemented"})`.
- Stub `__init__.py` with `register(ctx)` that wires schemas to handler.
- `tests/conftest.py` with a fixture path helper.

**Acceptance:**
- `python -c "import hermes_openapi_auditor"` succeeds.
- `python -c "from hermes_openapi_auditor.tools import audit_openapi_spec; import json; r = audit_openapi_spec({'path': '/nonexistent'}); assert isinstance(r, str); assert 'error' in json.loads(r)"` succeeds (handler returns JSON string even on missing path).
- `pytest tests/ --collect-only` discovers the tests directory.
- `ruff check .` returns no errors (or only style nits to fix).

**Commands:**
```bash
pip install -e ".[dev]"
ruff check .
pytest --collect-only
```

### Phase 2: Spec loader and version detection (≈1.5 h)

**Deliverables:**
- `auditor/detect.py` implementing `detect_version(spec_dict) -> Literal["2.0", "3.0", "3.1"]`.
- `auditor/loader.py` implementing `load_spec(path: str) -> Spec`:
  - Reads file (JSON or YAML, detected by extension).
  - Validates against the appropriate meta-schema via `openapi-spec-validator`.
  - Rejects Frankenstein specs (raises a clear `InvalidSpecError`).
  - Optionally resolves `$ref`s via `jsonref` (gated by a flag; circular refs must not crash).
- Fixtures downloaded: Petstore 2.0, 3.0, 3.1 (from the OpenAPI Initiative repos). Two invalid fixtures hand-written.

**Acceptance:**
- `pytest tests/test_detect.py tests/test_loader.py -v` passes.
- All three Petstore files load and report correct versions.
- Both invalid fixtures raise `InvalidSpecError` with a useful message.

### Phase 3: Internal model and walker (≈1.5 h)

**Deliverables:**
- `auditor/model.py` with `Finding`, `Spec`, and the `Severity`/`Version` literal types.
- `auditor/walker.py` with at minimum:
  - `iter_operations(spec) -> Iterator[tuple[str, str, dict, str]]` yielding `(path, verb, operation_dict, json_pointer)`.
  - `iter_responses(operation_dict) -> Iterator[tuple[str, dict]]`.
  - `iter_request_bodies(operation_dict, spec) -> Iterator[tuple[str, dict]]` (version-aware: yields mediaType objects for 3.x, synthesizes one entry for 2.0 body parameters).
  - `iter_schemas(spec) -> Iterator[tuple[str, dict, str]]` over reusable schemas (handles `definitions` vs `components.schemas`).

**Acceptance:**
- For all three Petstore versions, `iter_operations` yields the same set of paths/verbs (modulo trivial Petstore version differences — assert on a known subset like `/pets` GET, `/pets` POST).
- `pytest tests/test_walker.py -v` passes with the same assertion bodies for all three versions (proves the abstraction holds).

### Phase 4: The five audit rules (≈4–6 h)

Implement rules in this order (easiest first; each lands with its own unit tests):

#### 4a. `missing_descriptions` (≈30 min)
- Single `check()` body, no version dispatch.
- Flags operations missing both `summary` and `description`.
- 3 unit tests minimum: clean spec (zero findings), dirty spec (N findings), spec with `summary` only (zero findings).

#### 4b. `undocumented_errors` (≈30 min)
- Single `check()` body.
- Flags operations with no `4xx` or `5xx` responses and no `default` response.
- Accepts wildcards `4XX`, `5XX` (OpenAPI 3.x convention).

#### 4c. `additional_properties` (≈45 min)
- Mostly version-agnostic.
- Flags schemas with `additionalProperties: true` when at least one named property is defined (heuristic for "this is supposed to be a closed shape").
- 3.1 nuance: if `unevaluatedProperties` is also present, downgrade severity to `info` (the user is aware).

#### 4d. `missing_examples` (≈1.5 h)
- Use the reference implementation in §4.5 verbatim as a starting point.
- Adjust per profile (in `public`, missing examples on response bodies become `error`).

#### 4e. `ambiguous_types` (≈2 h, the gnarliest)
- Full version dispatch.
- v2.0: flag parameters with `type: string` and no `format`/`enum`/`pattern`. Accept `type: file` as legitimate for `multipart/form-data` (do NOT flag).
- v3.0: flag schemas with `nullable: true` AND no `type`. Flag `oneOf`/`anyOf` without discriminator hint.
- v3.1: flag schemas with `nullable: true` (it was removed in 3.1 — use `type: [..., "null"]`). Flag `exclusiveMinimum`/`exclusiveMaximum` as booleans (3.1 changed them to numbers per JSON Schema 2020-12).

**Acceptance for Phase 4:**
- Each rule has ≥3 unit tests against synthetic minimal specs (fixtures under `tests/fixtures/synthetic/`).
- `pytest tests/test_rules_*.py -v` all pass.
- Combined coverage of `auditor/rules/` ≥ 90% (rules are pure functions; high coverage is cheap).

### Phase 5: Runner, profiles, and rendering (≈1.5 h)

**Deliverables:**
- `auditor/runner.py` implementing `audit_openapi_spec(path, profile, severity_threshold, format) -> dict`:
  - **Returns a Python dict** (not a JSON string). The Hermes-facing handler in `tools.py` is responsible for `json.dumps()`. This separation keeps `auditor/` independently testable without forcing every test to parse JSON.
  - Loads spec.
  - Builds walker.
  - Iterates `REGISTRY` from `auditor/rules/__init__.py`.
  - Applies profile severity overrides.
  - Filters by threshold.
  - When `format="markdown"`, calls `rendering.to_markdown(...)` and wraps the result as `{"version": ..., "source": ..., "markdown": "..."}`.
- `auditor/profiles.py` with embedded defaults:
  ```python
  PROFILES = {
      "public": {"missing-examples": "error", "missing-descriptions": "error"},
      "internal": {"missing-descriptions": "info", "additional-properties": "info"},
      "agent-consumed": {},  # uses rule defaults
  }
  ```
  Optionally load overrides from `~/.hermes/openapi-auditor.yaml` (best-effort; if the file is missing or malformed, fall back to defaults silently and log a warning).
- `auditor/rendering.py` with a `to_markdown(findings, spec) -> str` function. Group findings by operation, sort by severity desc, then by rule_id.
- Update `tools.py` handler so it `json.dumps(runner.audit_openapi_spec(...))` and confirms the protocol from §2.6.1 end-to-end.

**Acceptance:**
- `pytest tests/test_integration.py -v` passes end-to-end against all three Petstore fixtures with each profile.
- `pytest tests/test_handler.py -v` confirms the Hermes-facing wrapper: returns a JSON string in every code path (success, missing-path, invalid-spec, file-not-found), never raises, accepts unexpected `**kwargs` without error.
- Markdown output is human-readable (manual spot check; no rigid format requirement).

### Phase 6: Hermes integration sanity check (≈30 min)

This phase verifies the plugin actually loads in Hermes. **Requires a local Hermes installation (v0.14.0+ recommended).**

**Deliverables:**
- The plugin directory copied or symlinked to `~/.hermes/plugins/hermes-openapi-auditor/`.
- Plugin discovery is automatic — Hermes scans `~/.hermes/plugins/` on startup. No `config.yaml` edits needed for activation.
  - If the plugin doesn't appear, run with `HERMES_PLUGINS_DEBUG=1 hermes` to surface discovery logs (added in v0.14.0, PR #22684).
- Manual smoke test: invoke `audit_openapi_spec` from Hermes CLI against one of the Petstore fixtures and verify a sensible result.

**Acceptance:**
- `hermes` startup banner lists `hermes-openapi-auditor: audit_openapi_spec`.
- `/plugins` in a session shows `✓ hermes-openapi-auditor v0.1.0 (1 tool, 0 hooks)`.
- A real invocation returns a non-empty JSON result for a known-dirty spec.
- No errors in `~/.hermes/logs/agent.log`.

**If this phase fails:** stop and consult the Hermes plugin documentation. Do not modify Hermes core to work around issues — the entire point of §2.1 is to not do that.

### Phase 7: Documentation (≈1 h)

**Deliverables:**
- `README.md` containing:
  - Installation instructions: clone repo, `pip install -e .`, symlink or copy to `~/.hermes/plugins/hermes-openapi-auditor/`, restart `hermes`. (No `config.yaml` activation needed — discovery is automatic.)
  - Usage examples (CLI invocation, expected output shapes — JSON string).
  - All 5 rules described with one-paragraph explanations and example findings.
  - Profile semantics.
  - Troubleshooting section: how to use `HERMES_PLUGINS_DEBUG=1` to debug discovery; common error messages and their causes.
  - Pinned Hermes version note (v0.14.0+).
  - License.
- `CHANGELOG.md` with the v0.1.0 entry.
- `CLAUDE.md` at the project root: a short note constraining future Claude Code sessions for this repo (e.g. "use Sonnet with `/effort auto`; prefix complex prompts with `think hard`; do not run `claude init`; follow PEP 8; full type hints; pytest must stay green before any commit").

**Acceptance:**
- A reader unfamiliar with the project can install and run the plugin using only `README.md`.

---

## 6. Quality bar

| Aspect | Requirement |
|---|---|
| Python version | 3.11+ |
| Type hints | All public functions and class methods fully type-hinted. `from __future__ import annotations` at the top of every module. |
| Docstrings | All public functions and classes. One-liner minimum; multi-line for non-obvious behaviour. |
| Formatting | `ruff format` (or `black`) — pick one, declare in `pyproject.toml`, apply consistently. |
| Linting | `ruff check` clean. |
| Type checking | `mypy --strict` on `auditor/` package. Allow `Any` on the `ctx` parameter only. |
| Tests | `pytest` with ≥85% coverage on `auditor/` (rules should be ≥90%). |
| Imports | No wildcard imports. No imports from `hermes_cli.*` or anything in the Hermes core. |

---

## 7. Testing strategy

### 7.1 Test taxonomy

| Type | Location | Purpose |
|---|---|---|
| Unit tests per rule | `tests/test_rules_*.py` | One file per rule. Synthetic minimal fixtures. Cover positive (zero findings), negative (N findings), and edge cases. |
| Walker tests | `tests/test_walker.py` | Same assertion bodies running against all three Petstore versions. |
| Loader/detect tests | `tests/test_loader.py`, `tests/test_detect.py` | Valid + invalid fixtures. |
| Integration tests | `tests/test_integration.py` | End-to-end runner invocations against Petstore fixtures with each profile. |

### 7.2 Fixtures

- Download official Petstore samples from the OpenAPI Initiative for all three versions. Vendor them under `tests/fixtures/` (do not fetch over the network during test runs).
- Hand-write minimal synthetic specs (10–30 lines each) under `tests/fixtures/synthetic/` for per-rule tests. Each synthetic spec triggers exactly one rule.

### 7.3 Test commands

```bash
pytest tests/ -v
pytest tests/ --cov=auditor --cov-report=term-missing
pytest tests/test_rules_missing_examples.py -v   # per-rule
```

### 7.4 Coverage target

≥85% line coverage on `auditor/` package. Rules ≥90%. CI fails below thresholds.

---

## 8. Constraints and non-goals

### 8.1 Hard constraints

- **No modifications to Hermes core.** None. If something seems to require it, open an issue against the Hermes repo instead.
- **No new ABCs.** This is a `general`-category plugin; it consumes existing APIs only.
- **No network calls at runtime.** The plugin reads local files only.
- **No file writes outside `/tmp` or explicit output paths.** The plugin is read-only on the user's filesystem.
- **No reading files other than the spec path the user provided.** Do not scan the user's filesystem for related specs, configs, etc.

### 8.2 Non-goals (out of scope for v0.1.0)

- **Spec generation/modification.** This plugin audits; it does not edit or generate specs. (A future `hermes-openapi-fixer` plugin could pair with this one.)
- **Runtime API testing.** No live calls to the API the spec describes.
- **Contract diffing between two specs.** Out of scope. A separate plugin (`hermes-contract-tester` in the catalog) handles that.
- **Custom rule plugins.** v0.1.0 ships with five hardcoded rules. Pluggable rules are deferred to v0.2.0.
- **Internationalization.** All messages in English.

---

## 9. Final acceptance criteria

Before declaring the plugin done:

- [ ] All five rules implemented with version-aware dispatch where needed.
- [ ] All three OpenAPI versions (2.0, 3.0, 3.1) supported with passing tests.
- [ ] Test coverage ≥85% on `auditor/` package, ≥90% on `auditor/rules/`.
- [ ] `mypy --strict auditor/` clean.
- [ ] `ruff check .` and `ruff format --check .` clean.
- [ ] `plugin.yaml` conforms to §2.3 and §4.2 (no `category`/`license`/`homepage`/`dependencies` fields; `provides_tools` populated).
- [ ] Handler in `tools.py` conforms to §2.6.1: signature `(args: dict, **kwargs) -> str`, returns JSON string in every code path including errors, never raises.
- [ ] `__init__.py`'s `register(ctx)` matches §2.5 and §4.3.
- [ ] Plugin loads in a local Hermes Agent v0.14.0+ installation and the tool is invocable end-to-end.
- [ ] `/plugins` in a running Hermes session shows the plugin with the correct tool count.
- [ ] `README.md` complete with install instructions, all rules documented, and profile semantics explained.
- [ ] No core files modified (verifiable: the plugin lives in its own repo and `~/.hermes/plugins/<name>/`; nothing else touched).
- [ ] `CHANGELOG.md` records v0.1.0.

---

## 10. Known gotchas (from prior design discussion)

The agent should be aware of these before encountering them mid-implementation:

1. **`$ref` resolution must happen before rules run**, or rules will see `{"$ref": "..."}` as a terminal node and emit false positives. Use `jsonref` with circular-ref handling.
2. **`additionalProperties` is not always wrong** — some endpoints legitimately accept extensions. The rule should be `info` severity by default, not `warning`, and configurable per profile.
3. **`type: file` in Swagger 2.0 is legitimate** for file uploads. Do not flag it as an ambiguous type. In 3.x this is modelled as `type: string, format: binary` inside `multipart/form-data`.
4. **`nullable: true` is valid in 3.0 but removed in 3.1.** A 3.1 spec using `nullable: true` is technically wrong, and many existing linters miss it. Flag this in `ambiguous_types` for 3.1.
5. **`exclusiveMinimum`/`exclusiveMaximum` semantics changed** between 2.0/3.0 (boolean modifier) and 3.1 (numeric value, per JSON Schema 2020-12). A spec migrated by hand from 3.0 to 3.1 often retains the boolean form — this is a useful finding.
6. **JSON Schema 2020-12 examples can live on the schema as an array** (`examples: [...]`). In 3.1, a media type without `example`/`examples` but whose schema has a non-empty `examples` array is fine. Do not flag.
7. **Hermes may auto-generate or modify some plugin files** (rare but possible during installation). Do not commit `__pycache__/` or any cached files. Use a strict `.gitignore`.
8. **The `PluginContext` type is not publicly documented.** Do not import or type-hint it strictly. Treat `ctx` as `Any` at the boundary.

---

## 11. References

### 11.1 Hermes Agent

- Core repository: https://github.com/NousResearch/hermes-agent
- Documentation root: https://hermes-agent.nousresearch.com/docs
- **Build a Plugin guide (authoritative for the requirements in this plan):** https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin
- Plugins user guide: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins
- Architecture overview: https://hermes-agent.nousresearch.com/docs/developer-guide/architecture
- Hooks reference: https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks
- Memory provider plugin guide: https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin
- Context engine plugin guide: https://hermes-agent.nousresearch.com/docs/developer-guide/context-engine-plugin
- Release notes for v0.14.0 (latest as of May 16, 2026): `RELEASE_v0.14.0.md` in the core repo
- Tested against release: **v0.14.0** (tag `v2026.5.16`)

### 11.2 OpenAPI / JSON Schema

- OpenAPI Specification (all versions): https://spec.openapis.org/
- Swagger 2.0 spec: https://swagger.io/specification/v2/
- OpenAPI 3.0.3 spec: https://spec.openapis.org/oas/v3.0.3
- OpenAPI 3.1.0 spec: https://spec.openapis.org/oas/v3.1.0
- JSON Schema 2020-12: https://json-schema.org/specification-links#2020-12
- Petstore fixtures: https://github.com/OAI/OpenAPI-Specification/tree/main/examples

### 11.3 Python dependencies

- `openapi-spec-validator`: https://github.com/python-openapi/openapi-spec-validator
- `jsonref`: https://github.com/gazpachoking/jsonref
- `jsonschema`: https://github.com/python-jsonschema/jsonschema

---

## 12. How to use this plan with Claude Code

1. Place this plan at the root of an empty directory.
2. Start a Claude Code session in that directory.
3. Begin with: `read the plan in hermes-openapi-auditor-plan.md and start Phase 1. Stop after each phase for review.`
4. Use `think hard` prefix for Phase 4d (`missing_examples`) and Phase 4e (`ambiguous_types`) — both contain the gnarliest version-dispatch logic.
5. After each phase, run the listed acceptance commands and verify before moving on.
6. Do not allow the agent to run `claude init` — it will overwrite the `CLAUDE.md` to be added in Phase 7.
