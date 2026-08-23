"""
Regression tests for bugs discovered while building this test suite (2026-08-22), unrelated
to the WHERE-clause parameterization work in tests/test_db_engine.py. Each docstring explains
what was broken so the fix's intent stays legible even after the bug itself is history.
"""
import pytest

from src.db import Experience, ExperienceInfo, Images
from src.db.engine.validators import sql_create_linked_record


@pytest.mark.asyncio
async def test_images_add_replace_true(db):
    """get_update_clause's type(old_value) != type(value) check used to always fail for BLOB
    columns (old_value comes back as BytesIO, a fresh value is bytes); even past that, BytesIO
    isn't a bindable sqlite3 parameter type at all - so the 'overwrite image?' flow always
    crashed after confirming."""

    images = await Images.initialize()
    await images.add("apple.png", b"orig-bytes")

    images = await Images.initialize()
    await images.add("apple.png", b"replaced-bytes", replace=True)

    images = await Images.initialize()
    stored = next(iter(images._get_values_from_raw_data(images.raw_data, add_id=True)))
    assert stored["data"].read() == b"replaced-bytes"


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

    @sql_create_linked_record
    async def tweak(self, is_new, user_id, pet_ashwinder):
        return "ok"

    await tweak(FakeSelf(), is_new=True, user_id=777, pet_ashwinder=True)

    assert created == {"user_id": 777, "pet_ashwinder": True, "defaults": None}
