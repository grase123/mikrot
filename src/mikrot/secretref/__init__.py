"""secretref -- resolve provider-prefixed secret references (e.g. ``op://...``).

Value-driven and host-agnostic: it resolves only values that match a known
reference prefix (see :data:`providers.PREFIX_PROVIDERS`) by shelling out to the
provider's CLI; every other value is returned unchanged. It knows nothing about
which variables a caller uses -- the caller chooses what mapping to pass in.

Designed to be self-contained (no imports from the host application) so it can
later be extracted into a standalone distribution.
"""

from __future__ import annotations

from mikrot.secretref.errors import SecretResolutionError
from mikrot.secretref.providers import (
    PREFIX_PROVIDERS,
    CliProvider,
    EnvProvider,
    Provider,
    active_providers,
    provider_for,
    providers_from_env,
)
from mikrot.secretref.resolver import resolve_mapping, resolve_value

__all__ = [
    "PREFIX_PROVIDERS",
    "CliProvider",
    "EnvProvider",
    "Provider",
    "SecretResolutionError",
    "active_providers",
    "provider_for",
    "providers_from_env",
    "resolve_mapping",
    "resolve_value",
]
