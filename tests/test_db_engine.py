import datetime

import pytest

from src.db import Experience, Images, WelcomeMessages
from src.db.engine import IdAlreadyExistsError
from src.db.engine.clauses import apply_conditions

class TestImagesFilterSafety:
    pytestmark = pytest.mark.asyncio

    async def test_initial_insert(self, db):
        images = await Images.initialize()
        await images.add("apple.png", b"orig-bytes")

        images = await Images.initialize()
        assert images.get_filenames() == ["apple.png"]

    async def test_duplicate_insert_raises_id_already_exists(self, db):
        images = await Images.initialize()
        await images.add("apple.png", b"orig-bytes")

        images = await Images.initialize()
        with pytest.raises(IdAlreadyExistsError):
            await images.add("apple.png", b"dup-attempt", replace=False)

    async def test_apostrophe_filename_roundtrips_unmangled(self, db):
        images = await Images.initialize()
        await images.add("o'brien.png", b"data")

        images = await Images.initialize()
        assert "o'brien.png" in images.get_filenames()

    async def test_like_filter_with_embedded_quote_does_not_break_out(self, db):
        images = await Images.initialize()
        await images.add("evil__x' OR '1'='1.png", b"payload-row")

        images = await Images.initialize(filename__like="x' OR '1'='1")
        assert images.get_filenames() == ["evil__x' OR '1'='1.png"]

    async def test_has_filter_matches(self, db):
        images = await Images.initialize()
        await images.add("evil__x' OR '1'='1.png", b"payload-row")

        images = await Images.initialize(filename__has="evil")
        assert images.get_filenames() == ["evil__x' OR '1'='1.png"]


class TestGetConditionsCallSites:
    """_get_conditions is shared by images.py, experience.py (x4), welcome_messages.py."""

    pytestmark = pytest.mark.asyncio

    async def test_get_conditions_update_targets_intended_row(self, db):
        exp = await Experience.initialize()
        await exp._insert(new_record=(1, 0, 0.0), custom_id=99999)

        exp = await Experience.initialize()
        await exp._update(conditions=exp._get_conditions(custom_id=99999), new_values={"xp": 42}, custom_id=99999)

        exp = await Experience.initialize(user_id=99999)
        assert exp.raw_data[99999][0] == 42

    async def test_experience_archive_unarchive_reset(self, db):
        exp = await Experience.initialize()
        await exp._insert(new_record=(10, 1, 0.0), custom_id=111)

        await exp.archive(user_id=111)
        check = await Experience.initialize(user_id=111)
        assert bool(check.raw_data[111][3])

        await exp.unarchive(user_id=111)
        check = await Experience.initialize(user_id=111)
        assert not check.raw_data[111][3]

        await exp.reset(user_id=111)
        check = await Experience.initialize(user_id=111)
        assert check.raw_data[111][0] == 0

    async def test_welcome_messages_remove(self, db):
        wm = await WelcomeMessages.initialize()
        await wm.add(user_id=222, message_id=333, date=datetime.datetime(2026, 1, 1))

        wm = await WelcomeMessages.initialize()
        removed = await wm.remove(user_id=222)
        assert removed == 333

        check = await WelcomeMessages.initialize()
        assert 222 not in check.raw_data


class TestFilterMechanics:
    @pytest.mark.asyncio
    async def test_bool_filter_excludes_archived(self, db):
        exp = await Experience.initialize()
        await exp._insert(new_record=(1, 0, 0.0), custom_id=111)
        await exp._insert(new_record=(1, 0, 0.0), custom_id=444)
        await exp.archive(user_id=444)

        filtered = await Experience.initialize(archived=False)
        assert 444 not in filtered.raw_data
        assert 111 in filtered.raw_data

    def test_extended_column_condition_and_param_dropped_together(self):
        """Experience.initialize(extended=True) itself is broken today (see
        test_known_bugs.py::test_experience_extended_initialize), so this exercises
        apply_conditions's extended-column stripping directly, without a real join."""

        class FakeSelf:
            def __init__(self, conditions, extended_columns):
                self.conditions = conditions
                self._extended_columns = extended_columns

            def _get_extended_columns(self):
                return self._extended_columns

        captured = {}

        @apply_conditions()
        def fake_update(self, conditions, condition_params, **kw):
            captured["conditions"] = conditions
            captured["condition_params"] = condition_params

        fake = FakeSelf(
            conditions=[
                ("ARCHIVED = 1", ()),          # non-extended, 0 params
                ("PET_ASHWINDER = ?", (True,)),  # extended col, 1 param -> must be stripped together
                ("XP = ?", (99,)),             # non-extended, 1 param -> must survive
            ],
            extended_columns=["PET_ASHWINDER"],
        )
        fake_update(fake)

        assert "PET_ASHWINDER" not in captured["conditions"]
        assert captured["condition_params"] == [99]
