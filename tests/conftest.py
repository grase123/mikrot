"""Suite-wide test isolation for environment and .env loading.

Two concerns are handled for every test (autouse):

1. ``mikrot.settings._load_env`` is neutralized to a no-op, so no test reads the
   repo's real ``.env`` or writes to the developer's ``~/.config``. Tests that
   exercise the loader on purpose re-install the real function (captured at
   their own module import time) and point ``MIKROT_CONFIG_HOME`` at a tmp dir.
2. ``os.environ`` is snapshotted and restored, so values written directly by
   ``dotenv.load_dotenv`` (which bypasses monkeypatch) cannot leak across tests.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

import mikrot.settings as settings_mod


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings_mod, "_load_env", lambda: None)
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)
