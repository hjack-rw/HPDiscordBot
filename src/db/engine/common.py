import asyncio


module_name    = "aiosqlite"
db_access_lock = asyncio.Lock()

class DatabaseError(Exception):
    """Base for all errors raised by the DB engine."""

class RecordNotFoundError(DatabaseError):
    """An UPDATE/DELETE targeted a record that doesn't exist (matched zero rows), or a
    validator expected a loaded record that isn't there."""

class IdAlreadyExistsError(DatabaseError):
    pass

def popattr(obj, attr_name, default=None):
    if hasattr(obj, attr_name):
        value = getattr(obj, attr_name)
        delattr(obj, attr_name)
        return value
    return default

def check_variable(self, variables:list, reverse=False):
    """Check the variables in question if == True"""

    result = any(getattr(self, name, False) for name in variables)
    return not result if reverse else result
