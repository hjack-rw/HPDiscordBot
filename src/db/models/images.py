import os

from src.db.engine import Database, sql_full_table_validator

from discord.file import File


class Images(Database):
    table = "images"

    def __init__(self):
        super().__init__()

        self.all_columns_init_validator = True

    @classmethod
    def _images_dir(cls):
        """Filesystem home for image bytes, sibling to the live DB file - re-derived from
        database_path on every call (not frozen at import time) so it still follows
        database_path when a test fixture redirects it to a tmp dir."""

        path = os.path.join(cls.database_path, "images")
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def _get_folder(filename):
        """Category folder a filename belongs to, derived from its existing '<folder>__<name>'
        naming convention (the same prefix filename__has= filters already key on) - no
        separate folder input needed on add()."""

        return filename.split("__")[0] if "__" in filename else "misc"

    # add Image
    @sql_full_table_validator
    async def add(self, filename, image, replace=False):
        folder_path = os.path.join(self._images_dir(), self._get_folder(filename))
        os.makedirs(folder_path, exist_ok=True)

        if not replace:
            await self._insert(new_record=(self._get_folder(filename),), custom_id=filename)

        with open(os.path.join(folder_path, filename), "wb") as file:
            file.write(image)

    # return Images
    def get(self, multiple=False):
        if multiple:
            return {filename_short: File(fp=os.path.join(self._images_dir(), row["folder"], row["filename"]), filename=f"{filename_short}.png")
                     for row in self._get_values_from_raw_data(self.raw_data, add_id=True)
                     if (filename_short := self._get_filename_short(row["filename"]))}

        if row := next(iter(self._get_values_from_raw_data(self.raw_data, add_id=True)), None):
            filename_short = self._get_filename_short(row["filename"])
            return File(fp=os.path.join(self._images_dir(), row["folder"], row["filename"]), filename=f"{filename_short}.png")
        return None

    # return only Filenames
    def get_filenames(self):
        return self._get_specific_value_from_raw_data(self.raw_data, "filename")
