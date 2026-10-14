"""
Reminder queue: planning (once per day, restart-safe), sending with retry until the event ends,
event + announcement as one unit, and the admin skip/postpone helpers. Runs on a real blank-seed
DB; only the Discord side (print_notification / send_webhook / the server) is stubbed.
"""
import asyncio

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

import src.variables as vars
from src import tasks
from src.db import ExtraVariable, ReminderQueue
from src.functions import notifications

GAME = vars.gameserver_timezone


def game_time(*args):
    return datetime(*args, tzinfo=GAME)


@pytest.fixture
def live_mode(monkeypatch):
    """Real trigger times and event windows instead of the test-mode 'now + 2 minutes' ones;
    the Dropbox upload after each queue change is stubbed."""
    monkeypatch.setitem(vars.test_bot, "test_tasks", False)
    monkeypatch.setattr(tasks, "time_trigger", vars.time_trigger)
    upload = AsyncMock()
    monkeypatch.setattr(tasks, "upload_backup_rotation", upload)
    return upload


@pytest_asyncio.fixture
async def queue_db(db):
    await ReminderQueue.ensure_schema()
    return db


def due(monkeypatch, *names):
    triggers = vars.notification_dict()
    monkeypatch.setattr(tasks, "_due_reminders", AsyncMock(return_value=[(name, triggers[name]) for name in names]))


async def queued_names():
    return [entry["name"] for entry in await tasks.list_reminders()]


async def set_planned(day):
    await (await ExtraVariable.initialize(name="reminder_queue_planned")).change(to=day)


# --- event windows ---

def test_event_window_maintenance_starts_at_midnight_after_trigger(live_mode):
    beginning, ending = notifications.event_window("Maintenance", game_time(2026, 10, 13, 23))
    assert (beginning, ending) == (game_time(2026, 10, 14, 0), game_time(2026, 10, 14, 3))


def test_event_window_housecup_same_day_skips_the_day_ahead(live_mode):
    beginning, _ = notifications.event_window("Housecup", game_time(2026, 10, 13, 12), same_day=True)
    assert beginning == game_time(2026, 10, 13, 19)


def test_event_window_none_for_notification_without_event(live_mode):
    assert notifications.event_window("Birthday", game_time(2026, 10, 13, 7)) is None


# --- event + announcement unit ---

@pytest.fixture
def discord_stubs(monkeypatch, tmp_path):
    image = tmp_path / "maintenance.png"
    image.write_bytes(b"img")
    monkeypatch.setattr(notifications, "glob", lambda pattern: [str(image)])

    send_webhook = AsyncMock(return_value=SimpleNamespace(id=1, delete=AsyncMock()))
    monkeypatch.setattr(notifications, "send_webhook", send_webhook)

    server = SimpleNamespace(get_channel=lambda channel_id: SimpleNamespace(),
                             create_scheduled_event=AsyncMock(return_value=SimpleNamespace(id=42)))
    return server, send_webhook


def maintenance_delivery(**kwargs):
    return notifications.Delivery(window=(game_time(2030, 1, 1, 0), game_time(2030, 1, 1, 3)), **kwargs)


@pytest.mark.asyncio
async def test_delivery_saves_the_created_event_id(live_mode, discord_stubs):
    server, _ = discord_stubs
    save_event_id = AsyncMock()

    await notifications.print_notification(server, "Maintenance", date=game_time(2029, 12, 31, 23), delivery=maintenance_delivery(save_event_id=save_event_id))

    save_event_id.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_delivery_with_event_id_does_not_create_a_second_event(live_mode, discord_stubs):
    server, _ = discord_stubs

    await notifications.print_notification(server, "Maintenance", date=game_time(2029, 12, 31, 23), delivery=maintenance_delivery(event_id=42))

    server.create_scheduled_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_failure_propagates_without_announcing(live_mode, discord_stubs):
    server, send_webhook = discord_stubs
    server.create_scheduled_event.side_effect = RuntimeError("429 Too Many Requests")

    with pytest.raises(RuntimeError):
        await notifications.print_notification(server, "Maintenance", date=game_time(2029, 12, 31, 23), delivery=maintenance_delivery(save_event_id=AsyncMock()))

    send_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_already_over_is_skipped_but_still_announced(live_mode, discord_stubs):
    server, send_webhook = discord_stubs
    now = datetime.now(tz=GAME)
    late = notifications.Delivery(window=(now - timedelta(hours=2), now + timedelta(minutes=1)), save_event_id=AsyncMock())

    await notifications.print_notification(server, "Maintenance", date=now - timedelta(hours=3), delivery=late)

    assert (server.create_scheduled_event.await_count, send_webhook.await_count) == (0, 1)


# --- planning ---

@pytest.mark.asyncio
async def test_first_plan_skips_reminders_already_due_today(queue_db, live_mode, monkeypatch):
    due(monkeypatch, "Card - Matagot", "Maintenance")   # 16:59 and 23:00

    await tasks.plan_reminders(game_time(2026, 10, 13, 18))

    assert await queued_names() == ["Maintenance"]


@pytest.mark.asyncio
async def test_plan_runs_once_per_day(queue_db, live_mode, monkeypatch):
    due(monkeypatch, "Maintenance")
    await tasks.plan_reminders(game_time(2026, 10, 13, 18))

    assert await tasks.plan_reminders(game_time(2026, 10, 13, 20)) is False


@pytest.mark.asyncio
async def test_plan_after_downtime_keeps_yesterdays_reminder_still_running(queue_db, live_mode, monkeypatch):
    await set_planned(datetime(2026, 10, 11))
    due(monkeypatch, "Maintenance")   # yesterday's event runs until 03:00 today

    await tasks.plan_reminders(game_time(2026, 10, 13, 0, 30))

    pending = [entry for entry in await tasks.list_reminders() if not entry["missed"]]
    assert [entry["date"].day for entry in pending] == [12, 13]


@pytest.mark.asyncio
async def test_plan_after_downtime_marks_yesterdays_ended_reminder_missed(queue_db, live_mode, monkeypatch):
    await set_planned(datetime(2026, 10, 11))
    due(monkeypatch, "Card - Matagot")   # yesterday's event ended at 21:00

    await tasks.plan_reminders(game_time(2026, 10, 13, 0, 30))

    missed = [entry["date"].day for entry in await tasks.list_reminders() if entry["missed"]]
    assert missed == [12]


# --- sending ---

async def plan_maintenance(monkeypatch):
    due(monkeypatch, "Maintenance")
    await tasks.plan_reminders(game_time(2026, 10, 13, 18))


@pytest.mark.asyncio
async def test_sent_reminder_is_removed(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    monkeypatch.setattr(tasks, "print_notification", AsyncMock())

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23))

    assert await queued_names() == []


@pytest.mark.asyncio
async def test_send_waits_for_send_time(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    send = AsyncMock()
    monkeypatch.setattr(tasks, "print_notification", send)

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 22, 59))

    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_send_is_retried_after_retry_delay(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    send = AsyncMock(side_effect=[RuntimeError("error code: 0"), None])
    monkeypatch.setattr(tasks, "print_notification", send)

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23))
    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23, 1))   # too early
    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23, 5))

    assert send.await_count == 2


@pytest.mark.asyncio
async def test_failed_send_keeps_the_error_for_the_list(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    monkeypatch.setattr(tasks, "print_notification", AsyncMock(side_effect=RuntimeError("error code: 0")))

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23))

    assert (await tasks.list_reminders())[0]["last_error"] == "error code: 0"


@pytest.mark.asyncio
async def test_retry_resumes_after_the_created_event(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    deliveries = []

    async def event_then_webhook_fails(*args, delivery, **kwargs):
        deliveries.append(delivery.event_id)
        if delivery.event_id is None:
            await delivery.save_event_id(42)
            raise RuntimeError("webhook failed")

    monkeypatch.setattr(tasks, "print_notification", event_then_webhook_fails)

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23))
    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23, 5))

    assert deliveries == [None, 42]


@pytest.mark.asyncio
async def test_reminder_past_its_event_end_is_missed_not_sent(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    send = AsyncMock()
    monkeypatch.setattr(tasks, "print_notification", send)

    await tasks.send_due_reminders(None, game_time(2026, 10, 14, 3))

    assert (send.await_count, (await tasks.list_reminders())[0]["missed"]) == (0, True)


@pytest.mark.asyncio
async def test_missed_reminder_is_dropped_after_a_day(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    monkeypatch.setattr(tasks, "print_notification", AsyncMock())

    await tasks.send_due_reminders(None, game_time(2026, 10, 14, 3))
    await tasks.send_due_reminders(None, game_time(2026, 10, 15, 3))

    assert await queued_names() == []


@pytest.mark.asyncio
async def test_queue_change_uploads_a_backup(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    live_mode.reset_mock()
    monkeypatch.setattr(tasks, "print_notification", AsyncMock())

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23))

    live_mode.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_send_does_not_upload_a_backup(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    live_mode.reset_mock()
    monkeypatch.setattr(tasks, "print_notification", AsyncMock(side_effect=RuntimeError("error code: 0")))

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23))

    live_mode.assert_not_awaited()


async def plan_birthday(monkeypatch):
    due(monkeypatch, "Birthday")
    await tasks.plan_reminders(game_time(2026, 10, 13, 0, 30))


@pytest.mark.asyncio
async def test_send_reads_variables_at_send_time(queue_db, live_mode, monkeypatch):
    await plan_birthday(monkeypatch)
    monkeypatch.setattr(tasks, "_birthday_users", AsyncMock(return_value=["joined after planning"]))
    send = AsyncMock()
    monkeypatch.setattr(tasks, "print_notification", send)

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 12))

    assert send.await_args.kwargs["variables"] == [["joined after planning"]]


@pytest.mark.asyncio
async def test_birthday_with_nobody_left_is_dropped_not_sent(queue_db, live_mode, monkeypatch):
    await plan_birthday(monkeypatch)
    monkeypatch.setattr(tasks, "_birthday_users", AsyncMock(return_value=[]))
    send = AsyncMock()
    monkeypatch.setattr(tasks, "print_notification", send)

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 12))

    assert (send.await_count, await queued_names()) == (0, [])


@pytest.mark.asyncio
async def test_failed_variables_read_is_retried_without_blocking_the_rest(queue_db, live_mode, monkeypatch):
    due(monkeypatch, "Birthday", "Maintenance")
    await tasks.plan_reminders(game_time(2026, 10, 13, 0, 30))
    monkeypatch.setattr(tasks, "_birthday_users", AsyncMock(side_effect=RuntimeError("database is locked")))
    monkeypatch.setattr(tasks, "print_notification", AsyncMock())

    await tasks.send_due_reminders(None, game_time(2026, 10, 13, 23))

    assert [(entry["name"], entry["last_error"]) for entry in await tasks.list_reminders()] == [("Birthday", "database is locked")]


@pytest.mark.asyncio
async def test_failing_plan_does_not_block_sending(queue_db, live_mode, monkeypatch):
    monkeypatch.setattr(tasks, "plan_reminders", AsyncMock(side_effect=RuntimeError("plan broke")))
    send = AsyncMock()
    monkeypatch.setattr(tasks, "send_due_reminders", send)

    await tasks.reminder_queue_task.coro(SimpleNamespace(server=None))

    send.assert_awaited_once()


# --- logging ---

def test_describe_reminder_names_event_start_and_duration(live_mode):
    entry = {"name": "Maintenance", "missed": False, "send_at": 0,
             "event_window": (int(game_time(2026, 10, 14, 0).timestamp()), int(game_time(2026, 10, 14, 3).timestamp()))}
    assert tasks.describe_reminder(entry) == "Maintenance (14/10 00:00, ~3 hours)"


def test_describe_reminder_says_missed_instead(live_mode):
    assert tasks.describe_reminder({"name": "Maintenance", "missed": True}) == "Maintenance missed"


# --- admin ---

@pytest.mark.asyncio
async def test_skip_removes_the_reminder(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)

    await tasks.skip_reminder((await tasks.list_reminders())[0]["id"])

    assert await queued_names() == []


@pytest.mark.asyncio
async def test_postpone_moves_event_and_deadline(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    before = (await tasks.list_reminders())[0]

    await tasks.postpone_reminder(None, before["id"], hours=2)

    after = (await tasks.list_reminders())[0]
    assert [after[key] - before[key] for key in ("event_start", "event_end", "deadline")] == [7200] * 3


@pytest.mark.asyncio
async def test_postpone_moves_an_already_created_discord_event(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    entry = (await tasks.list_reminders())[0]
    await (await ReminderQueue.initialize(id=entry["id"])).change(entry["id"], event_id=42)
    event = SimpleNamespace(edit=AsyncMock())
    server = SimpleNamespace(fetch_scheduled_event=AsyncMock(return_value=event))

    await tasks.postpone_reminder(server, entry["id"], hours=2)

    assert event.edit.await_args.kwargs["start_time"].timestamp() == entry["event_start"] + 7200


@pytest.mark.asyncio
async def test_postpone_rejects_reminder_without_event(queue_db, live_mode, monkeypatch):
    due(monkeypatch, "Birthday")
    await tasks.plan_reminders(game_time(2026, 10, 13, 0, 30))

    with pytest.raises(Exception, match="no event"):
        await tasks.postpone_reminder(None, (await tasks.list_reminders())[0]["id"], hours=2)


@pytest.mark.asyncio
async def test_skip_survives_a_failed_backup(queue_db, live_mode, monkeypatch):
    await plan_maintenance(monkeypatch)
    live_mode.side_effect = RuntimeError("dropbox down")

    await tasks.skip_reminder((await tasks.list_reminders())[0]["id"])

    assert await queued_names() == []


@pytest.mark.asyncio
async def test_skip_waits_for_an_in_flight_send(queue_db, live_mode, monkeypatch):
    monkeypatch.setattr(tasks, "queue_lock", asyncio.Lock())   # a fresh lock bound to this test's loop
    await plan_maintenance(monkeypatch)
    entry_id = (await tasks.list_reminders())[0]["id"]
    release  = asyncio.Event()

    async def slow_send(*args, **kwargs):
        await release.wait()

    monkeypatch.setattr(tasks, "print_notification", slow_send)

    sending  = asyncio.create_task(tasks.send_due_reminders(None, game_time(2026, 10, 13, 23)))
    await asyncio.sleep(0.05)
    skipping = asyncio.create_task(tasks.skip_reminder(entry_id))
    await asyncio.sleep(0.05)
    assert not skipping.done()

    release.set()
    await sending

    # the send finished first and removed the reminder, so the skip finds nothing to skip
    with pytest.raises(Exception, match="no queued reminder"):
        await skipping
