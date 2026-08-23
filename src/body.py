from src.db import Database
from src.db_classes import Experience, WelcomeMessages
from src.tasks import *
from src.variables import test_bot, server_id, bot_id, channel_ids, channel_ids_test
from src.views import WelcomeView, MemberView

import atexit

from datetime import datetime, timedelta
from discord.errors import NotFound
from discord.ext import commands
from discord.flags import Intents


# SETTINGS
# for testing
# test_bot["test_body"] = True # overwrite if needed
# test_bot["test_events"] = True # overwrite if needed

if test_bot["test_body"]:
    channel_ids = channel_ids_test


# Main BOT body
class BOT(commands.Bot):
    
    def __init__(self):
        super().__init__(command_prefix="/", intents=Intents.all(), application_id=bot_id)
        
        self.db = Database
        self.db.connect()
        atexit.register(self.db.disconnect)

        self.user_experience    = Experience()
        self.user_last_executed = {}
        self.user_last_reacted  = {}

    async def on_ready(self):
        print(f"{'Deployed' if any(test_bot.values()) else 'Logged on as'} {self.user}!")

        try:
            synched = await self.tree.sync()
            print(f"Synched {len(synched)} command(s)")
        
        except Exception as error:
            print(error)
        
        SERVER = self.server = self.get_guild(server_id)

        for reminder in [morning_reminder, weekly_cards_reminder, housecup_reminder, club_events_reminder, game_midnight_reminder, midnight_reminder]:
            if not reminder.is_running():
                reminder.start(self)

        # reactivate WelcomeViews
        for welcome_message in WelcomeMessages(date__greatequal=(datetime.now() - timedelta(days=14)), order=["date-"]).get():
            try:
                CHANNEL = SERVER.get_channel(channel_ids["welcome"])
                
                message = await CHANNEL.fetch_message(welcome_message["message_id"])
                user = SERVER.get_member(welcome_message["user_id"])
                
                self.add_view(view=WelcomeView(user=user, stickers=SERVER.stickers), message_id=message.id)
            except NotFound:
                pass

        
        # reactivate MemberView
        CHANNEL         = SERVER.get_channel(channel_ids["sorting-hat"])
        MEMBERS_MESSAGE = await CHANNEL.fetch_message(0)
        
        self.members_view = MemberView(members=SERVER.members, message=MEMBERS_MESSAGE)
        self.add_view(view=self.members_view, message_id=MEMBERS_MESSAGE.id)
        await self.members_view.print_list()
        

        if test_bot["test_events"]:
            self.dispatch('member_join',   SERVER.get_member(0))
            self.dispatch('member_remove', SERVER.get_member(0))

        ### TESTS HERE ###
        if test_bot["local_deploy"]:
           
            
      
            pass
        
        ### END ###

############################################################################################################

bot = BOT()