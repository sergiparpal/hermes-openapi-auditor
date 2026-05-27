"""Profile definitions and severity overrides.

A profile is a name plus a mapping of ``rule_id`` -> severity override.
The runner applies these overrides on top of each rule's
``DEFAULT_SEVERITY``.

Profiles are embedded as code defaults; users may override per-rule
severities via ``~/.hermes/openapi-auditor.yaml`` (best-effort: if the
file is missing or malformed, defaults stand and a warning is logged).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from .model import SEVERITY_LEVELS, ProfileName, Severity

logger = logging.getLogger(__name__)

# ProfileName lives in model.py so schemas.py / tools.py / profiles.py share
# the same enumeration. The user config may register additional profile
# names at runtime — the mapping below is open-ended on its key type.
PROFILES: dict[ProfileName, dict[str, Severity]] = {
    "public": {
        "missing-examples": "error",
        "missing-descriptions": "error",
    },
    "internal": {
        "missing-descriptions": "info",
        "additional-properties": "info",
    },
    "agent-consumed": {},  # uses each rule's DEFAULT_SEVERITY
}
"""Built-in profiles. Each profile's mapping overrides the default
severity of named rules; rules not listed keep their defaults."""


def severity_for(
    profile: ProfileName,
    rule_id: str,
    default: Severity,
    *,
    overrides: dict[ProfileName, dict[str, Severity]] | None = None,
) -> Severity:
    """Return the effective severity for ``rule_id`` under ``profile``.

    Resolution order: caller-provided overrides → built-in PROFILES →
    rule's ``default``.
    """
    if overrides is not None:
        override_map = overrides.get(profile, {})
        if rule_id in override_map:
            return override_map[rule_id]
    return PROFILES.get(profile, {}).get(rule_id, default)


def _user_config_path() -> Path:
    """Path to the user-level override config.

    Honours the ``HERMES_OPENAPI_AUDITOR_CONFIG`` environment variable
    (used by tests). Defaults to ``~/.hermes/openapi-auditor.yaml``.
    """
    override = os.environ.get("HERMES_OPENAPI_AUDITOR_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".hermes" / "openapi-auditor.yaml"


def load_user_overrides() -> dict[ProfileName, dict[str, Severity]]:
    """Load per-rule severity overrides from the user config.

    Expected YAML shape::

        profiles:
          public:
            missing-examples: error
          internal:
            additional-properties: info

    Returns an empty mapping on any error (file missing, malformed YAML,
    unexpected structure). Failures are logged at WARNING.
    """
    path = _user_config_path()
    raw = _read_yaml(path)
    if raw is None:
        return {}
    return _parse_profiles_section(raw, path)


def _read_yaml(path: Path) -> dict[str, Any] | None:
    """Load ``path`` as YAML and return its top-level mapping, or ``None``.

    ``None`` covers: file missing, OS read error, YAML parse error, and
    a top level that isn't a mapping. All but "file missing" log a
    warning so the user can debug.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        raw: Any = yaml.safe_load(text) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.warning("could not read auditor config at %s: %s", path, e)
        return None
    if not isinstance(raw, dict):
        _warn(path, "must be a mapping; ignoring")
        return None
    return raw


def _parse_profiles_section(
    raw: dict[str, Any],
    path: Path,
) -> dict[ProfileName, dict[str, Severity]]:
    profiles_section = raw.get("profiles") or {}
    if not isinstance(profiles_section, dict):
        _warn(path, "'profiles' must be a mapping; ignoring")
        return {}

    overrides: dict[ProfileName, dict[str, Severity]] = {}
    for profile, rules in profiles_section.items():
        if not isinstance(rules, dict):
            _warn(path, f"profile {profile!r} entry must be a mapping; ignoring")
            continue
        cleaned = _parse_profile_rules(rules, profile, path)
        if cleaned:
            overrides[profile] = cleaned
    return overrides


def _parse_profile_rules(
    rules: dict[Any, Any],
    profile: Any,
    path: Path,
) -> dict[str, Severity]:
    cleaned: dict[str, Severity] = {}
    for rule_id, severity in rules.items():
        if not isinstance(rule_id, str):
            _warn(path, f"non-string rule id {rule_id!r} under profile {profile!r}; ignoring")
            continue
        if severity not in SEVERITY_LEVELS:
            _warn(
                path,
                f"invalid severity {severity!r} for {rule_id} under profile {profile!r} "
                f"(expected one of {list(SEVERITY_LEVELS)}); ignoring",
            )
            continue
        cleaned[rule_id] = severity
    return cleaned


def _warn(path: Path, detail: str) -> None:
    """Emit the standard ``auditor config at <path>: <detail>`` warning."""
    logger.warning("auditor config at %s: %s", path, detail)
