import src.variables as vars

from .core import session

from asyncio  import to_thread
from io       import BytesIO
from os       import getcwd, getenv, path, walk
from time     import time
from zipfile  import ZipFile, ZIP_DEFLATED

import json


DROPBOX_TOKEN_URL       = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_UPLOAD_URL      = "https://content.dropboxapi.com/2/files/upload"
DROPBOX_LIST_FOLDER_URL = "https://api.dropboxapi.com/2/files/list_folder"
DROPBOX_DELETE_URL      = "https://api.dropboxapi.com/2/files/delete_v2"
DROPBOX_BACKUP_FOLDER   = "/HPDiscordBot/backups"
MAX_BACKUPS             = 3

# duplicated from src/db/engine/base.py - importing Database here would cycle back
# through src.db.models -> src.functions
DATABASE_PATH = path.join(getcwd(), "data", "__database__.db")


def _build_backup_zip():
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        if path.exists(DATABASE_PATH):
            archive.write(DATABASE_PATH, arcname="data/__database__.db")

        config_path = path.join(getcwd(), "server_config.toml")
        if path.exists(config_path):
            archive.write(config_path, arcname="server_config.toml")

        for root in (vars.image_data_path, vars.font_data_path):
            for directory, _, filenames in walk(root):
                for filename in filenames:
                    file_path = path.join(directory, filename)
                    archive.write(file_path, arcname=path.relpath(file_path, getcwd()).replace(path.sep, "/"))

    return buffer.getvalue()


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
    response.raise_for_status()
    return response.json()["entries"]


def _delete(dropbox_path, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = session.post(DROPBOX_DELETE_URL, headers=headers, json={"path": dropbox_path})
    response.raise_for_status()


def _upload_backup_rotation_sync():
    access_token = _get_access_token()
    zip_bytes = _build_backup_zip()

    _upload(f"{DROPBOX_BACKUP_FOLDER}/assets_{int(time())}.zip", zip_bytes, access_token)

    # prune down to MAX_BACKUPS, oldest first
    entries = sorted(_list_backups(access_token), key=lambda entry: entry["server_modified"])
    for entry in entries[:-MAX_BACKUPS]:
        _delete(entry["path_lower"], access_token)


async def upload_backup_rotation():
    ''' pushes a fresh backup zip into DROPBOX_BACKUP_FOLDER and prunes down to MAX_BACKUPS -
    see memory for the read side '''
    if not getenv("DROPBOX_REFRESH_TOKEN"):
        return

    await to_thread(_upload_backup_rotation_sync)
