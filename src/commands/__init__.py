''' split from commands.py - see memory for rationale. '''

from src.body      import bot
from src.functions import safe_handle_response

from discord.app_commands import CheckFailure
from discord.interactions import Interaction

from .admin      import AdminCommands
from .admin_apps import add_image, accept_portkey, edit_portkey
from .user       import GeneralCommands

__all__ = ["AdminCommands", "GeneralCommands", "add_image", "accept_portkey", "edit_portkey"]


# A check failure (e.g. missing admin permission) is raised by discord.py's dispatch before
# the command body ever runs, so standard_response's try/except never sees it - without this,
# the user just gets Discord's generic "This interaction failed" with no explanation.
@bot.tree.error
async def on_app_command_error(interaction:Interaction, error):
    if isinstance(error, CheckFailure):
        await safe_handle_response(interaction, message="You don't have permission to use this!")
    else:
        await safe_handle_response(interaction, message=f"Something went very wrong here... {error}!")


bot.tree.add_command(AdminCommands())
bot.tree.add_command(GeneralCommands())
