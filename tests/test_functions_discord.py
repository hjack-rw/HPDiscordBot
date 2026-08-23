"""
Tests for the Discord- and image-render-dependent pieces of src/functions/ that
tests/test_functions.py deliberately left out. Discord objects and network calls
(webhook HTTP patch, avatar downloads) are faked/monkeypatched; image rendering runs for
real against the actual local template assets under data/images/ and data/fonts/.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from discord.file import File

import src.variables as vars
from src.functions import discord_utils
from src.functions.leaderboard import get_leaderboard_static, draw_infocard, draw_leaderboard, create_leaderboard


def make_png_bytes(size=(4, 4), color=(255, 0, 0)):
    from io import BytesIO
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeWebhook:
    def __init__(self, webhook_id):
        self.id = webhook_id
        self.send = AsyncMock(return_value=SimpleNamespace(id=999))


class FakeChannel:
    def __init__(self, webhook, guild=None):
        self.id = 12345
        self._webhook = webhook
        self.guild = guild or SimpleNamespace()

    async def webhooks(self):
        return [self._webhook]


class FakeAssetsChannel:
    def __init__(self, url):
        self.fetch_message = AsyncMock(return_value=SimpleNamespace(attachments=[SimpleNamespace(url=url)]))


# --- discord_utils.get_avatar ---

def test_get_avatar_returns_custom_avatar_url():
    user = SimpleNamespace(avatar=SimpleNamespace(_url="https://cdn.discord/custom.png"))
    assert discord_utils.get_avatar(user) == "https://cdn.discord/custom.png"


def test_get_avatar_falls_back_to_default_when_no_custom_avatar():
    user = SimpleNamespace(avatar=None, default_avatar=SimpleNamespace(_url="https://cdn.discord/default.png"))
    assert discord_utils.get_avatar(user) == "https://cdn.discord/default.png"


def test_get_avatar_returns_none_when_requested_and_no_custom_avatar():
    user = SimpleNamespace(avatar=None, default_avatar=SimpleNamespace(_url="https://cdn.discord/default.png"))
    assert discord_utils.get_avatar(user, none=True) is None


# --- discord_utils.get_avatar_url ---

@pytest.mark.asyncio
async def test_get_avatar_url_fetches_from_assets_channel():
    discord_utils.avatar_url_cache.clear()

    assets_channel = FakeAssetsChannel(url="https://cdn.discord/avatar.png")
    guild = SimpleNamespace(get_channel=lambda channel_id: assets_channel)

    url = await discord_utils.get_avatar_url(guild, message_id=42)

    assert url == "https://cdn.discord/avatar.png"
    assets_channel.fetch_message.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_get_avatar_url_uses_cache_on_second_call():
    discord_utils.avatar_url_cache.clear()

    assets_channel = FakeAssetsChannel(url="https://cdn.discord/avatar.png")
    guild = SimpleNamespace(get_channel=lambda channel_id: assets_channel)

    await discord_utils.get_avatar_url(guild, message_id=42)
    await discord_utils.get_avatar_url(guild, message_id=42)

    assets_channel.fetch_message.assert_awaited_once()


# --- discord_utils.send_webhook ---

@pytest.mark.asyncio
async def test_send_webhook_sends_with_explicit_avatar(monkeypatch):
    webhook = FakeWebhook(vars.webhook_id)
    channel = FakeChannel(webhook)
    monkeypatch.setattr(discord_utils, "change_webhook_channel", lambda target_channel: SimpleNamespace(status_code=200))

    await discord_utils.send_webhook(target_channel=channel, user_name="Prof. Snape",
                                     user_avatar_url="https://example.com/avatar.png", content="hello")

    webhook.send.assert_awaited_once()
    kwargs = webhook.send.await_args.kwargs
    assert kwargs["content"] == "hello"
    assert kwargs["username"] == "Prof. Snape"
    assert kwargs["avatar_url"] == "https://example.com/avatar.png"


@pytest.mark.asyncio
async def test_send_webhook_looks_up_avatar_when_not_given(monkeypatch):
    discord_utils.avatar_url_cache.clear()

    webhook = FakeWebhook(vars.webhook_id)
    assets_channel = FakeAssetsChannel(url="https://cdn.discord/snape.png")
    guild = SimpleNamespace(get_channel=lambda channel_id: assets_channel)
    channel = FakeChannel(webhook, guild=guild)
    monkeypatch.setattr(discord_utils, "change_webhook_channel", lambda target_channel: SimpleNamespace(status_code=200))

    # "Prof. Snape" slugifies to "prof_snape", a real key in vars.custom_avatars
    await discord_utils.send_webhook(target_channel=channel, user_name="Prof. Snape", content="hello")

    assert webhook.send.await_args.kwargs["avatar_url"] == "https://cdn.discord/snape.png"


@pytest.mark.asyncio
async def test_send_webhook_raises_when_channel_repoint_fails(monkeypatch):
    webhook = FakeWebhook(vars.webhook_id)
    channel = FakeChannel(webhook)
    monkeypatch.setattr(discord_utils, "change_webhook_channel", lambda target_channel: SimpleNamespace(status_code=500))

    with pytest.raises(Exception, match="failed to create webhook"):
        await discord_utils.send_webhook(target_channel=channel, user_name="Prof. Snape",
                                         user_avatar_url="https://example.com/avatar.png", content="hello")


# --- leaderboard.get_leaderboard_static ---

def test_get_leaderboard_static_loads_real_local_assets():
    background, profile_border, full_bar, bar_mask, marker, fonts = get_leaderboard_static()
    assert background.size[0] > 0
    assert profile_border.size[0] > 0
    assert set(fonts) == {"MAGIC_88", "MAGIC_45", "MAGIC_42", "MAGIC_35", "RUNES_88", "RUNES_72"}


# --- leaderboard.draw_infocard ---

def test_draw_infocard_returns_a_png_file(monkeypatch):
    monkeypatch.setattr("src.functions.leaderboard.get_image", lambda url: make_png_bytes())

    new_user = SimpleNamespace(name="Harry", avatar=SimpleNamespace(_url="https://cdn.discord/harry.png"))
    file = draw_infocard(new_user=new_user, all_members_count=42)

    assert isinstance(file, File)
    assert file.filename == "card.png"


# --- leaderboard.draw_leaderboard ---

def test_draw_leaderboard_with_no_avatar_uses_black_avatar_and_skips_download():
    static = get_leaderboard_static()
    user = {"avatar": None, "username": "TestUser", "level": 3, "progress": 0.42, "user_id": 111}

    file = draw_leaderboard(user, rank=1, house=None, static=static)

    assert isinstance(file, File)
    assert file.filename == "leaderboard_111.png"


def test_draw_leaderboard_with_avatar_downloads_and_renders(monkeypatch):
    monkeypatch.setattr("src.functions.leaderboard.get_image", lambda url: make_png_bytes())

    static = get_leaderboard_static()
    user = {"avatar": "https://cdn.discord/harry.png", "username": "TestUser", "level": 3, "progress": 0.75, "user_id": 222}

    file = draw_leaderboard(user, rank=2, house=None, static=static)

    assert isinstance(file, File)
    assert file.filename == "leaderboard_222.png"


# --- leaderboard.create_leaderboard ---

def test_create_leaderboard_ranks_by_xp_and_returns_one_entry_per_member(monkeypatch):
    monkeypatch.setattr("src.functions.leaderboard.get_image", lambda url: make_png_bytes())

    role = SimpleNamespace(name="member")
    members = {
        1: SimpleNamespace(id=1, display_name="Alice", roles=[role], avatar=SimpleNamespace(_url="https://cdn.discord/a.png")),
        2: SimpleNamespace(id=2, display_name="Bob",   roles=[role], avatar=SimpleNamespace(_url="https://cdn.discord/b.png")),
    }
    server = SimpleNamespace(get_member=lambda user_id: members.get(user_id))

    data = [{"user_id": 1, "xp": 100, "level": 3, "progress": 0.5},
            {"user_id": 2, "xp": 50,  "level": 3, "progress": 0.1}]

    leaderboard, custom_housecup = create_leaderboard(server, data, custom_housecup=[])

    assert [entry[0] for entry in leaderboard] == [1, 2]
    assert custom_housecup == []


def test_create_leaderboard_skips_members_no_longer_on_server():
    server = SimpleNamespace(get_member=lambda user_id: None)
    data = [{"user_id": 999, "xp": 100, "level": 3, "progress": 0.5}]

    leaderboard, _ = create_leaderboard(server, data, custom_housecup=[])

    assert leaderboard == []
