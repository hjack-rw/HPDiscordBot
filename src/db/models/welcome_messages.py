from src.db.engine import Database, sql_full_table_validator


class WelcomeMessages(Database):
    table = "welcome_messages"

    def __init__(self):
        super().__init__()

        self.types = {"date":"datetime"}

    # add WelcomeMessage
    @sql_full_table_validator
    async def add(self, user_id, message_id, date):
        await self._insert(new_record=(message_id, date), custom_id=user_id)

    # remove WelcomeMessage
    @sql_full_table_validator
    async def remove(self, user_id):
        try:
            if deleted_record := await self._delete(conditions=self._get_conditions(custom_id=user_id), id=user_id):
                return self._get_specific_value_from_raw_data(deleted_record, "message_id")[0]
        except Exception:
            return None

    # return WelcomeMessages
    def get(self):
        return self._get_values_from_raw_data(self.raw_data, add_id=True, omitted=["date"])
