from src.db import *
from src.functions import parse_xp_amount, parse_portkey_data

import copy

from discord.file import File


# Tables
############################################################################################################

class Experience(Database):
    table = "experience"

    def __init__(self, **kwargs):
        self.columns  = self._setup_table(types={"archived":"bool"}, **kwargs)
        self.raw_data = self._select(self.table)
    
    # add / subtract / set Experience. also unarchive if done while archived
    @sql_full_table_validator
    @parse_xp_amount
    @sql_create_connection
    @sql_update_with_valid_keys(column_names=["pet_ashwinder", "is_new", "user_id", "experience"])
    def tweak(self, is_new, user_id, experience, **kwargs):
        if is_new:
            self._insert(new_record=tuple(experience.values()), custom_id=user_id)
        else:
            self._update(conditions=self._get_conditions(id=user_id), new_values=experience, id=user_id)
        
        return experience["xp"]

    # unarchive Experience
    @sql_full_table_validator
    @sql_record_exisits_validator()
    def unarchive(self, user_id):
        try:
            self._update(conditions=self._get_conditions(id=user_id), new_values={"archived":False}, id=user_id)
        except Exception:
            pass

    # archive Experience - soft lock for leaderboard and reset
    @sql_full_table_validator
    @sql_record_exisits_validator()
    def archive(self, user_id):
        try:
            self._update(conditions=self._get_conditions(id=user_id), new_values={"archived":True}, id=user_id)
        except Exception:
            pass

    # reset Experience
    @sql_full_table_validator
    @sql_record_exisits_validator(not_archived=True)
    def reset(self, user_id):
        self._update(conditions=self._get_conditions(id=user_id), new_values={"xp":0, "level":0, "progress":0.0}, id=user_id)

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
    
    def __init__(self, extended=False, **kwargs):
        self.extended = extended
        self.columns  = self._setup_table(types={"pet_from_sea":"bool", "pet_dog":"bool", "pet_ashwinder":"bool", "pet_thestral":"bool", "offset":"bool", "archived":"bool"}, **kwargs)
        self.raw_data = self._select(self.table)
    
    # add ExperienceInfo
    @sql_full_table_validator
    def add(self, user_id, pet_ashwinder):
        self._insert(new_record=(pet_ashwinder,), custom_id=user_id)

    # change ExperienceInfo
    @sql_only_one_validator
    @sql_update_with_valid_keys(column_names=["username", "pet_from_sea", "pet_dog", "pet_ashwinder", "pet_thestral", "favourite_color", "offset"])
    def change(self, **kwargs):
        self._update(new_values=kwargs)
    
    # return ExperienceInfo
    def get(self, multiple=False):
        if multiple:
            return self._get_values_from_raw_data(self.raw_data, add_id=True, omitted=["archived"] if self.extended else [])
        return next(iter(self._get_values_from_raw_data(self.raw_data, omitted=["username", "offset"])), None)


class ExtraVariable(Database):
    table = "extra_variables"

    @sql_entire_table_init_validator
    def __init__(self, **kwargs):  
        self.columns  = self._setup_table(types={"value":0}, **kwargs)
        self.raw_data = self._only_one_variable(self._select(self.table))
    
    # one at the time ExtraVariable validator
    def _only_one_variable(self, raw):
        if len(raw) > 1:
            raise Exception(f"{self.table} can only be loaded one at the time")
        elif getattr(self, "is_shortened", False):
            raise Exception(f"{self.table} can only be loaded fully")
        return raw

    # change the value of ExtraVariable
    def change(self, to):
        value = next(iter(self._get_values_from_raw_data(self.raw_data)))["value"]
        
        if type(value) == permutation:
            value = copy.deepcopy(value)
            value.instance = to
            to = value
        
        self._update(new_values={"value":to})

    # return ExtraVariable
    def get(self):
        value = next(iter(self._get_values_from_raw_data(self.raw_data)))["value"]
        if type(value) == permutation:
            return value.instance
        return value


class Images(Database):
    table = "images"

    @sql_entire_table_init_validator
    def __init__(self, **kwargs):
        self.columns  = self._setup_table(**kwargs)
        self.raw_data = self._select(self.table)
    
    # add Image
    @sql_full_table_validator
    def add(self, filename, image, replace=False):
        if replace:
            self._update(conditions=self._get_conditions(id=f"'{filename}'"), new_values={"data":image}, id=filename)
        else:
            self._insert(new_record=(image,), custom_id=filename)

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


class Portkeys(Database):
    table = "portkeys"

    def __init__(self, **kwargs):
        self.columns  = self._setup_table(types={"from_wb":"bool", "multiple_choice":"binary_13", "birthday":"datetime"}, **kwargs)
        self.raw_data = self._select(self.table)
    
    # add Portkey
    @sql_full_table_validator
    @parse_portkey_data
    def add(self, portkey):
        self._insert(new_record=portkey)
    
    # unarchive Portkey (update with message_id)
    @sql_only_one_validator
    @sql_update_with_valid_keys(column_names=["message_id"])
    def unarchive(self, **kwargs):
        self._update(new_values=kwargs)

    # archive Portkey (remove message_id)
    @sql_only_one_validator
    def archive(self):
        try:
            message_id = self.get()["message_id"]
            self._update(new_values={"message_id":None})
            return message_id
        except TypeError:
            return None

    # return Portkey / Portkeys
    def get(self, multiple=False):
        if multiple:
            return [portkey["user_id"] for portkey in self._get_values_from_raw_data(self.raw_data)]
        return next(iter(self._get_values_from_raw_data(self.raw_data, add_id=True, omitted=["message_id"])), None)


class WelcomeMessages(Database):
    table = "welcome_messages"
    
    def __init__(self, **kwargs):  
        self.columns  = self._setup_table(types={"date":"datetime"}, **kwargs)
        self.raw_data = self._select(self.table)

    # add WelcomeMessage
    @sql_full_table_validator
    def add(self, user_id, message_id, date):
        self._insert(new_record=(message_id, date), custom_id=user_id)
    
    # remove WelcomeMessage
    @sql_full_table_validator
    def remove(self, user_id):
        try:
            if deleted_record := self._delete(conditions=self._get_conditions(id=user_id), id=user_id):
                return self._get_specific_value_from_raw_data(deleted_record, "message_id")[0]
        except Exception:
            return None

    # return WelcomeMessages
    def get(self):
        return self._get_values_from_raw_data(self.raw_data, add_id=True, omitted=["date"])


# set up class attributes:
Experience.joined_table     = ExperienceInfo
ExperienceInfo.joined_table = Experience