import src.variables as vars

from .core import log, session

from asyncio  import to_thread
from hashlib  import sha256
from io       import BytesIO
from os       import getcwd, getenv, path, walk
from time     import time
from urllib.request import urlopen
from zipfile  import ZipFile, ZIP_DEFLATED

import json


DROPBOX_TOKEN_URL       = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_UPLOAD_URL      = "https://content.dropboxapi.com/2/files/upload"
DROPBOX_DOWNLOAD_URL    = "https://content.dropboxapi.com/2/files/download"
DROPBOX_LIST_FOLDER_URL = "https://api.dropboxapi.com/2/files/list_folder"
DROPBOX_DELETE_URL      = "https://api.dropboxapi.com/2/files/delete_v2"
DROPBOX_BACKUP_FOLDER   = "/Projects/DiscordBOT/backups"
DB_PREFIX               = "db_"
ASSETS_PREFIX           = "assets_"
MAX_BACKUPS             = 3
BASE_SOURCE             = "base"
# set by main.py's fetch_assets when a Dropbox error made it boot from the seed
DEGRADED_BOOT_ENV       = "DEGRADED_BOOT"

# duplicated from src/db/engine/base.py - importing Database here would cycle back
# through src.db.models -> src.functions
DATABASE_PATH = path.join(getcwd(), "data", "__database__.db")


def _db_files():
    ''' [(file_path, arcname)] for the DB + config - ~10 KB, changes often '''
    files = [(DATABASE_PATH, "data/__database__.db"),
             (path.join(getcwd(), "server_config.toml"), "server_config.toml")]
    return [(file_path, arcname) for file_path, arcname in files if path.exists(file_path)]


def _image_files():
    ''' [(file_path, arcname)] for images, sorted so the fingerprint is stable - ~8 MB, rarely
    changes; fonts are left out, they're tracked in git '''
    files = []
    for directory, _, filenames in walk(vars.image_data_path):
        for filename in filenames:
            file_path = path.join(directory, filename)
            files.append((file_path, path.relpath(file_path, getcwd()).replace(path.sep, "/")))

    return sorted(files, key=lambda file: file[1])


def _fingerprint(files):
    digest = sha256()
    for file_path, arcname in files:
        digest.update(arcname.encode() + b"\0")
        with open(file_path, "rb") as file:
            digest.update(file.read())

    return digest.hexdigest()[:12]


def _build_zip(files):
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for file_path, arcname in files:
            archive.write(file_path, arcname=arcname)

    return buffer.getvalue()


def _newest_of_kind(entries, prefix):
    matching = [entry for entry in entries if entry["name"].startswith(prefix)]
    return max(matching, key=lambda entry: entry["server_modified"]) if matching else None


def _newest_assets_fingerprint(entries):
    ''' the images fingerprint baked into the newest assets_<time>_<fingerprint>.zip name -
    None for pre-split assets_<time>.zip backups, which forces one fresh upload '''
    newest = _newest_of_kind(entries, ASSETS_PREFIX)
    if newest is None:
        return None

    parts = newest["name"].removesuffix(".zip").split("_")
    return parts[2] if len(parts) == 3 else None


def _get_access_token():
    response = session.post(DROPBOX_TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "refresh_token": getenv("DROPBOX_REFRESH_TOKEN"),
        "client_id":     getenv("DROPBOX_APP_KEY"),
        "client_secret": getenv("DROPBOX_APP_SECRET"),
    })
    response.raise_for_status()
    return response.json()["access_token"]


def _upload(dropbox_path, data, access_token):
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "Dropbox-API-Arg": json.dumps({"path": dropbox_path, "mode": "add", "mute": True}),
        "Content-Type":    "application/octet-stream",
    }
    response = session.post(DROPBOX_UPLOAD_URL, headers=headers, data=data)
    response.raise_for_status()


def _list_backups(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = session.post(DROPBOX_LIST_FOLDER_URL, headers=headers, json={"path": DROPBOX_BACKUP_FOLDER})
    # a missing folder is an empty one - the next upload recreates it, see memory
    if response.status_code == 409 and response.json().get("error_summary", "").startswith("path/not_found"):
        return []
    response.raise_for_status()
    return response.json()["entries"]


def _delete(dropbox_path, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = session.post(DROPBOX_DELETE_URL, headers=headers, json={"path": dropbox_path})
    response.raise_for_status()


def _download(dropbox_path, access_token):
    headers = {"Authorization": f"Bearer {access_token}", "Dropbox-API-Arg": json.dumps({"path": dropbox_path})}
    response = session.post(DROPBOX_DOWNLOAD_URL, headers=headers)
    response.raise_for_status()
    return response.content


def _upload_backup_rotation_sync():
    ''' a full assets zip (DB + config + images) only when the images differ from the newest
    one, then a DB + config zip every run - images are ~99% of the bytes and every byte counts
    against the host's bandwidth cap, see memory '''
    # a seed boot after a Dropbox error runs on stale data - uploading it would become the
    # newest backup and prune the real ones, see memory
    if getenv(DEGRADED_BOOT_ENV):
        log("backup rotation skipped: degraded boot (Dropbox fetch failed), restart to retry")
        return

    access_token = _get_access_token()
    stamp = int(time())
    db_files = _db_files()

    # assets first - an assets zip newer than the DB zip is harmless, the reverse leaves
    # Images rows pointing at files no backup has. No images means a broken boot, never
    # let that become the newest assets zip
    image_files = _image_files()
    if image_files:
        fingerprint = _fingerprint(image_files)
        if fingerprint != _newest_assets_fingerprint(_list_backups(access_token)):
            _upload(f"{DROPBOX_BACKUP_FOLDER}/{ASSETS_PREFIX}{stamp}_{fingerprint}.zip", _build_zip(db_files + image_files), access_token)

    _upload(f"{DROPBOX_BACKUP_FOLDER}/{DB_PREFIX}{stamp}.zip", _build_zip(db_files), access_token)

    # prune each kind down to MAX_BACKUPS, oldest first
    entries = _list_backups(access_token)
    for prefix in (DB_PREFIX, ASSETS_PREFIX):
        kind = sorted((entry for entry in entries if entry["name"].startswith(prefix)), key=lambda entry: entry["server_modified"])
        for entry in kind[:-MAX_BACKUPS]:
            _delete(entry["path_lower"], access_token)


async def upload_backup_rotation():
    ''' pushes a fresh DB zip (plus a full assets zip when images changed) into
    DROPBOX_BACKUP_FOLDER and prunes each kind down to MAX_BACKUPS - see memory for the read side '''
    if not getenv("DROPBOX_REFRESH_TOKEN"):
        return

    await to_thread(_upload_backup_rotation_sync)


def _list_backup_sources_sync():
    sources = [("Base (seed)", BASE_SOURCE)]

    if not getenv("DROPBOX_REFRESH_TOKEN"):
        return sources

    access_token = _get_access_token()
    entries = sorted(_list_backups(access_token), key=lambda entry: entry["server_modified"], reverse=True)
    sources += [(entry["name"], entry["path_lower"]) for entry in entries]

    return sources


async def list_backup_sources():
    ''' [("Base (seed)", "base"), ...live Dropbox backups newest-first] - for populating
    the redeploy command's source picker '''
    return await to_thread(_list_backup_sources_sync)


def _fetch_source_zip_bytes_sync(source):
    if source == BASE_SOURCE:
        url = getenv("ASSET_ZIP_URL")
        if not url:
            raise RuntimeError("redeploy: ASSET_ZIP_URL is not configured")
        with urlopen(url) as response:
            return response.read()

    access_token = _get_access_token()
    return _download(source, access_token)


async def fetch_source_zip_bytes(source):
    ''' source is "base" or a Dropbox path_lower from list_backup_sources() '''
    return await to_thread(_fetch_source_zip_bytes_sync, source)


def split_backup_zip(raw_bytes):
    ''' Parses a backup/seed zip into (db_bytes_or_None, {normalized_path: file_bytes}) -
    manual per-entry extraction to work around the same backslash-path zip bug fetch_assets()
    (main.py) works around; never touches Database, see module comment above '''
    db_bytes = None
    other_files = {}

    with ZipFile(BytesIO(raw_bytes)) as archive:
        for member in archive.infolist():
            normalized = member.filename.replace("\\", "/")
            if normalized.endswith("/"):
                continue

            with archive.open(member) as file:
                data = file.read()

            if normalized == "data/__database__.db":
                db_bytes = data
            else:
                other_files[normalized] = data

    return db_bytes, other_files
