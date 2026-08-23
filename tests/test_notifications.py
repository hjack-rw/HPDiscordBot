"""
Characterization tests for print_notification/set_event_and_notification - written before
refactoring print_notification's 11-branch if/elif chain into a dispatch table, to prove the
split preserves behavior exactly. send_webhook is stubbed (no real Discord I/O); everything
else (embed content, event_info assembly, the Level Up/Birthday extra-recipient logic, the
Card family's shared template) runs for real.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.variables as vars
from src.functions import notifications


class FakeChannel:
    def __init__(self, label):
        self.label = label


@pytest.fixture
def fake_server():
    channels = {}

    def get_channel(channel_id):
        return channels.setdefault(channel_id, FakeChannel(channel_id))

    return SimpleNamespace(
        get_channel=get_channel,
        fetch_member=AsyncMock(side_effect=lambda user_id: SimpleNamespace(id=user_id, display_name=f"User{user_id}")),
        create_scheduled_event=AsyncMock(),
    )


@pytest.fixture
def fake_send_webhook(monkeypatch):
    stub = AsyncMock(return_value=SimpleNamespace(id=1, delete=AsyncMock()))
    monkeypatch.setattr(notifications, "send_webhook", stub)
    return stub


def sent_kwargs(fake_send_webhook):
    fake_send_webhook.assert_awaited_once()
    return fake_send_webhook.await_args.kwargs


# --- direct-embed events (build inline, no set_event_and_notification) ---

@pytest.mark.asyncio
async def test_welcome_sends_to_welcome_channel_with_new_user_mention(fake_server, fake_send_webhook):
    new_user = SimpleNamespace(id=555, name="Harry")
    view = SimpleNamespace()
    await notifications.print_notification(fake_server, "Welcome", variables=[new_user, None, view], is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert kwargs["content"] == "Mention: <@555>"
    assert kwargs["embed"].title == "Welcome Harry, to Enemies of the Heir! <:hugs:1256225688403447888>"
    assert kwargs["view"] is view


@pytest.mark.asyncio
async def test_level_up_single_level_appends_ending_to_description(fake_server, fake_send_webhook):
    user = SimpleNamespace(id=1, display_name="Harry")
    user_data = {"level": 5}
    await notifications.print_notification(fake_server, "Level Up", variables=[user, user_data, [5]], is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert "How many more fantastic beasts" in kwargs["embed"].description
    assert not kwargs["embed"].fields


@pytest.mark.asyncio
async def test_level_up_multi_level_appends_ending_to_last_extra_field(fake_server, fake_send_webhook):
    user = SimpleNamespace(id=1, display_name="Harry")
    user_data = {"level": 4}
    await notifications.print_notification(fake_server, "Level Up", variables=[user, user_data, [3, 4]], is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert "How many more fantastic beasts" not in kwargs["embed"].description
    assert "How many more fantastic beasts" in kwargs["embed"].fields[-1].value


@pytest.mark.asyncio
async def test_birthday_attaches_thumbnail_file_and_mentions_everyone(fake_server, fake_send_webhook):
    from datetime import datetime

    await notifications.print_notification(fake_server, "Birthday", date=datetime(2026, 1, 1), variables=[[111]], is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert kwargs["content"] == "Mention: @everyone"
    assert kwargs["file"] is None
    assert kwargs["extra_files"][0].filename == "birthday.png"
    assert kwargs["embed"].thumbnail.url == "attachment://birthday.png"


@pytest.mark.asyncio
async def test_birthday_multiple_users_adds_extra_field_per_additional_user(fake_server, fake_send_webhook):
    from datetime import datetime

    await notifications.print_notification(fake_server, "Birthday", date=datetime(2026, 1, 1), variables=[[111, 222, 333]], is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert len(kwargs["embed"].fields) == 2


@pytest.mark.asyncio
async def test_club_points_uses_catch_error_defaults_for_missing_keys(fake_server, fake_send_webhook):
    await notifications.print_notification(fake_server, "Club Points", is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert kwargs["embed"].title is None
    # subtitle omitted -> no author set on the embed
    assert kwargs["embed"].author.name is None


@pytest.mark.asyncio
async def test_rankings_sends_to_staffroom_mentioning_staff_roles(fake_server, fake_send_webhook):
    await notifications.print_notification(fake_server, "Rankings", is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    staff_a, staff_b = vars.role_ids["staff"]
    assert f"<@&{staff_a}>" in kwargs["content"]
    assert f"<@&{staff_b}>" in kwargs["content"]


# --- delegated events (build event_info, hand off to set_event_and_notification) ---

@pytest.mark.asyncio
async def test_housecup_delegates_to_set_event_and_notification(fake_server, fake_send_webhook):
    from datetime import datetime

    await notifications.print_notification(fake_server, "Housecup", date=datetime(2026, 1, 1, 12), variables=[0], is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert kwargs["user_name"] == "Prof. Dumbledore"
    assert "House Cup" in kwargs["embed"].author.name


@pytest.mark.asyncio
async def test_club_events_uses_weekday_name_in_subtitle(fake_server, fake_send_webhook):
    from datetime import datetime

    # 2026-01-05 is a Monday
    await notifications.print_notification(fake_server, "Club Events", date=datetime(2026, 1, 5, 12), is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert "Monday" in kwargs["embed"].author.name


@pytest.mark.asyncio
async def test_maintenance_delegates_and_sends(fake_server, fake_send_webhook):
    from datetime import datetime

    await notifications.print_notification(fake_server, "Maintenance", date=datetime(2026, 1, 1, 12), is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert kwargs["user_name"] == "Mr. Filch"


@pytest.mark.asyncio
@pytest.mark.parametrize("event_name,expected_snippet", [
    ("Card - Matagot", "Staircase"),
    ("Card - Book of Monsters", "History of Magic Classroom"),
    ("Card - Cornish Pixies", "Library"),
])
async def test_card_variants_substitute_their_own_location_text(fake_server, fake_send_webhook, event_name, expected_snippet):
    from datetime import datetime

    await notifications.print_notification(fake_server, event_name, date=datetime(2026, 1, 1, 12), is_task=False)

    kwargs = sent_kwargs(fake_send_webhook)
    assert expected_snippet in kwargs["embed"].description
