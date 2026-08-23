import os
import sys
from pathlib import Path

import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# src/variables.py falls back to these when pre_init.py (gitignored) is absent
os.environ.setdefault("TEST_BODY", "True")
os.environ.setdefault("TEST_COMMAND", "True")
os.environ.setdefault("TEST_EVENTS", "True")
os.environ.setdefault("TEST_TASKS", "True")


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
