import src.variables as vars

from .media import get_animal_rank

from glob import glob
from os   import path

from discord.embeds import Embed
from discord.file    import File
from discord.utils   import MISSING


async def print_suitcase(info, level):
    embed = Embed(color=vars.system_embed_color, title=f"{info['username']}'{'s' if info['add_s'] else ''} Suitcase:", description="⭐ __Current Level__ ⭐" if info['current_level'] == level else "")

    if info['current_level']:
        pet = get_animal_rank(user=info, level=level)
        embed.set_footer(text=f"Level: {info['current_level']},​ ​ ​XP: {round(info['xp_for_next_level']*info['progress'])} / {info['xp_for_next_level']}​ ​ ({round(info['progress']*100, 2)}%)")
    else:
        pet = vars.pets.get(list(vars.pets)[level])
        embed.set_footer(text=f"Level: ♾️")

    embed.add_field(name="", value=f"*{pet['name']}* (Level {level})")

    # pets are a fixed, code-defined catalog (not admin-uploaded content), so they're plain
    # files under data/images/pets/, added by dropping a file there - no DB, no url stored.
    # image_name is independent of name (renaming a pet's display name shouldn't silently
    # break its file lookup). Extension on disk can be anything (png/jpg/webp/...);
    # attachment:// always names it .png since Discord content-sniffs rather than trusting
    # the filename extension.
    slug = pet["image"]
    local_files = glob(path.join(vars.image_data_path, "pets", f"{slug}.*"))
    if local_files:
        embed.set_image(url=f"attachment://{slug}.png")
        return embed, File(fp=local_files[0], filename=f"{slug}.png")

    return embed, MISSING
