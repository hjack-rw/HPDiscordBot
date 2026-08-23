import functools
import inspect

from src.db.engine.common import module_name, check_variable, DatabaseError, RecordNotFoundError


# Validators
############################################################################################################

def sql_full_table_validator(func):
    """Validator if the table was loaded fully"""

    @functools.wraps(func)
    async def validator(self, *args, **kwargs):
        if not check_variable(self, variables=["conditions", "is_shortened", "extended"]):
            return await func(self, *args, **kwargs)

        raise DatabaseError(f"{module_name} table error: can only '{func.__name__}' with fully loaded table that is not extended")

    return validator

def sql_only_one_validator(func):
    """Validate if more than one record was loaded"""

    @functools.wraps(func)
    async def validator(self, *args, **kwargs):
        return_empty = kwargs.pop("return_empty", False)

        # prepare new_kwargs dict for func
        new_kwargs = kwargs.copy()

        if not check_variable(self, variables=["is_shortened"]):
            if len(self.raw_data) == 1:
                return await func(self, *args, **new_kwargs)
            elif return_empty and len(self.raw_data) == 0:
                return None

        raise DatabaseError(f"{module_name} table error: can only '{func.__name__}' with one record loaded")

    return validator

def sql_update_with_valid_keys(column_names):
    """Validate if keys used to update are valid"""

    def run(func):
        @functools.wraps(func)
        async def validator(self, *args, **kwargs):
            valid_keys = [self._get_id_column(), *column_names]
            invalid_keys = [key for key in kwargs if key not in valid_keys]
            if invalid_keys:
                raise ValueError(f"{module_name} table error: invalid columns in kwargs: {invalid_keys}")

            return await func(self, *args, **kwargs)
        return validator
    return run

def sql_record_exisits_validator(not_archived=False):
    """Validate if record exisits in the loaded data"""

    def run(func):
        @functools.wraps(func)
        async def validator(self, *args, **kwargs):
            try:
                column_id = self._get_id_column()
                record = {kwargs[column_id]: self.raw_data[kwargs[column_id]]}

                if not_archived:
                    if next(iter(self._get_values_from_raw_data(record)))["archived"]:
                        raise DatabaseError(f"{module_name} table error: the {column_id.upper()} in question is ARCHIVED")
                return await func(self, *args, **kwargs)
            except KeyError:
                raise RecordNotFoundError(f"{module_name} table error: no such record in the database")
        return validator
    return run

# Decorators
############################################################################################################

def sql_create_linked_record(func):
    """Create linked table record"""

    @functools.wraps(func)
    async def decorator(self, *args, **kwargs):
        is_new = kwargs.get("is_new", False)
        result = await func(self, *args, **kwargs)

        # if the main table is new
        if is_new:

            # check if linked record already exsits
            column_id = self._get_id_column()
            if await self.get_joined_table(**{column_id:kwargs[column_id]}) is None:

                # create a new kwargs with the gotten key-value pairs
                add_params = [param for param in inspect.signature(self.joined_table.add).parameters.values() if param.name != "self"]
                needed_kwargs = {param.name: kwargs.get(param.name) for param in add_params}

                try:
                    # only flag as missing if truly required (no default in the target signature)
                    missing_params = [param.name for param in add_params
                                       if param.default is inspect.Parameter.empty and needed_kwargs[param.name] is None]

                    # not enough parameters provided
                    if missing_params:
                        raise DatabaseError("missing required parameters: " + ", ".join(missing_params))

                    await (await self.joined_table.initialize()).add(**needed_kwargs)
                except Exception as error:
                    raise DatabaseError(f"{module_name} table error: failed to create a link with '{self._get_joined_table_name()}' for '{self.__class__.__name__}'\n Error:{str(error)}")

        return result
    return decorator
