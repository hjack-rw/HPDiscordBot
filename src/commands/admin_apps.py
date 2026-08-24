import src.variables as vars

from src.body      import bot
from src.db        import *
from src.functions import compress_image, print_portkey, standard_response
from src.views     import *

from discord.app_commands import checks
from discord.interactions import Interaction
from discord.message      import Message


# context-menu commands can't join a Group - see memory
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


# Portkey handling additional functionality
@bot.tree.context_menu(name="Accept Portkey")
@checks.has_permissions(administrator=True)
@standard_response()
async def accept_portkey(interaction:Interaction, message:Message):
    ''' Accept Portkey '''

    SERVER = bot.server
    await (await Portkeys.initialize()).add(server=SERVER, message=message)
    await interaction.followup.send("The Portkey has been **added**!", ephemeral=True)


@bot.tree.context_menu(name="Edit Portkey")
@checks.has_permissions(administrator=True)
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
