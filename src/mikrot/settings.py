"""Pydantic-settings configuration for mikrot (env prefix ``MIKROT_``).

Two ``.env`` files are loaded into ``os.environ`` with ``override=False`` (real
shell env-vars always win over files), then :class:`Settings` reads the merged
environment. There is no YAML layer.

Load order and precedence (higher wins):

    shell env-vars > project-local ``.env`` (cwd) > global ``~/.config/mikrot/.env`` > defaults

The project-local ``.env`` (discovered by walking up from the current directory)
is loaded *before* the global file, so a local file wins over the global one
while the shell still beats both. The global file is auto-created (as a fully
commented scaffold) on first run if it does not exist.

``MIKROT_CONFIG_HOME`` overrides the directory of the global ``.env`` (it holds
the file directly, e.g. ``$MIKROT_CONFIG_HOME/.env``); it defaults to
``~/.config/mikrot`` on every OS. It is read from the shell environment only
(it decides where the files are) and is handy for tests and power users.
"""

from __future__ import annotations

import os
from pathlib import Path

import dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from mikrot.errors import MikrotError

# Scaffold written to the global .env on first run. Every variable is commented
# out on purpose: an all-commented file contributes no values (the built-in
# defaults apply) until the user edits it.
GLOBAL_ENV_TEMPLATE = """\
# mikrot global configuration.
# Auto-generated on first run. All variables are commented out: uncomment and
# edit only the ones you want to set here. Anything left commented falls back to
# the built-in defaults.
#
# Precedence (higher wins): shell environment > a project-local .env in the
# current directory > this file > built-in defaults.
#
# MIKROT_PASSWORD is required for any command that talks to the router; set it
# here, in a project-local .env, or in the shell environment.

#MIKROT_PASSWORD=change-me
#MIKROT_HOST=192.168.88.1
#MIKROT_PORT=80
#MIKROT_SCHEME=http
#MIKROT_USER=admin
#MIKROT_TIMEOUT=5.0
"""


class Settings(BaseSettings):
    """Connection settings for the MikroTik REST API.

    Defaults target a factory-fresh MikroTik (its default LAN address and the
    ``admin`` user). ``password`` defaults to empty and is enforced non-empty
    by :func:`load_settings` (so ``doctor`` can still build settings to report
    the missing secret).
    """

    model_config = SettingsConfigDict(
        env_prefix="MIKROT_",
        extra="ignore",
    )

    host: str = "192.168.88.1"
    port: int = 80
    scheme: str = "http"
    user: str = "admin"
    password: str = ""
    timeout: float = 5.0

    @property
    def base_url(self) -> str:
        """REST base, e.g. ``http://192.168.88.1:80/rest``."""
        return f"{self.scheme}://{self.host}:{self.port}/rest"


def _config_dir() -> Path:
    """Directory holding the global ``.env``.

    Overridable via ``MIKROT_CONFIG_HOME`` (read from the shell environment);
    defaults to ``~/.config/mikrot`` on every OS.
    """
    override = os.environ.get("MIKROT_CONFIG_HOME")
    if override:
        return Path(override)
    return Path.home() / ".config" / "mikrot"


def _global_env_path() -> Path:
    return _config_dir() / ".env"


def _ensure_global_env() -> Path:
    """Create the global ``.env`` scaffold (dir + commented template) if absent.

    Best-effort: filesystem errors are swallowed so read-only commands never
    abort just because the home directory is not writable. An existing file is
    never overwritten.
    """
    path = _global_env_path()
    try:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(GLOBAL_ENV_TEMPLATE, encoding="utf-8")
    except OSError:
        pass
    return path


def _load_env() -> None:
    # Precedence: shell env > cwd .env > global .env > defaults. Both files use
    # override=False (shell always wins); the cwd file is loaded BEFORE the
    # global one so a project-local .env wins over the global file.
    _ensure_global_env()
    cwd_env = dotenv.find_dotenv(usecwd=True)
    if cwd_env:
        dotenv.load_dotenv(cwd_env, override=False)
    dotenv.load_dotenv(_global_env_path(), override=False)


def load_settings() -> Settings:
    """Load the ``.env`` files then build :class:`Settings`, requiring a password.

    A missing ``MIKROT_PASSWORD`` surfaces as a
    ``MikrotError(code="config_missing")`` errors-as-data envelope rather
    than a raw pydantic error.
    """
    _load_env()
    settings = Settings()
    if not settings.password:
        raise MikrotError(
            "MIKROT_PASSWORD is not set",
            code="config_missing",
            fix_description=(
                "set MIKROT_PASSWORD in a project-local .env, in "
                f"{_global_env_path()}, or in the shell environment"
            ),
        )
    return settings


def load_settings_tolerant() -> Settings:
    """Build settings without enforcing the password.

    Used by ``doctor`` so a missing ``MIKROT_PASSWORD`` is reported as a
    check row instead of aborting the whole command.
    """
    _load_env()
    return Settings()
