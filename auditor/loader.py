"""Spec loader: file IO, parsing, validation, optional ``$ref`` resolution.

``load_spec`` is the single entry point. It performs:

1. Read the file (JSON or YAML, by extension).
2. Reject Frankenstein specs (both ``swagger`` and ``openapi`` set, or
   2.0 specs that mix in 3.x-only structural fields like ``components``).
3. Detect the version.
4. Validate against the appropriate OpenAPI meta-schema via
   ``openapi-spec-validator``.
5. Optionally resolve ``$ref`` pointers via ``jsonref`` (circular refs
   become lazy proxy objects rather than blowing up).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonref
import yaml
from openapi_spec_validator import (
    OpenAPIV2SpecValidator,
    OpenAPIV30SpecValidator,
    OpenAPIV31SpecValidator,
    validate,
)
from openapi_spec_validator.validation.validators import SpecValidator

from .detect import InvalidSpecError, detect_version
from .model import Spec, Version

_VALIDATORS: dict[Version, type[SpecValidator]] = {
    "2.0": OpenAPIV2SpecValidator,
    "3.0": OpenAPIV30SpecValidator,
    "3.1": OpenAPIV31SpecValidator,
}


def load_spec(
    path: str | Path,
    *,
    resolve_refs: bool = True,
    validate_schema: bool = True,
) -> Spec:
    """Load, validate, and (optionally) ref-resolve a spec at ``path``.

    Args:
        path: Filesystem path to a ``.json``, ``.yaml`` or ``.yml`` file.
        resolve_refs: When True (default), in-file and external ``$ref``
            pointers are eagerly resolved so rules see expanded
            structures. Circular references are tolerated (they become
            lazy proxies rather than infinite-recursing).
        validate_schema: When True (default), the parsed spec is checked
            against the matching OpenAPI meta-schema. Set to False to
            audit specs that are deliberately mid-migration (e.g. a 3.0
            spec being upgraded to 3.1 that still has boolean
            ``exclusiveMinimum`` — the ``ambiguous-types`` rule wants to
            flag exactly that, but the meta-schema would reject the spec
            before any rule could run).

    Returns:
        A :class:`Spec` with ``data`` ref-resolved and ``raw`` holding
        the pre-resolution dict.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        InvalidSpecError: if the file is unparseable, mixes versions, or
            (when ``validate_schema=True``) fails meta-schema validation.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"spec file not found: {p}")

    raw_text = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    try:
        if suffix == ".json":
            data: Any = json.loads(raw_text)
        elif suffix in (".yaml", ".yml"):
            data = yaml.safe_load(raw_text)
        else:
            raise InvalidSpecError(
                f"unsupported file extension {suffix!r}; expected .json, .yaml, or .yml"
            )
    except json.JSONDecodeError as e:
        raise InvalidSpecError(f"failed to parse JSON at {p}: {e}") from e
    except yaml.YAMLError as e:
        raise InvalidSpecError(f"failed to parse YAML at {p}: {e}") from e

    if not isinstance(data, dict):
        raise InvalidSpecError(f"spec root must be a mapping, got {type(data).__name__} at {p}")

    _reject_frankenstein(data, p)
    version = detect_version(data)

    # Validate against the matching meta-schema. We pick an explicit
    # validator class so we get a clearer error if detect_version and the
    # meta-schema ever disagree.
    if validate_schema:
        validator_cls = _VALIDATORS[version]
        try:
            validate(data, cls=validator_cls)
        except Exception as e:
            raise InvalidSpecError(
                f"spec at {p} failed {version} meta-schema validation: {e}"
            ) from e

    raw_snapshot = copy.deepcopy(data)
    if resolve_refs:
        try:
            base_uri = p.absolute().as_uri()
            data = jsonref.replace_refs(data, base_uri=base_uri, lazy_load=False, proxies=False)
        except Exception as e:
            # External refs may be unreachable in offline environments.
            # Leave the spec unresolved rather than failing the whole
            # audit — rules that need resolution will see the raw $ref
            # nodes and can decide for themselves.
            raise InvalidSpecError(f"$ref resolution failed for {p}: {e}") from e

    if not isinstance(data, dict):
        # jsonref can return a proxy that behaves like a dict; coerce.
        data = dict(data)

    return Spec(version=version, data=data, source=str(p), raw=raw_snapshot)


def _reject_frankenstein(data: dict[str, Any], path: Path) -> None:
    """Detect specs that mix mutually exclusive version markers.

    A 2.0 spec must not carry 3.x-only structural fields, and vice-versa.
    These rules don't catch every malformed spec — the meta-schema
    validator does the rest — but they produce clearer error messages.
    """
    has_swagger = "swagger" in data
    has_openapi = "openapi" in data

    if has_swagger and has_openapi:
        raise InvalidSpecError(f"spec at {path} declares both 'swagger' and 'openapi' fields")

    if has_swagger and "components" in data:
        raise InvalidSpecError(
            f"spec at {path} declares swagger: '2.0' but uses the 3.x-only 'components' object"
        )

    if has_openapi and "definitions" in data and "components" not in data:
        # 'definitions' is 2.0-only; the validator catches this, but a
        # targeted message helps the user.
        raise InvalidSpecError(
            f"spec at {path} declares openapi 3.x but uses the 2.0-only 'definitions' object"
        )
