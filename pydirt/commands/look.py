"""look / examine - describing rooms, items, and characters.

C equivalent: src/rooms.c (``lookin``/``trapch``) and the look-related
handlers in src/commands.c (``lookcom``).
"""
from __future__ import annotations

from pydirt import finder
from pydirt.models import Item, Placement, Room
from pydirt.sendsys import send_to_player
from pydirt.verbs import verb
from pydirt.world import World


def character_name(world: World, char_id: str) -> str:
    player = world.players.get(char_id.lower())
    if player is not None:
        return player.name
    mobile = world.mobiles.get(char_id.lower())
    if mobile is not None:
        return mobile.name
    return char_id


def item_room_line(item: Item) -> str:
    index = item.state if 0 <= item.state < len(item.descriptions) else 0
    return item.descriptions[index] or item.descriptions[0] or f"{item.name} is here."


def describe_room(world: World, player, room: Room) -> str:
    lines = [room.title, room.description]

    exits = [direction for direction, dest in room.exits.items() if dest]
    lines.append("Exits: " + (", ".join(exits) if exits else "none"))

    for item_id in room.items:
        item = world.items.get(item_id)
        if item is not None:
            lines.append(item_room_line(item))

    for char_id in room.characters:
        if char_id.lower() == player.name.lower():
            continue
        lines.append(f"{character_name(world, char_id)} is here.")

    return "\n".join(line for line in lines if line)


def _is_container(item: Item) -> bool:
    return "Container" in item.flags


def _is_closed(item: Item) -> bool:
    return "Openable" in item.flags and item.state == 0


@verb("look")
async def do_look(world: World, player, remainder: str) -> None:
    from pydirt.parser import split_nouns  # avoid a circular import at module load time

    args = split_nouns(player, remainder)
    room = world.room(player.location)
    if room is None:
        await send_to_player(player, "You are nowhere.")
        return

    if not args.item1:
        await send_to_player(player, describe_room(world, player, room))
        return

    if args.prep in ("in", "into"):
        await _look_in(world, player, room, args.item1)
        return

    await _look_at(world, player, room, args.item1)


async def _look_at(world: World, player, room: Room, name: str) -> None:
    char_id = finder.find_character_in_room(world, room.id, name)
    if char_id is not None:
        if char_id.lower() == player.name.lower():
            await send_to_player(player, player.description or "You look as well as can be expected.")
        else:
            text = _character_description(world, char_id)
            await send_to_player(player, text)
            player.last_target = char_id
        return

    item = finder.find_item_anywhere(world, player, room.id, name)
    if item is None:
        await send_to_player(player, "You don't see that here.")
        return
    await send_to_player(player, item.examine or item_room_line(item))
    player.last_target = item.id


async def _look_in(world: World, player, room: Room, name: str) -> None:
    item = finder.find_item_anywhere(world, player, room.id, name)
    if item is None:
        await send_to_player(player, "You don't see that here.")
        return
    if not _is_container(item):
        await send_to_player(player, "You can't look inside that.")
        return
    if _is_closed(item):
        await send_to_player(player, f"The {item.name} is closed.")
        return
    if not item.contents:
        await send_to_player(player, f"The {item.name} is empty.")
        return
    lines = [f"The {item.name} contains:"]
    for content_id in item.contents:
        content = world.items.get(content_id)
        if content is not None:
            lines.append(f"  {content.name}")
    await send_to_player(player, "\n".join(lines))
    player.last_target = item.id


def _character_description(world: World, char_id: str) -> str:
    player = world.players.get(char_id.lower())
    if player is not None:
        return player.description or f"{player.name} looks like an ordinary adventurer."
    mobile = world.mobiles.get(char_id.lower())
    if mobile is not None:
        return mobile.examine or mobile.description or f"{mobile.name} is here."
    return "You don't see that here."


@verb("examine")
async def do_examine(world: World, player, remainder: str) -> None:
    await do_look(world, player, "at " + remainder if remainder else "")


@verb("exits")
async def do_exits(world: World, player, remainder: str) -> None:
    """C equivalent: exitcom() in src/rooms.c - list each exit direction with
    the short description of the room it leads to."""
    room = world.room(player.location)
    if room is None:
        await send_to_player(player, "You are nowhere.")
        return
    lines = ["Obvious exits are:"]
    for direction, dest in room.exits.items():
        if not dest:
            continue
        dest_room = world.rooms.get(dest)
        if dest_room is None:
            continue
        lines.append(f"{direction:>5} : {dest_room.title or 'somewhere'}")
    if len(lines) == 1:
        await send_to_player(player, "None....")
    else:
        await send_to_player(player, "\n".join(lines))
