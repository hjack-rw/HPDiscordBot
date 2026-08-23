import src.variables as vars

from datetime import datetime
from os       import makedirs, path

import requests
session = requests.Session()


_log_dir_ready = False

def log(message):
    ''' print()-alike: prints while any test_bot flag is set (local dev), otherwise appends
    a timestamped line to data/bot.log - a real deployment has no console to watch. '''
    global _log_dir_ready

    if vars.is_test_mode():
        print(message)
    else:
        if not _log_dir_ready:
            makedirs(path.dirname(vars.log_path), exist_ok=True)
            _log_dir_ready = True

        with open(vars.log_path, "a", encoding="utf-8") as file:
            file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} {message}\n")
