from functools import reduce
from re        import sub
from time      import mktime
from datetime  import datetime


def replace_multiple(string:str, replace_list:list, self_idx=True):
    # new list, never in place - callers pass module-level tables that get reused every call
    if self_idx:
        replace_list = [(f"{idx+1}".rjust(3, "0"), instance) for idx, instance in enumerate(replace_list)]

    return reduce(lambda a, kv: a.replace(*kv), replace_list, string)


def convert_to_unix_time(date:datetime, mode:str):

    # get a tuple of the date attributes
    date_tuple = (date.year, date.month, date.day, date.hour, date.minute, date.second)

    # convert to unix time
    return f'<t:{int(mktime(datetime(*date_tuple).timetuple()))}:{mode}>'


# "flip through" a list
def turn_limit(turnable: int, max: int) -> int:
    return (turnable + max) % (max)


def catch_error(data:dict, keys:list):
    for key in keys:
        data.setdefault(key, None)
    return data


def remove_extra_characters(string:str, is_id:bool=False):
    if is_id:
        return sub(r'''\D''', "", string)
    else:
        return replace_multiple(string.lstrip(" ").rstrip(" "), [("\r", ""), ("\n", "")], self_idx=False)


def parse_multiple_possibilities(value:str):
    if len(list := [remove_extra_characters(value) for value in value.split("|")]) == 1:
        list.append(None)
    return list
