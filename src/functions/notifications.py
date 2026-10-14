import src.variables as vars

from .core        import log
from .discord_utils import send_webhook
from .text_utils   import replace_multiple, convert_to_unix_time, catch_error
from .media        import get_animal_rank

from dataclasses import dataclass
from datetime    import datetime, timedelta
from functools   import partial
from glob        import glob
from os          import path
from re          import search
from typing      import Awaitable, Callable, Optional

from discord.embeds              import Embed
from discord.enums               import EntityType, PrivacyLevel
from discord.file                import File


if vars.test_bot["test_command"] or vars.test_bot["test_events"] or vars.test_bot["test_tasks"]:
    channel_ids = vars.channel_ids_test
else:
    channel_ids = vars.channel_ids

BELL_ICON_URL = "https://storage.googleapis.com/chronicle-assets/images/icons/bell-alert-white.png"


@dataclass
class Delivery:
    ''' progress of a queued send - a retry reuses the stored window and resumes after an
    already-created event instead of creating a second one, see memory '''
    window:        tuple
    event_id:      Optional[int] = None
    save_event_id: Optional[Callable[[int], Awaitable[None]]] = None


def event_window(event_name, date, same_day=False):
    ''' (beginning, ending) of the scheduled event a notification announces, None for
    notifications without one - one source for the handlers and the reminder queue '''

    timing = EVENT_TIMINGS.get(event_name)
    if timing is None:
        return None

    # for testing
    if vars.test_bot["test_tasks"]:
        beginning = datetime.now(tz=date.tzinfo) + timedelta(minutes=vars.wait_for*2)
        return beginning, beginning + timedelta(minutes=vars.wait_for)

    hour, minute, second = timing["start"]
    trigger_day = date + timedelta(days=(0 if same_day else timing["days_after"]))
    beginning   = trigger_day.replace(hour=(hour % 24), minute=(minute % 60), second=(second % 60), microsecond=0)

    hours, minutes, seconds = timing["duration"]
    return beginning, beginning + timedelta(hours=hours, minutes=minutes, seconds=seconds)


def duration_text(beginning, ending):
    minutes = int((ending - beginning).total_seconds() // 60)

    if minutes < 60:
        return f"~{minutes} minutes"
    return f"~{minutes // 60} hour{'s' if minutes >= 120 else ''}"


async def set_event_and_notification(server, event_info, event_name, date, same_day=False, only_hour=True, role="@everyone", delivery=None):
    ''' the scheduled event and its announcement as one unit - Discord errors propagate, so a
    queued send retries the whole unit, see memory '''

    beginning, ending = delivery.window if delivery else event_window(event_name, date, same_day)
    duration = duration_text(beginning, ending)

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


    # fixed, code-defined asset - see memory
    image_path = glob(path.join(vars.image_data_path, "events", f"{event_info['image']}.*"))

    # create event, unless a previous try of this delivery already did
    if not vars.test_bot["test_tasks"] and not (delivery and delivery.event_id):
        # a late send can't start the event in the past - the minute of margin covers the request itself
        now   = datetime.now(tz=beginning.tzinfo)
        start = beginning if beginning > now + timedelta(minutes=1) else now + timedelta(minutes=2)

        if not image_path:
            log("Could not create event... Image not found!")
        elif start >= ending:
            log("Could not create event... It is already over!")
        else:
            with open(image_path[0], "rb") as file:
                image_bytes = file.read()

            event = await server.create_scheduled_event(name=event_name,
                                                        start_time=start.astimezone(),
                                                        end_time=ending.astimezone(),
                                                        description=event_info["description"],
                                                        location=event_info["location"],
                                                        privacy_level=PrivacyLevel.guild_only,
                                                        entity_type=EntityType.external,
                                                        image=image_bytes)
            if delivery:
                await delivery.save_event_id(event.id)


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

    # gone when the event ends - a late send stays up for less
    if not vars.test_bot["test_tasks"]:
        await message.delete(delay=max((ending - datetime.now(tz=ending.tzinfo)).total_seconds(), 0))


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


async def _notify_welcome(server, date, variables, same_day, delivery=None):
    new_user, file, view = variables
    channel = server.get_channel(channel_ids["welcome"])

    event_info = {"mention":    f"Mention: <@{new_user.id}>",
                  "title":      f"Welcome {new_user.name}, to {vars.club_name}! <:hugs:1256225688403447888>",
                  "description": "Go to <id:guide> and follow the instructions :)",
                  "footer":   f'''"You are a Wizard, {new_user.name}."''',
                  "account":     "Prof. Hagrid",}

    return await _send_direct_notification(channel, event_info, file, [], view)


async def _notify_level_up(server, date, variables, same_day, delivery=None):
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


async def _notify_birthday(server, date, variables, same_day, delivery=None):
    birthday_users = [await server.fetch_member(user_id) for user_id in variables[0]]
    birthday_user  = birthday_users[0]
    channel = server.get_channel(channel_ids["great-hall"])

    # fixed, code-defined asset - see memory
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


# one data table + one handler for the 3 weekly card reminders - see memory
CARD_VARIANTS = {"Card - Matagot":          {"card_message_key": "card_matagot", "image": "card_matagot", "title": "<Matagot! (rare)>",
                                              "replacements": ["Staircase", "\nMatagot", "next to the Transfiguration Classroom", "Hand it Over to Hagrid", "1 copy"]},
                  "Card - Book of Monsters":{"card_message_key": "card_book_of_monsters", "image": "card_book_of_monsters", "title": "<Book of Monsters! (rare)>",
                                              "replacements": ["History of Magic Classroom", "Book", "in the corner", "Stroke the Spine and Then Open It", "1 copy"]},
                  "Card - Cornish Pixies":  {"card_message_key": "card_cornish_pixies", "image": "card_cornish_pixies", "title": "<Cornish Pixies! (common)>",
                                              "replacements": ["Library", "Pixies", "first bookcase row left", "Use Glacius.", "3 copies"]},}

# start (h, m, s) on the trigger day + days_after (0 when same_day), and duration (h, m, s)
EVENT_TIMINGS = {**{name: {"start": (17,0,0), "duration": (4,0,0), "days_after": 0} for name in CARD_VARIANTS},
                 "Housecup":    {"start": (19,0,0),  "duration": (2,0,0), "days_after": 1},
                 "Club Events": {"start": (19,30,0), "duration": (1,0,0), "days_after": 0},
                 "Maintenance": {"start": (24,0,0),  "duration": (3,0,0), "days_after": 1},}


async def _notify_card(server, date, variables, same_day, delivery=None, *, event_name, card_message_key, image, title, replacements):
    # placeholders substituted before the link is spliced in, not after - see memory
    location_text = replace_multiple('''Go to the **001** and click on the 002 003!\n\nPick the option: **"004"**!\nYou will get 005 of the card.''', replacements)

    link = f"https://discord.com/channels/{vars.server_id}/{channel_ids['charms']}/{vars.card_message_ids[card_message_key]}"

    event_info = {"subtitle":       "Reminder: Weekly <Free Card>!",
                  "description":  f"Map: {link}\n{location_text}",
                  "footer":      '''"Swish and flick everyone!\nJust like we have been practicing..."''',
                  "account":        "Prof. Flitwick",
                  "image":          image,
                  "title":          title,}

    return await set_event_and_notification(server, event_info, event_name, date, role=f"<@&{vars.role_ids['card_reminder']}>", delivery=delivery)


async def _notify_housecup(server, date, variables, same_day, delivery=None):
    discipline = variables[0]

    event_info = {"image":       "housecup",
                  "title":      f"<{vars.housecup_disciplines_names[discipline]}!>",
                  "subtitle":    "Reminder: <House Cup>!",
                  "description": "Make sure you be there and may the best house win!",
                  "footer":   '''"Did you put your name for the House Cup yet?!" he asked calmly.''',
                  "account":     "Prof. Dumbledore",}

    return await set_event_and_notification(server, event_info, "Housecup", date, same_day=same_day, only_hour=False, role="@everyone", delivery=delivery)


async def _notify_club_events(server, date, variables, same_day, delivery=None):
    event_info = {"image":       "club_events",
                  "title":      f"{vars.club_name_short.upper()} Club Events!",
                  "subtitle":   f"Reminder: {vars.weekdays[date.weekday()]}!",
                  "description": "**We start 000!**\nWe will begin with a Quiz, and after roughly 20 min we go over to a Dance!",
                  "footer":   '''"Place your right hand on my waist and...\nOne, two, three... One, two, three..."''',
                  "account":     "Prof. McGonagall",}

    return await set_event_and_notification(server, event_info, "Club Events", date, role=f"<@&{vars.role_ids['club_events']}>", delivery=delivery)


async def _notify_club_points(server, date, variables, same_day, delivery=None):
    channel = server.get_channel(channel_ids["announcements"])
    staff_a, staff_b = vars.role_ids["staff"]

    event_info = {"mention":     f"Mention: <@&{vars.role_ids['club_events']}>",
                  "description": "Reminder to all who haven't earned\ntheir 100 Club points yet!\n\n"\
                                 f"Please do so by the **end of the week**\nor inform a <@&{staff_a}> / <@&{staff_b}>\nif you are unable to do so!",
                  "footer":   '''"And be warned... I shall know if you have not practiced."''',
                  "account":     "Prof. Snape",}

    return await _send_direct_notification(channel, event_info, None, [], None)


async def _notify_maintenance(server, date, variables, same_day, delivery=None):
    event_info = {"image":       "maintenance",
                  "title":       "",
                  "subtitle":    "Reminder: <Maintenance!>",
                  "description": "**It starts 000!**\nDuring this period the game will be unavailable!",
                  "footer":   '''"Go on, scram! Or I will hanging you by your thumbs in the dungeons!"''',
                  "account":     "Mr. Filch",}

    return await set_event_and_notification(server, event_info, "Maintenance", date, same_day=same_day, delivery=delivery)


async def _notify_rankings(server, date, variables, same_day, delivery=None):
    channel = server.get_channel(channel_ids["staffroom"])
    staff_a, staff_b = vars.role_ids["staff"]

    event_info = {"mention":     f"Mention: <@&{staff_a}> <@&{staff_b}>",
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
                          **{name: partial(_notify_card, event_name=name, **variant) for name, variant in CARD_VARIANTS.items()},}


async def print_notification(server, event_name, date=None, variables=None, is_task=True, same_day=False, delivery=None):
    variables = variables if variables is not None else []
    events    = vars.notification_dict()
    task_name = events[event_name]

    # trigger key, not the short-dict lookup that raised KeyError for every event but the first per trigger
    if vars.test_bot["test_tasks"] and is_task:
        log(f'''"{task_name}" task running... {datetime.now()}!''')
    elif not is_task:
        if date and task_name:
            date = date.astimezone(tz=vars.time_trigger[task_name].tzinfo)

    return await NOTIFICATION_HANDLERS[event_name](server, date, variables, same_day, delivery=delivery)
