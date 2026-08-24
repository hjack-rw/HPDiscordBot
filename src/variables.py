from datetime import datetime, time
from dotenv   import load_dotenv
from pathlib  import Path
from zoneinfo import ZoneInfo

import os
import tomllib


path = os.getcwd() + "/src/"
load_dotenv(dotenv_path=Path(os.getcwd() + "/env"))

absolute_path = path

image_data_path = os.getcwd() + "/data/images/"
font_data_path  = os.getcwd() + "/data/fonts/"
log_path        = os.getcwd() + "/data/bot.log"

discord_token = (os.getenv("DISCORD_TOKEN") or "").strip() or None
bot_token     = (os.getenv("DISCORD_BOT_TOKEN") or "").strip() or None

############################################################################################################
# Server-scoped config - repo-root server_config.toml (gitignored, one per deployment).
# See server_config.example.toml for the template and field descriptions.
############################################################################################################

server_config_path = Path(os.getcwd() + "/server_config.toml")
if not server_config_path.exists():
    raise RuntimeError(f"{server_config_path} not found - copy server_config.example.toml to "
                        "server_config.toml at the repo root and fill in your server's real IDs "
                        "before running the bot")

with open(server_config_path, "rb") as file:
    server_config = tomllib.load(file)

try:
    from pre_init import *
except ImportError:
    print("failed to import 'test_bot' from pre_init!")
    # no console access on most hosts to run pre_init.py's TUI - see memory
    test_bot_overrides = server_config.get("test_bot", {})
    test_bot = {"local_deploy": not os.path.exists("/.dockerenv"),
                "test_body":    test_bot_overrides.get("test_body",    False),
                "test_command": test_bot_overrides.get("test_command", False),
                "test_events":  test_bot_overrides.get("test_events",  False),
                "test_tasks":   test_bot_overrides.get("test_tasks",   False),}

def is_test_mode():
    return any(test_bot.values())

bot_id      = server_config["bot_id"]
dev_user_id = server_config["dev_user_id"]
webhook_id  = server_config["webhook_id"]
server_id   = server_config["server_id"]

club_name       = server_config["club_name"]
club_name_short = server_config["club_name_short"]

members_list_message_id = server_config["members_list_message_id"]
role_ids                = server_config["role_ids"]
card_message_ids        = server_config["card_message_ids"]

channel_sections_ids = server_config["channel_sections_ids"]
channel_ids           = server_config["channel_ids"]

channel_ids_test = {"assets": channel_ids["assets"],}
channel_ids_test.update({key: channel_ids["secret-lab"] for key in channel_ids if key not in list(channel_ids_test.keys())})

############################################################################################################
# Display / misc constants
############################################################################################################

system_embed_color = 16777215 # white

wait_for = 2 # seconds

weekdays = {0:"Monday", 1:"Tuesday", 2:"Wednesday", 3:"Thursday", 4:"Friday", 5:"Saturday", 6:"Sunday"}
months   = {"01|January": 1, "02|February": 2, "03|March": 3, "04|April": 4, "05|May": 5, "06|June": 6, "07|July": 7, "08|August": 8, "09|September": 9, "10|October": 10, "11|November": 11, "12|December": 12}

numbers = {0: "0️⃣", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣"}

############################################################################################################
# Houses
############################################################################################################

houses = {"other"     : {"emoji": "",                                             "crest": ""}, #for BOTS
          "gryffindor": {"emoji": "<:gryffindor:1255656359190462484> Gryffindor", "crest": "attachment://gryffindor.png"},
          "hufflepuff": {"emoji": "<:hufflepuff:1255656360780238849> Hufflepuff", "crest": "attachment://hufflepuff.png"},
          "ravenclaw" : {"emoji": "<:ravenclaw:1255656362617212999> Ravenclaw",   "crest": "attachment://ravenclaw.png"},
          "slytherin" : {"emoji": "<:slytherin:1255656364244729856> Slytherin",   "crest": "attachment://slytherin.png"},}

def houses_names_list(is_short=True):
    if is_short:
        return list(houses)[1:]
    else:
        return list(houses)

############################################################################################################
# NPC avatars
############################################################################################################

custom_avatars = server_config["custom_avatars"]

# slug -> proper display name shown in Discord - the slug itself is only a lookup key,
# never user-facing (see memory)
custom_avatar_names = { "mr_filch":        "Mr. Filch",
                        "prof_dumbledore": "Prof. Dumbledore",
                        "prof_flitwick":   "Prof. Flitwick",
                        "prof_hagrid":     "Prof. Hagrid",
                        "prof_mcgonagall": "Prof. McGonagall",
                        "prof_slughorn":   "Prof. Slughorn",
                        "prof_snape":      "Prof. Snape",
                        "prof_sprout":     "Prof. Sprout",
                        "prof_trelawney":  "Prof. Trelawney",}

############################################################################################################
# House cup disciplines
############################################################################################################

housecup_disciplines_names = {0: "Best Partners",
                              1: "Dance Club",
                              2: "Top Wizard",
                              3: "History of Magic",
                              4: "Muggle Studies",
                              5: "Casual Matches",
                              6: "Qudditch",
                              7: "Gobstones Showdown",}

############################################################################################################
# Sorting form answers
############################################################################################################

form_answers = ["🤺 Solo Dueling",
                "🤺🤺 Duo Dueling",
                "😎🤺 Casual Matches",
                "🧙🌳 Club Adventures",
                "🧙🧙 Club Events (Dance / Quiz / Duel Tournament)",
                "📚 Classes",
                "🧹 Quidditch",
                "🌳 Solo Forbidden Forest",
                "🌳🌳 Team Forbidden Forest (OTP / Gold / Echos)",
                "🌹 Verdant Victories",
                "🪖 Wizard's Warboard",
                "🌱 Herbology",
                "🥣 Gastronomy",
                "🕺💃 Dancing",
                "🏠 Decorating Space",
                "📸 Photoshoots",]

############################################################################################################
# Pets catalog
############################################################################################################

# Complete list at:
# https://harrypotter.fandom.com/wiki/List_of_creatures
pets = {
    "0":  {"name": "Flobberworm", "image": "flobberworm"}, #100 xp to finish
    "1":  {"name": "Manticore", "image": "manticore"}, #255
    "2a": {"name": "Cornish Pixie", "image": "cornish_pixie"}, #475
    "2b": {"name": "Lobalug", "image": "lobalug"},
    "3":  {"name": "Gnome", "image": "gnome"}, #770
    "4":  {"name": "Bowtruckle", "image": "bowtruckle"}, #1150
    "5":  {"name": "Puffskein", "image": "puffskein"}, #1625
    "6a": {"name": "Knarl", "image": "knarl"}, #2205
    "6b": {"name": "Jellyfish", "image": "jellyfish"},
    "7":  {"name": "Diricawl", "image": "diricawl"}, #2900
    "8":  {"name": "Fwooper", "image": "fwooper"}, #3720
    "9":  {"name": "Occamy", "image": "occamy"}, #4675
    "10a":{"name": "Kneazle", "image": "kneazle"}, #5775
    "10b":{"name": "Crup", "image": "crup"},
    "11a":{"name": "Jarvey", "image": "jarvey"}, #7030
    "11b":{"name": "Murtlap", "image": "murtlap"},
    "12": {"name": "Niffler", "image": "niffler"}, #8450
    "13": {"name": "Mooncalf", "image": "mooncalf"}, #10045
    "14": {"name": "Qilin", "image": "qilin"}, #11825
    "15a":{"name": "Tebo", "image": "tebo"}, #13800
    "15b":{"name": "Grindylow", "image": "grindylow"},
    "16": {"name": "Demiguise", "image": "demiguise"}, #15980
    "17": {"name": "Yeti", "image": "yeti"}, #18375
    "18a":{"name": "Matagot", "image": "matagot"}, #20995
    "18b":{"name": "Swooping Evil", "image": "swooping_evil"},
    "19a":{"name": "Hinkypunk", "image": "hinkypunk"}, #23850
    "19b":{"name": "Kappa", "image": "kappa"},
    "20a":{"name": "Sphinx", "image": "sphinx"}, #26950
    "20b":{"name": "Ashwinder", "image": "ashwinder"},
    "21": {"name": "Golden Snidget", "image": "golden_snidget"}, #30305
    "22": {"name": "Augurey", "image": "augurey"}, #33925
    "23": {"name": "Thunderbird", "image": "thunderbird"}, #37820
    "24": {"name": "Fire Crab", "image": "fire_crab"}, #42000
    "25a":{"name": "Blast-Ended Skrewt", "image": "blast_ended_skrewt"}, #46475
    "25b":{"name": "Dugbog", "image": "dugbog"},
    "26": {"name": "Erumpent", "image": "erumpent"}, #51255
    "27a":{"name": "Nundu", "image": "nundu"}, #56350
    "27b":{"name": "Graphorn", "image": "graphorn"},
    "28a":{"name": "Griffin", "image": "griffin"}, #61770
    "28b":{"name": "Kelpie", "image": "kelpie"},
    "29": {"name": "Hippogriff", "image": "hippogriff"}, #67525
    "30a":{"name": "Abraxan", "image": "abraxan"}, #73625
    "30b":{"name": "Thestral", "image": "thestral"},
    "31": {"name": "Unicorn", "image": "unicorn"}, #80080
    "32a":{"name": "Chimaera", "image": "chimaera"}, #86900
    "32b":{"name": "Giant Squid", "image": "giant_squid"},
    "33": {"name": "Manticore Mother", "image": "manticore_mother"}, #94195
    "34a":{"name": "Zouwu", "image": "zouwu"}, #101775
    "34b":{"name": "Three-Headed Dog", "image": "three_headed_dog"},
    "35": {"name": "Phoenix", "image": "phoenix"}, #109750
    "36": {"name": "Basilisk", "image": "basilisk"}, #118130
    "37a":{"name": "Runespoor", "image": "runespoor"}, #126925
    "37b":{"name": "Horned Serpent", "image": "horned_serpent"},
    "38": {"name": "Firedrake", "image": "firedrake"}, #136145
    "39": {"name": "Wyvern", "image": "wyvern"}, #145800
    "40a":{"name": "Chinese Fireball Dragon", "image": "chinese_fireball_dragon"},       # RED
    "40b":{"name": "Peruvian Vipertooth Dragon", "image": "peruvian_vipertooth_dragon"}, # ORANGE
    "40c":{"name": "Norwegian Ridgeback Dragon", "image": "norwegian_ridgeback_dragon"}, # YELLOW
    "40d":{"name": "Common Welsh Green Dragon", "image": "common_welsh_green_dragon"},   # GREEN
    "40e":{"name": "Swedish Short-Snout Dragon", "image": "swedish_short_snout_dragon"}, # BLUE
    "40f":{"name": "Antipodean Opaleye Dragon", "image": "antipodean_opaleye_dragon"},   # PURPLE
    "40g":{"name": "Ukrainian Ironbelly Dragon", "image": "ukrainian_ironbelly_dragon"}, # WHITE
    "40h":{"name": "Hungarian Horntail Dragon", "image": "hungarian_horntail_dragon"},   # BLACK
"unknown":{"name": "Error", "image": "error"}, # ERROR
}

############################################################################################################
# Scheduling
############################################################################################################

gameserver_timezone = ZoneInfo("Africa/Khartoum")
main_timezone       = ZoneInfo("Europe/London")

base_housecup_date = datetime(year=2025, month=1, day=10, tzinfo=gameserver_timezone)

time_trigger = {
    "game_reset":    time(hour=4,  minute=0,  second=0, tzinfo=gameserver_timezone), # UTC+2 - 03:00 - exact
    "morning":       time(hour=7,  minute=0,  second=0, tzinfo=main_timezone),       # UTC+1 - 08:00 - exact
    "weekly_cards":  time(hour=16, minute=59, second=0, tzinfo=gameserver_timezone), # UTC+2 - 16:00 - exact
    "housecup":      time(hour=19, minute=0,  second=0, tzinfo=gameserver_timezone), # UTC+2 - 18:00 - 24 h early
    "club_events":   time(hour=19, minute=15, second=0, tzinfo=main_timezone),       # UTC+1 - 20:30 - 15 min early
    "game_midnight": time(hour=23, minute=0,  second=0, tzinfo=gameserver_timezone), # UTC+2 - 23:00 - 1 h early
    "midnight":      time(hour=23, minute=0,  second=0, tzinfo=main_timezone),       # UTC+1 - 24:00 - 1 h early
}

def notification_dict(is_short=False):
    full_dict = {"Welcome":                  None,
                 "Level Up":                 None,
                 "Birthday":                "morning",
                 "Card - Matagot":          "weekly_cards",
                 "Card - Book of Monsters": "weekly_cards",
                 "Card - Cornish Pixies":   "weekly_cards",
                 "Housecup":                "housecup",
                 "Club Events":             "club_events",
                 "Club Points":             "club_events",
                 "Maintenance":             "game_midnight",
                 "Rankings":                "midnight",}

    if is_short:
        seen, time_triggers = set(), set(time_trigger.keys())

        short_dict = {}
        for key, value in full_dict.items():
            if (value not in seen) and (value in time_triggers):
                short_dict[key] = value
                seen.add(value)

        return short_dict
    return full_dict
