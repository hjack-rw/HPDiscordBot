from src.db.engine import Database, sql_full_table_validator

from discord.file import File


class Images(Database):
    table = "images"

    def __init__(self):
        super().__init__()

        self.all_columns_init_validator = True

    # add Image
    @sql_full_table_validator
    async def add(self, filename, image, replace=False):
        if replace:
            await self._update(conditions=self._get_conditions(custom_id=filename), new_values={"data":image}, custom_id=filename)
        else:
            await self._insert(new_record=(image,), custom_id=filename)

    # return Images
    def get(self, multiple=False):
        if multiple:
            return {filename_short:File(fp=image["data"], filename=f"{filename_short}.png") for image in self._get_values_from_raw_data(self.raw_data, add_id=True) if (filename_short := self._get_filename_short(image["filename"]))}

        if image := next(iter(self._get_values_from_raw_data(self.raw_data, add_id=True)), None):
            filename_short = self._get_filename_short(image["filename"])
            return File(fp=image["data"], filename=f"{filename_short}.png")
        return None

    # return only Filenames
    def get_filenames(self):
        return self._get_specific_value_from_raw_data(self.raw_data, "filename")
