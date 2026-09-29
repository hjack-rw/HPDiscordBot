from datetime    import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from io          import BytesIO
from os          import environ, getcwd, getenv, makedirs, path
from shutil      import copyfile
from threading   import Thread
from traceback   import format_exc
from urllib.parse  import urlparse, parse_qs
from urllib.request import urlopen
from zipfile      import ZipFile

# requests is imported lazily inside the Dropbox helpers below, not here - the health-check
# listener must bind before paying for that heavier import chain, see memory

# duplicated from src/variables.py - src isn't importable yet here
LOG_PATH = path.join(getcwd(), "data", "bot.log")

DROPBOX_TOKEN_URL       = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_DOWNLOAD_URL    = "https://content.dropboxapi.com/2/files/download"
DROPBOX_LIST_FOLDER_URL = "https://api.dropboxapi.com/2/files/list_folder"
# duplicated from src/functions/backups.py - src isn't importable yet here
DROPBOX_BACKUP_FOLDER = "/Projects/DiscordBOT/backups"
DB_PREFIX             = "db_"
ASSETS_PREFIX         = "assets_"
DEGRADED_BOOT_ENV     = "DEGRADED_BOOT"


def _early_log(message):
    makedirs(path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as file:
        file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} {message}\n")


def _dropbox_access_token():
    import requests
    response = requests.post(DROPBOX_TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "refresh_token": getenv("DROPBOX_REFRESH_TOKEN"),
        "client_id":     getenv("DROPBOX_APP_KEY"),
        "client_secret": getenv("DROPBOX_APP_SECRET"),
    })
    response.raise_for_status()
    return response.json()["access_token"]


def _dropbox_latest_backups(access_token):
    ''' (newest assets zip entry, newest DB zip entry) - either can be None '''
    import requests
    response = requests.post(DROPBOX_LIST_FOLDER_URL, headers={"Authorization": f"Bearer {access_token}"},
                              json={"path": DROPBOX_BACKUP_FOLDER})
    # a missing folder is an empty one - nothing backed up yet, not a failed fetch, see memory
    if response.status_code == 409 and response.json().get("error_summary", "").startswith("path/not_found"):
        return None, None
    response.raise_for_status()
    entries = response.json()["entries"]

    def latest(prefix):
        matching = [entry for entry in entries if entry["name"].startswith(prefix)]
        return max(matching, key=lambda entry: entry["server_modified"]) if matching else None

    return latest(ASSETS_PREFIX), latest(DB_PREFIX)


def _dropbox_download(dropbox_path, access_token):
    import json
    import requests
    headers = {"Authorization": f"Bearer {access_token}", "Dropbox-API-Arg": json.dumps({"path": dropbox_path})}
    response = requests.post(DROPBOX_DOWNLOAD_URL, headers=headers)
    response.raise_for_status()
    return response.content


def _fetch_zips():
    ''' zips to extract, in order: the newest full assets backup (else the ASSET_ZIP_URL seed),
    then the newest DB backup on top of it - DB and assets are backed up separately, see memory '''
    assets_raw = db_raw = None

    if getenv("DROPBOX_REFRESH_TOKEN"):
        try:
            access_token = _dropbox_access_token()
            assets, db = _dropbox_latest_backups(access_token)
            if assets:
                assets_raw = _dropbox_download(assets["path_lower"], access_token)
            # a DB zip older than the assets zip means its upload failed right after the assets
            # one - the assets zip carries the newer DB then
            if db and (assets is None or db["server_modified"] >= assets["server_modified"]):
                db_raw = _dropbox_download(db["path_lower"], access_token)
        except Exception as error:
            assets_raw = db_raw = None
            # the seed is older than the backups - keep this process from backing it up over
            # them, backups.py skips the rotation while this is set, see memory
            environ[DEGRADED_BOOT_ENV] = "1"
            _early_log(f"fetch_assets: backup fetch failed ({error}), falling back to ASSET_ZIP_URL, backups off until restart")

    url = getenv("ASSET_ZIP_URL")
    if assets_raw is None and url:
        with urlopen(url) as response:
            assets_raw = response.read()

    return [raw for raw in (assets_raw, db_raw) if raw is not None]


def _ensure_server_config():
    ''' seeds server_config.toml from the example so a clean instance (no asset source
    configured) can still start, instead of crashing at import time - see memory '''
    config_path    = path.join(getcwd(), "server_config.toml")
    example_path   = path.join(getcwd(), "server_config.example.toml")

    if not path.exists(config_path) and path.exists(example_path):
        copyfile(example_path, config_path)
        _early_log("fetch_assets: server_config.toml missing, seeded from server_config.example.toml")


def fetch_assets():
    ''' Fetches gitignored assets - prefers the latest Dropbox backup, falls back to
    ASSET_ZIP_URL. Must run before src is imported. '''
    if getenv("SKIP_ASSET_FETCH", "False") == "True":
        _early_log("fetch_assets: SKIP_ASSET_FETCH=True, skipping")
        _ensure_server_config()
        return

    zips = _fetch_zips()
    if not zips:
        _early_log("fetch_assets: no asset source configured, skipping")
        _ensure_server_config()
        return

    entry_count = 0
    for raw in zips:
        # a dead/replaced share link serves an HTML error page, not a 404 - fail loudly, unlike
        # the unset case above: a configured-but-broken source means something is actually wrong - see memory
        if not raw.startswith(b"PK"):
            raise RuntimeError(f"fetch_assets: source did not return a zip file (got {raw[:80]!r})")

        with ZipFile(BytesIO(raw)) as archive:
            # manual extraction works around a backslash-path zip bug - see memory
            entry_count += len(archive.infolist())
            for member in archive.infolist():
                normalized = member.filename.replace("\\", "/")
                target = path.join(getcwd(), *normalized.split("/"))

                if normalized.endswith("/"):
                    makedirs(target, exist_ok=True)
                    continue

                makedirs(path.dirname(target), exist_ok=True)
                with archive.open(member) as source, open(target, "wb") as dest:
                    dest.write(source.read())

    _early_log(f"fetch_assets: extracted {entry_count} entries")


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlparse(self.path).path

        if route == "/logs":
            self._serve_logs()
        elif route == "/":
            self._serve_index()
        else:
            self.send_response(200)
            self.end_headers()

    def _serve_index(self):
        # no secrets here - this is the public root, unlike /logs
        body = ("<!doctype html><title>HPDiscordBot</title>"
                "<h1>HPDiscordBot</h1><ul><li><a href=\"/logs\">/logs</a> (needs ?key=...)</li></ul>").encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _serve_logs(self):
        # gated behind LOG_ACCESS_KEY - unset means disabled, not open
        access_key = getenv("LOG_ACCESS_KEY")
        query_key = parse_qs(urlparse(self.path).query).get("key", [None])[0]

        if not access_key or query_key != access_key:
            self.send_response(403)
            self.end_headers()
            return

        try:
            with open(LOG_PATH, "rb") as file:
                contents = file.read()
        except FileNotFoundError:
            contents = b""

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(contents)

    def log_message(self, format, *args):
        pass


def start_health_check_server():
    # host expects something listening on PORT to consider the deploy healthy
    port = int(getenv("PORT", 8080))
    HTTPServer(("0.0.0.0", port), HealthCheckHandler).serve_forever()


def record_crash():
    # makes an uncaught exception visible via /logs too - see memory
    makedirs(path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as file:
        file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} CRASH\n{format_exc()}\n")


if __name__ == '__main__':
    Thread(target=start_health_check_server, daemon=True).start()

    try:
        fetch_assets()
        from src import bot, bot_token
        bot.run(bot_token)
    except Exception:
        record_crash()
        raise


#TODO! if people start using it, auto-delete from diagon-alley


#TODO! sprout:
# trigger on herbology related stuff:
# - weekly plants,
# - own timers for plants with notification for the server:
# -- for own timers use create_a_task that is run on restart of the bot:
# create_a_task(timer={"hours":0, "minutes":0, "seconds":0}).start(event_info={"id": 1})

# -- the times are from the database. while creating save to database. after executing delete
# -- limit for user that is set in code (2 for testing)
# -- seperate into aquatic and non aquatic


## CRAZY IDEAS ##

#TODO! subscription system:
# - pick a subscription and add the role to members before the event
# - clear all subscriptions on another button
# - IMPORTANT: check if clearing the role keeps the notification!

#TODO! image host:
# - upload file to the server, store only part of the link in db
# - replace old files on image host
# - show all filenames
# - delete file if removed from db

#TODO! a queue for all events this day so if the bot restarts he knows if he has to send something
# - when they trigger normally just remove them

#TODO! portkey:
# - automatic add to a paste service

#TODO! db changes:
# - update multiple, instead of just one?
# - multiple primary keys?