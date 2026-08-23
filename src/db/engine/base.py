import aiosqlite
import asyncio
import functools
import io
import os
import re
import sqlite3

from collections import namedtuple

from src.db.engine.common      import module_name, db_access_lock, popattr, DatabaseError, RecordNotFoundError
from src.db.engine.conversions import permutation, convert_int_to_date, convert_date_to_int, is_binary, check_type
from src.db.engine.clauses     import Filter, apply_selected_columns, apply_conditions, apply_order, get_sql_values, get_update_clause


QueryResult = namedtuple("QueryResult", ["rowcount", "lastrowid"])


# SQL connection
############################################################################################################

class Database():
    database_path    = os.getcwd() + "/data/"
    schema_seed_path = os.getcwd() + "/src/db/"
    database_name    = "__database__.db"

    con = None

    def __init__(self):
        self.columns  = {}
        self.raw_data = {}

    @classmethod
    async def connect(cls):
        """CONNECT to database"""

        if getattr(cls, 'con', None):
            return cls.con

        os.makedirs(cls.database_path, exist_ok=True)
        DB_PATH = os.path.join(cls.database_path, cls.database_name)

        try:
            cls.con = await aiosqlite.connect(DB_PATH)
            return cls.con

        except aiosqlite.Error as error:
            raise DatabaseError(f"{module_name} CONNECT error: {str(error)}!")

    @classmethod
    async def disconnect(cls):
        """CLOSE the database"""

        if getattr(cls, 'con', None):
            try:
                await cls.con.close()
            except aiosqlite.Error as error:
                print(f"{module_name} CLOSE error: {str(error)}!")
            finally:
                cls.con = None

    @classmethod
    async def reconnect(cls, retry_delay=2):
        """RECONNECT to database"""

        await cls.disconnect()

        while cls.con is None:
            try:
                cls.con = await cls.connect()
            except Exception:
                await asyncio.sleep(retry_delay)

    def _ensure_connection(func):
        @functools.wraps(func)
        async def decorator(cls, *args, **kwargs):

            # wait if restore is in progress
            async with db_access_lock:
                pass

            # a hybrid connection
            if not getattr(cls, 'con', None):
                await cls.connect()

            return await func(cls, *args, **kwargs)

        return decorator

    @classmethod
    @_ensure_connection
    async def run_query(cls, query, params=(), fetch=False):
        """Run a DB Query"""

        if not isinstance(params, (tuple, list)):
            raise DatabaseError(f"{module_name} QUERY error: params must be a tuple or list for parameterized queries")

        try:
            async with cls.con.execute(query, params) as cur:
                if fetch:
                    return await cur.fetchall()
                result = QueryResult(rowcount=cur.rowcount, lastrowid=cur.lastrowid)

            await cls.con.commit()
            return result

        except aiosqlite.Error as error:
            raise DatabaseError(f"{module_name} QUERY error: {str(error)}")

    @classmethod
    async def backup(cls):
        """BACKUP database to a dump file"""

        DB_PATH = os.path.join(cls.database_path, cls.database_name)
        DUMP_PATH = cls.database_path + f"{cls.database_name}-dump"

        def _do_backup():
            with sqlite3.connect(DB_PATH) as con:
                with io.open(DUMP_PATH, mode="w", encoding="utf-8") as file:

                    # iterdump() function
                    for line in con.iterdump():
                        file.write('%s\n' % line)

        try:
            # blocking sqlite3/file I/O off the event loop thread
            await asyncio.to_thread(_do_backup)
        except sqlite3.Error as error:
            raise DatabaseError(f"sqlite3 BACKUP error: {str(error)}")

    @classmethod
    async def restore(cls, clear=False):
        """Restore database from a dump file"""

        DB_PATH   = os.path.join(cls.database_path, cls.database_name)
        DUMP_PATH = os.path.join(cls.schema_seed_path if clear else cls.database_path,
                                  f"{cls.database_name}-{'blank' if clear else 'dump'}")

        def _do_restore():
            errors = []

            # delete existing DB file
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)

            with sqlite3.connect(DB_PATH) as con:
                with open(DUMP_PATH, "r", encoding="utf-8") as dump_file:
                    statement = ""
                    for line in dump_file:
                        stripped = line.strip()

                        # skip comments or empty lines
                        if not stripped or stripped.startswith("--"):
                            continue

                        statement += line

                        if stripped.endswith(";"):  # better to check end of line
                            try:
                                con.execute(statement.strip())
                            except Exception as error:
                                errors.append(f"Failed: {statement}\nError: {error}")
                            statement = ""

                con.commit()

            if errors:
                raise DatabaseError("\n\n".join(errors))

        # exclusive lock
        async with db_access_lock:
            await cls.disconnect()
            os.makedirs(cls.database_path, exist_ok=True)

            try:
                # blocking sqlite3/file I/O off the event loop thread
                await asyncio.to_thread(_do_restore)
            except Exception as error:
                raise DatabaseError(f"sqlite3 RESTORE error: {str(error)}")

            await cls.connect()

    @classmethod
    async def disable_journal(cls):
        """Restore database from a dump file"""

        await cls.run_query(query="PRAGMA journal_mode=DELETE;")
        await cls.run_query(query="VACUUM;")

    @classmethod
    async def is_empty(cls):
        """Check if the database is empty"""

        # check if any tables exist excluding internal SQLite tables
        command = "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        table_count = (await cls.run_query(command, fetch=True))[0][0]  # fetch returns list of tuples

        return table_count == 0


# Basic SQL commands
############################################################################################################

    @apply_selected_columns()
    @apply_conditions(is_select=True)
    @apply_order
    async def _select(self, table, columns, conditions, condition_params, order):
        """Command SELECT"""

        join = ""

        # check if the table has been extended
        if getattr(self, "extended", False):
            id_column = self._get_id_column()
            join = f"INNER JOIN {self._get_joined_table_name()} USING ({id_column})"

        # execute query, SELECT
        try:
            command = f"SELECT {columns} FROM {table} {join} {conditions} {order};"
            command = re.sub(r'\s+;', ';', command)
            rows    = await self.run_query(command, params=condition_params, fetch=True)

            return {row[0]:tuple(row[1:]) for row in rows}
        except Exception as error:
            raise DatabaseError(f"{module_name} SELECT error! faulty command:\n'{command}'\n{str(error)}")

    @apply_conditions()
    async def _update(self, conditions, condition_params, new_values, custom_id=None):
        """Command UPDATE"""

        update, record, sql_values, id = get_update_clause(self, new_values, custom_id)

        # execute query, UPDATE
        try:
            command = f"UPDATE {self.table} SET {update} {conditions};".replace("None", "NULL")
            result = await self.run_query(query=command, params=sql_values + list(condition_params))
        except Exception as error:
            raise DatabaseError(f"{module_name} UPDATE error! faulty values:\n'{sql_values}'\n{str(error)}")

        if not result.rowcount:
            raise RecordNotFoundError(f"{module_name} UPDATE error: no record matched for '{self.table}' (id={id})")

        # replace the changed value in record
        self.raw_data[id] = tuple(record)

    @apply_selected_columns(is_insert=True)
    async def _insert(self, required_columns, defaults, new_record, custom_id=None):
        """Command INSERT"""

        # get columns/values for a new record; the row itself is written to raw_data only
        # after the insert actually succeeds (and we know its real id, for autoincrement)
        columns, sql_values, entire_row = await get_sql_values(self, required_columns, defaults, new_record, custom_id)

        # prepare the record to be inserted
        columns_sql = ", ".join(columns).upper()
        values      = ", ".join(["?" for _ in sql_values])

        # execute query, INSERT
        try:
            command = f"INSERT INTO {self.table} ({columns_sql}) VALUES ({values});"
            result = await self.run_query(query=command, params=sql_values)
        except Exception as error:
            raise DatabaseError(f"{module_name} INSERT error: failed to add to the database! values:\n'{sql_values}'\n{str(error)}")

        id = custom_id if custom_id is not None else result.lastrowid
        self.raw_data[id] = entire_row

    @apply_conditions()
    async def _delete(self, conditions, condition_params, id):
        """Command DELETE"""

        # protect from deleting nonexistant
        try:
            record = self.raw_data[id]
        except KeyError:
            raise RecordNotFoundError(f"{module_name} DELETE error: no such record in the database! id={id}")

        try:
            command = f"DELETE FROM {self.table} {conditions};"
            result = await self.run_query(query=command, params=condition_params)
        except Exception as error:
            raise DatabaseError(f"{module_name} DELETE error! command:\n'{command}'\n{str(error)}")

        if not result.rowcount:
            raise RecordNotFoundError(f"{module_name} DELETE error: no record matched for '{self.table}' (id={id})")

        del self.raw_data[id]

        # return the deleted record
        return {id: record}

    async def _get_columns(self, types={}, omitted_columns=[], specified_columns=[]):
        """Get column names and basic info"""

        types_dict = {"INTEGER":"int",
                      "REAL":   "float",
                      "NUMERIC":"undetermined",   # Float or Int
                      "TEXT":   "str",
                      "BLOB":   "binary_object",} # Binary Large Object

        types_dict.update(types)

        # execute query, PRAGMA: get column info
        command = f"PRAGMA table_info({self.table});"
        columns = await self.run_query(query=command, fetch=True)

        # execute query, PRAGMA: extended the column info with the columns from joined_table
        if getattr(self, "extended", False):
            command        = f"PRAGMA table_info({self._get_joined_table_name()});"
            columns_origin = await self.run_query(query=command, fetch=True)
        else:
            columns_origin = []

        all_columns = {}
        for idx, (_, column_name, type, not_null, default, is_pk) in enumerate(columns + columns_origin):

            if "+" in column_name or "-" in column_name:
                raise DatabaseError(f"{module_name} table error: '+' / '-' cannot appear in the column name!")

            # skip redefinition if already processed
            if column_name in all_columns:
                continue

            # keep pk
            if not is_pk:
                if (specified_columns and column_name not in specified_columns) or (column_name in omitted_columns):
                    all_columns[column_name] = True if idx >= len(columns) else None
                    continue

            all_columns[column_name] = {"is_pk":       bool(is_pk),
                                        "type":        types_dict.pop(column_name, types_dict[type]),
                                        "not_null":    bool(not_null),
                                        "default":     self._parse_sqlite_default(default),
                                        "extended":    idx >= len(columns)}

        return all_columns

# SQL I/O
############################################################################################################

    def _get_value(self, value, type):
        """ Convert out of DB value """

        if value is None:
            return None
        elif "binary_" in type:
            if type == "binary_object":
                value = io.BytesIO(value)
                value.seek(0)
                return value
            return f"{int(value):0{int(type.split('_')[1])}b}"
        elif type == "bool":
            return bool(value)
        elif type == "datetime":
            return convert_int_to_date(value)
        elif type == "str":
            return value
        elif "permutation" in type:
            return permutation(value, requirements=type.split('_'))
        return value

    def _return_value(self, value, type):
        """ Convert to DB value """

        try:
            type = type.__name__
        except AttributeError:
            pass

        if value is None:
            return None
        elif type == "bool":
            return int(value)
        elif type == "datetime":
            return convert_date_to_int(value)
        elif type == "permutation":
            return value.convert_permutation_to_int()
        elif type == "str":
            if is_binary(value):
                return int(value, 2)
            return value
        return value

    def _parse_sqlite_default(self, value: str):
        """ Convert DB PRAGMA defult value """

        if value is None:
            return None
        value = value.strip("'\"")  # remove wrapping quotes if any
        if value.upper() in ('NULL', ''):
            return Filter.NONE  # placeholder for NULL
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return value

# Database structure
############################################################################################################

    @classmethod
    async def get_joined_table(cls, get_kwargs=None, **kwargs):
        get_kwargs = get_kwargs or {}
        return (await cls.joined_table.initialize(**kwargs)).get(**get_kwargs)

    def get_one_column(self, column):
        return next(iter(self._get_specific_value_from_raw_data(self.raw_data, column)), None)

    @classmethod
    async def initialize(cls, extended=False, **kwargs):
        if type(self := cls()) is Database:
            raise DatabaseError(f"{module_name} table error: cannot initialize 'Database' directly!")

        # validator for tables that need all columns loaded
        if popattr(self, "all_columns_init_validator", False):
            if {"omitted_columns", "specified_columns"} & kwargs.keys():
                raise DatabaseError(f"{module_name} table error: needs to load all rows for '{self.__class__.__name__}'")

        if extended:
            self.extended = True

        self.columns  = await self._setup_table(types=popattr(self, "types", {}), **kwargs)
        self.raw_data = await self._select(self.table)

        # validator for tables that can have only one row loaded at the time
        if popattr(self, "one_row_init_validator", False):
            if len(self.raw_data) > 1:
                raise DatabaseError(f"{self.table} can only be loaded one at the time")
            elif getattr(self, "is_shortened", False):
                raise DatabaseError(f"{self.table} can only be loaded fully")

        return self

    async def _setup_table(self, types={}, **kwargs):
        """Setup filters and sorting of the table"""

        omitted_columns   = kwargs.pop("omitted_columns",   [])
        specified_columns = kwargs.pop("specified_columns", [])
        order             = kwargs.pop("order",             [])

        # protect from excluding specified
        if omitted_columns in specified_columns:
            raise DatabaseError(f"{module_name} FILTER error: 'specified_columns' and 'omitted_columns' can't overlap!")


        columns = await self._get_columns(types, omitted_columns, specified_columns)

        if not all((columns.values())):
            self.is_shortened = True

        allowed_filters = set(self._get_imported_columns(columns))

        replacements = {"below":      "less",
                        "belowequal": "lessequal",
                        "upper":      "great",
                        "upperequal": "greatequal",}

        allowed_specs = {"less":       "<",
                         "lessequal":  "<=",
                         "great":      ">",
                         "greatequal": ">=",
                         "inequal":    "<>"}

        text_spec = {"has", "like"}

        # set conditions based on the filters
        self.conditions = []
        for key, value in kwargs.items():

            # specification on certain variables
            try:
                key, spec = key.split("__")
                spec = spec.split("_")[0]
            except ValueError:
                key, spec = next(iter(key.split("__"))), None

            if key not in allowed_filters:
                raise DatabaseError(f"{module_name} FILTER error: filter '{key}' can't be applied to the requested data/table!")

            self.conditions.append(await self._build_condition(key, spec, value, columns, text_spec, replacements, allowed_specs))

        # set order in columns
        self.order = []
        for column in order:

            column_name, spec = column[:-1], column[-1]

            if spec not in ["+", "-"]:
                raise DatabaseError(f"{module_name} order error: the last character has to be '+' / '-' !")
            elif column_name not in list(columns.keys()):
                raise DatabaseError(f"{module_name} order error: the '{column_name}' does not exsit or was not loaded!")

            self.order.append(column_name.upper() + (" ASC" if spec == "+" else " DESC"))

        # columns dict {"column_name":...}
        return columns

    async def _build_condition(self, key, spec, value, columns, text_spec, replacements, allowed_specs):
        """Build the (sql_fragment, params_tuple) pair for one filter kwarg."""

        type = columns[key]["type"]

        # if value has the correct type apply conditions
        if type != "bool":

            # int / float / undetermined / datetime / binary / permutation / binary_object
            if type != "str":
                if type == "int":

                    # except accepted keywords
                    if key == "id" and value in ["last"]:
                        value = await self._get_last_id()

                    elif key == "message_id" and value in ["archived", "unarchived"]:
                        null_condition = Filter.NULL.value.replace("*", key.upper())

                        if value == "unarchived":
                            null_condition = null_condition.replace("IS", "IS NOT")

                        return (null_condition, ())

                    elif isinstance(value, str):
                        raise DatabaseError(f"{module_name} FILTER error: '{value}' is not an accepted keyword!")

                elif "permutation" in type:
                    permutation_value = permutation(0, requirements=type.split('_'))
                    permutation_value.instance = value
                    value = permutation_value

                check_type(key, value, type, spec, required={"is_numeric":True,
                                                             "is_text":   False})

                condition, params = key.upper() + Filter.STANDARD.value, (self._return_value(value, type),)

            # string
            else:
                if spec and spec not in text_spec:
                    type = "int"

                check_type(key, value, type, spec, required={"is_numeric":False,
                                                             "is_text":   True})

                if spec:
                    if spec not in text_spec:
                        condition, params = Filter.SUBSTR.value.replace("*", key.upper()) + "?", (value,)
                    elif spec == "has":
                        condition, params = Filter.HAS.value.replace("*", key.upper()) + "?", (self._return_value(value, type),)
                    else:
                        condition, params = key.upper() + Filter.LIKE.value, (f"%{value}%",)
                else:
                    condition, params = key.upper() + Filter.STANDARD.value, (self._return_value(value, type),)

        # bool
        elif type == "bool" and check_type(key, value, type, spec, required={"is_numeric":True,
                                                                             "is_text":   False}):
            value_filter = Filter.BOOL_T if value else Filter.BOOL_F
            condition, params = value_filter.value.replace("*", key.upper()), ()

        # apply specification
        if spec and spec not in text_spec:
            condition = condition.replace("=", allowed_specs[replacements.get(spec, spec)])

        return (condition, params)

    def _get_values_from_raw_data(self, raw, add_id=False, omitted=[], specified=[]):
        """ Return the table records in a list of dict """

        # protect from excluding specified
        if omitted in specified:
            raise DatabaseError(f"{module_name} FILTER error: 'specified' and 'omitted' can't overlap!")

        return_list = []
        for idx, instance in raw.items():
            temp_dict = {}

            for idx_column, column in enumerate(self._get_imported_columns(), -1):
                is_pk , value_type, _, _, _  = self.columns[column].values()

                if is_pk:
                    if add_id:
                        temp_dict[column] = idx
                    continue

                if (specified and column not in specified) or (column in omitted):
                    continue

                temp_dict[column] = self._get_value(instance[idx_column], self._get_type_from_column(value_type))

            return_list.append(temp_dict)

        return return_list

    def _get_specific_value_from_raw_data(self, raw, specified):
        """ Return the specific value from the table records """

        columns = self._get_imported_columns()

        # protect from returning non-existent
        if specified not in columns:
            raise DatabaseError(f"{module_name} FILTER error: '{specified}' not in columns!")
        else:
            idx_column = columns.index(specified) - 1
            value_type = self.columns[specified]["type"]
            is_pk      = self.columns[specified]["is_pk"]

        return_list = []
        for idx, instance in raw.items():
            value = idx if is_pk else self._get_value(instance[idx_column], self._get_type_from_column(value_type))

            return_list.append(value)

        return return_list

    def _get_type_from_column(self, value_type):
        """ Return value_type from another column if needed """

        if isinstance(value_type, int):
            return next(iter(self.raw_data.values()))[value_type]
        return value_type

    #NOTE! only one ID supported at the time, the first Primary Key
    def _get_id_column(self):
        return next(filter(lambda item: item[1]["is_pk"], self.columns.items()))[0]

    def _get_imported_columns(self, columns=None):
        columns = columns if columns is not None else getattr(self, "columns", {})
        return [name for name,meta in columns.items() if isinstance(meta, dict)]

    def _get_extended_columns(self):
        return [name for name,meta in self.columns.items() if isinstance(meta, dict) and meta["extended"]]

    async def _get_last_id(self):
        return int(next(iter((await self._select(table="sqlite_sequence", conditions=[("NAME" + Filter.STANDARD.value, (self.table,))])).values()))[0])

    # if with @sql_full_table_validator but need id
    def _get_conditions(self, custom_id):
        return [(self._get_id_column().upper() + Filter.STANDARD.value, (custom_id,))]

    @staticmethod
    def _get_filename_short(filename):
        if "__" in filename:
            return filename.split("__")[1]
        return filename

    @classmethod
    def _get_joined_table_name(cls):
        return cls.joined_table.table
