import src.variables as vars

from src.db_classes import ExtraVariable, Portkeys
from src.functions import get_today, print_notification

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
        hour += 1
        minute = (minute + vars.wait_for) % 60
    tz = now.astimezone().tzinfo

    time_trigger = {key:time(hour=hour, minute=minute, tzinfo=tz) for key in vars.time_trigger}
    channel_ids = vars.channel_ids_test
    
    del[hour, minute, tz]
else:
    channel_ids = vars.channel_ids
    time_trigger = vars.time_trigger



# game reset reminder:
#@tasks.loop(time=time_trigger["game_reset"])
#async def game_reset_reminder(server):
#    today = datetime.now(tz=time_trigger["game_reset"].tzinfo)


# morning reminder:
@tasks.loop(time=time_trigger["morning"])
@get_today()
async def morning_reminder(bot, today):
    DB = bot.db
    SERVER = bot.server
    
    if not vars.test_bot["test_tasks"]:
        birthdays = Portkeys(message_id="unarchived", birthday=datetime(year=2000, month=today.month, day=today.day), specified_columns=["user_id", "message_id", "birthday"]).get(multiple=True)
    else:
        birthdays = [0 for _ in range(1)]

    # trigger on someone birthday
    if birthdays:
        await print_notification(SERVER, event_name="Birthday", date=today, variables=[birthdays])
    
    try:
        DB.backup()
    except Exception as error:
        print("task error, " + error)


# weekly_cards reminder:
@tasks.loop(time=time_trigger["weekly_cards"])
@get_today()
async def weekly_cards_reminder(bot, today):
    SERVER = bot.server

    # trigger on monday, wednesday and friday
    if not vars.test_bot["test_tasks"]:
        if today.weekday() == 0:
            await print_notification(SERVER, event_name="Card - Matagot", date=today)
        
        elif today.weekday() == 2:
            await print_notification(SERVER, event_name="Card - Book of Monsters", date=today)
        
        elif today.weekday() == 4:
            await print_notification(SERVER, event_name="Card - Cornish Pixies", date=today)
    
    else:
        await print_notification(SERVER, event_name="Card - Matagot", date=today)
        await print_notification(SERVER, event_name="Card - Book of Monsters", date=today)
        await print_notification(SERVER, event_name="Card - Cornish Pixies", date=today)


# housecup reminder:
@tasks.loop(time=time_trigger["housecup"])
@get_today()
async def housecup_reminder(bot, today):
    SERVER = bot.server
    
    housecup_disciplines = ExtraVariable(name="housecup_disciplines")
    housecup_reset = ExtraVariable(name="housecup_reset")

    # trigger every 2 weeks from base date
    delta = datetime(year=today.year, month=today.month, day=today.day, tzinfo=vars.gameserver_timezone) - vars.base_housecup_date
    if (vars.test_bot["test_tasks"] or delta.days % 14 == 0):
        discipline = housecup_disciplines.get()[int(delta.days / 14) % 4]

        await print_notification(SERVER, event_name="Housecup", variables=[discipline], date=today)

        if (not vars.test_bot["test_tasks"] and housecup_disciplines.get()[3] == discipline):
            housecup_reset.change(to=True)

    # reset to default (0, 1, 2, 3)    
    elif (delta.days % 14 == 9 and housecup_reset.get()):
        housecup_disciplines.change(to=(0, 1, 2, 3))
        housecup_reset.change(to=False)


# club_events reminder:
@tasks.loop(time=time_trigger["club_events"])
@get_today()
async def club_events_reminder(bot, today):
    SERVER = bot.server

    # trigger every workday
    if (vars.test_bot["test_tasks"] or today.weekday() not in [5, 6]):
        
        # and if variable is True
        trigger_club_events = ExtraVariable(name="trigger_club_events")
        
        if trigger_club_events.get():
            await print_notification(SERVER, event_name="Club Events", date=today)
        
        # default True
        else:
            trigger_club_events.change(to=True)
    
    # trigger every weekend
    if (vars.test_bot["test_tasks"] or today.weekday() in [4, 6]):
        
        # delete the previous ones
        if not vars.test_bot["test_tasks"]:
            channel = SERVER.get_channel(channel_ids["announcements"])
            [await message.delete() async for message in channel.history(after=(today - timedelta(days=2))) if (message.author.name == "Prof. Snape" and message.content == "Mention: <@&0>")]
        
        message = await print_notification(SERVER, event_name="Club Points", date=today)
        
        # if it is Sunday delete it after reset
        if not vars.test_bot["test_tasks"] and today.weekday() == 6:
            next_reset = today.replace(hour  =time_trigger["game_reset"].hour,
                                       minute=time_trigger["game_reset"].minute,
                                       second=time_trigger["game_reset"].second,
                                       tzinfo=time_trigger["game_reset"].tzinfo,) + timedelta(days=1)

            delta = next_reset - today
            await message.delete(delay=delta.seconds)


# game_midnight reminder:
@tasks.loop(time=time_trigger["game_midnight"])
@get_today()
async def game_midnight_reminder(bot, today):
    SERVER = bot.server

    # trigger every 2 weeks from base date
    delta = datetime(year=today.year, month=today.month, day=today.day) - ExtraVariable(name="base_date_maintenance").get()
    if (vars.test_bot["test_tasks"] or delta.days % 14 == 0):
        await print_notification(SERVER, event_name="Maintenance", date=today)


# midnight reminders
@tasks.loop(time=time_trigger["midnight"])
@get_today()
async def midnight_reminder(bot, today):
    SERVER = bot.server

    # trigger on sunday (FOR STAFF ONLY!)
    if (vars.test_bot["test_tasks"] or today.weekday() == 6):        
        await print_notification(SERVER, event_name="Rankings", date=today)


# user create task
def create_a_task(timer):

    @tasks.loop(hours=timer["hours"], minutes=timer["minutes"], seconds=timer["seconds"], count=2)
    async def task_template(event_info):
        if task_template.current_loop != 0:
            print(f"Task executed! {event_info} {datetime.now()}")
        else:
            task_template.__name__ = f"task_{event_info['id']}"

    return task_template