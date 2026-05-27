# hermes-openapi-auditor

A [Hermes Agent](https://hermes-agent.nousresearch.com/) plugin that audits
OpenAPI / Swagger specs for the kind of quality issues that hurt **LLM
function calling**, not just human readers.

Specs that pass a classic linter (e.g. Spectral) can still be useless to an
LLM if they lack descriptions, examples, narrow enums, or documented error
codes. This plugin is a linter oriented to that consumption pattern.

Supports **Swagger 2.0**, **OpenAPI 3.0.x**, and **OpenAPI 3.1.x** out of the
box.

## Quick start

```bash
git clone <this repo>
cd hermes-openapi-auditor
pip install -e .

# Drop or symlink into Hermes' plugin directory (discovery is automatic):
ln -s "$(pwd)" ~/.hermes/plugins/hermes-openapi-auditor

# Start (or restart) Hermes and look for the plugin in the loading banner.
hermes
```

In a Hermes session, run `/plugins` and confirm the entry:

```
✓ hermes-openapi-auditor v0.1.0 (1 tool, 0 hooks)
```

Then ask the agent to audit a spec:

```
> please audit the OpenAPI spec at ./openapi.yaml
```

## The tool

A single tool, `audit_openapi_spec(path, profile, severity_threshold, format)`,
that returns a JSON string with the findings.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | string (required) | — | Path to an OpenAPI/Swagger file (`.json`, `.yaml`, `.yml`). |
| `profile` | enum | `agent-consumed` | `public`, `internal`, or `agent-consumed`. Adjusts severities. |
| `severity_threshold` | enum | `warning` | `info`, `warning`, or `error`. Filters out findings below the level. |
| `format` | enum | `json` | `json` (default) or `markdown` (wrapped in a JSON envelope). |

Sample JSON return:

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
      "suggestion": "Add 'example'/'examples' on the mediaType or 'example' on the schema."
    }
  ]
}
```

On any error the return is still a JSON string:

```json
{"error": "file not found: /path/to/missing.yaml"}
```

## The five rules

### `missing-descriptions` (default: warning)

Flags operations that have **neither** `summary` nor `description`. Either
field alone is fine; both being absent leaves the LLM with nothing but path
and verb to infer intent.

### `undocumented-errors` (default: warning)

Flags operations that declare **no `4xx`/`5xx` response and no `default`
response**. Without error-shape information the agent can't tell a
recoverable input error from an unrecoverable server failure. The `4XX` /
`5XX` wildcards (3.x) and `default` both count as documented.

### `additional-properties` (default: info)

Flags schemas with `additionalProperties: true` **and** at least one named
property. A schema that lists fields *and* accepts arbitrary extras is
ambiguous: the LLM can't tell whether the named set is exhaustive. The
default severity is `info` because some endpoints legitimately accept
extensions; promote it in the profile if you care.

3.1 nuance: when `unevaluatedProperties` is also present the author has
explicitly addressed open-ended composition, so the rule stays at `info`.

### `missing-examples` (default: warning)

Flags request/response bodies without an example value. Examples are the
single biggest signal an LLM has for how the data actually looks. The rule
checks (per version):

- **2.0:** body parameter schema, and per-response `examples` (mime-keyed)
  / `example` on the schema.
- **3.0:** each `requestBody.content.<mime>` and `responses.<status>.
  content.<mime>` for `example` / `examples` (named) on the mediaType, or
  `example` on the schema.
- **3.1:** same as 3.0 plus a non-empty schema-level `examples: [...]`
  array (JSON Schema 2020-12).

### `ambiguous-types` (default: warning)

Flags type declarations that are ambiguous or version-incorrect:

- **2.0:** parameters declared as `type: string` with no
  `format` / `enum` / `pattern`. `type: file` is a legitimate 2.0 multipart
  idiom and is **not** flagged.
- **3.0:** schemas with `nullable: true` but no `type`; `oneOf` / `anyOf`
  with two or more variants and no `discriminator`.
- **3.1:** any use of `nullable` (it was removed in 3.1 — use
  `type: [..., "null"]`); `exclusiveMinimum` / `exclusiveMaximum` declared
  as booleans (3.1 / JSON Schema 2020-12 expects numbers).

## Profiles

A profile is a named set of per-rule severity overrides. The built-ins:

| Profile | Intent | Overrides |
|---|---|---|
| `public` | Strictest. Public-facing API. | `missing-examples` → error; `missing-descriptions` → error |
| `internal` | Relaxed. Internal-only API. | `missing-descriptions` → info; `additional-properties` → info |
| `agent-consumed` (default) | LLM consumption | (none — each rule's default) |

You can override any profile's severities in `~/.hermes/openapi-auditor.yaml`:

```yaml
profiles:
  agent-consumed:
    missing-descriptions: error
  public:
    additional-properties: error
```

If the file is missing or malformed it is silently ignored (a warning is
logged).

## Troubleshooting

**Plugin doesn't appear in the Hermes startup banner.** Run with
`HERMES_PLUGINS_DEBUG=1 hermes` to surface plugin discovery logs (added in
Hermes v0.14.0, PR #22684). Common causes:

- The plugin directory isn't under `~/.hermes/plugins/` (or wherever the
  `HERMES_PLUGINS_DIR` env var points).
- `plugin.yaml` is missing or malformed.
- Python dependencies aren't installed in the same interpreter Hermes is
  using — re-run `pip install -e .` inside Hermes' venv.

**Handler returns `{"error": "..."}` instead of findings.** That is the
contract — the handler never raises. Inspect the error message; typically
it's `file not found`, `invalid spec: ...`, or a third-party parser
complaint. Run `python -m hermes_openapi_auditor.tools` against the same
path for a reproduction outside Hermes (see "developer notes" below).

**Spec validation rejects a file the agent should audit.** The Hermes
runner runs with `validate_schema=False` by default so the rules can still
fire on partially-invalid specs (typical when migrating 3.0 → 3.1). If you
want strict validation, set `validate_schema=True` when calling the loader
directly.

## Developer notes

```bash
pip install -e ".[dev]"
pytest                                # full test suite
pytest --cov=auditor --cov-report=term-missing
ruff check . && ruff format --check .
mypy auditor/
```

Layout:

```
hermes-openapi-auditor/
├── plugin.yaml              # Hermes manifest
├── pyproject.toml
├── __init__.py              # plugin entrypoint with register(ctx)
├── schemas.py               # OpenAI function-calling schemas (what the LLM reads)
├── tools.py                 # Hermes handler (args:dict, **kwargs → str JSON)
├── auditor/                 # internal implementation (Hermes-free)
│   ├── detect.py            # version detection
│   ├── loader.py            # parse + validate + ref-resolve
│   ├── model.py             # Finding / Spec / Severity / Version
│   ├── walker.py            # version-agnostic iterators
│   ├── runner.py            # orchestration
│   ├── profiles.py          # severity overrides
│   ├── rendering.py         # markdown output
│   └── rules/               # one file per rule
└── tests/                   # pytest, with Petstore fixtures
```

## Compatibility

Tested against **Hermes Agent v0.14.0** (release tag `v2026.5.16`). Hermes is
under heavy development; the plugin API has been stable through v0.13.x →
v0.14.x but pin a version explicitly if you depend on this.

Python 3.11+.

## License

GPL-3.0. See [LICENSE](./LICENSE).
