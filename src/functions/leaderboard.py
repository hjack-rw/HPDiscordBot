import src.variables as vars

from .core          import log
from .media          import get_image, get_level_and_progress, get_level_change, get_animal_rank
from .discord_utils  import get_avatar
from .notifications  import print_notification

from copy      import deepcopy
from functools import wraps
from io        import BytesIO
from types     import SimpleNamespace

from PIL          import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError
from discord.file import File


class CustomHousecup:
    def __init__(self, house:str, all_members_count:int):
        self.name = house
        self.all_members_count = all_members_count
        self.points = []

    def for_scoreboard(self, mean, sd):
        if not self.points:
            return 0

        points = [point for point in self.points if (mean - 2 * sd <= point <= mean + 2 * sd)]

        # sum of points / active members / all_members
        return sum(points) / max(len(points), 1) / max(self.all_members_count, 1)


def get_leaderboard_static():

    # the basic template
    background = Image.open(vars.image_data_path + "leaderboard/template.png")

    # the profile border
    profile_border = Image.open(vars.image_data_path + "leaderboard/frogcard_template.png")

    # the full progress bar
    full_bar = Image.open(vars.image_data_path + "leaderboard/bar.png")

    # the mask for the begining of the bar
    bar_mask = Image.new(mode="L", size=full_bar.size, color=255)
    draw = ImageDraw.Draw(bar_mask)
    _, y = full_bar.size
    draw.polygon(check_shape(shape=[(0, 0), (0, y), (91, y), (91, 0)]), fill=0)

    # the progress bar marker
    marker = Image.open(vars.image_data_path + "leaderboard/bar_frog.png")

    # the fonts
    fonts = {"MAGIC_88": ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=88),
             "MAGIC_45": ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=45),
             "MAGIC_42": ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=42),
             "MAGIC_35": ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=35),
             "RUNES_88": ImageFont.truetype(font=(vars.font_data_path + "RUNES.ttf"), size=88),
             "RUNES_72": ImageFont.truetype(font=(vars.font_data_path + "RUNES.ttf"), size=72),}

    return (background, profile_border, full_bar, bar_mask, marker, fonts)


def scale_image(base_width, image):
    x, y = image.size

    w_size = base_width
    w_percent = base_width / float(x)

    h_size = int(round(y * w_percent))
    return image.resize((w_size, h_size), Image.Resampling.LANCZOS)


def check_shape(shape):
    return [(int(round(x)), int(round(y))) for x,y in shape]


def get_position(center, image_center, offset=(0,0)):
    x, y = center
    x_off, y_off = offset
    w_size, h_size = image_center

    return check_shape(shape=[(x - (w_size / 2) + x_off, y - (h_size / 2) + y_off)])[0]


def draw_infocard(new_user, all_members_count):
    background = Image.open(vars.image_data_path + "card/template.png")

    ## profile picture ##
    url = get_avatar(user=new_user)

    # download avatar
    avatar = Image.open(BytesIO(get_image(url=url)))

    # scaling
    avatar = scale_image(base_width=220, image=avatar)
    x, _ = avatar.size

    # add avatar mask
    blur_radius = 1
    avatar_mask = Image.new(mode="L", size=avatar.size, color=0)
    draw = ImageDraw.Draw(avatar_mask)
    draw.ellipse(xy=(5, 8, x-5, x-5), fill=255)
    avatar_mask = avatar_mask.filter(ImageFilter.GaussianBlur(blur_radius))

    background.paste(im=avatar, box=(215,20), mask=avatar_mask)

    draw = ImageDraw.Draw(background)


    ## text ##
    # add nickname
    if len(new_user.name) > 15:
        name_font = ImageFont.truetype(font=(vars.font_data_path + "RUNES.ttf"), size=80)
    else:
        name_font = ImageFont.truetype(font=(vars.font_data_path + "RUNES.ttf"), size=100)

    if len(new_user.name) > 9:
        draw.text(xy=(995,115), text=new_user.name, fill=(235,235,235), font=name_font, align="center", anchor='rm')
    else:
        draw.text(xy=(795,115), text=new_user.name, fill=(235,235,235), font=name_font, align="center", anchor='mm')

    # add footer
    footer_font = ImageFont.truetype(font=(vars.font_data_path + "MAGIC.ttf"), size=35)
    draw.text(xy=(790,200), text=f"We are now {all_members_count} members!", fill=(235,235,235), font=footer_font, align="center", anchor='mm')


    ## save and return file ##
    bytes = BytesIO()
    background.save(bytes, format="PNG")
    bytes.seek(0)

    return File(bytes, filename="card.png")


def draw_leaderboard(user, rank, house, static, is_bytes=False):
    background, profile_border, full_bar, bar_mask, marker, fonts = static
    background = deepcopy(background)


    ## profile picture ##
    xy = (150, 150)

    avatar = None
    avatar_center = (177, 156)

    if url := user["avatar"]:
        try:
            # download avatar
            image_data = get_image(url)

            image = Image.open(BytesIO(image_data))
            image.load()  # force-load the image

            # scaling
            avatar = scale_image(base_width=xy[0], image=image)
        except (OSError, UnidentifiedImageError, TypeError) as error:
            log(f"PIL: failed to load image for {user.get('username')}: {error}")

    # black avatar if missing
    if avatar is None:
        avatar = Image.new(mode="L", size=xy, color=0)

    # add avatar mask
    avatar_mask = Image.new(mode="L", size=avatar.size, color=0)
    draw = ImageDraw.Draw(avatar_mask)
    draw.ellipse(xy=(0, 0, *avatar.size), fill=255)

    x, y = avatar.size
    draw.polygon(check_shape(shape=[(0,y/2), (0,y), (x,y), (x,y/2)]), fill=255)

    offset = user.pop("offset", True)
    background.paste(im=avatar, box=get_position(center=avatar_center, image_center=avatar.size, offset=(5,8) if offset else (0,0)), mask=avatar_mask)

    # add profile border
    background.alpha_composite(im=profile_border, dest=get_position(center=avatar_center, image_center=profile_border.size))

    draw = ImageDraw.Draw(background)


    ## box info ##
    # add rank
    draw.text(xy=(380, 118), text="#" + f"{rank}".rjust(3, "0"), fill=(235,235,235), font=fonts["MAGIC_88"], align="left", anchor='lm')

    # add nickname
    if len(user["username"]) <= 9 and ("\n" in user["username"]):
        name_font = fonts["RUNES_88"]
    else:
        name_font = fonts["RUNES_72"]

    draw.multiline_text(xy=(570, 160 if "\n" in user["username"] else 128), text=user["username"], fill=(235,235,235), font=name_font, align="left", anchor='lm', spacing=-35)

    # add house logo
    if house:
        house_logo = Image.open(vars.image_data_path + f"houses/{house}.png")
        background.alpha_composite(im=house_logo, dest=(388, 194))

    # progress details (pet name and level)
    pet = get_animal_rank(user)["name"]

    if len(pet) > 20:
        pet_font = fonts["MAGIC_35"]
    else:
        pet_font = fonts["MAGIC_45"]

    draw.text(xy=(901, 170), text=f"Pet: ", fill=(235,235,235), font=fonts["MAGIC_45"], align="left", anchor='lm')
    draw.text(xy=(961, 169), text=pet, fill=(235,235,235), font=pet_font, align="left", anchor='lm')
    draw.text(xy=(901, 227), text=f"Level: {user['level']}", fill=(235,235,235), font=fonts["MAGIC_45"], align="left", anchor='lm')


    ## progress bar ##
    # limit progress
    percent = user["progress"]

    if percent < 0.05:
        percent = 0.05
    elif percent > 1:
        percent = 1

    # proportion
    bar_offset = 1480 - int(round(percent * 1480))

    progress_bar = Image.new("RGBA", full_bar.size, (0, 0, 0, 0))

    x, y = full_bar.size
    progress_bar.paste(im=full_bar.crop((bar_offset, 0, x, y)), mask=bar_mask.crop((0, 0, x-bar_offset, y)))

    # add progress bar
    background.alpha_composite(im=progress_bar)

    # add progress bar marker
    background.alpha_composite(im=marker, dest=get_position(center=(95, 322), image_center=marker.size, offset=(int(round(percent * 1480)-85), 0) if percent >= 0.059 else (0, 0)))

    # add percentage
    draw.text(xy=(x-175 if percent < 0.5 else 175, 322), text=f"{round(user['progress']*100, 2)}%", fill=(235,235,235), font=fonts["MAGIC_42"], align="center", anchor='mm')


    ## save and return file ##
    bytes = BytesIO()
    background.save(bytes, format="PNG")
    bytes.seek(0)

    if is_bytes:
        return bytes
    return File(bytes, filename=f"leaderboard_{user['user_id']}.png")


def parse_xp_amount(func):
    @wraps(func)
    async def parse(self, *args, **kwargs):
        server       = kwargs.pop("server")
        member       = kwargs.pop("member", SimpleNamespace(id=None))
        amount       = kwargs.pop("amount")
        after_action = kwargs.pop("after_action", "add")

        if amount <= 0:
            raise Exception("parse error: 'amount' cannot be zero or negative")

        user_id = kwargs.get("user_id", member.id)
        record  = self.get_from_dict(user_id=user_id)
        is_new  = not bool(record)

        # modify existing record or create a new record
        previous_xp    = record["xp"]    if record else 0
        previous_level = record["level"] if record else 0

        # compute new xp based on the action
        if after_action == "add":
            current_xp = previous_xp + amount
        elif after_action == "subtract":
            current_xp = previous_xp - amount
            if current_xp <= 0:
                raise Exception("parse error: 'xp' cannot be zero or negative after subtraction")
        else:  # action == "set"
            current_xp = amount

        current_level, progress = get_level_and_progress(current_xp)

        # prepare new_kwargs dict for func
        new_kwargs = deepcopy(kwargs)
        new_kwargs.update({"is_new":  is_new,
                           "user_id": user_id,
                           "experience": {"xp": current_xp, "level": current_level, "progress": progress, **({} if is_new else {"archived": False}),}})

        # check roles to assign Sphinx or Ashwinder pet accordingly
        if is_new:
            new_kwargs["pet_ashwinder"] = not bool({role.name for role in getattr(member, "roles", [])} & {vars.club_name_short, "guest"})

        # call the original function
        current_xp = await func(self, *args, **new_kwargs)

        # when on server send a level up message
        if server:
            level_ups = get_level_change(previous_level, current_level)
            if level_ups:
                user_data = await self.get_joined_table(user_id=member.id)
                await print_notification(server, event_name="Level Up", variables=[member, user_data, level_ups], is_task=False)

        return current_xp
    return parse


def create_leaderboard(server, data, custom_housecup):
    ## get static files for leaderboard ##
    static = get_leaderboard_static()

    ## create loop for each user ##
    rank, rank_xp, leaderboard = 0, 0, []
    for user in data:

        # get member, skip if can't
        member = server.get_member(user["user_id"])
        if member is None:
            log(f"user_id {user['user_id']} not in member cache, skipping")
            continue
        else:
            if user["xp"] != rank_xp:
                rank += 1
                rank_xp = user["xp"]

        house = None
        roles = {role.name for role in getattr(member, "roles", [])}

        # add points for the custom housecup
        for idx, house in enumerate(custom_housecup):
            if house.name in roles:
                custom_housecup[idx].points.append(rank_xp)
                house = house.name
                break
        else:
            # get house if no custom housecup
            if house is None:
                house = next((house for house in vars.houses_names_list() if house in roles), None)

        # get the special role color
        try:
            if member.roles[-1].name in {"captain", "moderator", "co-captain",}:
                color = member.roles[-1].color.value
            else:
                color = 5198940
        except AttributeError:
            color = vars.system_embed_color

        if (username := user.pop("username", None)) is None:
            user["username"] = (member.display_name).replace(" ", "\n ")
        else:
            user["username"] = username

        user["avatar"] = get_avatar(user=member, none=True)

        file = draw_leaderboard(user, rank, house, static)
        leaderboard.append((user["user_id"], color, file))

    return leaderboard, custom_housecup
