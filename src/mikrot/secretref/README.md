# secretref

Resolve provider-prefixed **secret references** (e.g. `op://Vault/Item/field`) into real
secret values.

It is **value-driven** and host-agnostic: it resolves only values that match a known
reference prefix and returns everything else unchanged. It does not know (or need) the list
of variables a caller uses -- the caller decides what mapping to pass in. The package has no
dependency on the host application, so it can later be extracted into its own distribution.

## Usage

```python
from mikrot.secretref import resolve_mapping, resolve_value

resolve_value("op://Vault/Item/field")   # -> the secret (via `op read`)
resolve_value("env://${PORT:-8080}")      # -> value of $PORT, or "8080" if unset
resolve_value("plain-value")              # -> "plain-value" (unchanged)

resolve_mapping({"PASSWORD": "op://V/I/f", "HOST": "192.168.88.1"})
# -> {"PASSWORD": "<secret>", "HOST": "192.168.88.1"}
```

A non-reference value is returned as-is. On failure (tool missing, non-zero exit, timeout,
empty output, bad config, undefined variable) a `SecretResolutionError` is raised, carrying
the offending `ref` and (when applicable) `tool`.

## Built-in providers

| Prefix   | Kind                | Resolves to                                            |
| -------- | ------------------- | ------------------------------------------------------ |
| `op://`  | CLI (`op`)          | 1Password secret via `op read <ref>`                   |
| `env://` | internal (example)  | environment variable, shell-style `${VAR:-default}`    |

The `op://` provider checks the tool is on `PATH` (`shutil.which`) before launching it and
reads the secret with a timeout.

## Custom providers

A provider is anything that matches a `prefix` and implements `resolve(value)`. Two shapes
ship in [`providers.py`](providers.py):

- **`CliProvider`** -- shells out to an external CLI (this is also what
  `SECRETREF_PROVIDERS` builds, below).
- **`EnvProvider`** -- the **example of a custom (internal) provider**: it runs no external
  tool. The reference body after `env://` is a shell-style expansion expression handed
  verbatim to the [`expandvars`](https://pypi.org/project/expandvars/) library, so the full
  `${VAR:-default}` / `${VAR:?err}` / ... syntax works without secretref parsing it. An
  undefined variable without a default raises.

To add a provider that does not fit the CLI model, subclass `Provider` and implement
`resolve` -- `EnvProvider` is the worked example.

## Adding CLI providers without code: `SECRETREF_PROVIDERS`

Set `SECRETREF_PROVIDERS` to a JSON array of provider objects. Each needs a non-empty
`prefix` and `tool`, plus optional `args` (a list of strings). In `args`, a `{ref}` token is
replaced by the reference; if absent the reference is appended.

```bash
SECRETREF_PROVIDERS='[
  {"prefix": "bw://", "tool": "bw", "args": ["get", "password", "{ref}"]}
]'
```

- These build `CliProvider` instances.
- Env-defined providers take precedence over built-ins on a prefix clash.
- Malformed config (invalid JSON, missing `prefix`/`tool`, non-string `args`) raises
  `SecretResolutionError`.
- `SECRETREF_PROVIDERS` is read from the real environment only -- it configures the resolver
  and is never itself resolved.

## Security note

A CLI provider's `tool` is an executable that gets run. Treat `SECRETREF_PROVIDERS` with the
same trust as `PATH`: define it in your real shell environment, not in an untrusted `.env`
shipped by someone else. References are passed as argv (no shell), so `{ref}` cannot inject
commands.

## Public API

- `resolve_value(value, *, providers=None, timeout=40.0) -> str`
- `resolve_mapping(values, *, timeout=40.0) -> dict[str, str]`
- `provider_for(value, providers=None) -> Provider | None`
- `active_providers(environ=None) -> tuple[Provider, ...]`
- `providers_from_env(environ=None) -> tuple[Provider, ...]`
- `Provider` (base), `CliProvider`, `EnvProvider`, `PREFIX_PROVIDERS`, `SecretResolutionError`
