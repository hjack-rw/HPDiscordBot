import src.variables as vars

from src.body       import bot
from src.db         import *
from src.functions  import compress_image, CustomHousecup, create_leaderboard, draw_infocard, get_avatar, get_file, log, print_portkey, safe_handle_response, send_webhook, standard_response
from src.tasks      import print_notification
from src.views      import *

from datetime   import datetime, timedelta
from itertools  import chain
from os         import path, walk
from statistics import mean, stdev
from typing     import Literal, Optional
from zipfile    import ZipFile, ZIP_DEFLATED

from discord.app_commands import checks, CheckFailure, Group, command
from discord.components   import SelectOption
from discord.embeds       import Embed
from discord.errors       import NotFound
from discord.file         import File
from discord.interactions import Interaction
from discord.member       import Member
from discord.message      import Message


# SETTINGS
# for testing
# vars.test_bot["test_command"] = True # overwrite if needed

if vars.test_bot["test_command"]:
    channel_ids = vars.channel_ids_test
else:
    channel_ids = vars.channel_ids


# Tree-wide error handling
############################################################################################################

# A check failure (e.g. missing admin permission) is raised by discord.py's dispatch before
# the command body ever runs, so standard_response's try/except never sees it - without this,
# the user just gets Discord's generic "This interaction failed" with no explanation.
@bot.tree.error
async def on_app_command_error(interaction:Interaction, error):
    if isinstance(error, CheckFailure):
        await safe_handle_response(interaction, message="You don't have permission to use this!")
    else:
        await safe_handle_response(interaction, message=f"Something went very wrong here... {error}!")


# Admin only
############################################################################################################
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

    @command(name="download_db")
    @standard_response()
    async def download_db(self, interaction:Interaction, url:str):
        ''' Download the Database from URL '''

        get_file(url, filename="__database__.db-dump", directory=Database.database_path)

        await interaction.response.send_message("The Database was **downloaded**!", ephemeral=True)

    @command(name="export_backup")
    @standard_response()
    async def export_backup(self, interaction:Interaction):
        ''' Get the Database dump and a zip of all stored Images as attachments '''

        DB = bot.db
        await DB.backup()

        dump_path    = path.join(Database.database_path, f"{Database.database_name}-dump")
        images_dir   = path.join(Database.database_path, "images")
        archive_path = path.join(Database.database_path, "images.zip")

        with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
            for directory, _, filenames in walk(images_dir):
                for filename in filenames:
                    file_path = path.join(directory, filename)
                    archive.write(file_path, arcname=path.relpath(file_path, images_dir))

        await interaction.response.send_message(
            "Here's the **Database dump** and **Image archive**:",
            files=[File(dump_path), File(archive_path)],
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
    @standard_response()
    async def send_as(self, interaction:Interaction, member:Optional[Member], option:Optional[Literal[tuple(vars.custom_avatars.keys())]], say:str): # type: ignore
        ''' Send a Message as User '''
        
        if (member and not option) or (not member and option):
            user_name = member.display_name if member else option
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
                    image = draw_infocard(new_user=member, all_members_count=len([member for member in SERVER.members if not member.bot]))
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
            
            leaderboard, custom_housecup = create_leaderboard(SERVER, data, custom_housecup)

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

                await custom_housecup_message.edit(content="", embed=custom_housecup_embed)


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


    @command(name="reload_xp")
    @standard_response(silent=True)
    async def reload_xp(self, interaction:Interaction):
        ''' Reload XP data manually if DB has been changed '''

        bot.user_experience = await Experience.initialize()

        await interaction.response.send_message("The XP data has been **reloaded**!", ephemeral=True)


bot.tree.add_command(AdminCommands())

# Context-menu commands can't be Group members (app_commands.Group only supports
# .command()/.error()) - kept admin-only via its own check, grouped here by proximity instead.
@bot.tree.context_menu(name="Add Image")
@checks.has_permissions(administrator=True)
@standard_response(silent=True)
async def add_image(interaction:Interaction, message:Message):
    ''' Add Image to DB '''

    if not (filename := message.content.strip()):
        raise Exception("the Filename was not provided")

    if len(message.attachments) == 1:
        image = compress_image(await message.attachments[0].read())
    elif len(message.attachments) <1:
        raise Exception("no Image is attached")
    else:
        raise Exception("multiple Images are attached. Leave only one to save")

    images = await Images.initialize()
    try:
        await images.add(filename, image)

    # except it is already in the Database, ask if to overwrite
    except IdAlreadyExistsError:
        view = YesNoView()
        await interaction.response.send_message("The Filename already exists.\nAre you sure you wanna overwrite the Image?", view=view, ephemeral=True)
        await view.wait()

        if view.trigger:
            await images.add(filename, image, replace=True)
            return await interaction.followup.send("The Image has been **changed**!", ephemeral=True)
        else:
            return await interaction.followup.send("No action taken!", ephemeral=True)

    await interaction.response.send_message("The Image has been **added**!", ephemeral=True)

############################################################################################################

# All users commands
############################################################################################################

class GeneralCommands(Group):
    def __init__(self):
        super().__init__(name="_", description="General commands")

    @command(name="questionnaire")
    @standard_response()
    async def questionnaire_leaderboard(self, interaction:Interaction, question_idx:Optional[int]):
        ''' Answer questions to customize your Pets '''

        member = interaction.user
        info = await ExperienceInfo.initialize(extended=True, user_id=member.id, omitted_columns=["xp", "level", "progress"])

        if (is_archived := info.get_one_column("archived")) is True:
            USER_EXPERIENCE = bot.user_experience
            await USER_EXPERIENCE.unarchive(user_id=member.id)

        QUESTIONS = 4
        questions = {1: {"description": "Do you enjoy exploring the Black Lake?", "variable": "pet_from_sea"},
                     2: {"description": "Do you prefer dogs to cats?",            "variable": "pet_dog"},
                     3: {"description": "Can you see Thestrals?",                 "variable": "pet_thestral"},
                     4: {"description": "What is your favorite color?",           "variable": "favourite_color"},}

        if question_idx:
            if 1 <= question_idx <= QUESTIONS:
                questions_idxs = [question_idx]
            else:
                raise Exception(f"'{question_idx}' is not a valid question number")
        else:
            questions_idxs = [i for i in range(1, QUESTIONS+1)]

        all_picked = {}
        for question_idx in questions_idxs:
            if question_idx != 4:
                options = [SelectOption(label="Yes", value=True), SelectOption(label="No", value=False)]
                default_value = options[1].value
            else:
                options = [SelectOption(label="Red",    value=0),
                           SelectOption(label="Orange", value=1),
                           SelectOption(label="Yellow", value=2),
                           SelectOption(label="Green",  value=3),
                           SelectOption(label="Blue",   value=4),
                           SelectOption(label="Purple", value=5),
                           SelectOption(label="White",  value=6),
                           SelectOption(label="Black",  value=7),]
                
                default_value = options[0].value

            view = QuestionnaireView(options)
            await interaction.followup.send(content=f"**Question {question_idx}:**\n" + questions[question_idx]["description"], view=view, ephemeral=True)
            await view.wait()

            if (picked := view.picked) is None:
                picked = default_value

            all_picked[questions[question_idx]["variable"]] = picked

        # insert a new record
        if is_archived is None:
            await (await ExperienceInfo.initialize()).add(user_id=member.id, 
                                                          pet_ashwinder=not bool({role.name for role in getattr(member, "roles", [])} & {vars.club_name_short, "guest"}),
                                                          defaults=all_picked)
        # otherwise modify record
        else:
            await info.change(**all_picked)


    @command(name="suitcase")
    @standard_response(silent=True)
    async def scamander_suitcase(self, interaction:Interaction, all_pets:Optional[bool]):
        ''' Prints a list of all your caught Pets '''

        member = interaction.user

        if all_pets and member.id not in {vars.dev_user_id}:
            raise Exception("you don't have access to all pets")

        if all_pets:
            info = {"username": "Newt Scamander",
                    "level":     None,
                    "add_s":     True,}

        else:
            info = (await ExperienceInfo.initialize(extended=True, user_id=member.id, omitted_columns=["xp"])).get()
            info["username"]          = member.display_name
            info["xp_for_next_level"] = 5 * (info["level"] ** 2) + (50 * info["level"]) + 100

            # find if the username ends with 's'
            for char in reversed(info["username"]):
                if char.isalpha():
                    info["add_s"] = char.lower() != 's'
                    break
            else:
                info["add_s"] = True

        await PetsView(info).print_pet(interaction)


    @command(name="house_members")
    @standard_response(silent=True)
    async def house_members(self, interaction:Interaction):
        ''' Prints a list of Members of each House without cooldown (it will only be seen by you) '''
        
        SERVER = bot.server
        await MemberView(members=SERVER.members, message=None).print_list(interaction)


    @command(name="change_nickname")
    @standard_response(silent=True)
    async def change_nick(self, interaction:Interaction, nick:str):
        ''' Change your Nickname on Discord to the one in game '''

        await interaction.user.edit(nick=nick)
        await interaction.response.send_message("Your Nickname should have now **changed**!", ephemeral=True)


    @command(name="is_house_cup_this_week")
    @standard_response(silent=True)
    async def is_housecup_this_week(self, interaction:Interaction):
        ''' Informs you if there will be a House Cup this week '''

        today = datetime.now(tz=vars.gameserver_timezone)
        today = today.replace(hour=0,
                            minute=0,
                            second=0,
                            microsecond=0,)
        
        housecup_disciplines_names = vars.housecup_disciplines_names
        disciplines = (await ExtraVariable.initialize(name="housecup_disciplines")).get()

        trigger = False

        if (delta := (today - vars.base_housecup_date).days  % (14*4) - 1) > 50:    
            trigger = True
            discipline = disciplines[0]
            text = "New Season!\nThe schedule hasn't been released yet."
        else:
            dates, text = [today - timedelta(days=delta)], []
            for idx in range(4):
                if idx != 0:
                    dates.append(dates[-1] + timedelta(days=14))
                text.append(f"{idx+1}. **{housecup_disciplines_names[disciplines[idx]]}** - {dates[-1].strftime('%d/%m/%Y')}\n")
            
            if today.weekday() != 6:
                next_saturday = today + timedelta(days=5-today.weekday())

                try:
                    discipline = disciplines[dates.index(next_saturday)]
                    trigger = True
                except ValueError:
                    pass

        embed = Embed(color=vars.system_embed_color, description="".join(text))
        
        if trigger:
            await interaction.response.send_message(f"**YES**, there will be the **{housecup_disciplines_names[discipline]}** House Cup {'today' if today.weekday() == 5 else 'this week'}!", embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("There's **NO** House Cup this week!", embed=embed, ephemeral=True)


bot.tree.add_command(GeneralCommands())

# Standalone commands
############################################################################################################

# Portkey handling additional functionality
@bot.tree.context_menu(name="Accept Portkey")
@standard_response()
async def accept_portkey(interaction:Interaction, message:Message):
    ''' Accept Portkey '''
    
    SERVER = bot.server
    await (await Portkeys.initialize()).add(server=SERVER, message=message)
    await interaction.followup.send("The Portkey has been **added**!", ephemeral=True)


@bot.tree.context_menu(name="Edit Portkey")
@standard_response()
async def edit_portkey(interaction:Interaction, message:Message):
    ''' Edit Portkey '''

    SERVER = bot.server

    # check if message is sent by webhook and if it has the correct embed
    if (message.author.id == vars.bot_id) and ("Portkey" in message.embeds[0].footer.text):
        if portkey_values := (await Portkeys.initialize(message_id=message.id)).get():
            member = SERVER.get_member(portkey_values["user_id"])
            
            await message.edit(embed=print_portkey(member, portkey_values))
        else:
            await message.delete()
    
    elif message.author.id == 952824326766333972:
        raise Exception("the Portkey you are trying to edit has not yet been accepted")
    else:
        raise Exception("what you are trying to edit is not a Portkey")