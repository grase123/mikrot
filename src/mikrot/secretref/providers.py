"""Secret providers: a polymorphic base + built-in implementations.

A :class:`Provider` matches a reference ``prefix`` and knows how to ``resolve``
a value that starts with it. Two built-in kinds:

* :class:`CliProvider` -- shells out to an external CLI (e.g. 1Password ``op``).
  These are also what the ``SECRETREF_PROVIDERS`` env var builds.
* :class:`EnvProvider` -- an **example of a custom (internal) provider**: it runs
  no external tool and resolves environment variables in-process.

To add a provider that does not fit the CLI model, subclass :class:`Provider`
and implement ``resolve`` (see :class:`EnvProvider`).

Extra CLI providers can be added without code via ``SECRETREF_PROVIDERS`` -- a
JSON array of provider objects, for example::

    SECRETREF_PROVIDERS='[{"prefix":"bw://","tool":"bw","args":["get","password","{ref}"]}]'

Env-defined providers take precedence over built-ins on a prefix clash.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from expandvars import ExpandvarsException, expand

from mikrot.secretref.errors import SecretResolutionError

# Environment variable holding the JSON array of extra (CLI) providers.
ENV_VAR = "SECRETREF_PROVIDERS"
# Timeout (seconds) for an external tool to return a secret.
DEFAULT_TIMEOUT = 40.0


class Provider(ABC):
    """Base provider: matches a reference ``prefix`` and resolves it."""

    prefix: str

    @abstractmethod
    def resolve(self, value: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
        """Resolve a reference ``value`` (which starts with ``self.prefix``)."""
        raise NotImplementedError


@dataclass(frozen=True)
class CliProvider(Provider):
    """Resolve a reference by shelling out to an external CLI (e.g. ``op``).

    In ``args`` a ``{ref}`` token is replaced by the reference; otherwise the
    reference is appended. The tool's presence is checked before launching it.
    """

    prefix: str
    tool: str
    args: tuple[str, ...]

    def argv(self, ref: str) -> list[str]:
        if any("{ref}" in arg for arg in self.args):
            return [self.tool, *(arg.replace("{ref}", ref) for arg in self.args)]
        return [self.tool, *self.args, ref]

    def resolve(self, value: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
        if shutil.which(self.tool) is None:
            raise SecretResolutionError(
                f"cannot resolve secret reference: '{self.tool}' is not installed "
                "or not on PATH",
                ref=value,
                tool=self.tool,
            )
        try:
            # argv is built from a fixed provider definition (no shell).
            result = subprocess.run(
                self.argv(value),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SecretResolutionError(
                f"failed to run '{self.tool}' to resolve a secret reference: {exc}",
                ref=value,
                tool=self.tool,
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit code {result.returncode}"
            raise SecretResolutionError(
                f"'{self.tool}' could not resolve a secret reference: {detail}",
                ref=value,
                tool=self.tool,
            )
        secret = result.stdout.rstrip("\n")
        if not secret:
            raise SecretResolutionError(
                f"'{self.tool}' returned an empty secret for a reference",
                ref=value,
                tool=self.tool,
            )
        return secret


@dataclass(frozen=True)
class EnvProvider(Provider):
    """EXAMPLE of a custom (internal) provider -- resolves env vars in-process.

    Unlike :class:`CliProvider` it runs no external tool. The reference body
    after the prefix is a shell-style expansion expression handed verbatim to
    the ``expandvars`` library, so the full ``${VAR:-default}`` / ``${VAR:?err}``
    / ... syntax works without us parsing it, e.g. ``env://${APP_PORT:-8080}``.
    An undefined variable without a default raises (``nounset``). Provided to
    demonstrate plugging a non-CLI provider into secretref by subclassing
    :class:`Provider`.
    """

    prefix: str = "env://"

    def resolve(self, value: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
        body = value[len(self.prefix) :]
        try:
            return expand(body, nounset=True)
        except ExpandvarsException as exc:
            raise SecretResolutionError(
                f"could not expand environment reference: {exc}",
                ref=value,
            ) from exc


# Built-in providers: 1Password (CLI) + the example env provider.
PREFIX_PROVIDERS: tuple[Provider, ...] = (
    CliProvider(prefix="op://", tool="op", args=("read",)),
    EnvProvider(),  # example custom (internal) provider, prefix "env://"
)


def providers_from_env(environ: Mapping[str, str] | None = None) -> tuple[Provider, ...]:
    """Build extra CLI providers from the ``SECRETREF_PROVIDERS`` JSON array.

    Read from the real environment only (these configure the resolver itself,
    so they are never themselves resolved). Raises
    :class:`SecretResolutionError` on malformed configuration.
    """
    env = os.environ if environ is None else environ
    raw = env.get(ENV_VAR)
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecretResolutionError(f"{ENV_VAR} is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise SecretResolutionError(f"{ENV_VAR} must be a JSON array of provider objects")

    providers: list[Provider] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise SecretResolutionError(f"{ENV_VAR}: each provider must be a JSON object")
        prefix = entry.get("prefix")
        tool = entry.get("tool")
        args = entry.get("args", [])
        if not (isinstance(prefix, str) and prefix and isinstance(tool, str) and tool):
            raise SecretResolutionError(
                f"{ENV_VAR}: each provider needs a non-empty 'prefix' and 'tool'"
            )
        if not (isinstance(args, list) and all(isinstance(arg, str) for arg in args)):
            raise SecretResolutionError(f"{ENV_VAR}: 'args' must be a list of strings")
        providers.append(CliProvider(prefix=prefix, tool=tool, args=tuple(args)))
    return tuple(providers)


def active_providers(environ: Mapping[str, str] | None = None) -> tuple[Provider, ...]:
    """Env-defined providers first (override built-ins), then the built-ins."""
    return (*providers_from_env(environ), *PREFIX_PROVIDERS)


def provider_for(value: str, providers: Sequence[Provider] | None = None) -> Provider | None:
    """Return the provider whose prefix matches ``value``, or ``None``.

    Without ``providers`` the active set (env + built-ins) is used.
    """
    candidates = active_providers() if providers is None else providers
    for provider in candidates:
        if value.startswith(provider.prefix):
            return provider
    return None
