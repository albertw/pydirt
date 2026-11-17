"""Direction commands and `go <direction>`.

C equivalent: src/move.c (``dodirn``/``dogocom``).
"""
from __future__ import annotations

from pydirt.commands.look import describe_room
from pydirt.sendsys import send_to_player, send_to_room
from pydirt.verbs import verb
from pydirt.world import World

_FULL_NAME = {"n": "north", "e": "east", "s": "south", "w": "west", "u": "up", "d": "down"}
_OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}


async def move_character(world: World, player, direction: str) -> None:
    """C equivalent: dodirn() - validate the exit, move, announce, auto-look."""
    room = world.room(player.location)
    if room is None:
        await send_to_player(player, "You are nowhere.")
        return

    destination_id = room.exits.get(direction)
    if not destination_id:
        await send_to_player(player, "You can't go that way.")
        return

    destination = world.room(destination_id)
    if destination is None:
        await send_to_player(player, "That exit leads nowhere useful (unresolved room).")
        return

    occupant_key = player.name.lower()
    if occupant_key in room.characters:
        room.characters.remove(occupant_key)
    await send_to_room(world, room.id, f"{player.name} leaves {direction}.")

    player.location = destination_id
    destination.characters.append(occupant_key)
    await send_to_room(world, destination_id, f"{player.name} arrives from the {_OPPOSITE.get(direction, 'nowhere')}.",
                        exclude=[player.name])

    await send_to_player(player, describe_room(world, player, destination))


def _direction_handler(direction: str):
    async def handler(world: World, player, remainder: str) -> None:
        await move_character(world, player, direction)

    return handler


for _dir in ("north", "east", "south", "west", "up", "down"):
    verb(_dir)(_direction_handler(_dir))


@verb("go")
async def do_go(world: World, player, remainder: str) -> None:
    """C equivalent: dogocom() - accepts a full or abbreviated direction."""
    word = remainder.strip().lower()
    direction = _FULL_NAME.get(word, word)
    if direction not in _OPPOSITE and direction not in ("up", "down"):
        await send_to_player(player, "Go where?")
        return
    await move_character(world, player, direction)
