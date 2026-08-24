import src.variables as vars

import inspect

from datetime import datetime
from os       import makedirs, path

import requests
session = requests.Session()


_log_dir_ready = False

def log(message):
    ''' print()-alike: prints while any test_bot flag is set (local dev), otherwise appends
    a timestamped, caller-tagged line to data/bot.log - a real deployment has no console to
    watch, so the caller's module.function:line is prefixed automatically (see memory) rather
    than relying on every call site to spell it out by hand. '''
    global _log_dir_ready

    caller = inspect.stack()[1]
    origin = f"{path.splitext(path.basename(caller.filename))[0]}.{caller.function}:{caller.lineno}"
    entry  = f"{origin}: {message}"

    if vars.is_test_mode():
        print(entry)
    else:
        if not _log_dir_ready:
            makedirs(path.dirname(vars.log_path), exist_ok=True)
            _log_dir_ready = True

        with open(vars.log_path, "a", encoding="utf-8") as file:
            file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} {entry}\n")
