import src.variables as vars

from src.body       import bot
from src.db         import *
from src.functions  import CustomHousecup, create_leaderboard, draw_infocard, get_avatar, log, print_portkey, send_webhook, standard_response
from src.tasks      import print_notification
from src.views      import *

from asyncio    import to_thread
from datetime   import datetime, timedelta
from itertools  import chain
from os         import path, walk
from statistics import mean, stdev
from typing     import Literal, Optional
from zipfile    import ZipFile, ZIP_DEFLATED

from discord.app_commands import checks, choices, Choice, Group, command
from discord.components   import SelectOption
from discord.embeds       import Embed
from discord.errors       import NotFound
from discord.file         import File
from discord.interactions import Interaction
from discord.member       import Member


# SETTINGS
# for testing
# vars.test_bot["test_command"] = True # overwrite if needed

if vars.test_bot["test_command"]:
    channel_ids = vars.channel_ids_test
else:
    channel_ids = vars.channel_ids


@checks.has_permissions(administrator=True)
class AdminCommands(Group):
    def __init__(self):
        super().__init__(name="_admin", description="Admin-only commands")

    # DB functionality
    @command(name="backup_db")
    @standard_response(silent=True)
    async def backup_db(self, interaction:Interaction):
        ''' Backup the Database manually '''

        DB = bot.db
        await DB.backup()

        await interaction.response.send_message("The Database was **backed up**!", ephemeral=True)

    @command(name="restore_db")
    @standard_response(silent=True)
    async def restore_db(self, interaction:Interaction):
        ''' Restore the Database from backup '''

        DB = bot.db
        await DB.restore()

        # reload XP automatically when DB has been changed
        bot.user_experience = await Experience.initialize()

        await interaction.response.send_message("The Database was **restored**!", ephemeral=True)

    @command(name="export_data")
    @standard_response()
    async def export_data(self, interaction:Interaction):
        ''' Get the Database file, its dump, and a zip of all stored Images as attachments '''

        DB = bot.db
        await DB.backup()

        db_path      = path.join(Database.database_path, Database.database_name)
        dump_path    = path.join(Database.database_path, f"{Database.database_name}-dump")
        images_dir   = path.join(Database.database_path, "images")
        archive_path = path.join(Database.database_path, "images.zip")

        with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
            for directory, _, filenames in walk(images_dir):
                for filename in filenames:
                    file_path = path.join(directory, filename)
                    archive.write(file_path, arcname=path.relpath(file_path, images_dir))

        await interaction.followup.send(
            "Here's the **Database**, its **dump**, and the **Image archive**:",
            files=[File(db_path), File(dump_path), File(archive_path)],
            ephemeral=True,
        )

    ############################################################################################################

    # Event functionality
    @command(name="postpone")
    @standard_response(silent=True)
    async def postpone_club_event_24h(self, interaction:Interaction):
        ''' Postpone the next Club Event by 24h in DB '''

        trigger_club_events = await ExtraVariable.initialize(name="trigger_club_events")

        # change the variable value
        await trigger_club_events.change(to=not trigger_club_events.get())

        await interaction.response.send_message(f"The next Club Event will be **{'restored' if trigger_club_events.get() else 'skipped'}**!", ephemeral=True)


    @command(name="set_maintenance")
    @standard_response(silent=True)
    async def set_maintenance_base_date(self, interaction:Interaction, month:Literal[tuple(vars.months.keys())], day:int): # type: ignore
        ''' Set the base Date for Maintenance in DB '''

        new_date=datetime(year=datetime.now().year, month=vars.months[month], day=day)

        base_date_maintenance = await ExtraVariable.initialize(name="base_date_maintenance")

        # change the variable value
        await base_date_maintenance.change(to=new_date)

        await interaction.response.send_message(f"The next Maintenance will trigger **every two weeks** from **{new_date.strftime('%d/%m/%Y')}**", ephemeral=True)


    @command(name="add_disciplines")
    @standard_response(silent=True)
    async def add_disciplines(self, interaction:Interaction):
        ''' Add House Cup disciplines to DB '''

        REQUIRED_OPTIONS = 4

        # invert dictionary
        options = [SelectOption(label=value, value=key) for key,value in vars.housecup_disciplines_names.items()]

        await interaction.response.send_message(f"Preper to pick {REQUIRED_OPTIONS} times!", ephemeral=True)

        all_picked = []
        for idx in range(1, REQUIRED_OPTIONS+1):
            view = DisciplinesView(options)
            await interaction.followup.send(content=f"{idx}. Discipline:", view=view, ephemeral=True)
            await view.wait()

            # if nothing was picked
            picked = 0 if view.picked is None else view.picked

            # dropdown list gets smaller with each picked option
            all_picked.append(options.pop(picked).value)

        await (await ExtraVariable.initialize(name="housecup_disciplines")).change(to=tuple(all_picked))

        await interaction.followup.send("The House Cup disciplines have been **added**!", ephemeral=True)

    ############################################################################################################

    # Webhook functionality
    @command(name="polyjuice")
    @choices(option=[Choice(name=display_name, value=slug) for slug, display_name in vars.custom_avatar_names.items()])
    @standard_response()
    async def send_as(self, interaction:Interaction, member:Optional[Member], option:Optional[str], say:str):
        ''' Send a Message as User '''

        if (member and not option) or (not member and option):
            user_name = member.display_name if member else vars.custom_avatar_names[option]
            user_avatar_url = get_avatar(member, none=True)

            await send_webhook(target_channel=interaction.channel, user_name=user_name, user_avatar_url=user_avatar_url, content=say)
        elif member and option:
            raise Exception("pick either a 'member' or an 'option', not both")
        else:
            raise Exception("pick a 'member' or an 'option'")


    @command(name="send_notification")
    @standard_response()
    async def send_notification(self, interaction:Interaction, event:Literal[tuple(vars.notification_dict().keys())], member:Optional[Member], same_day:Optional[bool]=False): # type: ignore
        ''' Send the Notification manually '''

        SERVER = bot.server
        today = datetime.now()

        variables = []
        if event == "Welcome" or event == "Birthday":
            if member is None:
                return await interaction.followup.send(f"{event} notifications require to select a Member!", ephemeral=True)
            else:
                if event == "Welcome":
                    # off the event loop - see memory
                    image = await to_thread(draw_infocard, new_user=member, all_members_count=len([member for member in SERVER.members if not member.bot]))
                    view = WelcomeView(user=member, stickers=SERVER.stickers)

                    variables += [member, image, view]
                elif event == "Birthday":
                    variables.append([member.id])

        elif event == "Housecup":
            housecup_disciplines = await ExtraVariable.initialize(name="housecup_disciplines")
            housecup_reset       = await ExtraVariable.initialize(name="housecup_reset")

            today = today.astimezone(tz=vars.gameserver_timezone)
            delta = datetime(year=today.year, month=today.month, day=today.day, tzinfo=vars.gameserver_timezone) - vars.base_housecup_date

            discipline = housecup_disciplines.get()[int(delta.days / 14) % 4]
            variables.append(discipline)

        message = await print_notification(SERVER, event_name=event, date=today, variables=variables, is_task=False, same_day=same_day)

        if not vars.test_bot["test_command"]:
            if event == "Welcome":
                await (await WelcomeMessages.initialize()).add(user_id=member.id, message_id=message.id, date=datetime.now())
            elif event == "Housecup":
                if housecup_disciplines.get()[3] == discipline:
                    await housecup_reset.change(to=True)

    ############################################################################################################

    # Portkey handling functionality
    @command(name="accept_portkey")
    @standard_response()
    async def accept_portkey_for_user(self, interaction:Interaction, message_id:str, member:Member):
        ''' Accept Portkey for User '''

        SERVER  = bot.server

        try:
            message = await interaction.channel.fetch_message(message_id)
            await (await Portkeys.initialize()).add(server=SERVER, message=message, user_id=member.id)
            await interaction.followup.send("The Portkey has been **added**!", ephemeral=True)
        except NotFound:
            raise Exception("what you are trying to accept is not a Portkey")


    @command(name="post_portkey")
    @standard_response()
    async def post_portkey(self, interaction:Interaction, portkey_id:str="last"):
        ''' Print a Portkey '''

        SERVER = bot.server
        CHANNEL = SERVER.get_channel(channel_ids["portkey-arrival"])

        if (portkey := await Portkeys.initialize(id=portkey_id)).raw_data:
            portkey_values = portkey.get()

            if portkey_values["message_id"] is None:
                member = SERVER.get_member(portkey_values["user_id"])

                message = await CHANNEL.send(embed=print_portkey(member, portkey_values))
                await portkey.unarchive(message_id=message.id)
            else:
                raise Exception("the Portkey was already UNARCHIVED")
        else:
            raise Exception("there is no Portkey with that ID")

    ############################################################################################################

    # Leaderboard functionality
    @command(name="update_lb")
    @standard_response()
    async def update_leaderboard(self, interaction: Interaction, mention_all:bool=True, with_custom_housecup:bool=True):
        ''' Updates the Server's Leaderboard '''

        SERVER  = bot.server
        CHANNEL = SERVER.get_channel(channel_ids["leaderboard"])

        # get leaderboard info
        if data := (await ExperienceInfo.initialize(extended=True, archived=False, order=["xp-"])).get(multiple=True):

            # clear the channel
            await CHANNEL.purge(limit=None)

            custom_housecup = []

            # post custom housecup
            if with_custom_housecup:
                custom_housecup_message = await CHANNEL.send(content="", embed=Embed(title="The leading house is... ", color=vars.system_embed_color))
                custom_housecup = [CustomHousecup(house=role.name, all_members_count=len(role.members)) for role in SERVER.roles if role.name in set(vars.houses_names_list())]

            # warm the member cache before threading - see memory
            for user in data:
                if SERVER.get_member(user["user_id"]) is None:
                    try:
                        await SERVER.fetch_member(user["user_id"])
                    except NotFound:
                        log(f"user_id {user['user_id']} no longer in the server, skipping")

            # off the event loop - see memory
            leaderboard, custom_housecup = await to_thread(create_leaderboard, SERVER, data, custom_housecup)

            # post leaderboard
            for position in leaderboard:
                user_id, color, file = position

                embed = Embed(color=color)
                embed.set_image(url=f"attachment://{file.filename}")

                await CHANNEL.send(content="", embed=embed, file=file)

                if mention_all:
                    await CHANNEL.send(content=f"<@{user_id}>")

            # find winning house
            if with_custom_housecup:
                all_points = list(chain.from_iterable([house.points for house in custom_housecup]))

                mn = mean(all_points)
                sd = stdev(all_points)

                scoreboard = {house.name:house.for_scoreboard(mn, sd) for house in custom_housecup}

                log(str(scoreboard))
                winning_house = max(custom_housecup, key=lambda house: scoreboard.get(house.name, float('-inf'))).name

                custom_housecup_embed = custom_housecup_message.embeds[0]
                custom_housecup_embed.title += f"\n {winning_house.capitalize()} !!!"
                custom_housecup_embed.set_thumbnail(url=vars.houses[winning_house]["crest"])

                # crest must be attached to this same edit to resolve - see memory
                crest_file = File(fp=vars.image_data_path + f"houses/{winning_house}.png", filename=f"{winning_house}.png")
                await custom_housecup_message.edit(content="", embed=custom_housecup_embed, attachments=[crest_file])


    @command(name="tweak_xp")
    @standard_response(silent=True)
    async def tweak_xp_manually(self, interaction: Interaction, member:Member, action:Literal["Add", "Subtract", "Set"]="Add", amount:int=10, comment:Optional[str]=None):
        ''' Add / Subtract / Set  XP for User '''

        SERVER          = bot.server
        CHANNEL         = SERVER.get_channel(channel_ids["points-log"])
        USER_EXPERIENCE = bot.user_experience

        action = action.lower()
        current_xp = await USER_EXPERIENCE.tweak(server=SERVER, member=member, amount=amount, after_action=action.lower())

        if current_xp:
            if action != "set":
                action += "ed"
                log = f"**{member.display_name}** - {amount} points {action}! Current XP: **{current_xp}**"
            else:
                log = f"**{member.display_name}** - points set! XP: **{amount}**"

            if comment:
                log += f"\nComment: {comment}"

            await interaction.response.send_message(f"User {member.display_name} has been **{action}**!", ephemeral=True)
            await CHANNEL.send(content=log)


    @command(name="reset_xp")
    @standard_response(silent=True)
    async def reset_xp(self, interaction: Interaction, member:Member):
        ''' Reset XP for User '''

        SERVER  = bot.server
        CHANNEL = SERVER.get_channel(channel_ids["points-log"])

        USER_EXPERIENCE = bot.user_experience
        await USER_EXPERIENCE.reset(user_id=member.id)

        await interaction.response.send_message(f"User {member.display_name} has been **reseted**!", ephemeral=True)
        await CHANNEL.send(content=f"**{member.display_name}** - points reseted! XP: **0**")


    @command(name="reload_xp")
    @standard_response(silent=True)
    async def reload_xp(self, interaction:Interaction):
        ''' Reload XP data manually if DB has been changed '''

        bot.user_experience = await Experience.initialize()

        await interaction.response.send_message("The XP data has been **reloaded**!", ephemeral=True)


    @command(name="change_lb")
    @standard_response(silent=True)
    async def change_leaderboard(self, interaction: Interaction, member:Member, username:Optional[str], offset:Optional[bool]):
        ''' Change the Leaderboard properties for User '''

        info = await ExperienceInfo.initialize(extended=True, user_id=member.id, omitted_columns=["xp", "level", "progress"])

        if (is_archived := info.get_one_column("archived")) is None:
            raise Exception(f"User {member.display_name} doesn't have a leaderboard card")

        if is_archived is True:
            raise Exception(f"User {member.display_name} was ARCHIVED")

        if username is None and offset is None:
            raise Exception("pick a 'username' or an 'offset'")

        all_picked = {}
        if username and username.strip() != "":
            all_picked["username"] = username
        if offset is not None:
            all_picked["offset"] = offset

        await info.change(**all_picked)

        await interaction.response.send_message(f"User {member.display_name} leaderboard card has been **changed**!", ephemeral=True)

    ############################################################################################################

    # Cleanup functionality
    @command(name="clear_downtime")
    @standard_response()
    async def clear_downtime(self, interaction:Interaction):
        ''' Delete all Downtime-logging messages from the `Downtime notifier` bot in this channel '''

        SERVER = bot.server
        CHANNEL = SERVER.get_channel(channel_ids["the-sorting-hat"])

        deleted = await CHANNEL.purge(limit=None, check=lambda message: message.author.id == 818105614055112715)

        await interaction.followup.send(f"**{len(deleted)}** downtime messages have been **deleted**!", ephemeral=True)
