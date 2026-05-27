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

from .model import Severity

logger = logging.getLogger(__name__)

ProfileName = str  # 'public' | 'internal' | 'agent-consumed' (open-ended)

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
        profile_map = overrides.get(profile, {})
        if rule_id in profile_map:
            return profile_map[rule_id]
    profile_map = PROFILES.get(profile, {})
    return profile_map.get(rule_id, default)


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
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        raw: Any = yaml.safe_load(text) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.warning("could not read auditor config at %s: %s", path, e)
        return {}

    if not isinstance(raw, dict):
        logger.warning("auditor config at %s must be a mapping; ignoring", path)
        return {}

    profiles_section = raw.get("profiles") or {}
    if not isinstance(profiles_section, dict):
        logger.warning("auditor config at %s: 'profiles' must be a mapping; ignoring", path)
        return {}

    out: dict[ProfileName, dict[str, Severity]] = {}
    for prof, rules in profiles_section.items():
        if not isinstance(rules, dict):
            logger.warning(
                "auditor config at %s: profile %r entry must be a mapping; ignoring",
                path,
                prof,
            )
            continue
        clean: dict[str, Severity] = {}
        for rule_id, sev in rules.items():
            if not isinstance(rule_id, str):
                logger.warning(
                    "auditor config at %s: non-string rule id %r under profile %r; ignoring",
                    path,
                    rule_id,
                    prof,
                )
                continue
            if sev not in {"info", "warning", "error"}:
                logger.warning(
                    "auditor config at %s: invalid severity %r for %s under profile %r "
                    "(expected one of 'info', 'warning', 'error'); ignoring",
                    path,
                    sev,
                    rule_id,
                    prof,
                )
                continue
            clean[rule_id] = sev
        if clean:
            out[prof] = clean
    return out
