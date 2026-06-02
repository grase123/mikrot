"""Resolve secret references in a mapping by delegating to providers.

Each provider knows how to resolve its own references (an external CLI, an
in-process lookup, ...); this module just matches a value to a provider and
calls it. Non-reference values pass through unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from mikrot.secretref.providers import (
    DEFAULT_TIMEOUT,
    Provider,
    active_providers,
    provider_for,
)


def resolve_value(
    value: str,
    *,
    providers: Sequence[Provider] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Resolve ``value`` if it is a secret reference, else return it unchanged."""
    provider = provider_for(value, providers)
    if provider is None:
        return value
    return provider.resolve(value, timeout=timeout)


def resolve_mapping(
    values: Mapping[str, str], *, timeout: float = DEFAULT_TIMEOUT
) -> dict[str, str]:
    """Return a copy of ``values`` with any secret references resolved.

    Non-reference values are copied unchanged. Raises
    :class:`mikrot.secretref.errors.SecretResolutionError` on malformed provider
    config or on the first reference that cannot be resolved.
    """
    providers = active_providers()  # parse env providers once (may raise on bad config)
    return {
        key: resolve_value(value, providers=providers, timeout=timeout)
        for key, value in values.items()
    }
