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

    # fixed catalog, plain files, no DB - see memory
    slug = pet["image"]
    local_files = glob(path.join(vars.image_data_path, "pets", f"{slug}.*"))
    if local_files:
        embed.set_image(url=f"attachment://{slug}.png")
        return embed, File(fp=local_files[0], filename=f"{slug}.png")

    return embed, MISSING
