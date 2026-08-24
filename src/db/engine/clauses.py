from enum import Enum

import io
import re

from src.db.engine.common      import module_name, DatabaseError, IdAlreadyExistsError
from src.db.engine.conversions import permutation


# Clauses
############################################################################################################

def apply_selected_columns(is_insert=False):
    """Apply correct formatting for selected columns"""

    def run(func):

        # standard apply: handle shortened or extended mode
        def apply(self, *args, **kwargs):

            if getattr(self, "is_shortened", False) or getattr(self, "extended", False):
                kwargs["columns"] = ", ".join(self._get_imported_columns()).upper()
            else:
                kwargs["columns"] = "*"
            return func(self, *args, **kwargs)

        # special apply for INSERT
        def apply_for_insert(self, *args, **kwargs):

            kwargs["required_columns"] = sum(1 for _,meta in self.columns.items() if not meta.get('is_pk') and meta.get('default') is None)

            kwargs["defaults"] = kwargs.get("defaults") or {}

            if custom_id := kwargs.pop("custom_id", None):
                kwargs["custom_id"] = self._return_value(custom_id, type(custom_id))

            return func(self, *args, **kwargs)

        if is_insert:
            return apply_for_insert
        return apply
    return run

class Filter(Enum):
    NONE     = ""
    STANDARD = " = ?"
    BOOL_T   = "* = 1"
    BOOL_F   = "* = 0"
    NULL     = "* IS NULL"
    LIKE     = " LIKE ?"
    HAS      = "substr(*, 1, instr(*, '_') - 1) = "
    SUBSTR   = "instr(*, '__') > 0 AND CAST(substr(*, instr(*, '_') + 1, instr(*, '__') - instr(*, '_') - 1) AS INTEGER) = "

def apply_conditions(is_select=False):
    """Apply correct formatting for conditions. Each condition is a (sql_fragment, params_tuple) pair;
    params travel with their condition so filtering (e.g. dropping extended-column conditions) can never
    desync a params list from the condition strings it belongs to."""

    def run(func):
        def apply(self, *args, **kwargs):
            conditions = kwargs.pop("conditions", self.conditions)

            if conditions and not any(condition == Filter.NONE.value for condition, _ in conditions):
                extended_columns = [column.upper() for column in self._get_extended_columns()]

                if is_select:
                    pairs = conditions
                else:
                    pairs = [(condition, params) for condition, params in conditions
                             if all(not re.search(rf"\b{re.escape(col)}\b", condition) for col in extended_columns)]

                clause = " AND ".join(condition for condition, _ in pairs)

                if "*" in clause:
                    raise DatabaseError(f"{module_name} error applying conditions:\n'{clause}'")

                kwargs["conditions"]      = "WHERE " + clause
                kwargs["condition_params"] = [param for _, params in pairs for param in params]
            else:
                kwargs["conditions"]      = ""
                kwargs["condition_params"] = []

            return func(self, *args, **kwargs)

        return apply
    return run

def apply_order(func):
    """Apply correct formatting order"""

    def apply(self, *args, **kwargs):
        kwargs["order"] = ""

        try:
            if self.order:
                kwargs["order"] = "ORDER BY " + ", ".join(self.order)
        except AttributeError:
            pass

        return func(self, *args, **kwargs)

    return apply

async def get_sql_values(self, required_columns, defaults, new_record, custom_id=None):
    """Get sql values for a new record (columns + bound values) before INSERT. For an explicit
    custom_id, its duplicate check happens here. For an autoincrement id, SQLite assigns it on
    insert - the caller reads it back via the query's lastrowid and updates raw_data only after
    the insert actually succeeds, instead of predicting the id with an extra round-trip."""

    sql_values = [custom_id] if custom_id is not None else []

    try:

        # protect from creating duplicates (explicit id only - an autoincrement id can't collide)
        if custom_id is not None and custom_id in self.raw_data:
            raise IdAlreadyExistsError(f"'{custom_id}' is already in the database")

        # determine correct record length
        if len(new_record) != required_columns:
            raise DatabaseError("incorrect number of values for insertion")

        new_record = iter(new_record)

        columns_to_insert, entire_row = [], []
        for column, meta in self.columns.items():

            # skip primary keys, but include in columns to insert (only when custom_id)
            if meta.get("is_pk"):
                if custom_id is not None:
                    columns_to_insert.append(column)
                continue

            # get default value from provided defaults
            elif column in defaults:
                next_value = defaults[column]

            # get default value from table meta
            elif meta.get("default") is not None:
                next_value = None if meta["default"] == Filter.NONE else meta["default"]  # normalize 'NULL' to None
                entire_row.append(next_value)
                continue

            # next value from new_record
            else:
                next_value = next(new_record)

            columns_to_insert.append(column)
            next_value = self._return_value(next_value, type(next_value))  # convert value to the DB format

            entire_row.append(next_value)
            sql_values.append(next_value)

        entire_row = tuple(entire_row)

        # check if new_record is a duplicate (if no custom_id)
        if custom_id is None and entire_row in self.raw_data.values():
            raise IdAlreadyExistsError("is already in the database")

        return columns_to_insert, sql_values, entire_row

    except IdAlreadyExistsError:
        raise
    except Exception as exception:
        raise DatabaseError(f"{module_name} INSERT error: {new_record} {exception}")

def get_update_clause(self, new_values, custom_id=None):
    """Get update clause"""

    id = custom_id

    try:
        # get the only loaded record
        if id is None:
            if len(self.raw_data) != 1:
                raise DatabaseError(f"for more than 1 record loaded ID has to be provided")

            id, record = next(iter(self.raw_data.items()))

        # get the record by id
        else:
            record = self.raw_data[id]

        record = list(record)

        update_clause, sql_values = [], []
        for column,value in new_values.items():

            # get column_id
            try:
                column_id = list(self.columns.keys())[1:].index(column)
            except ValueError:
                if column == self._get_id_column():
                    raise DatabaseError(f"{column} is an ID!")
                raise DatabaseError(f"{column} is not a column name!")

            # get the old value string
            _, value_type, not_null, _, _  = self.columns[column].values()

            # get the old value
            old_value = self._get_value(record[column_id], self._get_type_from_column(value_type))

            # protect from None if not_null
            if not_null and value is None:
                raise DatabaseError(f"data cannot be set to NULL for column '{column}'")

            # protect from mismatched datatypes (except None)
            elif value is not None:
                # BytesIO (read-back BLOB) and raw bytes (fresh write) represent the same data
                is_binary_object_pair = isinstance(old_value, io.BytesIO) and isinstance(value, (bytes, bytearray))
                if old_value is not None and type(old_value) != type(value) and not is_binary_object_pair:
                    raise DatabaseError(f"datatype mismatch for column '{column}'")
                if isinstance(old_value, permutation) and not value.check():
                    raise DatabaseError(f"invalid permutation object for column '{column}'")

            # convert to DB value
            change = self._return_value(value, type(value))
            sql_values.append(change)

            update_clause.append(f"{column.upper()} = ?")

            # convert to DB value
            record[column_id] = change
        return ", ".join(update_clause), record, sql_values, id

    except Exception as exception:
        raise DatabaseError(f"{module_name} UPDATE clause error: {str(exception)}")
