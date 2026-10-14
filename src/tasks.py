import src.variables as vars

from src.db import ExtraVariable, Portkeys, ReminderQueue
from src.functions  import get_today, log, print_notification, upload_backup_rotation, Delivery, event_window, duration_text

from asyncio  import Lock
from calendar import isleap
from datetime import datetime, time, timedelta

from discord.ext import tasks


# SETTINGS
# for testing
# vars.test_bot["test_tasks"] = True # overwrite if needed

if vars.test_bot["test_tasks"]:
    now = datetime.now()

    # replace time
    hour, minute  = (int(value) for value in now.strftime("%H/%M").split("/"))
    if minute <= (59 - vars.wait_for):
        minute += vars.wait_for
    else:
        hour = (hour + 1) % 24
        minute = (minute + vars.wait_for) % 60
    tz = now.astimezone().tzinfo

    time_trigger = {key:time(hour=hour, minute=minute, tzinfo=tz) for key in vars.time_trigger}
    channel_ids = vars.channel_ids_test
    
    del[hour, minute, tz]
else:
    channel_ids = vars.channel_ids
    time_trigger = vars.time_trigger



# game reset reminder:
@tasks.loop(time=time_trigger["game_reset"])
@get_today()
async def game_reset_reminder(bot, today):
    DB = bot.db
    SERVER = bot.server
    
    # run cleanup of past notifications
    # webhook messages carry the display name, custom_avatars keys are slugs - see memory
    notification_authors = set(vars.custom_avatar_names.values())

    # - delete SNAPE only on mondays
    if today.weekday() != 0:
        notification_authors.remove("Prof. Snape")
    
    # - delete DUMBLEDORE only on sundays
    if today.weekday() != 6:
        notification_authors.remove("Prof. Dumbledore")

    channel = SERVER.get_channel(channel_ids["announcements"])
    [await message.delete() async for message in channel.history(after=(today - timedelta(days=2))) if (message.author.name in notification_authors and "Mention: " in message.content)]

    # backup database
    if not vars.test_bot["test_tasks"]:
        try:
            await DB.backup()
        except Exception as error:
            log(str(error))


# reminder queue - every reminder due today goes into the DB first, so a restart or a failed
# send (e.g. Discord's Cloudflare 429) never loses one - see memory
RETRY_DELAY  = 5 * 60
MISSED_KEPT  = 24 * 3600
CARD_DAYS    = {0: "Card - Matagot", 2: "Card - Book of Monsters", 4: "Card - Cornish Pixies"}

# a send pass and the admin skip/postpone never interleave around a Discord await
queue_lock = Lock()


async def _birthday_users(day):
    if vars.test_bot["test_tasks"]:
        return [vars.dev_user_id]

    birthdays = (await Portkeys.initialize(message_id="unarchived", birthday=datetime(year=2000, month=day.month, day=day.day), specified_columns=["user_id", "message_id", "birthday"])).get(multiple=True)

    # if year is not leap, check for Feb 29 birthdays on Feb 28
    if (day.month == 2 and day.day == 28) and not isleap(day.year):
        birthdays += (await Portkeys.initialize(message_id="unarchived", birthday=datetime(year=2000, month=2, day=29), specified_columns=["user_id", "message_id", "birthday"])).get(multiple=True)

    return birthdays


def _housecup_delta(day):
    return datetime(year=day.year, month=day.month, day=day.day, tzinfo=vars.gameserver_timezone) - vars.base_housecup_date


async def _reminder_variables(name, day):
    ''' read when the reminder is sent, not when it is planned - a birthday member who left
    since midnight or a discipline changed during the day must not be sent stale '''
    if name == "Birthday":
        return [await _birthday_users(day)]
    elif name == "Housecup":
        return [(await ExtraVariable.initialize(name="housecup_disciplines")).get()[int(_housecup_delta(day).days / 14) % 4]]
    return []


async def _due_reminders(day):
    ''' [(event_name, trigger_key)] for every reminder due on `day` '''
    due = []

    # birthdays
    if await _birthday_users(day):
        due.append(("Birthday", "morning"))

    # weekly cards on monday, wednesday and friday
    due += [(name, "weekly_cards") for weekday, name in CARD_DAYS.items() if vars.test_bot["test_tasks"] or day.weekday() == weekday]

    # housecup every 2 weeks from base date
    housecup_disciplines = await ExtraVariable.initialize(name="housecup_disciplines")
    housecup_reset       = await ExtraVariable.initialize(name="housecup_reset")

    # trigger every 2 weeks from base date
    delta = _housecup_delta(day)
    if (vars.test_bot["test_tasks"] or delta.days % 14 == 0):
        discipline = housecup_disciplines.get()[int(delta.days / 14) % 4]
        due.append(("Housecup", "housecup"))

        if (not vars.test_bot["test_tasks"] and housecup_disciplines.get()[3] == discipline):
            await housecup_reset.change(to=True)

    # reset to default (0, 1, 2, 3)
    elif (delta.days % 14 == 9 and housecup_reset.get()):
        await housecup_disciplines.change(to=(0, 1, 2, 3))
        await housecup_reset.change(to=False)

    # maintenance every 2 weeks from base date
    delta = datetime(year=day.year, month=day.month, day=day.day) - (await ExtraVariable.initialize(name="base_date_maintenance")).get()
    if (vars.test_bot["test_tasks"] or delta.days % 14 == 0):
        due.append(("Maintenance", "game_midnight"))

    return due


async def plan_reminders(now, force=False):
    ''' queue every reminder of the days not planned yet (at most yesterday + today) -
    returns whether anything was planned '''
    planned = await ExtraVariable.initialize(name="reminder_queue_planned")
    today   = now.astimezone(vars.gameserver_timezone).date()
    last    = planned.get()

    if last is not None and last.date() >= today and not force:
        return False

    # first plan ever (or a test run): today's earlier reminders already went out without the queue
    if last is None or force:
        days, not_before = [today], now
    else:
        days, not_before = [day for day in (today - timedelta(days=1), today) if day > last.date()], None

    queue = await ReminderQueue.initialize()
    queued = {(entry["name"], entry["date"].date()) for entry in queue.get()}

    for day in days:
        for name, trigger_key in await _due_reminders(day):
            send_at = datetime.combine(day, time_trigger[trigger_key])
            if (name, day) in queued or (not_before and send_at < not_before):
                continue

            # a reminder without an event (birthday) is due until the end of its day
            window   = event_window(name, send_at)
            deadline = window[1] if window else datetime.combine(day + timedelta(days=1), time(tzinfo=send_at.tzinfo))

            entry = {"name":         name,
                     "send_at":      int(send_at.timestamp()),
                     "deadline":     int(deadline.timestamp()),
                     "event_window": window and tuple(int(moment.timestamp()) for moment in window),
                     "missed":       deadline <= now,}

            await queue.add(date=datetime.combine(day, time()), **entry)
            log(f"queue: {describe_reminder(entry)}{'' if entry['missed'] else ' planned'}")

    await planned.change(to=datetime.combine(today, time()))
    return True


# club_events reminder:
@tasks.loop(time=time_trigger["club_events"])
@get_today()
async def club_events_reminder(bot, today):
    SERVER = bot.server

    # trigger every workday
    if (vars.test_bot["test_tasks"] or today.weekday() not in [5, 6]):
        
        # and if variable is True
        trigger_club_events = await ExtraVariable.initialize(name="trigger_club_events")
        
        if trigger_club_events.get():
            await print_notification(SERVER, event_name="Club Events", date=today)
        
        # default True
        else:
            await trigger_club_events.change(to=True)
    
    # trigger every weekend
    if (vars.test_bot["test_tasks"] or today.weekday() in [4, 6]):
        
        # delete the previous ones
        if not vars.test_bot["test_tasks"]:
            channel = SERVER.get_channel(channel_ids["announcements"])
            [await message.delete() async for message in channel.history(after=(today - timedelta(days=2))) if (message.author.name == "Prof. Snape" and "Mention: " in message.content)]
        
        await print_notification(SERVER, event_name="Club Points", date=today)


# midnight reminders
@tasks.loop(time=time_trigger["midnight"])
@get_today()
async def midnight_reminder(bot, today):
    SERVER = bot.server

    # trigger on sunday (FOR STAFF ONLY!)
    if (vars.test_bot["test_tasks"] or today.weekday() == 6):
        await print_notification(SERVER, event_name="Rankings", date=today)


def describe_reminder(entry):
    ''' "Maintenance (15/10 00:00, ~3 hours)" - the event's start and duration (the send time for a
    reminder without an event), "Maintenance missed" once its deadline passed '''
    if entry["missed"]:
        return f"{entry['name']} missed"

    tz = time_trigger[vars.notification_dict()[entry["name"]]].tzinfo

    if not entry["event_window"]:
        return f"{entry['name']} ({datetime.fromtimestamp(entry['send_at'], tz=tz):%d/%m %H:%M})"

    beginning, ending = (datetime.fromtimestamp(moment, tz=tz) for moment in entry["event_window"])
    return f"{entry['name']} ({beginning:%d/%m %H:%M}, {duration_text(beginning, ending)})"


def _as_entry(row):
    ''' DB row -> the shape describe_reminder() and the senders use '''
    return row | {"event_window": (row["event_start"], row["event_end"]) if row["event_start"] is not None else None}


async def _backup_queue():
    # the live DB is restored from the newest Dropbox backup - without this a restart re-sends
    # or forgets what changed since the last hourly one, see memory
    # a failed upload never fails the queue change it follows
    if not vars.test_bot["test_tasks"]:
        try:
            await upload_backup_rotation()
        except Exception as error:
            log(f"queue: backup failed: {error}")


async def send_due_reminders(server, now):
    async with queue_lock:
        await _send_due_reminders(server, now)


async def _send_due_reminders(server, now):
    ''' one pass over the queue: send what is due, retry a failure every RETRY_DELAY until its
    deadline, drop sent ones, keep missed ones for MISSED_KEPT '''
    queue   = await ReminderQueue.initialize()
    now     = int(now.timestamp())
    changed = False

    for entry in map(_as_entry, queue.get()):
        if entry["missed"]:
            if now >= entry["deadline"] + MISSED_KEPT:
                await queue.remove(entry["id"])
                changed = True
            continue

        if entry["send_at"] > now or entry["next_try"] > now:
            continue

        if now >= entry["deadline"]:
            await queue.change(entry["id"], missed=True)
            log(f"queue: {entry['name']} missed")
            changed = True
            continue

        tz = time_trigger[vars.notification_dict()[entry["name"]]].tzinfo

        async def save_event_id(event_id, entry_id=entry["id"]):
            nonlocal changed
            await queue.change(entry_id, event_id=event_id)
            changed = True

        window   = entry["event_window"] and tuple(datetime.fromtimestamp(moment, tz=tz) for moment in entry["event_window"])
        delivery = Delivery(window=window, event_id=entry["event_id"], save_event_id=save_event_id)

        # event + announcement as one unit - a failure retries the unit, resuming after the event if it was created;
        # the send-time variables read is part of it, so a failed read retries too instead of ending the pass
        try:
            variables = await _reminder_variables(entry["name"], entry["date"])
            if entry["name"] == "Birthday" and not variables[0]:
                await queue.remove(entry["id"])
                log(f"queue: {describe_reminder(entry)} dropped, nobody has a birthday any more")
                changed = True
                continue

            await print_notification(server, event_name=entry["name"], date=datetime.fromtimestamp(entry["send_at"], tz=tz), variables=variables, delivery=delivery)
        except Exception as error:
            # retry bookkeeping only - not worth a backup, a restart just retries at once
            await queue.change(entry["id"], next_try=now + RETRY_DELAY, last_error=str(error)[:200])
            log(f"queue: {describe_reminder(entry)} failed, retry in {RETRY_DELAY // 60} min: {error}")
            continue

        await queue.remove(entry["id"])
        log(f"queue: {describe_reminder(entry)} sent")
        changed = True

    if changed:
        await _backup_queue()


@tasks.loop(minutes=1)
async def reminder_queue_task(bot):
    # keeps the loop alive if one pass fails, like get_today() does for the old reminders;
    # a failing plan never blocks the reminders already queued
    now = datetime.now(tz=vars.gameserver_timezone)

    try:
        await ReminderQueue.ensure_schema()

        if await plan_reminders(now, force=(vars.test_bot["test_tasks"] and reminder_queue_task.current_loop == 0)):
            await _backup_queue()
    except Exception as error:
        log(f"task error in 'reminder_queue_task' (plan): {error}")

    try:
        await send_due_reminders(bot.server, now)
    except Exception as error:
        log(f"task error in 'reminder_queue_task' (send): {error}")


async def _queued_reminder(entry_id):
    queue = await ReminderQueue.initialize(id=entry_id)
    entry = next(iter(queue.get()), None)
    if entry is None:
        raise Exception(f"no queued reminder #{entry_id}")

    return queue, _as_entry(entry)


async def skip_reminder(entry_id):
    ''' drop a queued reminder - an event it already created stays '''
    async with queue_lock:
        queue, entry = await _queued_reminder(entry_id)

        await queue.remove(entry_id)
        log(f"queue: {describe_reminder(entry)} skipped")
        await _backup_queue()

    return entry


async def postpone_reminder(server, entry_id, hours):
    ''' move a queued reminder's event by `hours` - the announced time and the retry deadline
    follow, an already-created Discord event is moved too '''
    async with queue_lock:
        return await _postpone_reminder(server, entry_id, hours)


async def _postpone_reminder(server, entry_id, hours):
    queue, entry = await _queued_reminder(entry_id)

    if entry["missed"]:
        raise Exception(f"reminder #{entry_id} was already missed")
    elif not entry["event_window"]:
        raise Exception(f"reminder #{entry_id} has no event to postpone")

    shift = hours * 3600
    new_values = {"event_start": entry["event_start"] + shift, "event_end": entry["event_end"] + shift, "deadline": entry["deadline"] + shift}

    if entry["event_id"] and not vars.test_bot["test_tasks"]:
        event = await server.fetch_scheduled_event(entry["event_id"])
        await event.edit(start_time=datetime.fromtimestamp(new_values["event_start"]).astimezone(),
                         end_time=datetime.fromtimestamp(new_values["event_end"]).astimezone())

    await queue.change(entry_id, **new_values)
    entry = _as_entry(entry | new_values)

    log(f"queue: {describe_reminder(entry)} postponed by {hours} h")
    await _backup_queue()

    return entry


async def list_reminders():
    return [_as_entry(entry) for entry in (await ReminderQueue.initialize()).get()]


# backup rotation - pushes to Dropbox so an unplanned restart doesn't lose data, see memory
@tasks.loop(hours=1)
async def backup_rotation_task(bot):
    if not vars.test_bot["test_tasks"]:
        try:
            await upload_backup_rotation()
        except Exception as error:
            log(str(error))


# user create task
def create_a_task(timer):

    @tasks.loop(hours=timer["hours"], minutes=timer["minutes"], seconds=timer["seconds"], count=2)
    async def task_template(event_info):
        if task_template.current_loop != 0:
            log(f"Task executed! {event_info} {datetime.now()}")
        else:
            task_template.__name__ = f"task_{event_info['id']}"

    return task_template