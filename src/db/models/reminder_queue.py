from src.db.engine import Database, sql_full_table_validator


class ReminderQueue(Database):
    ''' every reminder due today, so a restart or a failed send never loses one - see memory.
    Times are unix timestamps; a row is removed once sent, a missed one 24 h after its deadline '''

    table = "reminder_queue"

    def __init__(self):
        super().__init__()

        self.types = {"date":"datetime", "missed":"bool"}

    # the live DB comes from a Dropbox backup that may predate the queue, so the schema is
    # created here on every run instead of only in the blank seed - see memory
    @classmethod
    async def ensure_schema(cls):
        await cls.run_query('''CREATE TABLE IF NOT EXISTS "reminder_queue" (
                                   "id"          INTEGER NOT NULL UNIQUE,
                                   "name"        TEXT    NOT NULL,
                                   "date"        INTEGER NOT NULL,
                                   "send_at"     INTEGER NOT NULL,
                                   "deadline"    INTEGER NOT NULL,
                                   "event_start" INTEGER DEFAULT NULL,
                                   "event_end"   INTEGER DEFAULT NULL,
                                   "event_id"    INTEGER DEFAULT NULL,
                                   "next_try"    INTEGER NOT NULL DEFAULT 0,
                                   "last_error"  TEXT    DEFAULT NULL,
                                   "missed"      INTEGER NOT NULL DEFAULT 0,
                                   PRIMARY KEY("id" AUTOINCREMENT),
                                   UNIQUE("name", "date"));''')

        # last planned day, NULL until the first plan ever ran
        await cls.run_query('''INSERT OR IGNORE INTO "extra_variables" VALUES('reminder_queue_planned', 'datetime', NULL);''')

    # add a reminder
    @sql_full_table_validator
    async def add(self, name, date, send_at, deadline, event_window=None, missed=False):
        event_start, event_end = event_window or (None, None)

        await self._insert(new_record=(name, date, send_at, deadline),
                           defaults={"event_start": event_start,
                                     "event_end":   event_end,
                                     "missed":      missed})

    # change columns of one reminder
    async def change(self, entry_id, **new_values):
        await self._update(conditions=self._get_conditions(custom_id=entry_id), new_values=new_values, custom_id=entry_id)

    # remove one reminder
    async def remove(self, entry_id):
        await self._delete(conditions=self._get_conditions(custom_id=entry_id), id=entry_id)

    # return reminders, oldest send first
    def get(self):
        return sorted(self._get_values_from_raw_data(self.raw_data, add_id=True), key=lambda entry: entry["send_at"])
