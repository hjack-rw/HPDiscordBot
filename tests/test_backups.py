import io
import json
import os
import zipfile

import pytest
import requests

import main
import src.variables as vars
from src.functions import backups


def _zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for arcname, data in files.items():
            archive.writestr(arcname, data)
    return buffer.getvalue()


def _entry(name, modified):
    return {"name": name, "path_lower": f"{backups.DROPBOX_BACKUP_FOLDER}/{name}", "server_modified": modified}


def _dropbox_error(error_summary):
    """What Dropbox answers a route error with - 409 and a JSON error_summary."""
    response = requests.Response()
    response.status_code = 409
    response.url = backups.DROPBOX_LIST_FOLDER_URL
    response._content = json.dumps({"error_summary": error_summary}).encode()
    return response


@pytest.fixture
def live_files(tmp_path, monkeypatch):
    """A fake live instance in tmp_path: DB + config + one image + one font."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "images" / "pets").mkdir(parents=True)
    (tmp_path / "data" / "fonts").mkdir(parents=True)
    (tmp_path / "data" / "__database__.db").write_bytes(b"db")
    (tmp_path / "server_config.toml").write_bytes(b"config")
    (tmp_path / "data" / "images" / "pets" / "owl.png").write_bytes(b"owl")
    (tmp_path / "data" / "fonts" / "MAGIC.ttf").write_bytes(b"font")

    monkeypatch.setattr(backups, "DATABASE_PATH", str(tmp_path / "data" / "__database__.db"))
    monkeypatch.setattr(vars, "image_data_path", str(tmp_path) + "/data/images/")
    monkeypatch.setattr(vars, "font_data_path", str(tmp_path) + "/data/fonts/")
    return tmp_path


@pytest.fixture
def fake_dropbox(monkeypatch):
    """In-memory stand-in for the Dropbox folder the rotation writes to."""
    store = {"entries": [], "uploads": [], "deleted": []}

    def upload(dropbox_path, data, access_token):
        name = dropbox_path.rsplit("/", 1)[1]
        store["uploads"].append((name, data))
        store["entries"].append(_entry(name, f"2026-09-29T12:00:{len(store['entries']):02d}Z"))

    def delete(dropbox_path, access_token):
        store["deleted"].append(dropbox_path)
        store["entries"] = [entry for entry in store["entries"] if entry["path_lower"] != dropbox_path]

    monkeypatch.setattr(backups, "_get_access_token", lambda: "token")
    monkeypatch.setattr(backups, "_list_backups", lambda access_token: list(store["entries"]))
    monkeypatch.setattr(backups, "_upload", upload)
    monkeypatch.setattr(backups, "_delete", delete)
    return store


def _uploaded_names(store):
    return [name for name, _ in store["uploads"]]


class TestUploadBackupRotation:
    def test_first_run_uploads_a_full_assets_zip_then_a_db_zip(self, live_files, fake_dropbox):
        backups._upload_backup_rotation_sync()

        assets_zip, db_zip = fake_dropbox["uploads"]
        assert assets_zip[0].startswith("assets_")
        assert db_zip[0].startswith("db_")

        # fonts are tracked in git, so they're never backed up
        assert sorted(zipfile.ZipFile(io.BytesIO(assets_zip[1])).namelist()) == ["data/__database__.db", "data/images/pets/owl.png", "server_config.toml"]
        assert sorted(zipfile.ZipFile(io.BytesIO(db_zip[1])).namelist()) == ["data/__database__.db", "server_config.toml"]

    def test_unchanged_assets_are_not_uploaded_again(self, live_files, fake_dropbox):
        backups._upload_backup_rotation_sync()
        backups._upload_backup_rotation_sync()

        names = _uploaded_names(fake_dropbox)
        assert [name.split("_")[0] for name in names] == ["assets", "db", "db"]

    def test_changed_image_triggers_a_new_assets_upload(self, live_files, fake_dropbox):
        backups._upload_backup_rotation_sync()
        (live_files / "data" / "images" / "pets" / "owl.png").write_bytes(b"new owl")
        backups._upload_backup_rotation_sync()

        assets = [name for name in _uploaded_names(fake_dropbox) if name.startswith("assets_")]
        assert len(assets) == 2
        assert assets[0].split("_")[2] != assets[1].split("_")[2]

    def test_pre_split_assets_zip_forces_one_fresh_assets_upload(self, live_files, fake_dropbox):
        fake_dropbox["entries"].append(_entry("assets_1790684086.zip", "2026-09-29T11:00:00Z"))

        backups._upload_backup_rotation_sync()

        assert any(name.startswith("assets_") for name in _uploaded_names(fake_dropbox))

    def test_missing_images_never_become_the_newest_assets_zip(self, live_files, fake_dropbox):
        # fonts stay - they ship with the repo, so they're present even on a broken boot
        os.remove(live_files / "data" / "images" / "pets" / "owl.png")

        backups._upload_backup_rotation_sync()

        assert [name.split("_")[0] for name in _uploaded_names(fake_dropbox)] == ["db"]

    def test_degraded_boot_skips_the_whole_rotation(self, live_files, fake_dropbox, monkeypatch):
        monkeypatch.setattr(backups, "log", lambda message: None)
        monkeypatch.setenv(backups.DEGRADED_BOOT_ENV, "1")

        backups._upload_backup_rotation_sync()

        assert fake_dropbox["uploads"] == []

    def test_prunes_each_kind_to_max_backups_independently(self, live_files, fake_dropbox):
        fake_dropbox["entries"] += [_entry(f"assets_{i}_old{i}.zip", f"2026-09-2{i}T00:00:00Z") for i in range(1, 4)]
        fake_dropbox["entries"] += [_entry(f"db_{i}.zip", f"2026-09-2{i}T00:00:00Z") for i in range(1, 4)]

        backups._upload_backup_rotation_sync()

        names = [entry["name"] for entry in fake_dropbox["entries"]]
        assert len([name for name in names if name.startswith("db_")]) == backups.MAX_BACKUPS
        assert len([name for name in names if name.startswith("assets_")]) == backups.MAX_BACKUPS
        assert "db_1.zip" not in names
        assert "assets_1_old1.zip" not in names


class TestListBackups:
    def test_missing_backup_folder_lists_as_empty(self, monkeypatch):
        monkeypatch.setattr(backups.session, "post", lambda *args, **kwargs: _dropbox_error("path/not_found/.."))

        assert backups._list_backups("token") == []

    def test_other_list_errors_still_raise(self, monkeypatch):
        monkeypatch.setattr(backups.session, "post", lambda *args, **kwargs: _dropbox_error("path/not_folder/.."))

        with pytest.raises(requests.HTTPError):
            backups._list_backups("token")


class TestFetchAssets:
    @pytest.fixture
    def boot(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "refresh")
        monkeypatch.delenv("SKIP_ASSET_FETCH", raising=False)
        monkeypatch.delenv("ASSET_ZIP_URL", raising=False)
        monkeypatch.setattr(main, "LOG_PATH", str(tmp_path / "data" / "bot.log"))
        monkeypatch.setattr(main, "_dropbox_access_token", lambda: "token")
        yield tmp_path
        # fetch_assets sets it straight on os.environ, which monkeypatch doesn't track
        os.environ.pop(main.DEGRADED_BOOT_ENV, None)

    @pytest.fixture
    def seed(self, monkeypatch):
        raw = _zip_bytes({"data/__database__.db": b"seed db"})
        monkeypatch.setenv("ASSET_ZIP_URL", "https://example.invalid/seed.zip")
        monkeypatch.setattr(main, "urlopen", lambda url: io.BytesIO(raw))
        return raw

    def test_newer_db_zip_overlays_the_newest_assets_zip(self, boot, monkeypatch):
        blobs = {
            "/assets": _zip_bytes({"data/__database__.db": b"stale db", "data/images/pets/owl.png": b"owl"}),
            "/db":     _zip_bytes({"data/__database__.db": b"fresh db", "server_config.toml": b"config"}),
        }
        monkeypatch.setattr(main, "_dropbox_latest_backups", lambda access_token: (
            {"path_lower": "/assets", "server_modified": "2026-09-29T10:00:00Z"},
            {"path_lower": "/db",     "server_modified": "2026-09-29T12:00:00Z"},
        ))
        monkeypatch.setattr(main, "_dropbox_download", lambda dropbox_path, access_token: blobs[dropbox_path])

        main.fetch_assets()

        assert (boot / "data" / "__database__.db").read_bytes() == b"fresh db"
        assert (boot / "data" / "images" / "pets" / "owl.png").read_bytes() == b"owl"
        assert (boot / "server_config.toml").read_bytes() == b"config"

    def test_db_zip_older_than_the_assets_zip_is_not_overlaid(self, boot, monkeypatch):
        blobs = {"/assets": _zip_bytes({"data/__database__.db": b"newer db", "data/images/pets/owl.png": b"owl"})}
        monkeypatch.setattr(main, "_dropbox_latest_backups", lambda access_token: (
            {"path_lower": "/assets", "server_modified": "2026-09-29T12:00:00Z"},
            {"path_lower": "/db",     "server_modified": "2026-09-29T11:00:00Z"},
        ))
        monkeypatch.setattr(main, "_dropbox_download", lambda dropbox_path, access_token: blobs[dropbox_path])

        main.fetch_assets()

        assert (boot / "data" / "__database__.db").read_bytes() == b"newer db"

    def test_missing_assets_backup_falls_back_to_the_seed_under_the_db_zip(self, boot, monkeypatch):
        seed = _zip_bytes({"data/__database__.db": b"seed db", "data/images/pets/owl.png": b"seed owl"})
        monkeypatch.setenv("ASSET_ZIP_URL", "https://example.invalid/seed.zip")
        monkeypatch.setattr(main, "urlopen", lambda url: io.BytesIO(seed))
        monkeypatch.setattr(main, "_dropbox_latest_backups", lambda access_token: (
            None, {"path_lower": "/db", "server_modified": "2026-09-29T12:00:00Z"}))
        monkeypatch.setattr(main, "_dropbox_download", lambda dropbox_path, access_token: _zip_bytes({"data/__database__.db": b"fresh db"}))

        main.fetch_assets()

        assert (boot / "data" / "__database__.db").read_bytes() == b"fresh db"
        assert (boot / "data" / "images" / "pets" / "owl.png").read_bytes() == b"seed owl"

    @pytest.fixture
    def db_download_fails(self, monkeypatch):
        monkeypatch.setattr(main, "_dropbox_latest_backups", lambda access_token: (
            {"path_lower": "/assets", "server_modified": "2026-09-29T10:00:00Z"},
            {"path_lower": "/db",     "server_modified": "2026-09-29T12:00:00Z"},
        ))

        def download(dropbox_path, access_token):
            if dropbox_path == "/db":
                raise RuntimeError("dropbox down")
            return _zip_bytes({"data/__database__.db": b"backup db"})

        monkeypatch.setattr(main, "_dropbox_download", download)

    def test_dropbox_failure_falls_back_to_the_seed_alone(self, boot, seed, db_download_fails):
        main.fetch_assets()

        assert (boot / "data" / "__database__.db").read_bytes() == b"seed db"

    def test_dropbox_failure_marks_the_boot_degraded(self, boot, seed, db_download_fails):
        main.fetch_assets()

        assert os.environ.get(main.DEGRADED_BOOT_ENV) == "1"

    def test_missing_backup_folder_does_not_mark_the_boot_degraded(self, boot, seed, monkeypatch):
        monkeypatch.setattr(requests, "post", lambda *args, **kwargs: _dropbox_error("path/not_found/.."))

        main.fetch_assets()

        assert main.DEGRADED_BOOT_ENV not in os.environ
