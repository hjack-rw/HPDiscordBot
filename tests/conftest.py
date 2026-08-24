import os
import sys
import types
from pathlib import Path

import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# fakes pre_init before anything under src/ is touched - see memory for why post-import is too late
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
