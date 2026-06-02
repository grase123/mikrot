"""Version-string helper shared by `app.py` (--version) and `manifest.py`.

Reads the installed distribution version via importlib.metadata, falling
back to the in-package ``__version__`` constant when metadata is
unavailable (e.g. running straight from an uninstalled source tree).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from mikrot import __version__ as _fallback_version


def version_string() -> str:
    """Return the installed package version, or the in-package fallback."""
    try:
        return version("mikrot")
    except PackageNotFoundError:
        return _fallback_version
