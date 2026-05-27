# Changelog

All notable changes to `hermes-openapi-auditor` are recorded here.
This project follows [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-05-27

### Added
- Initial release. Single tool `audit_openapi_spec(path, profile,
  severity_threshold, format)` registered against Hermes Agent v0.14.0.
- Five audit rules, all version-aware where the underlying spec is:
  - `missing-descriptions`
  - `undocumented-errors`
  - `additional-properties`
  - `missing-examples`
  - `ambiguous-types`
- Three OpenAPI versions supported: Swagger 2.0, OpenAPI 3.0.x, OpenAPI 3.1.x.
- Three profiles: `public`, `internal`, `agent-consumed` (default), with
  user-level severity overrides via `~/.hermes/openapi-auditor.yaml`.
- JSON (default) and markdown output formats.
- 128 unit + integration tests; ≥90% line coverage on the `auditor/` package.
