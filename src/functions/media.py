import src.variables as vars

from .core import log, session

from datetime   import datetime
from functools  import wraps
from io         import BytesIO
from os         import path
from PIL        import Image
from time       import sleep

import requests


def get_today():
    def run(func):
        @wraps(func)
        async def insert_today(*args, **kwargs):
            func_name = func.__name__
            if not func_name.endswith("_reminder"):
                raise ValueError(f"Function name '{func_name}' should end with '_reminder'.")

            time_key = func.__name__.replace("_reminder", "")
            if time_key not in vars.time_trigger:
                raise ValueError(f"Time key '{time_key}' not found in time_trigger.")

            kwargs['today'] = datetime.now(tz=vars.time_trigger[time_key].tzinfo)

            # keeps every scheduled reminder alive if one run fails - see memory
            try:
                return await func(*args, **kwargs)
            except Exception as error:
                log(f"task error in '{func_name}': {error}")
        return insert_today
    return run


def get_file(url, filename, directory=None):
    try:
        # mimic a browser request
        response = requests.get(url, headers={"user-agent": "Mozilla/5.0"}, stream=True)
        response.raise_for_status() # raise an exception for HTTP errors

        with open(path.join(directory or vars.absolute_path, filename), 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)

    except requests.exceptions.RequestException as e:
        raise Exception("no file found")


def compress_image(image_bytes):
    ''' Re-encode raw image bytes as a lossless-optimized PNG, regardless of source format '''

    img = Image.open(BytesIO(image_bytes))
    output = BytesIO()
    img.save(output, format="PNG", optimize=True)
    return output.getvalue()


def get_image(url, delay=2, max_retries=10):
    attempts = 0
    while True:
        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as error:
            attempts += 1
            log(f"requests: failed to download image from {url}: {error}")

            if attempts < max_retries:
                log(f"Retrying in {delay} seconds...")
                sleep(delay)
            else:
                log(f"Failed to download image after {max_retries} attempts.")
                return None


def get_level_and_progress(xp_total):
    xp = 0
    level = 0

    # calculate current level
    while True:
        xp_for_next_level = 5 * (level ** 2) + (50 * level) + 100
        if xp + xp_for_next_level > xp_total:
            break
        xp += xp_for_next_level
        level += 1

    # progress within the current level
    xp_into_next_level = xp_total - xp
    progress = xp_into_next_level / xp_for_next_level

    return level, round(progress, 2)


# precomputed once - pets is a fixed catalog, no need to rescan per call
MAX_PET_LEVEL = max(int("".join(filter(str.isdigit, level))) for level in vars.pets if level != "unknown")

def get_animal_rank(user, level=None):
    pets = vars.pets
    user_level = user.get("level", level)

    # limit the levels
    max_level = MAX_PET_LEVEL
    if user_level > max_level:
        user_level = max_level

    # find suffix per level rules
    suffix_rules = {(2, 6, 11, 15, 19, 25, 28, 32, 37,): lambda: "b" if user["pet_from_sea"] else "a",
                    (10, 18, 27, 34,):                   lambda: "b" if user["pet_dog"] else "a",
                    (20,):                               lambda: "b" if user["pet_ashwinder"] else "a",
                    (30,):                               lambda: "b" if user["pet_thestral"] else "a",
                    (40,):                               lambda: {1: "b", 2: "c", 3: "d", 4: "e", 5: "f", 6: "g", 7:"h"}.get(user["favourite_color"], "a"),}

    suffix = ""
    for levels, rule in suffix_rules.items():
        if user_level in levels:
            suffix = rule()
            break

    # add suffix
    return pets.get(f"{user_level}{suffix}", "unknown")


def get_level_change(previous_level, current_level):

    # no change
    if previous_level == current_level:
        return []

    # leveled up (progression)
    if current_level > previous_level:
        return list(range(previous_level+1, current_level+1))

    # level down (regressionm, final)
    return [current_level]


def get_member_id_by_nick(server, nick):
    try:
        return [member.id for member in server.members if member.nick == nick][0]
    except IndexError:
        return None
