import src.variables as vars

from .media      import get_member_id_by_nick
from .text_utils import remove_extra_characters, parse_multiple_possibilities

from copy      import deepcopy
from datetime  import datetime
from functools import wraps

from discord.embeds import Embed


def parse_portkey_data(func):
    @wraps(func)
    async def parse(self, *args, **kwargs):
        server  = kwargs.pop("server")
        message = kwargs.pop("message")
        user_id = kwargs.pop("user_id", None)

        if message.author.id != 952824326766333972:
            raise Exception("what you are trying to accept is not a Portkey")

        # predeclare all expected variables to prevent UnboundLocalError
        game_id = from_wb = old_username = multiple_choice = additional_info = birthday = birth_year = extra = None


        for field in message.embeds[0].fields:
            idx = field.name.split(".")[0]

            match idx:
                case "1":
                    if user_id is None:
                        user_id = get_member_id_by_nick(server, nick=field.value)
                        if user_id is None:
                            raise Exception(f"no User with Nickname {field.value} on this server")

                case "2":
                    game_id = remove_extra_characters(field.value, is_id=True)
                    game_id = int(game_id) if game_id else 0

                case "3":
                    continue

                case "4":
                    from_wb, old_username = parse_multiple_possibilities(field.value)
                    from_wb = (from_wb == "Yes")

                case "5":
                    multiple_choice = parse_multiple_possibilities(field.value)
                    additional_info = multiple_choice.pop(-1)

                    form_answers     = vars.form_answers
                    form_answers_set = set(form_answers)

                    if additional_info in form_answers_set:
                        multiple_choice.append(additional_info)
                        additional_info = None

                    selected_answers = set(multiple_choice)
                    multiple_choice  = "".join("1" if answer in selected_answers else "0" for answer in reversed(form_answers))

                case "6":
                    birth_parts = field.value.split(".")

                    if birth_parts != ["-"]:
                        birthday = datetime(day=int(birth_parts[0]), month=int(birth_parts[1]), year=2000)
                        if (birth_year := int(birth_parts[2])-1900) == datetime.now().year-1900:
                            birth_year = None
                    else:
                        birthday, birth_year = None, None

                case "7":
                    extra = field.value if (field.value != "-") else None

        # prepare new_kwargs dict for func
        new_kwargs = deepcopy(kwargs)
        new_kwargs["portkey"] = (user_id, game_id, from_wb, old_username, multiple_choice, additional_info, birthday, birth_year, extra)

        # call the original function
        return await func(self, *args, **new_kwargs)
    return parse


def print_portkey(member, portkey):
    try:
        roles = {role.name for role in getattr(member, "roles", [])}

        if member.roles[-1].name in {"captain", "moderator", "co-captain",}:
            color = member.roles[-1].color.value
        else:
            color = 5198940
    except AttributeError:
        color = vars.system_embed_color


    doc_url = "https://docs.google.com/document/d/1CJMk8wJZkYnXG729xHGPvsyaj5BtrXMZeqlIOV_4qtA/edit?usp=sharing"

    form_answers_extended = [f"{answer}\n\n" for answer in vars.form_answers]
    form_answers_extended.append(f"{portkey['additional_info']}\n\n")


    embed = Embed(color=color, description=f"**User:** <@{portkey['user_id']}>")

    line_1 = f"{member.display_name} | `#" + f"{portkey['game_id'] if portkey['game_id'] else 0}`".rjust(10, "0") + f" [📋]({doc_url})"
    embed.add_field(name="1. Hello, I'm... | And my ID is...", value=line_1, inline=True)

    line_2 = vars.houses[next((house for house in vars.houses_names_list() if house in roles), "other")]["emoji"]
    embed.add_field(name="2. My house is...", value=line_2, inline=True)

    line_3 = (("Yes | " if portkey["from_wb"] else "No, ") + portkey["old_username"]) if portkey["old_username"] else ("Yes" if portkey["from_wb"] else "No")
    embed.add_field(name="3. Am I from the WB server? | My name was...", value=line_3.replace(" | 0", ", "), inline=False)

    line_4 = "• " + "• ".join([form_answers_extended[idx].replace(" ", "​ ​ ", 1) for idx,choice in enumerate(portkey["multiple_choice"][::-1] + ("1" if portkey["additional_info"] else "0")) if choice == "1"])
    embed.add_field(name="4. In the game I like doing...", value=line_4, inline=False)

    if (not_skip := portkey["birthday"] is not None):
        birthday = portkey["birthday"]

        if year := portkey["year"]:
            birthday = birthday.replace(year = year + 1900)

        line_5 = birthday.strftime("%d.%m.%Y") if year else birthday.strftime("%d.%m")
        embed.add_field(name="5. I was born...", value=line_5, inline=False)

    if portkey["extra"]:
        line_6 = portkey["extra"]
        embed.add_field(name=f"{6 if not_skip else 5}. You may also want to know...", value=line_6, inline=False)

    embed.set_footer(text=f"{vars.club_name_short.upper()}  •  Portkey #{portkey['id']}")

    return embed
