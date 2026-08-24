import src.variables as vars

from src.body       import bot
from src.db         import *
from src.functions  import print_portkey, standard_response
from src.views      import *

from datetime   import datetime, timedelta
from typing     import Optional

from discord.app_commands import Group, command
from discord.components   import SelectOption
from discord.embeds       import Embed
from discord.interactions import Interaction


class GeneralCommands(Group):
    def __init__(self):
        super().__init__(name="_", description="General commands")

    @command(name="questionnaire")
    @standard_response()
    async def questionnaire_leaderboard(self, interaction:Interaction, question_idx:Optional[int]):
        ''' Answer questions to customize your Pets '''

        member = interaction.user
        info = await ExperienceInfo.initialize(extended=True, user_id=member.id, omitted_columns=["xp", "level", "progress"])

        if info.get_one_column("archived") is True:
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

        # re-check fresh, don't trust the pre-wait read - see memory
        async with ExperienceInfo.transaction():
            info = await ExperienceInfo.initialize(extended=True, user_id=member.id, omitted_columns=["xp", "level", "progress"])

            # insert a new record
            if info.get_one_column("archived") is None:
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
