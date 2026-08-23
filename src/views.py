from src.db_classes import Images
from src.functions import disable_after, turn_limit, print_suitcase, print_house_members
from src.variables import houses_names_list, pets

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.interactions import Interaction
from discord.partial_emoji import PartialEmoji
from discord.ui import button, Button, View, Select

from random import choice


# welcome message
class WelcomeView(View):
    
    def __init__(self, user, stickers):
        super().__init__(timeout=None)
        
        self.user = user
        self.stickers = stickers
        self.clicked_users = []
    
    # click button to send sticker
    @button(label="Raise your wand in greetings!",  style=ButtonStyle.grey, emoji=PartialEmoji.from_str("<:wandsup:1256318918943969391>"), custom_id="welcome")
    async def hello(self, interaction: Interaction, button: Button):
        
        if self.user is None:
            return await interaction.response.send_message("User not found!", ephemeral=True)
        
        elif interaction.user.id == self.user.id:
            return await interaction.response.send_message("You can't do it yourself, let others greet you!", ephemeral=True)

        if interaction.user.id not in self.clicked_users:
            self.clicked_users.append(interaction.user.id)

            sticker = choice(self.stickers)

            #NOTE if they ever allow webhooks to send stickers
            await interaction.response.send_message("Your message has been sent!", ephemeral=True)
            await interaction.message.reply(content=f"<@{interaction.user.id}> says: Welcome <@{self.user.id}>! {sticker.description}", stickers=[sticker])

        else:
            await interaction.response.send_message("We limited the interactions to one greeting per user!", ephemeral=True)


# disciplines in a dropdown select
class DisciplinesView(View):
    def __init__(self, options):
        super().__init__(timeout=None)

        self.dropdown = self.DisciplinesList(options, self)
        self.picked = None

        self.add_item(self.dropdown)
    
    @disable_after
    async def respond(self, interaction:Interaction, choice_idx):
        self.picked = choice_idx

    class DisciplinesList(Select):
        def __init__(self, options, parent_view):
            super().__init__(placeholder="Choose an option...", options=options)
            
            self.parent_view = parent_view

        async def callback(self, interaction:Interaction):
            selected_value = int(self.values[0])
            matching_index = next((i for i, option in enumerate(self.options) if option.value == selected_value), None)
            await self.parent_view.respond(interaction, choice_idx=matching_index)


# yes/no confirmation
class YesNoView(View):
    def __init__(self):
        super().__init__(timeout=None)

        self.trigger = None
    
    def break_interaction(func):
        async def response(self, interaction: Interaction, button: Button):
            
            # call the actual button handler
            await func(self, interaction, button)

            # after interaction stop
            await interaction.response.defer()
            self.stop()
        
        return response

    @button(label="YES",  style=ButtonStyle.grey, emoji="✅", custom_id="yes")
    @break_interaction
    async def answer_yes(self, interaction: Interaction, button: Button):
        self.trigger = True

    @button(label="NO",  style=ButtonStyle.grey, emoji="⛔", custom_id="no")
    @break_interaction
    async def answer_no(self, interaction: Interaction, button: Button):
        self.trigger = False


# questions in a dropdown select
class QuestionnaireView(View):
    def __init__(self, options):
        super().__init__(timeout=None)
        
        self.dropdown = self.QuestionnaireList(options, self)
        self.picked   = None

        self.add_item(self.dropdown)
    
    @disable_after
    async def respond(self, interaction:Interaction, choice):
        self.picked = choice
    
    class QuestionnaireList(Select):
        def __init__(self, options, parent_view):
            super().__init__(placeholder="Choose an option...", options=options)
            
            self.parent_view = parent_view

        async def callback(self, interaction:Interaction):
            selected_value = self.values[0]
            await self.parent_view.respond(interaction, choice=True if selected_value == "True" else False if selected_value == "False" else int(selected_value) if selected_value.isdigit() else None)


# view pets of each level
class PetsView(View):
    def __init__(self, info):
        super().__init__(timeout=None)

        current_level = info.pop("level")
        self.info     = info

        self.info["current_level"] = current_level
        
        if current_level:
            self.max_pet = current_level + 1
            self.pet     = current_level
        else:
            self.max_pet = len(pets)
            self.pet     = 0

        self.images = Images
    
    # print a new pet
    async def print_pet(self, interaction):
        embed, file = await print_suitcase(images=self.images, info=self.info, level=self.pet)
        await interaction.response.send_message(embed=embed, file=file, view=self, ephemeral=True)

    # print a new pet
    def cooldown_interaction(func):
        async def response(self, interaction: Interaction, button: Button): 
            
            # call the actual button handler
            func(self, interaction, button)

            # after interaction, send the updated embed
            await self.print_pet(interaction)
        
        return response

    @button(label="",  style=ButtonStyle.grey, emoji="⬅️", custom_id="left")
    @cooldown_interaction
    def turn_left(self, interaction: Interaction, button: Button):
        self.pet = turn_limit(turnable=(self.pet-1), max=self.max_pet)

    @button(label="",  style=ButtonStyle.grey, emoji="➡️", custom_id="right")
    @cooldown_interaction
    def turn_right(self, interaction: Interaction, button: Button):
        self.pet = turn_limit(turnable=(self.pet+1), max=self.max_pet)


# view members list
class MemberView(View):
    def __init__(self, members, message):
        super().__init__(timeout=None)
        
        self.members = members
        self.houses  = houses_names_list()
        self.groups  = ["gop", "guest", "cross guild"]

        if message is not None:
            self.message = message
            self.cooldown = commands.CooldownMapping.from_cooldown(rate=1, per=3, type=commands.BucketType.member)
        else:
            self.message = None

        self.page = 0
        self.filter = 0
    
    # print a new list
    async def print_list(self, interaction=None):
        list = print_house_members(self.members, house=self.houses[self.page], group=self.groups[self.filter])
        
        if self.message is not None:
            await self.message.edit(embed=list, view=self)
        else:
            if interaction:
                await interaction.response.send_message(embed=list, view=self, ephemeral=True)
            else:
                raise Exception("no interaction has been provided")
    
    # change printed members
    async def update_members(self, members):
        self.members = members
        await self.print_list()

    # cooldown between button presses
    def cooldown_interaction(func):
        async def response(self, interaction: Interaction, button: Button): 
            cooldown = getattr(self, "cooldown", None)

            # handle cooldown for interactions if message exists
            if cooldown is not None:
                bucket = cooldown.get_bucket(interaction.message)
                retry = bucket.update_rate_limit()

                if retry:
                    return await interaction.response.send_message(f"Slow down! Try again in {round(retry, 1)} seconds.", ephemeral=True)

            # call the actual button handler
            func(self, interaction, button)

            # after interaction, update the list
            await self.print_list(interaction)
            
            # defer the response if message exists
            if self.message is not None:
                return await interaction.response.defer()
    
        return response

    @button(label="",  style=ButtonStyle.grey, emoji="⬅️", custom_id="left")
    @cooldown_interaction
    def turn_left(self, interaction: Interaction, button: Button):
        self.page = turn_limit(turnable=(self.page-1), max=len(self.houses))

    @button(label="",  style=ButtonStyle.grey, emoji="➡️", custom_id="right")
    @cooldown_interaction
    def turn_right(self, interaction: Interaction, button: Button):
        self.page = turn_limit(turnable=(self.page+1), max=len(self.houses))
    
    @button(label="GOP",  style=ButtonStyle.red, custom_id="filter")
    @cooldown_interaction
    def switch_filter(self, interaction: Interaction, button: Button):
        self.filter = turn_limit(turnable=(self.filter+1), max=len(self.groups))

        if self.filter == 0:
            self.children[2].label = "GOP"
            self.children[2].style = ButtonStyle.red
        elif self.filter == 1:
            self.children[2].label = "Guest"
            self.children[2].style = ButtonStyle.green
        else:
            self.children[2].label = "Cross Guild"
            self.children[2].style = ButtonStyle.blurple