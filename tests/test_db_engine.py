import datetime
import os

import pytest

from src.db import Database, Experience, Images, Portkeys, WelcomeMessages
from src.db.engine import DatabaseError, IdAlreadyExistsError, RecordNotFoundError
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

    async def test_add_writes_bytes_to_disk_not_the_database(self, db):
        """Images is metadata-only now (filename + message_id + folder) - the bytes live on
        disk under database_path/images/<folder>/<filename>, not in a DB column. folder is
        derived from the filename's own '<folder>__<name>' prefix - 'apple.png' carries none,
        so it falls into the 'misc' bucket."""

        images = await Images.initialize()
        await images.add("apple.png", b"raw-bytes")

        stored_path = os.path.join(Images.database_path, "images", "misc", "apple.png")
        assert os.path.exists(stored_path)
        with open(stored_path, "rb") as file:
            assert file.read() == b"raw-bytes"

    async def test_get_returns_a_file_pointing_at_the_stored_bytes(self, db):
        """Real stored filenames carry no extension before the double-underscore split
        (e.g. 'pet__badger') - get() always appends '.png' itself, matching the
        attachment://<name>.png convention print_suitcase relies on."""

        images = await Images.initialize()
        await images.add("pet__badger", b"pet-bytes")

        images = await Images.initialize(filename__has="pet")
        file = images.get()
        assert file.filename == "badger.png"
        with open(file.fp.name if hasattr(file.fp, "name") else file.fp, "rb") as raw:
            assert raw.read() == b"pet-bytes"


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
        """Exercises apply_conditions's extended-column stripping directly (no real join
        needed) - see test_regressions.py::test_experience_extended_initialize for the
        real end-to-end extended=True path."""

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


class TestErrorHandling:
    def test_exception_hierarchy(self):
        assert issubclass(DatabaseError, Exception)
        assert issubclass(RecordNotFoundError, DatabaseError)
        assert issubclass(IdAlreadyExistsError, DatabaseError)

    @pytest.mark.asyncio
    async def test_update_with_no_matching_row_raises_record_not_found(self, db):
        """A WHERE clause that matches zero rows must raise loudly, not report success -
        this is the exact bug class that made Images.add(replace=True) silently no-op."""

        exp = await Experience.initialize()
        await exp._insert(new_record=(1, 0, 0.0), custom_id=111)

        exp = await Experience.initialize(user_id=111)
        # simulate a cache/DB desync: row gone from the DB, still present in raw_data
        await db.run_query(query="DELETE FROM experience WHERE user_id = ?;", params=[111])

        with pytest.raises(RecordNotFoundError):
            await exp._update(conditions=exp._get_conditions(custom_id=111), new_values={"xp": 99}, custom_id=111)

    @pytest.mark.asyncio
    async def test_delete_with_no_matching_row_raises_record_not_found(self, db):
        wm = await WelcomeMessages.initialize()
        await wm.add(user_id=222, message_id=333, date=datetime.datetime(2026, 1, 1))

        wm = await WelcomeMessages.initialize()
        await db.run_query(query="DELETE FROM welcome_messages WHERE user_id = ?;", params=[222])

        with pytest.raises(RecordNotFoundError):
            await wm._delete(conditions=wm._get_conditions(custom_id=222), id=222)


class TestBackupRestore:
    @pytest.mark.asyncio
    async def test_backup_writes_dump_file_off_the_event_loop(self, db):
        """backup() became async (asyncio.to_thread wrapping the blocking sqlite3/file I/O)
        so it no longer stalls the event loop mid-command; this confirms it still awaits
        correctly and actually produces a dump file."""

        dump_path = os.path.join(Database.database_path, f"{Database.database_name}-dump")
        assert not os.path.exists(dump_path)

        await Database.backup()

        assert os.path.exists(dump_path)
        assert os.path.getsize(dump_path) > 0


class TestAutoincrementInsert:
    """Portkeys is the only table without an explicit custom_id - its INSERT relies on
    SQLite assigning the id and get_sql_values/_insert reading it back via lastrowid,
    instead of predicting it upfront with an extra _get_last_id() round-trip."""

    @pytest.mark.asyncio
    async def test_insert_without_custom_id_assigns_and_caches_the_real_id(self, db):
        pk = await Portkeys.initialize()
        await pk._insert(new_record=(555, 1, False, None, "0000000000000000", None, None, None, None))

        pk = await Portkeys.initialize()
        assert 1 in pk.raw_data  # first row in a fresh AUTOINCREMENT table is id=1
        assert pk.raw_data[1][1] == 555  # index 0 is message_id (has a schema default)

    @pytest.mark.asyncio
    async def test_second_autoincrement_insert_gets_a_new_id(self, db):
        pk = await Portkeys.initialize()
        await pk._insert(new_record=(555, 1, False, None, "0000000000000000", None, None, None, None))

        pk = await Portkeys.initialize()
        await pk._insert(new_record=(666, 1, False, None, "0000000000000000", None, None, None, None))

        pk = await Portkeys.initialize()
        assert set(pk.raw_data.keys()) == {1, 2}
        assert pk.raw_data[2][1] == 666
