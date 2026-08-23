from datetime import datetime, time
from dotenv   import load_dotenv
from pathlib  import Path
from zoneinfo import ZoneInfo

import os


path = os.getcwd() + "/src/"
load_dotenv(dotenv_path=Path(path + "env"))

absolute_path = path

discord_token = os.getenv("DISCORD_TOKEN")
bot_token     = os.getenv("DISCORD_BOT_TOKEN")

try:
    from pre_init import *
except ImportError:
    print("failed to import 'test_bot' from pre_init!")
    test_bot = {"local_deploy": os.getcwd() != "/home/container",
                "test_body":    False,
                "test_command": False,
                "test_events":  False,
                "test_tasks":   False,}

############################################################################################################

bot_id      = 0
dev_user_id = 0
webhook_id  = 0
server_id   = 0

club_name = "Enemies of the Heir"
club_name_short = "eoth"

channel_sections_ids = {"archive":  0,
                        "team":     0,
                        "club":     0,
                        "tickets":  0,
                        "general":  0,
                        "guides":   0,
                        "offtopic": 0,}

channel_ids = {"welcome":                 0,
               
               "secret-lab":              0,
               "assets":                  0,
               "staffroom":               0,
               "absence-list":            0,
               "points-log":              0,
               "the-sorting-hat":         0,
               
               "rules":                   0,
               "marauders-map":           0,
               "announcements":           0,
               "the-daily-prophet":       0,
               "important-polls":         0,
               "portkey-arrival":         0,
               "leaderboard":             0,

               "owlery":                  0,
               "come-and-go":             0,

               "great-hall":              0,
               "portraits":               0,
               "dueling-club":            0,
               "diagon-alley":            0,

               "charms":                  0,
               "greenhouse":              0,
               "kitchen":                 0,
               "dada":                    0,
               
               "gallery":                 0,
               "frog-choir":              0,
               "the-quibbler":            0,
               "weasleys-wizard-wheezes": 0,
               "hagrids-hut":             0,
               "wizard-cards":            0,
               "crystal-ball":            0,

               "pensieve":                0,}

channel_ids_test = {"assets": channel_ids["assets"],}
channel_ids_test.update({key: channel_ids["secret-lab"] for key in channel_ids if key not in list(channel_ids_test.keys())})

############################################################################################################

system_embed_color = 16777215 # white

wait_for = 2 # seconds

weekdays = {0:"Monday", 1:"Tuesday", 2:"Wednesday", 3:"Thursday", 4:"Friday", 5:"Saturday", 6:"Sunday"}
months   = {"01|January": 1, "02|February": 2, "03|March": 3, "04|April": 4, "05|May": 5, "06|June": 6, "07|July": 7, "08|August": 8, "09|September": 9, "10|October": 10, "11|November": 11, "12|December": 12}

numbers = {0: "0️⃣", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣"}

houses = {"other"     : {"emoji": "",                                             "crest": ""}, #for BOTS
          "gryffindor": {"emoji": "<:gryffindor:1255656359190462484> Gryffindor", "crest": "https://static.wikia.nocookie.net/pottermore/images/1/16/Gryffindor_crest.png/revision/latest?cb=20111112232412"},
          "hufflepuff": {"emoji": "<:hufflepuff:1255656360780238849> Hufflepuff", "crest": "https://static.wikia.nocookie.net/pottermore/images/5/5e/Hufflepuff_crest.png/revision/latest?cb=20111112232427"},
          "ravenclaw" : {"emoji": "<:ravenclaw:1255656362617212999> Ravenclaw",   "crest": "https://static.wikia.nocookie.net/pottermore/images/4/40/Ravenclaw_Crest_1.png/revision/latest?cb=20140604194505"},
          "slytherin" : {"emoji": "<:slytherin:1255656364244729856> Slytherin",   "crest": "https://static.wikia.nocookie.net/pottermore/images/4/45/Slytherin_Crest.png/revision/latest?cb=20111112232353"},}

def houses_names_list(is_short=True):
    if is_short:
        return list(houses)[1:]
    else:
        return list(houses)

custom_avatars = {"Mr. Filch":        "https://www.tafce.com/images/c/c6/Mr_Filch_HPATGOF_-_Edited.png",
                  "Prof. Dumbledore": "https://static.wikia.nocookie.net/harrypotter/images/8/82/ProfessorDumbledore.jpg",
                  "Prof. Flitwick":   "https://files.catbox.moe/9cfhlt.jpg",
                  "Prof. Hagrid":     "https://ostatniatawerna.pl/wp-content/cache/thumb/7c/f366d57c85cd27c_730x452.jpg",
                  "Prof. McGonagall": "https://m.natemat.pl/4cccf528bb2fabc88d662c3ac8a519ef,922,0,0,0.png",
                  "Prof. Slughorn":   "https://fwcdn.pl/cpo/03/33/333/199.4.jpg",
                  "Prof. Snape":      "https://images.bravo.de/harry-potter-star-was-stimmt-mit-seinen-augen-nichtjpg,id=ac02185e,b=bravo,w=1200,rm=sk.jpeg",
                  "Prof. Sprout":     "https://m.media-amazon.com/images/M/MV5BMzY1ZTFlMTctYmNmMC00MWQyLWI1MDAtOGM5N2MyZGI5N2JkXkEyXkFqcGc@._V1_QL75_UX331_.jpg",
                  "Prof. Trelawney":  "https://www.tafce.com/images/thumb/9/9b/Professor_Sybil_Trelawney_HPATOOTP_-_Edited.png/350px-Professor_Sybil_Trelawney_HPATOOTP_-_Edited.png",}

housecup_disciplines_names = {0: "Best Partners",
                              1: "Dance Club",
                              2: "Top Wizard",
                              3: "History of Magic",
                              4: "Muggle Studies",
                              5: "Casual Matches",
                              6: "Qudditch",
                              7: "Gobstones Showdown",}

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

# Complete list at:
# https://harrypotter.fandom.com/wiki/List_of_creatures
pets = {
    "0":  {"name": "Flobberworm",                "url": "https://files.catbox.moe/k2qcmw.jpg"},                                                                                               #100 xp to finish
    "1":  {"name": "Manticore",                  "url": "https://media.harrypotterfanzone.com/baby-manticore.jpg"},                                                                           #255
    "2a": {"name": "Cornish Pixie",              "url": "attachment://cornish_pixie.png"},                                                                                                    #475
    "2b": {"name": "Lobalug",                    "url": "https://static.wikia.nocookie.net/harrypotter/images/1/1a/Lobalug.png/revision/latest?cb=20171226234304"},
    "3":  {"name": "Gnome",                      "url": "https://i.pinimg.com/736x/7b/42/34/7b4234641bc6118dc878d279fe706540.jpg"},                                                           #770
    "4":  {"name": "Bowtruckle",                 "url": "https://i.pinimg.com/736x/68/81/f5/6881f5322ec892c779b0e0881e67e7f4.jpg"},                                                           #1150
    "5":  {"name": "Puffskein",                  "url": "https://i.pinimg.com/736x/ef/b0/90/efb090578e599a12a305564b64c24d2e.jpg"},                                                           #1625
    "6a": {"name": "Knarl",                      "url": "https://i.pinimg.com/736x/fd/dc/8f/fddc8f7ab8f4b57a970c0a3a488753ac.jpg"},                                                           #2205
    "6b": {"name": "Jellyfish",                  "url": "https://i.pinimg.com/736x/43/99/16/439916ec289110b190f5efc7970e4831.jpg"},
    "7":  {"name": "Diricawl",                   "url": "https://i.pinimg.com/736x/51/3a/83/513a831fdc04aef7ff5fc476aee47a52.jpg"},                                                           #2900
    "8":  {"name": "Fwooper",                    "url": "https://i.pinimg.com/736x/e1/8a/c5/e18ac555875e3c33561c8bb81e748dd7.jpg"},                                                           #3720
    "9":  {"name": "Occamy",                     "url": "https://i.pinimg.com/736x/a8/ee/6b/a8ee6bdc067d101d6ca4790d8b7e5e63.jpg"},                                                           #4675
    "10a":{"name": "Kneazle",                    "url": "https://pm1.aminoapps.com/6761/6073f81e332935ad223300284d5ee081de4ee52dv2_hq.jpg"},                                                  #5775
    "10b":{"name": "Crup",                       "url": "https://i.pinimg.com/736x/44/73/14/44731418cf4d378cd80fe8d5d5e43577.jpg"},
    "11a":{"name": "Jarvey",                     "url": "https://static.wikia.nocookie.net/harrypotter/images/9/98/Jarvey.png/revision/latest?cb=20161202173149"},                            #7030
    "11b":{"name": "Murtlap",                    "url": "https://i.pinimg.com/736x/aa/4c/ed/aa4ceda0555f9d9772a4bbd4628b19aa.jpg"},
    "12": {"name": "Niffler",                    "url": "https://i.pinimg.com/736x/a5/6f/4b/a56f4be149ba82d4dad3e3ba4c982157.jpg"},                                                           #8450
    "13": {"name": "Mooncalf",                   "url": "https://i.pinimg.com/736x/ab/18/a7/ab18a7ea239db16326ba5c2fa26f2e29.jpg"},                                                           #10045
    "14": {"name": "Qilin",                      "url": "https://i.pinimg.com/736x/94/0f/c0/940fc01d0959d4070deffc3706a522c5.jpg"},                                                           #11825
    "15a":{"name": "Tebo",                       "url": "https://i.pinimg.com/736x/d8/f4/b0/d8f4b0f45d604eca6037953be5593b09.jpg"},                                                           #13800
    "15b":{"name": "Grindylow",                  "url": "https://i.pinimg.com/736x/09/c9/89/09c989eff287f4dbcd94effde3e4b883.jpg"},
    "16": {"name": "Demiguise",                  "url": "https://i.pinimg.com/736x/f7/a0/17/f7a017f8b16059c7ca2593d6f43fbf19.jpg"},                                                           #15980
    "17": {"name": "Yeti",                       "url": "https://i.pinimg.com/736x/57/74/2d/57742d39a2376de105791fb60de7781f.jpg"},                                                           #18375
    "18a":{"name": "Matagot",                    "url": "https://i.pinimg.com/736x/0d/55/a6/0d55a64539413282c823aaac9da59a1c.jpg"},                                                           #20995
    "18b":{"name": "Swooping Evil",              "url": "attachment://swooping_evil.png"},
    "19a":{"name": "Hinkypunk",                  "url": "https://i.pinimg.com/736x/1f/09/0f/1f090fa6b800551606a9788879edd10e.jpg"},                                                           #23850
    "19b":{"name": "Kappa",                      "url": "https://i.pinimg.com/736x/56/9f/d2/569fd22d1677997c4d8889ffdcfc8c16.jpg"},
    "20a":{"name": "Sphinx",                     "url": "https://2.bp.blogspot.com/-P5hI3De5blA/UugVe-7tZsI/AAAAAAAAOUI/pBN_pAx4SyU/s1600/PZO_sphinx_timkingslynne.jpg"},                     #26950
    "20b":{"name": "Ashwinder",                  "url": "attachment://ashwinder.png"},
    "21": {"name": "Golden Snidget",             "url": "https://i.pinimg.com/736x/15/d0/c1/15d0c13c0f6a87f9daddc27ed5ae643a.jpg"},                                                           #30305
    "22": {"name": "Augurey",                    "url": "https://cdnb.artstation.com/p/assets/images/images/031/592/281/large/kate-vigdis-.jpg?1621081086"},                                  #33925
    "23": {"name": "Thunderbird",                "url": "attachment://thunderbird.png"},                                                                                                      #37820
    "24": {"name": "Fire Crab",                  "url": "attachment://fire_crab.png"},                                                                                                        #42000
    "25a":{"name": "Blast-Ended Skrewt",         "url": "https://blooloop.com/wp-content/uploads/2019/04/blast-ended-skrewt-small.jpeg"},                                                     #46475
    "25b":{"name": "Dugbog",                     "url": "https://cdnb.artstation.com/p/assets/images/images/075/126/241/large/maike-otto-dugbog-keyvisual-background.jpg?1713815446"},
    "26": {"name": "Erumpent",                   "url": "https://static.wikia.nocookie.net/harrypotter/images/6/61/Erumpent_Concept_Art_FB1.png/revision/latest"},                            #51255
    "27a":{"name": "Nundu",                      "url": "https://cdna.artstation.com/p/assets/images/images/051/492/600/large/baptiste-ousset-nundu.jpg?1657448088"},                         #56350
    "27b":{"name": "Graphorn",                   "url": "https://i.pinimg.com/736x/89/99/cd/8999cd089228bfa1602162e8ae6e8390.jpg"},
    "28a":{"name": "Griffin",                    "url": "https://i.pinimg.com/736x/44/1b/8d/441b8dbf9b4fe9d62d70e853e54dd243.jpg"},                                                           #61770
    "28b":{"name": "Kelpie",                     "url": "https://i.pinimg.com/736x/17/e1/2e/17e12e5e2ae1e99a5b7bae42b1b8c9b0.jpg"},
    "29": {"name": "Hippogriff",                 "url": "https://i.pinimg.com/736x/5e/02/0e/5e020eaaf225be342c65ef1fd0b6a4ce.jpg"},                                                           #67525
    "30a":{"name": "Abraxan",                    "url": "https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/hostedimages/1384909457i/7024980.png"},                              #73625
    "30b":{"name": "Thestral",                   "url": "https://i.pinimg.com/736x/73/61/e9/7361e9a0af224c768f17f5deadb07b54.jpg"},
    "31": {"name": "Unicorn",                    "url": "https://contentful.harrypotter.com/usf1vwtuqyxm/7LdBbmsnpgs6mCHpRrnGal/df819e7c91f65eef31fdb7e3f87d1424/unicorn_2_1800x1248.png"},   #80080
    "32a":{"name": "Chimaera",                   "url": "https://i.pinimg.com/736x/ad/ff/e0/adffe0d43f0cf86f67c6442d84ba038c.jpg"},                                                           #86900
    "32b":{"name": "Giant Squid",                "url": "attachment://giant_squid.png"},
    "33": {"name": "Manticore Mother",           "url": "attachment://manticore_mother.png"},                                                                                                 #94195
    "34a":{"name": "Zouwu",                      "url": "https://i.pinimg.com/736x/bb/db/dd/bbdbddecb24b4d30917f7a994dc3c5ca.jpg"},                                                           #101775
    "34b":{"name": "Three-Headed Dog",           "url": "https://i.pinimg.com/736x/44/68/4f/44684f3a9c4d64ba08c48710d9c14f9e.jpg"}, 
    "35": {"name": "Phoenix",                    "url": "https://i.pinimg.com/736x/39/8f/b9/398fb97264ea72317170c0680d696d60.jpg"},                                                           #109750
    "36": {"name": "Basilisk",                   "url": "https://i.pinimg.com/736x/94/c9/74/94c974650969630a31064eaf42815604.jpg"},                                                           #118130
    "37a":{"name": "Runespoor",                  "url": "https://static.wikia.nocookie.net/harrypotter/images/b/b9/Runespoor_-_FBcases.png/revision/latest?cb=20161129175049"},               #126925
    "37b":{"name": "Horned Serpent",             "url": "https://i.pinimg.com/736x/0d/06/72/0d06729619e18c551f1f1af539ead561.jpg"},
    "38": {"name": "Firedrake",                  "url": "https://i.pinimg.com/736x/6f/99/41/6f994136ea7683e6888c560eced8411c.jpg"},                                                           #136145
    "39": {"name": "Wyvern",                     "url": "https://i.pinimg.com/736x/5d/8c/95/5d8c957a7e897ae0d4d4249389e1e634.jpg"},                                                           #145800
    "40a":{"name": "Chinese Fireball Dragon",    "url": "https://static.wikia.nocookie.net/harrypotter/images/f/f2/Chinese_Fireball_FBC.png/revision/latest?cb=20161129175906"},              # RED
    "40b":{"name": "Peruvian Vipertooth Dragon", "url": "https://i.pinimg.com/736x/5f/7c/b8/5f7cb8b98fa4a773139c28aa9b1d6f3f.jpg"},                                                           # ORANGE
    "40c":{"name": "Norwegian Ridgeback Dragon", "url": "https://i.pinimg.com/736x/5b/2d/1c/5b2d1c7681fdb46f1a104c17104e92df.jpg"},                                                           # YELLOW
    "40d":{"name": "Common Welsh Green Dragon",  "url": "https://64.media.tumblr.com/eafe255ca12c1ae82e5bd65010734349/tumblr_nkge4cs2r11tqfyozo2_r1_400.png"},                                # GREEN
    "40e":{"name": "Swedish Short-Snout Dragon", "url": "https://i.pinimg.com/736x/25/4c/4c/254c4c448a440069fad6cd6fdd638b6e.jpg"},                                                           # BLUE
    "40f":{"name": "Antipodean Opaleye Dragon",  "url": "https://static1.srcdn.com/wordpress/wp-content/uploads/2019/09/Harry-Potter-Antipodean-Opaleye-Image-Credit-Sonny-Sun.jpg?q=50"},    # PURPLE
    "40g":{"name": "Ukrainian Ironbelly Dragon", "url": "https://static.wikia.nocookie.net/harrypotter/images/4/4c/Ukrainean_Ironbelly_%28FBCFTWW%29.png/revision/latest?cb=20161215033814"}, # WHITE
    "40h":{"name": "Hungarian Horntail Dragon",  "url": "https://i.pinimg.com/736x/3a/fd/c3/3afdc3c0dcb5fdf834c52c69d453fa1b.jpg"},                                                           # BLACK
"unknown":{"name": "Error",                      "url": "https://www.litespeedtech.com/support/wiki/lib/exe/fetch.php/litespeed_wiki:config:404.png?cache="},                                 # ERROR
}

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