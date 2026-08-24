from src.db.engine import Database, permutation, RecordNotFoundError

from copy import deepcopy


class ExtraVariable(Database):
    table = "extra_variables"

    def __init__(self):
        super().__init__()

        self.types = {"value":0}

        self.all_columns_init_validator = True
        self.one_row_init_validator     = True

    def _raw_value(self):
        row = next(iter(self._get_values_from_raw_data(self.raw_data)), None)
        if row is None:
            raise RecordNotFoundError(f"extra_variables table error: no matching row for {self.conditions} - is the blank schema seed missing it?")
        return row["value"]

    # change the value of ExtraVariable
    async def change(self, to):
        value = self._raw_value()

        if type(value) == permutation:
            value = deepcopy(value)
            value.instance = to
            to = value

        await self._update(new_values={"value":to})

    # return ExtraVariable
    def get(self):
        value = self._raw_value()
        if type(value) == permutation:
            return value.instance
        return value
