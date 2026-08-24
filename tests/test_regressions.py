"""
Regression tests for bugs discovered while building this test suite (2026-08-22), unrelated
to the WHERE-clause parameterization work in tests/test_db_engine.py. Each docstring explains
what was broken so the fix's intent stays legible even after the bug itself is history.
"""
import os

from contextlib import asynccontextmanager
from types      import SimpleNamespace

import pytest

from src.db import Experience, ExperienceInfo, Images
from src.db.engine.validators import sql_create_linked_record


@pytest.mark.asyncio
async def test_images_add_replace_true(db):
    """Originally: get_update_clause's type(old_value) != type(value) check always failed for
    BLOB columns (old_value comes back as BytesIO, a fresh value is bytes), and BytesIO isn't a
    bindable sqlite3 parameter anyway - so the 'overwrite image?' flow always crashed after
    confirming. Images has since moved to filesystem-backed storage (metadata-only DB row,
    bytes on disk), which sidesteps that bug class entirely - replace=True now just overwrites
    the file and never touches _update. Kept as a behavioral check that overwrite still works."""

    images = await Images.initialize()
    await images.add("apple.png", b"orig-bytes")

    images = await Images.initialize()
    await images.add("apple.png", b"replaced-bytes", replace=True)

    stored_path = os.path.join(Images.database_path, "images", "misc", "apple.png")
    with open(stored_path, "rb") as file:
        assert file.read() == b"replaced-bytes"


@pytest.mark.asyncio
async def test_experience_info_add_without_explicit_defaults(db):
    """ExperienceInfo.add's own defaults=None default used to send None straight into
    get_sql_values's 'elif column in defaults:' - an unconditional TypeError. No real caller
    in the codebase ever passes defaults= explicitly."""

    exp_info = await ExperienceInfo.initialize()
    await exp_info.add(user_id=111, pet_ashwinder=True)

    exp_info = await ExperienceInfo.initialize()
    assert 111 in exp_info.raw_data


@pytest.mark.asyncio
async def test_experience_extended_initialize(db):
    """_get_joined_table_name() used to return cls.joined_table.__name__.lower()
    ('experienceinfo'), but the real table is 'experience_info' - the only 1:1 linked-table
    pair in the codebase never had a working extended=True JOIN."""

    exp = await Experience.initialize()
    await exp._insert(new_record=(1, 0, 0.0), custom_id=111)

    exp_info = await ExperienceInfo.initialize()
    await exp_info.add(user_id=111, pet_ashwinder=True)

    exp_ext = await Experience.initialize(extended=True, pet_ashwinder=True)
    assert 111 in exp_ext.raw_data


@pytest.mark.asyncio
async def test_sql_create_linked_record_does_not_treat_optional_param_as_missing():
    """sql_create_linked_record's missing_params check used to flag ANY needed kwarg that
    resolved to None as 'missing', with no check against the target signature's actual
    default - so a genuinely optional parameter like ExperienceInfo.add's `defaults`
    (default=None) was wrongly treated as required. This broke auto-creating the linked
    ExperienceInfo row for a brand-new XP earner. Isolated reproduction (no real DB needed):
    exercises the actual decorator against a minimal stand-in joined_table."""

    created = {}

    class FakeJoined:
        @staticmethod
        async def add(user_id, pet_ashwinder, defaults=None):
            created.update(user_id=user_id, pet_ashwinder=pet_ashwinder, defaults=defaults)

        @classmethod
        async def initialize(cls, **kwargs):
            return cls()

    class FakeSelf:
        joined_table = FakeJoined

        def _get_id_column(self):
            return "user_id"

        async def get_joined_table(self, **kwargs):
            return None  # linked record doesn't exist yet -> should attempt auto-create

        @asynccontextmanager
        async def transaction(self):
            yield  # no real DB here, nothing to commit/roll back

    @sql_create_linked_record
    async def tweak(self, is_new, user_id, pet_ashwinder):
        return "ok"

    await tweak(FakeSelf(), is_new=True, user_id=777, pet_ashwinder=True)

    assert created == {"user_id": 777, "pet_ashwinder": True, "defaults": None}


@pytest.mark.asyncio
async def test_experience_tweak_creates_both_rows(db):
    """Experience.tweak() on a brand-new user_id should end with both the experience row and
    its auto-created experience_info row present - the normal, successful path."""

    member = SimpleNamespace(id=222, roles=[])
    exp = await Experience.initialize()
    await exp.tweak(server=None, member=member, amount=15)

    assert 222 in (await Experience.initialize()).raw_data
    assert 222 in (await ExperienceInfo.initialize()).raw_data


@pytest.mark.asyncio
async def test_experience_tweak_rolls_back_on_linked_record_failure(db, monkeypatch):
    """Real cause behind two live users showing an experience row with no matching
    experience_info row (silently dropped off the leaderboard's INNER JOIN, see
    project_comment-rationale-archive memory): sql_create_linked_record used to insert the
    experience row and its linked experience_info row as two separate, independently
    committed statements - if anything interrupted execution between them (a crash, a race
    with another path creating the same link), the experience row stayed committed with no
    link. Both inserts now share one transaction() - forcing the linked-record step to fail
    must roll back the experience insert too, leaving neither row behind."""

    async def _raise(*args, **kwargs):
        raise RuntimeError("simulated failure creating the linked record")

    monkeypatch.setattr(ExperienceInfo, "add", _raise)

    member = SimpleNamespace(id=333, roles=[])
    exp = await Experience.initialize()

    with pytest.raises(Exception):
        await exp.tweak(server=None, member=member, amount=15)

    assert 333 not in (await Experience.initialize()).raw_data
    assert 333 not in (await ExperienceInfo.initialize()).raw_data
