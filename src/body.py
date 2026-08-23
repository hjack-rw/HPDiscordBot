from src.db         import Database, Experience, WelcomeMessages
from src.tasks      import *
from src.variables  import bot_id, channel_ids, channel_ids_test, dev_user_id, server_id, test_bot 
from src.views      import WelcomeView, MemberView

import asyncio

from atexit   import register
from datetime import datetime, timedelta

from discord.app_commands import Group
from discord.errors       import NotFound
from discord.ext          import commands
from discord.flags        import Intents


# SETTINGS
# for testing
# test_bot["test_body"]   = True # overwrite if needed
# test_bot["test_events"] = True # overwrite if needed

if test_bot["test_body"]:
    channel_ids = channel_ids_test


# Main BOT body
class BOT(commands.Bot):
    
    def __init__(self):
        super().__init__(command_prefix="/", intents=Intents.all(), application_id=bot_id)
        
        self.server = None
        self.db     = Database
        
        register(self.disconnect_sync)

        self.user_last_executed = {}
        self.user_last_reacted  = {}

    # Async initialization goes here
    async def async_init(self):
        DB = self.db
        
        await DB.disable_journal()

        if await DB.is_empty():
            await DB.restore(clear=True)

        #TODO a hybrid connection to DB if hitting peak performance
        #await self.db.reconnect()

        self.user_experience = await Experience.initialize()

    # Sync function for atexit
    def disconnect_sync(self):
        asyncio.run(self.db.disconnect())


    # Start event
    async def on_ready(self):        
        print(f"{'Deployed' if any(test_bot.values()) else 'Logged on as'} {self.user}!")


        # asynchornous initialization
        await self.async_init()


        # load commands
        try:
            await self.tree.sync()
            synched  = bot.tree.get_commands()

            groups   = [cmd for cmd in synched if isinstance(cmd, Group)]
            commands = [cmd for cmd in synched if not isinstance(cmd, Group)]

            print(f"Synched {len(groups)} group(s)")
            print(f"With {len(commands) + sum(len(group.commands) for group in groups)} command(s) total")
        
        except Exception as error:
            print(error)
        
        
        # get SERVER
        while self.server is None:
            self.server = self.get_guild(server_id)
            
            if self.server:
                break

            await asyncio.sleep(3)

        SERVER = self.server


        # start tasks
        for reminder in [
                         game_reset_reminder, 
                         morning_reminder,
                         weekly_cards_reminder,
                         housecup_reminder,
                         #club_events_reminder,
                         game_midnight_reminder,
                         #midnight_reminder
                        ]:
            if not reminder.is_running():
                reminder.start(self)

        
        # reactivate WelcomeViews
        for welcome_message in (await WelcomeMessages.initialize(date__greatequal=(datetime.now() - timedelta(days=14)), order=["date-"])).get():
            try:
                CHANNEL = SERVER.get_channel(channel_ids["welcome"])
                
                message = await CHANNEL.fetch_message(welcome_message["message_id"])
                user = SERVER.get_member(welcome_message["user_id"])
                
                self.add_view(view=WelcomeView(user=user, stickers=SERVER.stickers), message_id=message.id)
            except NotFound:
                pass

        
        # reactivate MemberView
        CHANNEL         = SERVER.get_channel(channel_ids["marauders-map"])
        MEMBERS_MESSAGE = await CHANNEL.fetch_message(0)
        
        self.members_view = MemberView(members=SERVER.members, message=MEMBERS_MESSAGE)
        self.add_view(view=self.members_view, message_id=MEMBERS_MESSAGE.id)
        await self.members_view.print_list()
        

        if test_bot["test_events"]:
            self.dispatch("member_join",   SERVER.get_member(dev_user_id))
            self.dispatch("member_remove", SERVER.get_member(dev_user_id))


        ### TESTS HERE ###
        if test_bot["local_deploy"]:
           
            
      
            pass
        
        ### END ###

############################################################################################################

bot = BOT()