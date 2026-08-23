import os
import sys
import types
from pathlib import Path

import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# pre_init.py (gitignored) may be absent entirely, or present locally with every test_bot flag
# hardcoded False (it only reads live TUI input, never env vars) - either way test_bot can't be
# steered from outside via a plain post-import override: src/__init__.py does
# `from src.commands import *` / `from src.events import *` before it imports variables at
# all, and those transitively import src/functions/notifications.py, which reads test_bot at
# MODULE-IMPORT time (to pick channel_ids_test vs channel_ids) - so by the time any test code
# gets a chance to run `import src.variables`, that's already baked in and can't be undone.
# Faking out pre_init BEFORE anything under src/ is touched fixes it at the actual source.
fake_pre_init = types.ModuleType("pre_init")
fake_pre_init.test_bot = {"local_deploy": os.getcwd() != "/home/container",
                           "test_body":    True,
                           "test_command": True,
                           "test_events":  True,
                           "test_tasks":   True,}
sys.modules["pre_init"] = fake_pre_init

import src.variables as vars


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    """A fresh, isolated database (from the blank schema seed) for a single test.

    Only database_path (where the live .db file lives) is redirected to a tmp dir;
    database_name/schema_seed_path stay as-is so restore(clear=True) reads the real,
    read-only seed at src/db/__database__.db-blank - no copying needed."""

    from src.db import Database

    monkeypatch.setattr(Database, "database_path", str(tmp_path) + os.sep)

    await Database.restore(clear=True)
    yield Database
    await Database.disconnect()
