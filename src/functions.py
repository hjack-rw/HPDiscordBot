import src.variables as vars

import asyncio

from copy      import deepcopy
from csv       import DictReader
from datetime  import datetime, timedelta
from functools import reduce, wraps
from io        import BytesIO, StringIO
from os        import getcwd, makedirs, path
from PIL       import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError
from re        import search, sub
from shutil    import copy2
from time      import mktime, sleep
from types     import SimpleNamespace

import requests
session = requests.Session()

from discord.app_commands        import Group
from discord.app_commands.errors import CommandInvokeError
from discord.errors              import DiscordServerError, NotFound
from discord.embeds              import Embed
from discord.enums               import EntityType, PrivacyLevel
from discord.file                import File
from discord.interactions        import Interaction, InteractionResponded
from discord.message             import Message
from discord.utils               import MISSING

from typing import Awaitable, Callable, ParamSpec, TypeVar
P = ParamSpec("P") # parameters
R =   TypeVar("R") # returns


# SETTINGS
# for testing
# vars.test_bot["test_command"] = True # overwrite if needed
# vars.test_bot["test_events"]  = True # overwrite if needed
# vars.test_bot["test_tasks"]   = True # overwrite if needed


def log(message):
    ''' print()-alike: prints while any test_bot flag is set (local dev), otherwise appends
    a timestamped line to data/bot.log - a real deployment has no console to watch. '''

    if vars.is_test_mode():
        print(message)
    else:
        makedirs(path.dirname(vars.log_path), exist_ok=True)
        with open(vars.log_path, "a", encoding="utf-8") as file:
            file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} {message}\n")


delete_after = {"hours":0, "minutes":0, "seconds":0}

if vars.test_bot["test_command"] or vars.test_bot["test_events"] or vars.test_bot["test_tasks"]:
    channel_ids = vars.channel_ids_test
    
    if vars.test_bot["test_tasks"]:
        delete_after["minutes"] = vars.wait_for * 2
else:
    channel_ids = vars.channel_ids

headers = {"authorization": f"Bot {vars.bot_token}",
           "content-type":   "application/json",
           "user-agent":     "BOT (http://discord.com, v1.0)",}

class CustomHousecup:
    def __init__(self, house:str, all_members_count:int):
        self.name = house
        self.all_members_count = all_members_count
        self.points = []

    def for_scoreboard(self, mean, sd):
        if not self.points:
            return 0
        
        points = [point for point in self.points if (mean - 2 * sd <= point <= mean + 2 * sd)]
           
        # sum of points / active members / all_members
        return sum(points) / max(len(points), 1) / max(self.all_members_count, 1)

############################################################################################################

def standard_response(silent: bool=False):
    def run(func: Callable[P, Awaitable[R]]):
        @wraps(func)
        async def response(*args: P.args, **kwargs: P.kwargs) -> R:
            interaction = kwargs.get("interaction", None)
            message     = kwargs.get("message", None)
            
            if interaction is None and message is None:
                output = {Group: None, Interaction: None, Message: None}

                for arg in args:
                    for expected_type in output:
                        if isinstance(arg, expected_type) and output[expected_type] is None:
                            output[expected_type] = arg
                            break  # stop checking once matched

                _, interaction, message  = output[Group], output[Interaction], output[Message]
            
            if not silent:
                wait_text = "A wizard must show patience... please, wait for the command to finish!"

                if interaction:
                    await safe_handle_response(interaction, message=wait_text)
                elif message:
                    await message.channel.send(wait_text, delete_after=10)

            try:
                return await func(*args, **kwargs)
            except Exception as error:
                error_text = f"Something went very wrong here... {error}!"
                
                try:
                    if interaction:
                        return await safe_handle_response(interaction, message=error_text)
                    elif message:
                        return await message.channel.send(error_text, delete_after=10)
                except Exception as followup_error:
                    log(f"Failed to send error follow-up: {followup_error}")

                log(error_text)
        
        return response
    return run


async def safe_handle_response(interaction, message):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    
    # if already responded/deferred
    except InteractionResponded:
        await interaction.followup.send(message, ephemeral=True)


def disable_after(func):
    @wraps(func)
    async def decorator(self, interaction:Interaction, *args, **kwargs):
        await func(self, interaction, *args, **kwargs)
        
        self.dropdown.disabled= True
        
        try:
            await interaction.message.edit(view=self)
        except NotFound:
            pass
        
        await interaction.response.defer()
        self.stop()
    return decorator


async def wait_till_posted(channel, idx):
    test = vars.test_bot["test_command"]
    
    while len([message async for message in channel.history(limit=None)]) != idx:
        if test:
            break
    
    log("endless loop finished!")


async def send_command(target_channel_id, app_id, version, id, command, options=[]):
    payload = {"type":           2,
               "application_id":str(app_id),
               "guild_id":      str(vars.server_id),
               "channel_id":    str(target_channel_id),
               "session_id":    "3794653e1bf277766e6356b596fd495d",
               "data":{"version":str(version), "id":str(id), "name":command, "type":1, "options": options}}
    
    # overwrite headers
    headers = {"authorization": str(vars.discord_token),
               "content-type":  "application/json",}

    response = session.post(url="https://discord.com/api/v9/interactions", json=payload, headers=headers,)
    #print(response)

    if response.status_code < 300:
        sleep(vars.wait_for)
    else:
        raise Exception("failed to send command!")


# the one shared webhook gets repointed to a channel right before every send/edit - without
# a lock, two concurrent calls for different channels can interleave their repoint+send, so
# a message lands in the wrong channel under the wrong persona
webhook_lock = asyncio.Lock()

def change_webhook_channel(target_channel):
    payload = {"channel_id":target_channel.id}
    return session.patch(f"https://discordapp.com/api/webhooks/{vars.webhook_id}", json=payload, headers=headers,)


async def send_webhook(target_channel, user_name, user_avatar_url=None, content="", embed=None, file=None, view=None):

    if user_avatar_url is None:
        try:
            user_avatar_url = vars.custom_avatars[user_name]
        except KeyError:
            user_avatar_url = vars.custom_avatars["Prof. Dumbledore"]

    async with webhook_lock:
        response = await asyncio.to_thread(change_webhook_channel, target_channel)
        #print(response)

        if response.status_code == 200:
            webhook = [webhook for webhook in await target_channel.webhooks() if webhook.id == vars.webhook_id][0]

            embed = embed if embed else MISSING
            file = file if file else MISSING
            view = view if view else MISSING

            return await webhook.send(content=content, username=user_name, avatar_url=user_avatar_url, embed=embed, file=file, view=view, wait=True)
        else:
            raise Exception("failed to create webhook")


async def edit_webhook(target_channel, message_id, embed=None, file=None):

    async with webhook_lock:
        response = await asyncio.to_thread(change_webhook_channel, target_channel)
        #print(response)

        webhook = [webhook for webhook in await target_channel.webhooks() if webhook.id == vars.webhook_id][0]

        embeds, attachments = [], []

        if embed:
            embeds = [embed]

        if file:
            attachments = [file]

        await webhook.edit_message(message_id=message_id, embeds=embeds, attachments=attachments)


############################################################################################################

def replace_multiple(string:str, replace_list:list, self_idx=True):
    if self_idx:
        for idx, instance in enumerate(replace_list):
            replace_list[idx] = (f"{idx+1}".rjust(3, "0"), instance)
    
    return reduce(lambda a, kv: a.replace(*kv), replace_list, string)


def convert_to_unix_time(date:datetime, mode:str):
    
    # get a tuple of the date attributes
    date_tuple = (date.year, date.month, date.day, date.hour, date.minute, date.second)

    # convert to unix time
    return f'<t:{int(mktime(datetime(*date_tuple).timetuple()))}:{mode}>'


# "flip through" a list
def turn_limit(turnable: int, max: int) -> int:
    return (turnable + max) % (max)


def catch_error(dict:dict, keys:list):
    for key in keys:
        try:
            dict[key]
        except KeyError:
            dict[key] = None
    else:
        return dict


def remove_extra_characters(string:str, is_id:bool=False):
    if is_id:
        return sub(r'''\D''', "", string)
    else:
        return replace_multiple(string.lstrip(" ").rstrip(" "), [("\r", ""), ("\n", "")], self_idx=False)

 
def parse_multiple_possibilities(value:str):
    if len(list := [remove_extra_characters(value) for value in value.split("|")]) == 1:
        list.append(None)
    return list

############################################################################################################

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

            # discord.ext.tasks.loop silently stops looping forever if an unhandled
            # exception escapes the loop body - every _reminder task shares this wrapper,
            # so catching here (rather than in each task individually) keeps every
            # scheduled reminder alive even if one run of it fails.
            try:
                return await func(*args, **kwargs)
            except Exception as error:
                log(f"task error in '{func_name}': {error}")
        return insert_today
    return run


def get_json(url):
    try:
        # create HTTP response object 
        response = requests.get(url, timeout=10)
        response.raise_for_status() # raise an exception for HTTP errors

        return response.json()
    except (requests.RequestException, ValueError):
        raise Exception("no JSON file found")


def get_csv(url):
    try:
        # create HTTP response object 
        response = requests.get(url)
        response.raise_for_status() # raise an exception for HTTP errors

        # decode the csv format
        decoded = response.content.decode("utf-8-sig")
        content = DictReader(StringIO(decoded))

        # skip empty rows
        data = []
        for row in content:
            if not any(row.values()):
                continue
            data.append(row)
        
        if not data:
            raise Exception("CSV is empty or has invalid format")
        
        return data
    except requests.RequestException:
        raise Exception("no CSV file found")


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
            log(f"Error: failed to download image from {url}: {error}")

            if attempts < max_retries:
                log(f"Retrying in {delay} seconds...")
                sleep(delay)
            else:
                log(f"Failed to download image after {max_retries} attempts.")
                return None

async def get_image_from_channel(channel, message_id):
    message = await channel.fetch_message(message_id)
    return message.attachments[0]


def get_avatar(user, none=False):
    try:
        return user.avatar._url
    except AttributeError:
        if none:
            return None
        return user.default_avatar._url


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


def get_animal_rank(user, level=None):
    pets = vars.pets
    user_level = user.get("level", level) 

    # get max level ignoring the suffixes
    max_level = max(int("".join(filter(str.isdigit, level))) for level in pets if level != "unknown")

    # limit the levels
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


def get_leaderboard_static():
    
    # the basic template
    background = Image.open(vars.image_data_path + "leaderboard/template.png")

    # the profile border
    profile_border = Image.open(vars.image_data_path + "leaderboard/frogcard_template.png")

    # the full progress bar
    full_bar = Image.open(vars.image_data_path + "leaderboard/bar.png")

    # the mask for the begining of the bar
    bar_mask = Image.new(mode="L", size=full_bar.size, color=255)
    draw = ImageDraw.Draw(bar_mask)
    _, y = full_bar.size
    draw.polygon(check_shape(shape=[(0, 0), (0, y), (91, y), (91, 0)]), fill=0)

    # the progress bar marker
    marker = Image.open(vars.image_data_path + "leaderboard/bar_frog.png")

    # the fonts
    fonts = {"MAGIC_88": ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=88),
             "MAGIC_45": ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=45),
             "MAGIC_42": ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=42),
             "MAGIC_35": ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=35),
             "RUNES_88": ImageFont.truetype(font=(vars.font_data_path + "RUNES.ttf"), size=88),
             "RUNES_72": ImageFont.truetype(font=(vars.font_data_path + "RUNES.ttf"), size=72),}
    
    return (background, profile_border, full_bar, bar_mask, marker, fonts)

############################################################################################################

def scale_image(base_width, image):
    x, y = image.size
    
    w_size = base_width
    w_percent = base_width / float(x)
    
    h_size = int(round(y * w_percent))
    return image.resize((w_size, h_size), Image.Resampling.LANCZOS)


def check_shape(shape):
    return [(int(round(x)), int(round(y))) for x,y in shape]


def get_position(center, image_center, offset=(0,0)):
    x, y = center
    x_off, y_off = offset
    w_size, h_size = image_center
    
    return check_shape(shape=[(x - (w_size / 2) + x_off, y - (h_size / 2) + y_off)])[0]

############################################################################################################

def draw_infocard(new_user, all_members_count):
    background = Image.open(vars.image_data_path + "card/template.png")
    
    ## profile picture ##
    url = get_avatar(user=new_user)

    # download avatar
    avatar = Image.open(BytesIO(get_image(url=url)))
    
    # scaling
    avatar = scale_image(base_width=220, image=avatar)
    x, _ = avatar.size

    # add avatar mask
    blur_radius = 1
    avatar_mask = Image.new(mode="L", size=avatar.size, color=0)
    draw = ImageDraw.Draw(avatar_mask)
    draw.ellipse(xy=(5, 8, x-5, x-5), fill=255)
    avatar_mask = avatar_mask.filter(ImageFilter.GaussianBlur(blur_radius))

    background.paste(im=avatar, box=(215,20), mask=avatar_mask)

    draw = ImageDraw.Draw(background)


    ## text ##
    # add nickname
    if len(new_user.name) > 15:
        name_font = ImageFont.truetype(font=(vars.font_data_path + "RUNES.ttf"), size=80)
    else:
        name_font = ImageFont.truetype(font=(vars.font_data_path + "RUNES.ttf"), size=100)

    if len(new_user.name) > 9:
        draw.text(xy=(995,115), text=new_user.name, fill=(235,235,235), font=name_font, align="center", anchor='rm')
    else:
        draw.text(xy=(795,115), text=new_user.name, fill=(235,235,235), font=name_font, align="center", anchor='mm')
    
    # add footer
    footer_font = ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=35)
    draw.text(xy=(790,200), text=f"We are now {all_members_count} members!", fill=(235,235,235), font=footer_font, align="center", anchor='mm')

    
    ## save and return file ##
    bytes = BytesIO()
    background.save(bytes, format="PNG")
    bytes.seek(0)
    
    return File(bytes, filename="card.png")


def draw_leaderboard(user, rank, house, static, is_bytes=False):
    background, profile_border, full_bar, bar_mask, marker, fonts = static
    background = deepcopy(background)


    ## profile picture ##
    xy = (150, 150)

    avatar = None
    avatar_center = (177, 156)
   
    if url := user["avatar"]:
        try:
            # download avatar
            image_data = get_image(url)

            image = Image.open(BytesIO(image_data))
            image.load()  # force-load the image

            # scaling
            avatar = scale_image(base_width=xy[0], image=image)
        except (OSError, UnidentifiedImageError, TypeError) as error:
            log(f"PIL error: failed to load image for {user.get('username')}:\n{error}")

    # black avatar if missing
    if avatar is None:
        avatar = Image.new(mode="L", size=xy, color=0)

    # add avatar mask
    avatar_mask = Image.new(mode="L", size=avatar.size, color=0)
    draw = ImageDraw.Draw(avatar_mask)
    draw.ellipse(xy=(0, 0, *avatar.size), fill=255)

    x, y = avatar.size
    draw.polygon(check_shape(shape=[(0,y/2), (0,y), (x,y), (x,y/2)]), fill=255)

    offset = user.pop("offset", True)
    background.paste(im=avatar, box=get_position(center=avatar_center, image_center=avatar.size, offset=(5,8) if offset else (0,0)), mask=avatar_mask)

    # add profile border
    background.alpha_composite(im=profile_border, dest=get_position(center=avatar_center, image_center=profile_border.size))

    draw = ImageDraw.Draw(background)


    ## box info ##
    # add rank
    draw.text(xy=(380, 118), text="#" + f"{rank}".rjust(3, "0"), fill=(235,235,235), font=fonts["MAGIC_88"], align="left", anchor='lm')

    # add nickname
    if len(user["username"]) <= 9 and ("\n" in user["username"]):
        name_font = fonts["RUNES_88"]
    else:
        name_font = fonts["RUNES_72"]

    draw.multiline_text(xy=(570, 160 if "\n" in user["username"] else 128), text=user["username"], fill=(235,235,235), font=name_font, align="left", anchor='lm', spacing=-35)

    # add house logo
    if house:
        house_logo = Image.open(vars.image_data_path + f"houses/{house}.png")
        background.alpha_composite(im=house_logo, dest=(388, 194))

    # progress details (pet name and level)    
    pet = get_animal_rank(user)["name"]

    if len(pet) > 20:
        pet_font = fonts["MAGIC_35"]
    else:
        pet_font = fonts["MAGIC_45"]
    
    draw.text(xy=(901, 170), text=f"Pet: ", fill=(235,235,235), font=fonts["MAGIC_45"], align="left", anchor='lm')
    draw.text(xy=(961, 169), text=pet, fill=(235,235,235), font=pet_font, align="left", anchor='lm')
    draw.text(xy=(901, 227), text=f"Level: {user['level']}", fill=(235,235,235), font=fonts["MAGIC_45"], align="left", anchor='lm')


    ## progress bar ##
    # limit progress
    percent = user["progress"]

    if percent < 0.05:
        percent = 0.05
    elif percent > 1:
        percent = 1

    # proportion
    bar_offset = 1480 - int(round(percent * 1480))

    progress_bar = Image.new("RGBA", full_bar.size, (0, 0, 0, 0))

    x, y = full_bar.size
    progress_bar.paste(im=full_bar.crop((bar_offset, 0, x, y)), mask=bar_mask.crop((0, 0, x-bar_offset, y)))

    # add progress bar
    background.alpha_composite(im=progress_bar)

    # add progress bar marker
    background.alpha_composite(im=marker, dest=get_position(center=(95, 322), image_center=marker.size, offset=(int(round(percent * 1480)-85), 0) if percent >= 0.059 else (0, 0)))

    # add percentage
    draw.text(xy=(x-175 if percent < 0.5 else 175, 322), text=f"{round(user['progress']*100, 2)}%", fill=(235,235,235), font=fonts["MAGIC_42"], align="center", anchor='mm')
    
    
    ## save and return file ##
    bytes = BytesIO()
    background.save(bytes, format="PNG")
    bytes.seek(0)
    
    if is_bytes:
        return bytes
    return File(bytes, filename=f"leaderboard_{user['user_id']}.png")

############################################################################################################

def parse_xp_amount(func):
    @wraps(func)
    async def parse(self, *args, **kwargs):
        server       = kwargs.pop("server")
        member       = kwargs.pop("member", SimpleNamespace(id=None))
        amount       = kwargs.pop("amount")
        after_action = kwargs.pop("after_action", "add")

        if amount <= 0:
            raise Exception("parse error: 'amount' cannot be zero or negative")

        user_id = kwargs.get("user_id", member.id)
        record  = self.get_from_dict(user_id=user_id)
        is_new  = not bool(record)

        # modify existing record or create a new record
        previous_xp    = record["xp"]    if record else 0
        previous_level = record["level"] if record else 0
            
        # compute new xp based on the action
        if after_action == "add":
            current_xp = previous_xp + amount
        elif after_action == "subtract":
            current_xp = previous_xp - amount
            if current_xp <= 0:
                raise Exception("parse error: 'xp' cannot be zero or negative after subtraction")
        else:  # action == "set"
            current_xp = amount
        
        current_level, progress = get_level_and_progress(current_xp)

        # prepare new_kwargs dict for func
        new_kwargs = deepcopy(kwargs)
        new_kwargs.update({"is_new":  is_new,
                           "user_id": user_id,
                           "experience": {"xp": current_xp, "level": current_level, "progress": progress, **({} if is_new else {"archived": False}),}})

        # check roles to assign Sphinx or Ashwinder pet accordingly
        if is_new:
            new_kwargs["pet_ashwinder"] = not bool({role.name for role in getattr(member, "roles", [])} & {vars.club_name_short, "guest"})

        # call the original function
        current_xp = await func(self, *args, **new_kwargs)

        # when on server send a level up message
        if server:
            level_ups = get_level_change(previous_level, current_level)
            if level_ups:
                user_data = await self.get_joined_table(user_id=member.id)
                await print_notification(server, event_name="Level Up", variables=[member, user_data, level_ups], is_task=False)

        return current_xp
    return parse


def create_leaderboard(server, data, custom_housecup):
    ## get static files for leaderboard ##
    static = get_leaderboard_static()

    ## create loop for each user ##
    rank, rank_xp, leaderboard = 0, 0, []
    for user in data:

        # get member, skip if can't
        member = server.get_member(user["user_id"])
        if member is None:
            continue
        else:
            if user["xp"] != rank_xp:
                rank += 1
                rank_xp = user["xp"]

        house = None
        roles = {role.name for role in getattr(member, "roles", [])}

        # add points for the custom housecup
        for idx, house in enumerate(custom_housecup):
            if house.name in roles:
                custom_housecup[idx].points.append(rank_xp)
                house = house.name
                break
        else:
            # get house if no custom housecup
            if house is None:
                house = next((house for house in vars.houses_names_list() if house in roles), None)

        # get the special role color
        try:
            if member.roles[-1].name in {"captain", "moderator", "co-captain",}:
                color = member.roles[-1].color.value
            else:
                color = 5198940
        except AttributeError:
            color = vars.system_embed_color

        if (username := user.pop("username", None)) is None:
            user["username"] = (member.display_name).replace(" ", "\n ")
        else:
            user["username"] = username
        
        user["avatar"] = get_avatar(user=member, none=True)

        file = draw_leaderboard(user, rank, house, static)
        leaderboard.append((user["user_id"], color, file))

    return leaderboard, custom_housecup

############################################################################################################

def parse_portkey_data(func):  
    @wraps(func)
    async def parse(self, *args, **kwargs):
        server  = kwargs.pop("server")
        message = kwargs.pop("message")
        user_id = kwargs.pop("user_id", None)

        if message.author.id != 952824326766333972:
            raise Exception("what you are trying to accept is not a Portkey")
        
        # predeclare all expected variables to prevent UnboundLocalError
        game_id = from_wb = old_username = multiple_choice = additional_info = birthday = birth_year = extra = None


        for field in message.embeds[0].fields:
            idx = field.name.split(".")[0]

            match idx:
                case "1":
                    if user_id is None:
                        user_id = get_member_id_by_nick(server, nick=field.value)
                        if user_id is None:
                            raise Exception(f"no User with Nickname {field.value} on this server")
            
                case "2":
                    game_id = remove_extra_characters(field.value, is_id=True)
                    game_id = int(game_id) if game_id else 0
                
                case "3":
                    continue
                
                case "4":
                    from_wb, old_username = parse_multiple_possibilities(field.value)
                    from_wb = (from_wb == "Yes")
                
                case "5":
                    multiple_choice = parse_multiple_possibilities(field.value)
                    additional_info = multiple_choice.pop(-1)
                    
                    form_answers     = vars.form_answers
                    form_answers_set = set(form_answers)

                    if additional_info in form_answers_set:
                        multiple_choice.append(additional_info)
                        additional_info = None

                    selected_answers = set(multiple_choice)
                    multiple_choice  = "".join("1" if answer in selected_answers else "0" for answer in reversed(form_answers))
                
                case "6":
                    birth_parts = field.value.split(".")
                    
                    if birth_parts != ["-"]:
                        birthday = datetime(day=int(birth_parts[0]), month=int(birth_parts[1]), year=2000)
                        if (birth_year := int(birth_parts[2])-1900) == datetime.now().year-1900:
                            birth_year = None
                    else:
                        birthday, birth_year = None, None
                
                case "7":
                    extra = field.value if (field.value != "-") else None       
        
        # prepare new_kwargs dict for func
        new_kwargs = deepcopy(kwargs)
        new_kwargs["portkey"] = (user_id, game_id, from_wb, old_username, multiple_choice, additional_info, birthday, birth_year, extra)
        
        # call the original function
        return await func(self, *args, **new_kwargs)
    return parse


def print_portkey(member, portkey):
    try:
        roles = {role.name for role in getattr(member, "roles", [])}

        if member.roles[-1].name in {"captain", "moderator", "co-captain",}:
            color = member.roles[-1].color.value
        else:
            color = 5198940
    except AttributeError:
        color = vars.system_embed_color

    
    doc_url = "https://docs.google.com/document/d/1CJMk8wJZkYnXG729xHGPvsyaj5BtrXMZeqlIOV_4qtA/edit?usp=sharing"
    
    form_answers_extended = [f"{answer}\n\n" for answer in vars.form_answers]
    form_answers_extended.append(f"{portkey['additional_info']}\n\n")
    

    embed = Embed(color=color, description=f"**User:** <@{portkey['user_id']}>")
    
    line_1 = f"{member.display_name} | `#" + f"{portkey['game_id'] if portkey['game_id'] else 0}`".rjust(10, "0") + f" [📋]({doc_url})"
    embed.add_field(name="1. Hello, I'm... | And my ID is...", value=line_1, inline=True)

    line_2 = vars.houses[next((house for house in vars.houses_names_list() if house in roles), "other")]["emoji"]
    embed.add_field(name="2. My house is...", value=line_2, inline=True)
    
    line_3 = (("Yes | " if portkey["from_wb"] else "No, ") + portkey["old_username"]) if portkey["old_username"] else ("Yes" if portkey["from_wb"] else "No")
    embed.add_field(name="3. Am I from the WB server? | My name was...", value=line_3.replace(" | 0", ", "), inline=False)

    line_4 = "• " + "• ".join([form_answers_extended[idx].replace(" ", "​ ​ ", 1) for idx,choice in enumerate(portkey["multiple_choice"][::-1] + ("1" if portkey["additional_info"] else "0")) if choice == "1"])
    embed.add_field(name="4. In the game I like doing...", value=line_4, inline=False)
    
    if (not_skip := portkey["birthday"] is not None):
        birthday = portkey["birthday"]
        
        if year := portkey["year"]:
            birthday = birthday.replace(year = year + 1900)

        line_5 = birthday.strftime("%d.%m.%Y") if year else birthday.strftime("%d.%m")
        embed.add_field(name="5. I was born...", value=line_5, inline=False)

    if portkey["extra"]:
        line_6 = portkey["extra"]
        embed.add_field(name=f"{6 if not_skip else 5}. You may also want to know...", value=line_6, inline=False)
    
    embed.set_footer(text=f"{vars.club_name_short.upper()}  •  Portkey #{portkey['id']}")

    return embed

############################################################################################################

async def print_suitcase(images, info, level):
    embed = Embed(color=vars.system_embed_color, title=f"{info['username']}'{'s' if info['add_s'] else ''} Suitcase:", description="⭐ __Current Level__ ⭐" if info['current_level'] == level else "")
    
    if info['current_level']:
        pet = get_animal_rank(user=info, level=level)
        embed.set_footer(text=f"Level: {info['current_level']},​ ​ ​XP: {round(info['xp_for_next_level']*info['progress'])} / {info['xp_for_next_level']}​ ​ ({round(info['progress']*100, 2)}%)")
    else:
        pet = vars.pets.get(list(vars.pets)[level])
        embed.set_footer(text=f"Level: ♾️")

    embed.add_field(name="", value=f"*{pet['name']}* (Level {level})")
    embed.set_image(url=pet["url"])

    match = search(r'attachment://(.*?)\.png', pet["url"])
    if match:
        return embed, (await images.initialize(filename__has="pet", filename__like=match.group(1))).get()
    else:
        return embed, MISSING

############################################################################################################

def print_house_members(members, house, group):
    
    # filter by house and group
    users = []
    for member in members:

        # equivalent to .issubset()
        if {house, group} <= {role.name for role in getattr(member, "roles", [])}:
            users.append(member)

    users = sorted(users, key=lambda x: (x.display_name))
    
    for idx, user in enumerate(users):
        users[idx] = f"{idx+1}. {user.display_name} - <@{user.id}>"

    return Embed(color=vars.system_embed_color, title=vars.houses[house]["emoji"], description=f"**{group.capitalize() if group != vars.club_name_short else vars.club_name}:**\n"+"\n".join(users))

############################################################################################################

async def set_event_and_notification(server, event_info, date, event_duration, start_time, only_hour=True, time_delta=0, role="@everyone"):
    global delete_after
    
    trigger_day = date
    if time_delta:
        trigger_day += timedelta(days=time_delta)
    
    # for testing
    if vars.test_bot["test_tasks"]:
        beginning = datetime.now() + timedelta(minutes=vars.wait_for*2)
        ending    = beginning + timedelta(minutes=vars.wait_for)
        duration  = f"~{vars.wait_for} minutes"
    else:
        delete_after["hours"]   = event_duration[0] + (start_time[0] - trigger_day.hour)   + (time_delta * 24)
        delete_after["minutes"] = event_duration[1] + (start_time[1] - trigger_day.minute)
        delete_after["seconds"] = event_duration[2] + (start_time[2] - trigger_day.second)
        
        beginning = trigger_day.replace(hour  =(start_time[0] % 24),
                                        minute=(start_time[1] % 60),
                                        second=(start_time[2] % 60),)
        
        ending = beginning + timedelta(hours=event_duration[0], minutes=event_duration[1], seconds=event_duration[2])
        
        duration = f"~{event_duration[0]} hour{'s' if event_duration[0] > 1 else ''}"
    
    log(f"h: {delete_after['hours']}  m: {delete_after['minutes']}  s: {delete_after['seconds']}")

    # get alternative title and insert timer
    if not event_info["title"]:
        event_name = search('<(.*)>', event_info["subtitle"]).group(1)
        event_info["subtitle"] = replace_multiple(event_info["subtitle"], [("<", ""), (">", "")], self_idx=False)

    elif ("<" in event_info["title"]) and (">" in event_info["title"]):
        event_name = search('<(.*)>', event_info["subtitle"]).group(1) + f": {search('<(.*)>', event_info['title']).group(1)}"
        event_info["title"] = replace_multiple(event_info["title"], [("<", ""), (">", "")], self_idx=False)
        event_info["subtitle"] = replace_multiple(event_info["subtitle"], [("<", ""), (">", "")], self_idx=False)
    else:
        event_name = event_info["title"]
   
    event_info["description"] = event_info["description"].replace("000", convert_to_unix_time(date=beginning.astimezone(), mode="R"))
    
    try:
        event_info["location"]
    except KeyError:
        event_info["location"] = "HP: Magic Awakened ឵឵(Sphinx)"

    
    # get image
    channel = server.get_channel(channel_ids["assets"])

    if not vars.test_bot["test_tasks"]:

        # create event
        try:
            await server.create_scheduled_event(name=event_name,
                                                start_time=beginning.astimezone() if beginning > date else (date + timedelta(minutes=2)).astimezone(),
                                                end_time=ending.astimezone(),
                                                description=event_info["description"],
                                                location=event_info["location"],
                                                privacy_level=PrivacyLevel.guild_only,
                                                entity_type=EntityType.external,
                                                image=get_image(url=await get_image_from_channel(channel, message_id=event_info["image_id"])))
        except DiscordServerError:
            log("Could not create event... Discord API error!")
        except CommandInvokeError:
            log("Could not create event... Bad timestamp!")
        except ValueError:
            log("Could not create event... Image not found!")
    
    
    # create notification message
    embed = Embed(color=vars.system_embed_color, title=event_info["title"], description=event_info["description"])
    embed.set_author(icon_url="https://storage.googleapis.com/chronicle-assets/images/icons/bell-alert-white.png", name=event_info["subtitle"])
    embed.add_field(name="Location", value=event_info["location"], inline=False)
    embed.add_field(name="Scheduled for", value=f"{convert_to_unix_time(date=beginning.astimezone(), mode=('t' if only_hour else 'f'))}", inline=True)
    embed.add_field(name="Duration", value=duration, inline=True)

    if event_info["footer"]:
        embed.set_footer(text=event_info["footer"])

    channel = server.get_channel(channel_ids["announcements"])
    message = await send_webhook(target_channel=channel, user_name=event_info["account"], content=f"Mention: {role}", embed=embed)

    if not vars.test_bot["test_tasks"]:
        await message.delete(delay=(delete_after["hours"]*3600)+(delete_after["minutes"]*60)+delete_after["seconds"])


async def print_notification(server, event_name, date=None, variables=[], is_task=True, same_day=False):
    events    = vars.notification_dict()
    task_name = events[event_name]

    if vars.test_bot["test_tasks"] and is_task:
        events_short = vars.notification_dict(is_short=True)
        log(f'''"{events_short[event_name]}" task running... {datetime.now()}!''')
    elif not is_task:
        if date and task_name:
            date = date.astimezone(tz=vars.time_trigger[task_name].tzinfo)

    file, view = None, None

    if event_name == "Welcome":
        new_user, file, view = variables
        
        channel = server.get_channel(channel_ids["welcome"])

        event_info = {"mention":    f"Mention: <@{new_user.id}>",
                      "title":      f"Welcome {new_user.name}, to {vars.club_name}! <:hugs:1256225688403447888>",
                      "description": "Go to <id:guide> and follow the instructions :)",
                      "footer":   f'''"You are a Wizard, {new_user.name}."''',
                      "account":     "Prof. Hagrid",}
        
        embed = Embed(title=event_info["title"],  description=event_info["description"], color=vars.system_embed_color)

    elif event_name == "Level Up":
        user, user_data, level_ups = variables

        channel = server.get_channel(channel_ids["great-hall"])

        event_info = {"mention":    f"Mention: <@{user.id}>",
                      "title":      f"Level {level_ups[-1]}!",
                      "description":f"**{user.display_name}** just caught a **{get_animal_rank(user=user_data, level=level_ups[0])['name']}** <:hugs:1256225688403447888>\n",
                      "extra_fields":[f"Wait! There is more... they also caught a {get_animal_rank(user=user_data, level=level)['name']}\n" for level in level_ups[1:]],
                      "footer":   '''"One can never have enough pets!"''',
                      "account":     "Prof. Dumbledore",}

        ending = "How many more fantastic beasts\ncan they catch?"
        if event_info["extra_fields"]:
            event_info["extra_fields"][-1] += ending
        else:
            event_info["description"] += ending

    elif event_name == "Birthday":
        birthday_users = [await server.fetch_member(user_id) for user_id in variables[0]]
        birthday_user  = birthday_users[0]
        
        channel = server.get_channel(channel_ids["great-hall"])

        event_info = {"mention":       "Mention: @everyone",
                      "subtitle":      "Birthday Announcement!",
                      "description":  f"**{vars.club_name_short.upper()}  •  {date.strftime('%d/%m/%Y')}**\nPlease, wish **{birthday_user.display_name}** a **Happy Birthday** <:hugs:1256225688403447888> :heart:",
                      "extra_fields":[f"Wait! There is more...\nPlease, wish **{birthday_user.display_name}** a **Happy Birthday** as well <:hugs:1256225688403447888> :heart:" for birthday_user in birthday_users[1:]],
                      "thumbnail":     "https://i.pinimg.com/564x/d8/48/59/d848592fca62cc100b148b5b77006248.jpg",
                      "footer":     '''"I can see something in the stars...\nToday is a very special day!"''',
                      "account":       "Prof. Trelawney",}


    elif task_name == "weekly_cards":
        link = "https://discord.com/channels/0/0/000"

        event_info = {"subtitle":       "Reminder: Weekly <Free Card>!",
                      "description": f'''Map: {link}\nGo to the **001** and click on the 002 003!\n\nPick the option: **"004"**!\nYou will get 005 of the card.''',
                      "footer":      '''"Swish and flick everyone!\nJust like we have been practicing..."''',
                      "account":        "Prof. Flitwick",}

        if event_name == "Card - Matagot":
            event_info["image_id"] = "0"
            event_info["title"] = "<Matagot! (rare)>"
            
            event_info["description"] = event_info["description"].replace("/000", "/0")
            event_info["description"] = replace_multiple(event_info["description"], ["Staircase", "\nMatagot", "next to the Transfiguration Classroom", "Hand it Over to Hagrid", "1 copy"])
        
        elif event_name == "Card - Book of Monsters":
            event_info["image_id"] = "0"
            event_info["title"] = "<Book of Monsters! (rare)>"

            event_info["description"] = event_info["description"].replace("/000", "/0")
            event_info["description"] = replace_multiple(event_info["description"], ["History of Magic Classroom", "Book", "in the corner", "Stroke the Spine and Then Open It", "1 copy"])
            
        elif event_name == "Card - Cornish Pixies":
            event_info["image_id"] = "0"
            event_info["title"] = "<Cornish Pixies! (common)>"
            
            event_info["description"] = event_info["description"].replace("/000", "/0")
            event_info["description"] = replace_multiple(event_info["description"], ["Library", "Pixies", "first bookcase row left", "Use Glacius.", "3 copies"])

        return await set_event_and_notification(server, event_info, date, event_duration=(4,0,0), start_time=(17,0,0), role="<@&0>")


    elif event_name == "Housecup":
        discipline = variables[0]
        
        event_info = {"image_id":    "0",
                      "title":      f"<{vars.housecup_disciplines_names[discipline]}!>",
                      "subtitle":    "Reminder: <House Cup>!",
                      "description": "Make sure you be there and may the best house win!",
                      "footer":   '''"Did you put your name for the House Cup yet?!" he asked calmly.''',
                      "account":     "Prof. Dumbledore",}
        
        return await set_event_and_notification(server, event_info, date, time_delta=(0 if same_day else 1), event_duration=(2,0,0), start_time=(19,0,0), only_hour=False, role="@everyone")


    elif event_name == "Club Events":
        event_info = {"image_id":    "0",
                      "title":      f"{vars.club_name_short.upper()} Club Events!",
                      "subtitle":   f"Reminder: {vars.weekdays[date.weekday()]}!",
                      "description": "**We start 000!**\nWe will begin with a Quiz, and after roughly 20 min we go over to a Dance!",
                      "footer":   '''"Place your right hand on my waist and...\nOne, two, three... One, two, three..."''',
                      "account":     "Prof. McGonagall",}
        
        return await set_event_and_notification(server, event_info, date, event_duration=(1,0,0), start_time=(19,30,0), role="<@&0>")


    elif event_name == "Club Points":
        channel = server.get_channel(channel_ids["announcements"])

        event_info = {"mention":     "Mention: <@&0>",
                      "description": "Reminder to all who haven't earned\ntheir 100 Club points yet!\n\n"\
                                     "Please do so by the **end of the week**\nor inform a <@&0> / <@&0>\nif you are unable to do so!",
                      "footer":   '''"And be warned... I shall know if you have not practiced."''',
                      "account":     "Prof. Snape",}


    elif event_name == "Maintenance":
        event_info = {"image_id":    "0",
                      "title":       "",
                      "subtitle":    "Reminder: <Maintenance!>",
                      "description": "**It starts 000!**\nDuring this period the game will be unavailable!",
                      "footer":   '''"Go on, scram! Or I will hanging you by your thumbs in the dungeons!"''',
                      "account":     "Mr. Filch",}
        
        return await set_event_and_notification(server, event_info, date, time_delta=(0 if same_day else 1), event_duration=(3,0,0), start_time=(24,0,0))


    elif event_name == "Rankings":
        channel = server.get_channel(channel_ids["staffroom"])

        event_info = {"mention":     "Mention: <@&0> <@&0>",
                      "description": "Dear Staff,\nremember to take a picture of this week's top 3 students!\n\n(Please post the screenshots below!)",
                      "footer":   '''"But be quick! It is not wise to be wandering around this late hour."''',
                      "account":     "Prof. Dumbledore",}
    
    
    event_info = catch_error(event_info, keys=["extra_fields", "title", "subtitle", "thumbnail"])

    embed = Embed(color=vars.system_embed_color, title=event_info["title"], description=event_info["description"])

    if event_info["subtitle"]:
        embed.set_author(icon_url="https://storage.googleapis.com/chronicle-assets/images/icons/bell-alert-white.png", name=event_info["subtitle"])

    if event_info["extra_fields"]:
        for field in event_info["extra_fields"]:
            embed.add_field(name="", value=field, inline=False)

    if event_info["thumbnail"]:
        embed.set_thumbnail(url=event_info["thumbnail"])
    
    embed.set_footer(text=event_info["footer"])

    if file:
        embed.set_image(url=f"attachment://{file.filename}")
    
    return await send_webhook(target_channel=channel, user_name=event_info["account"], content=event_info["mention"], embed=embed, file=file, view=view)