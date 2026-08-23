"""
Unit tests for the pure-logic pieces of src/functions/ (split from a single functions.py
into a package - see git history). Scoped to functions with no Discord/PIL/network
dependency: text_utils, the level/pet math in media.py, and CustomHousecup's scoring.
"""
import pytest

from src.functions.text_utils import (replace_multiple, convert_to_unix_time, turn_limit,
                                       catch_error, remove_extra_characters, parse_multiple_possibilities)
from src.functions.media import get_level_and_progress, get_level_change, get_animal_rank, MAX_PET_LEVEL
from src.functions.leaderboard import CustomHousecup


# --- text_utils.replace_multiple ---

def test_replace_multiple_explicit_pairs():
    assert replace_multiple("hello world", [("hello", "hi"), ("world", "earth")], self_idx=False) == "hi earth"


def test_replace_multiple_self_idx_uses_positional_placeholders():
    assert replace_multiple("go to 001 then 002", ["Kitchen", "Library"]) == "go to Kitchen then Library"


# --- text_utils.convert_to_unix_time ---

def test_convert_to_unix_time_formats_discord_timestamp():
    from datetime import datetime
    from time import mktime

    date = datetime(2026, 1, 1, 12, 0, 0)
    expected_ts = int(mktime(date.timetuple()))

    assert convert_to_unix_time(date, mode="R") == f"<t:{expected_ts}:R>"


# --- text_utils.turn_limit ---

@pytest.mark.parametrize("turnable,max_,expected", [(0, 3, 0), (2, 3, 2), (-1, 3, 2), (3, 3, 0)])
def test_turn_limit_wraps_within_bounds(turnable, max_, expected):
    assert turn_limit(turnable, max_) == expected


# --- text_utils.catch_error ---

def test_catch_error_fills_missing_keys_with_none():
    assert catch_error({"a": 1}, keys=["a", "b", "c"]) == {"a": 1, "b": None, "c": None}


def test_catch_error_does_not_overwrite_existing_keys():
    assert catch_error({"a": 1}, keys=["a"]) == {"a": 1}


# --- text_utils.remove_extra_characters ---

def test_remove_extra_characters_is_id_strips_non_digits():
    assert remove_extra_characters("abc123-456", is_id=True) == "123456"


def test_remove_extra_characters_default_strips_whitespace_and_newlines():
    assert remove_extra_characters("  hello\r\nworld  ") == "helloworld"


# --- text_utils.parse_multiple_possibilities ---

def test_parse_multiple_possibilities_single_value_pads_with_none():
    assert parse_multiple_possibilities("Yes") == ["Yes", None]


def test_parse_multiple_possibilities_splits_on_pipe():
    assert parse_multiple_possibilities("Yes|OldName") == ["Yes", "OldName"]


# --- media.get_level_and_progress ---

def test_get_level_and_progress_zero_xp_is_level_zero():
    assert get_level_and_progress(0) == (0, 0.0)


def test_get_level_and_progress_below_first_threshold_stays_level_zero():
    # level 0 -> 1 costs 5*0^2 + 50*0 + 100 = 100 xp
    level, progress = get_level_and_progress(50)
    assert level == 0
    assert progress == 0.5


def test_get_level_and_progress_exact_threshold_advances_level():
    # 100 xp exactly clears level 0's cost, landing at the start of level 1
    level, progress = get_level_and_progress(100)
    assert level == 1
    assert progress == 0.0


# --- media.get_level_change ---

def test_get_level_change_no_change_returns_empty():
    assert get_level_change(5, 5) == []


def test_get_level_change_level_up_returns_full_range():
    assert get_level_change(2, 5) == [3, 4, 5]


def test_get_level_change_level_down_returns_only_final_level():
    assert get_level_change(5, 2) == [2]


# --- media.get_animal_rank ---

def test_get_animal_rank_no_suffix_level_returns_named_pet():
    assert get_animal_rank(user={"level": 3}, level=3)["name"] == "Gnome"


def test_get_animal_rank_suffix_level_picks_sea_variant():
    user = {"level": 2, "pet_from_sea": True}
    assert get_animal_rank(user=user, level=2)["name"] == "Lobalug"


def test_get_animal_rank_suffix_level_picks_non_sea_variant():
    user = {"level": 2, "pet_from_sea": False}
    assert get_animal_rank(user=user, level=2)["name"] == "Cornish Pixie"


def test_get_animal_rank_clamps_to_max_pet_level():
    user = {"level": 999, "favourite_color": 1}
    clamped = get_animal_rank(user=user, level=999)
    at_cap = get_animal_rank(user={"level": MAX_PET_LEVEL, "favourite_color": 1}, level=MAX_PET_LEVEL)
    assert clamped == at_cap


# --- leaderboard.CustomHousecup ---

def test_customhousecup_for_scoreboard_empty_points_is_zero():
    housecup = CustomHousecup(house="Gryffindor", all_members_count=10)
    assert housecup.for_scoreboard(mean=0, sd=0) == 0


def test_customhousecup_for_scoreboard_averages_points_normalized_by_members():
    housecup = CustomHousecup(house="Gryffindor", all_members_count=10)
    housecup.points = [10, 20, 30]

    # mean=20, sd=0 -> the +-2sd window only keeps the point equal to the mean (20)
    assert housecup.for_scoreboard(mean=20, sd=0) == pytest.approx(20 / 1 / 10)


def test_customhousecup_for_scoreboard_excludes_outliers_beyond_two_sd():
    housecup = CustomHousecup(house="Gryffindor", all_members_count=10)
    housecup.points = [10, 12, 1000]  # 1000 is a wild outlier

    mean, sd = 10, 1
    result = housecup.for_scoreboard(mean=mean, sd=sd)

    # window is [mean-2sd, mean+2sd] = [8, 12] -> keeps 10 and 12, drops 1000
    assert result == pytest.approx((10 + 12) / 2 / 10)
