from src.db.engine import Database, permutation

from copy import deepcopy


class ExtraVariable(Database):
    table = "extra_variables"

    def __init__(self):
        super().__init__()

        self.types = {"value":0}

        self.all_columns_init_validator = True
        self.one_row_init_validator     = True

    # change the value of ExtraVariable
    async def change(self, to):
        value = next(iter(self._get_values_from_raw_data(self.raw_data)))["value"]

        if type(value) == permutation:
            value = deepcopy(value)
            value.instance = to
            to = value

        await self._update(new_values={"value":to})

    # return ExtraVariable
    def get(self):
        value = next(iter(self._get_values_from_raw_data(self.raw_data)))["value"]
        if type(value) == permutation:
            return value.instance
        return value
