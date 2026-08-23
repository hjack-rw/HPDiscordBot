from src.body import bot
from src.db_classes import Portkeys, WelcomeMessages
from src.functions import draw_infocard, print_notification
from src.variables import test_bot, channel_sections_ids, channel_ids, channel_ids_test
from src.views import WelcomeView

from asyncio import get_event_loop
from datetime import datetime
from random import randint

# SETTINGS
# for testing
# test_bot["test_events"] = True # overwrite if needed

if test_bot["test_events"]:
    channel_ids = channel_ids_test


# Enter Server
@bot.event
async def on_member_join(member):
    MEMBERS_VIEW = bot.members_view

    # skip bots
    if not member.bot:
        SERVER = bot.server

        image = draw_infocard(new_user=member, all_members_count=len([member for member in SERVER.members if not member.bot]))
        view = WelcomeView(user=member, stickers=SERVER.stickers)

        message = await print_notification(SERVER, event_name="Welcome", variables=[member, image, view])

        if not test_bot["test_events"]:
            WelcomeMessages().add(user_id=member.id, message_id=message.id, date=datetime.now())
    
        await MEMBERS_VIEW.update_members(members=SERVER.members)
    
    else:
        print(f"BOT: {member.name} joined the server!")


# Leave Server
@bot.event
async def on_member_remove(member):
    SERVER          = bot.server
    MEMBERS_VIEW    = bot.members_view
    USER_EXPERIENCE = bot.user_experience

    await MEMBERS_VIEW.update_members(members=SERVER.members)
    
    if not test_bot["test_events"] and not member.bot:
        
        CHANNEL = SERVER.get_channel(channel_ids["portkey-arrival"])
        if message_id := Portkeys(user_id=member.id).archive(return_empty=True):
            
            message = await CHANNEL.fetch_message(message_id)
            await message.delete()

        CHANNEL = SERVER.get_channel(channel_ids["welcome"])
        if message_id := WelcomeMessages().remove(user_id=member.id):
            
            message = await CHANNEL.fetch_message(message_id)
            await message.delete()
        
        USER_EXPERIENCE.archive(user_id=member.id)


# Post on Server
@bot.event
async def on_message(message):
    SERVER             = bot.server
    USER_EXPERIENCE    = bot.user_experience
    USER_LAST_EXECUTED = bot.user_last_executed
    MESSAGE_COOLDOWN   = 60.0
    
    # skip bots
    if message.author.bot:
        return
    
    # skip if message channel is not allowed
    if message.channel.id != channel_ids["welcome"]:
        category = message.channel.category
        if not category or category.id not in [channel_sections_ids["general"], channel_sections_ids["guides"], channel_sections_ids["offtopic"]]:
            return

    # user cooldown
    now = get_event_loop().time()
    last_time = USER_LAST_EXECUTED.get(message.author.id, 0)

    # assert cooldown
    if now - last_time < MESSAGE_COOLDOWN:
        return # still in cooldown
    
    # update cooldown
    USER_LAST_EXECUTED[message.author.id] = now
    
    
    # double points on weekend 
    multiplier = 2 if datetime.now().weekday() in [5, 6] else 1

    
    # attachments have fixed points, capped at 5 xp
    if (count_attachments := min(len(message.attachments), 5)) > 0:
        base = 15 * count_attachments * multiplier
    
    # random xp for messages btween 15-25
    else:
        base = randint(15, 25) * multiplier

    
    # reward 1 additional xp per 50 characters, capped at 5 xp
    xp_gained = base + min(len(message.content) // 50, 5)
    
    if not test_bot["test_events"]:
        try:
            await USER_EXPERIENCE.tweak(server=SERVER, member=message.author, amount=xp_gained)
        except Exception as error:
            print(str(error))


# React on Server
@bot.event
async def on_reaction_add(reaction, user):
    SERVER             = bot.server
    USER_EXPERIENCE    = bot.user_experience
    USER_LAST_REACTED  = bot.user_last_reacted
    REACTION_COOLDOWN  = 30

    # skip bots
    if user.bot:
        return

    message = reaction.message

    # skip if message channel is not allowed
    if message.channel.id not in [channel_ids["portraits"], channel_ids["hagrids-hut"], channel_ids["dueling-club"], channel_ids["felix-felicis"], channel_ids["gallery"]]:
        return

    # user cooldown    
    now = get_event_loop().time()
    last_time = USER_LAST_REACTED.get(user.id, 0)
    
    # assert cooldown
    if now - last_time < REACTION_COOLDOWN:
        return  # still in cooldown
    
    # update cooldown
    USER_LAST_REACTED[user.id] = now

    if not test_bot["test_events"]:
        try:
            await USER_EXPERIENCE.tweak(server=SERVER, member=user, amount=5)
        except Exception as error:
            print(str(error))