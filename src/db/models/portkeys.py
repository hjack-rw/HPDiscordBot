from src.db.engine import Database, sql_full_table_validator, sql_only_one_validator, sql_update_with_valid_keys
from src.functions  import parse_portkey_data


class Portkeys(Database):
    table = "portkeys"

    def __init__(self):
        super().__init__()

        self.types = {"from_wb":"bool", "multiple_choice":"binary_16", "birthday":"datetime"}

    # add Portkey
    @sql_full_table_validator
    @parse_portkey_data
    async def add(self, portkey):
        await self._insert(new_record=portkey)

    # unarchive Portkey (update with message_id)
    @sql_only_one_validator
    @sql_update_with_valid_keys(column_names=["message_id"])
    async def unarchive(self, **kwargs):
        await self._update(new_values=kwargs)

    # archive Portkey (remove message_id)
    @sql_only_one_validator
    async def archive(self):
        try:
            message_id = self.get_one_column("message_id")
            await self._update(new_values={"message_id":None})
            return message_id
        except TypeError:
            return None

    # return Portkey / Portkeys
    def get(self, multiple=False):
        if multiple:
            return [portkey["user_id"] for portkey in self._get_values_from_raw_data(self.raw_data)]
        return next(iter(self._get_values_from_raw_data(self.raw_data, add_id=True)), None)
