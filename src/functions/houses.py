import src.variables as vars

from discord.embeds import Embed


def print_house_members(members, house, group):

    # filter by house and group
    users = []
    for member in members:

        # equivalent to .issubset()
        if {house, group} <= {role.name for role in getattr(member, "roles", [])}:
            users.append(member)

    users = sorted(users, key=lambda x: (x.display_name))

    for idx, user in enumerate(users):
        users[idx] = f"{idx+1}. {user.display_name} - <@{user.id}>"

    return Embed(color=vars.system_embed_color, title=vars.houses[house]["emoji"], description=f"**{group.capitalize() if group != vars.club_name_short else vars.club_name}:**\n"+"\n".join(users))
