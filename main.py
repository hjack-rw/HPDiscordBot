from datetime    import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from io          import BytesIO
from os          import getcwd, getenv, makedirs, path
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
DROPBOX_BACKUP_FOLDER = "/HPDiscordBot/backups"


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


def _dropbox_latest_backup_path(access_token):
    import requests
    response = requests.post(DROPBOX_LIST_FOLDER_URL, headers={"Authorization": f"Bearer {access_token}"},
                              json={"path": DROPBOX_BACKUP_FOLDER})
    response.raise_for_status()
    entries = response.json()["entries"]
    if not entries:
        return None
    return max(entries, key=lambda entry: entry["server_modified"])["path_lower"]


def _dropbox_download(dropbox_path, access_token):
    import json
    import requests
    headers = {"Authorization": f"Bearer {access_token}", "Dropbox-API-Arg": json.dumps({"path": dropbox_path})}
    response = requests.post(DROPBOX_DOWNLOAD_URL, headers=headers)
    response.raise_for_status()
    return response.content


def _fetch_zip_bytes():
    ''' prefers the latest Dropbox backup over the ASSET_ZIP_URL seed - see memory '''
    if getenv("DROPBOX_REFRESH_TOKEN"):
        try:
            access_token = _dropbox_access_token()
            latest_path = _dropbox_latest_backup_path(access_token)
            if latest_path:
                return _dropbox_download(latest_path, access_token)
        except Exception as error:
            _early_log(f"fetch_assets: backup fetch failed ({error}), falling back to ASSET_ZIP_URL")

    url = getenv("ASSET_ZIP_URL")
    if not url:
        return None
    with urlopen(url) as response:
        return response.read()


def fetch_assets():
    ''' Fetches gitignored assets - prefers the latest Dropbox backup, falls back to
    ASSET_ZIP_URL. Must run before src is imported. '''
    if getenv("SKIP_ASSET_FETCH", "False") == "True":
        _early_log("fetch_assets: SKIP_ASSET_FETCH=True, skipping")
        return

    raw = _fetch_zip_bytes()
    if raw is None:
        _early_log("fetch_assets: no asset source configured, skipping")
        return

    with ZipFile(BytesIO(raw)) as archive:
        # manual extraction works around a backslash-path zip bug - see memory
        entry_count = len(archive.infolist())
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
        else:
            self.send_response(200)
            self.end_headers()

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
# - insert without defaults if provided
# - more backups?
# - update multiple, instead of just one?
# - multiple primary keys?