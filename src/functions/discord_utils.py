import src.variables as vars

from .core import log, session

import asyncio

from datetime  import datetime, timedelta
from functools import wraps
from re        import sub

from discord.app_commands import Group
from discord.errors       import NotFound
from discord.interactions import Interaction, InteractionResponded
from discord.message      import Message
from discord.utils        import MISSING

from typing import Awaitable, Callable, ParamSpec, TypeVar
P = ParamSpec("P") # parameters
R =   TypeVar("R") # returns


headers = {"authorization": f"Bot {vars.bot_token}",
           "content-type":   "application/json",
           "user-agent":     "BOT (http://discord.com, v1.0)",}


def standard_response(silent: bool=False):
    def run(func: Callable[P, Awaitable[R]]):
        @wraps(func)
        async def response(*args: P.args, **kwargs: P.kwargs) -> R:
            interaction = kwargs.get("interaction", None)
            message     = kwargs.get("message", None)

            if interaction is None and message is None:
                output = {Group: None, Interaction: None, Message: None}

                for arg in args:
                    for expected_type in output:
                        if isinstance(arg, expected_type) and output[expected_type] is None:
                            output[expected_type] = arg
                            break  # stop checking once matched

                _, interaction, message  = output[Group], output[Interaction], output[Message]

            if not silent:
                wait_text = "A wizard must show patience... please, wait for the command to finish!"

                if interaction:
                    await safe_handle_response(interaction, message=wait_text)
                elif message:
                    await message.channel.send(wait_text, delete_after=10)

            try:
                return await func(*args, **kwargs)
            except Exception as error:
                error_text = f"Something went very wrong here... {error}!"

                try:
                    if interaction:
                        return await safe_handle_response(interaction, message=error_text)
                    elif message:
                        return await message.channel.send(error_text, delete_after=10)
                except Exception as followup_error:
                    log(f"Failed to send error follow-up: {followup_error}")

                log(error_text)

        return response
    return run


async def safe_handle_response(interaction, message):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    # if already responded/deferred
    except InteractionResponded:
        await interaction.followup.send(message, ephemeral=True)


def disable_after(func):
    @wraps(func)
    async def decorator(self, interaction:Interaction, *args, **kwargs):
        await func(self, interaction, *args, **kwargs)

        self.dropdown.disabled= True

        try:
            await interaction.message.edit(view=self)
        except NotFound:
            pass

        await interaction.response.defer()
        self.stop()
    return decorator


# the one shared webhook gets repointed to a channel right before every send/edit - without
# a lock, two concurrent calls for different channels can interleave their repoint+send, so
# a message lands in the wrong channel under the wrong persona
webhook_lock = asyncio.Lock()

def change_webhook_channel(target_channel):
    payload = {"channel_id":target_channel.id}
    return session.patch(f"https://discordapp.com/api/webhooks/{vars.webhook_id}", json=payload, headers=headers,)


def get_avatar(user, none=False):
    try:
        return user.avatar._url
    except AttributeError:
        if none:
            return None
        return user.default_avatar._url


def slugify(name):
    ''' shared with scripts/migrate_pet_images.py - both sides need identical slug logic
    or a dropped-in filename won't match the name it's supposed to belong to '''
    return sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# webhook avatar_url must be a plain URL (no attachment:// support, unlike embeds) - Discord's
# CDN attachment URLs are signed and expire (~24h), so a hardcoded one would just rot slower
# than the original hotlinks. Instead custom_avatars maps name -> #assets message id, and this
# re-fetches that message (Discord always hands back a freshly-signed URL) with a short cache
# to avoid doing that on every single webhook send.
avatar_url_cache = {} # message_id -> (url, fetched_at)
AVATAR_CACHE_TTL = timedelta(hours=6)

async def get_avatar_url(guild, message_id):
    cached = avatar_url_cache.get(message_id)
    if cached and (datetime.now() - cached[1]) < AVATAR_CACHE_TTL:
        return cached[0]

    assets_channel = guild.get_channel(vars.channel_ids["assets"])
    message = await assets_channel.fetch_message(message_id)
    url = message.attachments[0].url

    avatar_url_cache[message_id] = (url, datetime.now())
    return url


async def send_webhook(target_channel, user_name, user_avatar_url=None, content="", embed=None, file=None, extra_files=None, view=None):
    ''' file becomes the embed's attachment://<filename> target (callers set embed image/
    thumbnail urls themselves); extra_files are attached alongside without being referenced
    by url - e.g. a thumbnail image next to a differently-purposed main file. '''

    if user_avatar_url is None:
        try:
            message_id = vars.custom_avatars[slugify(user_name)]
        except KeyError:
            message_id = vars.custom_avatars["prof_dumbledore"]
        user_avatar_url = await get_avatar_url(target_channel.guild, message_id)

    async with webhook_lock:
        response = await asyncio.to_thread(change_webhook_channel, target_channel)
        #print(response)

        if response.status_code == 200:
            webhook = [webhook for webhook in await target_channel.webhooks() if webhook.id == vars.webhook_id][0]

            embed = embed if embed else MISSING
            files = ([file] if file else []) + (extra_files or [])
            files = files if files else MISSING
            view = view if view else MISSING

            return await webhook.send(content=content, username=user_name, avatar_url=user_avatar_url, embed=embed, files=files, view=view, wait=True)
        else:
            raise Exception("failed to create webhook")


async def edit_webhook(target_channel, message_id, embed=None, file=None):

    async with webhook_lock:
        response = await asyncio.to_thread(change_webhook_channel, target_channel)
        #print(response)

        webhook = [webhook for webhook in await target_channel.webhooks() if webhook.id == vars.webhook_id][0]

        embeds, attachments = [], []

        if embed:
            embeds = [embed]

        if file:
            attachments = [file]

        await webhook.edit_message(message_id=message_id, embeds=embeds, attachments=attachments)
