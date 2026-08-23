import src.variables as vars

from .core        import log
from .discord_utils import send_webhook
from .text_utils   import replace_multiple, convert_to_unix_time, catch_error
from .media        import get_animal_rank

from datetime  import datetime, timedelta
from functools import partial
from glob      import glob
from os        import path
from re        import search

from discord.app_commands.errors import CommandInvokeError
from discord.errors              import DiscordServerError
from discord.embeds              import Embed
from discord.enums               import EntityType, PrivacyLevel
from discord.file                import File


if vars.test_bot["test_command"] or vars.test_bot["test_events"] or vars.test_bot["test_tasks"]:
    channel_ids = vars.channel_ids_test
else:
    channel_ids = vars.channel_ids

delete_after = {"hours":0, "minutes":0, "seconds":0}
if vars.test_bot["test_tasks"]:
    delete_after["minutes"] = vars.wait_for * 2

BELL_ICON_URL = "https://storage.googleapis.com/chronicle-assets/images/icons/bell-alert-white.png"


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


    # get image - event banners are fixed, code-defined assets (data/images/events/),
    # same convention as pets/houses: no #assets channel round-trip, no DB
    image_path = glob(path.join(vars.image_data_path, "events", f"{event_info['image']}.*"))

    if not vars.test_bot["test_tasks"]:

        # create event
        try:
            with open(image_path[0], "rb") as file:
                image_bytes = file.read()

            await server.create_scheduled_event(name=event_name,
                                                start_time=beginning.astimezone() if beginning > date else (date + timedelta(minutes=2)).astimezone(),
                                                end_time=ending.astimezone(),
                                                description=event_info["description"],
                                                location=event_info["location"],
                                                privacy_level=PrivacyLevel.guild_only,
                                                entity_type=EntityType.external,
                                                image=image_bytes)
        except DiscordServerError:
            log("Could not create event... Discord API error!")
        except CommandInvokeError:
            log("Could not create event... Bad timestamp!")
        except (ValueError, IndexError):
            log("Could not create event... Image not found!")


    # create notification message
    embed = Embed(color=vars.system_embed_color, title=event_info["title"], description=event_info["description"])
    embed.set_author(icon_url=BELL_ICON_URL, name=event_info["subtitle"])
    embed.add_field(name="Location", value=event_info["location"], inline=False)
    embed.add_field(name="Scheduled for", value=f"{convert_to_unix_time(date=beginning.astimezone(), mode=('t' if only_hour else 'f'))}", inline=True)
    embed.add_field(name="Duration", value=duration, inline=True)

    if event_info["footer"]:
        embed.set_footer(text=event_info["footer"])

    channel = server.get_channel(channel_ids["announcements"])
    message = await send_webhook(target_channel=channel, user_name=event_info["account"], content=f"Mention: {role}", embed=embed)

    if not vars.test_bot["test_tasks"]:
        await message.delete(delay=(delete_after["hours"]*3600)+(delete_after["minutes"]*60)+delete_after["seconds"])


async def _send_direct_notification(channel, event_info, file, extra_files, view):
    ''' Shared tail for every notification that isn't a scheduled-event announcement:
    fill in the fields callers left out, build the embed, send it as-is. '''

    event_info = catch_error(event_info, keys=["extra_fields", "title", "subtitle", "thumbnail"])

    embed = Embed(color=vars.system_embed_color, title=event_info["title"], description=event_info["description"])

    if event_info["subtitle"]:
        embed.set_author(icon_url=BELL_ICON_URL, name=event_info["subtitle"])

    if event_info["extra_fields"]:
        for field in event_info["extra_fields"]:
            embed.add_field(name="", value=field, inline=False)

    if event_info["thumbnail"]:
        embed.set_thumbnail(url=event_info["thumbnail"])

    embed.set_footer(text=event_info["footer"])

    if file:
        embed.set_image(url=f"attachment://{file.filename}")

    return await send_webhook(target_channel=channel, user_name=event_info["account"], content=event_info["mention"], embed=embed, file=file, extra_files=extra_files, view=view)


async def _notify_welcome(server, date, variables, same_day):
    new_user, file, view = variables
    channel = server.get_channel(channel_ids["welcome"])

    event_info = {"mention":    f"Mention: <@{new_user.id}>",
                  "title":      f"Welcome {new_user.name}, to {vars.club_name}! <:hugs:1256225688403447888>",
                  "description": "Go to <id:guide> and follow the instructions :)",
                  "footer":   f'''"You are a Wizard, {new_user.name}."''',
                  "account":     "Prof. Hagrid",}

    return await _send_direct_notification(channel, event_info, file, [], view)


async def _notify_level_up(server, date, variables, same_day):
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

    return await _send_direct_notification(channel, event_info, None, [], None)


async def _notify_birthday(server, date, variables, same_day):
    birthday_users = [await server.fetch_member(user_id) for user_id in variables[0]]
    birthday_user  = birthday_users[0]
    channel = server.get_channel(channel_ids["great-hall"])

    # thumbnail is a fixed, code-defined asset (data/images/events/), same
    # convention as pets/houses - not a third-party hotlink
    birthday_thumbnail = glob(path.join(vars.image_data_path, "events", "birthday.*"))[0]
    extra_files = [File(fp=birthday_thumbnail, filename="birthday.png")]

    event_info = {"mention":       "Mention: @everyone",
                  "subtitle":      "Birthday Announcement!",
                  "description":  f"**{vars.club_name_short.upper()}  •  {date.strftime('%d/%m/%Y')}**\nPlease, wish **{birthday_user.display_name}** a **Happy Birthday** <:hugs:1256225688403447888> :heart:",
                  "extra_fields":[f"Wait! There is more...\nPlease, wish **{birthday_user.display_name}** a **Happy Birthday** as well <:hugs:1256225688403447888> :heart:" for birthday_user in birthday_users[1:]],
                  "thumbnail":     "attachment://birthday.png",
                  "footer":     '''"I can see something in the stars...\nToday is a very special day!"''',
                  "account":       "Prof. Trelawney",}

    return await _send_direct_notification(channel, event_info, None, extra_files, None)


# the 3 weekly free-card reminders only differ by these 4 values - one data table plus one
# handler instead of 3 near-identical copy-pasted functions
CARD_VARIANTS = {"Card - Matagot":          {"link_suffix": "0", "image": "card_matagot", "title": "<Matagot! (rare)>",
                                              "replacements": ["Staircase", "\nMatagot", "next to the Transfiguration Classroom", "Hand it Over to Hagrid", "1 copy"]},
                  "Card - Book of Monsters":{"link_suffix": "0", "image": "card_book_of_monsters", "title": "<Book of Monsters! (rare)>",
                                              "replacements": ["History of Magic Classroom", "Book", "in the corner", "Stroke the Spine and Then Open It", "1 copy"]},
                  "Card - Cornish Pixies":  {"link_suffix": "0", "image": "card_cornish_pixies", "title": "<Cornish Pixies! (common)>",
                                              "replacements": ["Library", "Pixies", "first bookcase row left", "Use Glacius.", "3 copies"]},}


async def _notify_card(server, date, variables, same_day, *, link_suffix, image, title, replacements):
    # replace_multiple's "001".."005" placeholders must be substituted before the real
    # message-id link is spliced in - the link is a long, effectively-arbitrary Discord
    # snowflake, and a blind string-replace over it could corrupt the URL if it ever
    # happened to contain one of those digit sequences
    location_text = replace_multiple('''Go to the **001** and click on the 002 003!\n\nPick the option: **"004"**!\nYou will get 005 of the card.''', replacements)

    link = f"https://discord.com/channels/0/0/{link_suffix}"

    event_info = {"subtitle":       "Reminder: Weekly <Free Card>!",
                  "description":  f"Map: {link}\n{location_text}",
                  "footer":      '''"Swish and flick everyone!\nJust like we have been practicing..."''',
                  "account":        "Prof. Flitwick",
                  "image":          image,
                  "title":          title,}

    return await set_event_and_notification(server, event_info, date, event_duration=(4,0,0), start_time=(17,0,0), role="<@&0>")


async def _notify_housecup(server, date, variables, same_day):
    discipline = variables[0]

    event_info = {"image":       "housecup",
                  "title":      f"<{vars.housecup_disciplines_names[discipline]}!>",
                  "subtitle":    "Reminder: <House Cup>!",
                  "description": "Make sure you be there and may the best house win!",
                  "footer":   '''"Did you put your name for the House Cup yet?!" he asked calmly.''',
                  "account":     "Prof. Dumbledore",}

    return await set_event_and_notification(server, event_info, date, time_delta=(0 if same_day else 1), event_duration=(2,0,0), start_time=(19,0,0), only_hour=False, role="@everyone")


async def _notify_club_events(server, date, variables, same_day):
    event_info = {"image":       "club_events",
                  "title":      f"{vars.club_name_short.upper()} Club Events!",
                  "subtitle":   f"Reminder: {vars.weekdays[date.weekday()]}!",
                  "description": "**We start 000!**\nWe will begin with a Quiz, and after roughly 20 min we go over to a Dance!",
                  "footer":   '''"Place your right hand on my waist and...\nOne, two, three... One, two, three..."''',
                  "account":     "Prof. McGonagall",}

    return await set_event_and_notification(server, event_info, date, event_duration=(1,0,0), start_time=(19,30,0), role="<@&0>")


async def _notify_club_points(server, date, variables, same_day):
    channel = server.get_channel(channel_ids["announcements"])

    event_info = {"mention":     "Mention: <@&0>",
                  "description": "Reminder to all who haven't earned\ntheir 100 Club points yet!\n\n"\
                                 "Please do so by the **end of the week**\nor inform a <@&0> / <@&0>\nif you are unable to do so!",
                  "footer":   '''"And be warned... I shall know if you have not practiced."''',
                  "account":     "Prof. Snape",}

    return await _send_direct_notification(channel, event_info, None, [], None)


async def _notify_maintenance(server, date, variables, same_day):
    event_info = {"image":       "maintenance",
                  "title":       "",
                  "subtitle":    "Reminder: <Maintenance!>",
                  "description": "**It starts 000!**\nDuring this period the game will be unavailable!",
                  "footer":   '''"Go on, scram! Or I will hanging you by your thumbs in the dungeons!"''',
                  "account":     "Mr. Filch",}

    return await set_event_and_notification(server, event_info, date, time_delta=(0 if same_day else 1), event_duration=(3,0,0), start_time=(24,0,0))


async def _notify_rankings(server, date, variables, same_day):
    channel = server.get_channel(channel_ids["staffroom"])

    event_info = {"mention":     "Mention: <@&0> <@&0>",
                  "description": "Dear Staff,\nremember to take a picture of this week's top 3 students!\n\n(Please post the screenshots below!)",
                  "footer":   '''"But be quick! It is not wise to be wandering around this late hour."''',
                  "account":     "Prof. Dumbledore",}

    return await _send_direct_notification(channel, event_info, None, [], None)


# every event_name notification_dict() can hand back must have an entry here
NOTIFICATION_HANDLERS = {"Welcome":     _notify_welcome,
                          "Level Up":    _notify_level_up,
                          "Birthday":    _notify_birthday,
                          "Housecup":    _notify_housecup,
                          "Club Events": _notify_club_events,
                          "Club Points": _notify_club_points,
                          "Maintenance": _notify_maintenance,
                          "Rankings":    _notify_rankings,
                          **{name: partial(_notify_card, **variant) for name, variant in CARD_VARIANTS.items()},}


async def print_notification(server, event_name, date=None, variables=None, is_task=True, same_day=False):
    variables = variables if variables is not None else []
    events    = vars.notification_dict()
    task_name = events[event_name]

    if vars.test_bot["test_tasks"] and is_task:
        events_short = vars.notification_dict(is_short=True)
        log(f'''"{events_short[event_name]}" task running... {datetime.now()}!''')
    elif not is_task:
        if date and task_name:
            date = date.astimezone(tz=vars.time_trigger[task_name].tzinfo)

    return await NOTIFICATION_HANDLERS[event_name](server, date, variables, same_day)
