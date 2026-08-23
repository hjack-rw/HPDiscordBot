from src.db.engine import Database, sql_full_table_validator, sql_record_exisits_validator, sql_update_with_valid_keys, sql_create_linked_record, sql_only_one_validator
from src.functions  import parse_xp_amount


class Experience(Database):
    table = "experience"

    def __init__(self):
        super().__init__()

        self.types = {"archived":"bool"}


    # add / subtract / set Experience. also unarchive if done while archived
    @sql_full_table_validator
    @parse_xp_amount
    @sql_create_linked_record
    @sql_update_with_valid_keys(column_names=["pet_ashwinder", "is_new", "user_id", "experience"])
    async def tweak(self, is_new, user_id, experience, **kwargs):
        if is_new:
            await self._insert(new_record=tuple(experience.values()), custom_id=user_id)
        else:
            await self._update(conditions=self._get_conditions(custom_id=user_id), new_values=experience, custom_id=user_id)

        return experience["xp"]

    # unarchive Experience
    @sql_full_table_validator
    @sql_record_exisits_validator()
    async def unarchive(self, user_id):
        try:
            await self._update(conditions=self._get_conditions(custom_id=user_id), new_values={"archived":False}, custom_id=user_id)
        except Exception:
            pass

    # archive Experience - soft lock for leaderboard and reset
    @sql_full_table_validator
    @sql_record_exisits_validator()
    async def archive(self, user_id):
        try:
            await self._update(conditions=self._get_conditions(custom_id=user_id), new_values={"archived":True}, custom_id=user_id)
        except Exception:
            pass

    # reset Experience
    @sql_full_table_validator
    @sql_record_exisits_validator(not_archived=True)
    async def reset(self, user_id):
        await self._update(conditions=self._get_conditions(custom_id=user_id), new_values={"xp":0, "level":0, "progress":0.0}, custom_id=user_id)

    # return Experience
    def get(self, multiple=True):
        if multiple:
            return self._get_values_from_raw_data(self.raw_data, add_id=True, omitted=["archived"])
        return next(iter(self._get_values_from_raw_data(self.raw_data, omitted=["progress", "archived"])), None)

    # special return Experience from dict
    def get_from_dict(self, user_id):
        try:
            return self._get_values_from_raw_data({user_id: self.raw_data[user_id]}, omitted=["progress", "archived"])[0]
        except KeyError:
            return None


class ExperienceInfo(Database):
    table = "experience_info"

    def __init__(self):
        super().__init__()

        self.types = {"pet_from_sea":"bool", "pet_dog":"bool", "pet_ashwinder":"bool", "pet_thestral":"bool", "offset":"bool", "archived":"bool"}

    # add ExperienceInfo
    @sql_full_table_validator
    async def add(self, user_id, pet_ashwinder, defaults=None):
        await self._insert(new_record=(pet_ashwinder,), custom_id=user_id, defaults=defaults)

    # change ExperienceInfo
    @sql_only_one_validator
    @sql_update_with_valid_keys(column_names=["username", "pet_from_sea", "pet_dog", "pet_ashwinder", "pet_thestral", "favourite_color", "offset"])
    async def change(self, **kwargs):
        await self._update(new_values=kwargs)

    # return ExperienceInfo
    def get(self, multiple=False):
        if multiple:
            return self._get_values_from_raw_data(self.raw_data, add_id=True, omitted=["archived"] if self.extended else [])
        return next(iter(self._get_values_from_raw_data(self.raw_data, omitted=["username", "offset"])), None)
