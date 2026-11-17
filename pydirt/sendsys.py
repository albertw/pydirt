"""Message delivery to connected players.

C equivalent: src/sendsys.c + src/bprintf.c. The C version formats into one
shared global buffer and writes through each player's ``FILE*``, flushing as
the "current player" context switches. Here every Player owns its own
``asyncio.StreamWriter``, so sending a message is just an async write - no
shared buffer or global context-switch is needed. In-game color/markup codes
that C's bprintf() expanded are not implemented; everything is sent as
plain text for the MVP.
"""
from __future__ import annotations

import logging
from typing import Iterable

from pydirt.models import Player
from pydirt.world import World

logger = logging.getLogger("pydirt.sendsys")


async def send_to_player(player: Player, text: str) -> None:
    """C equivalent: bprintf()/pbfr() writing to one player's stream."""
    if player.writer is None:
        return
    try:
        player.writer.write((text + "\r\n").encode("utf-8", errors="replace"))
        await player.writer.drain()
    except (ConnectionError, OSError):
        logger.debug("write failed for %s, connection.py will clean up", player.name)


async def send_prompt(player: Player, text: str = ">") -> None:
    """C equivalent: build_prompt() + bprintf("\\r%s", cprompt) in mud.c -
    reprints the "> " prompt (no trailing newline) after a command completes."""
    if player.writer is None:
        return
    try:
        player.writer.write(f"\r{text} ".encode("utf-8", errors="replace"))
        await player.writer.drain()
    except (ConnectionError, OSError):
        logger.debug("write failed for %s, connection.py will clean up", player.name)


async def send_to_room(world: World, room_id: str, text: str, exclude: Iterable[str] = ()) -> None:
    """C equivalent: send_msg() targeting every occupant of a room."""
    room = world.rooms.get(room_id)
    if room is None:
        return
    exclude_set = {name.lower() for name in exclude}
    for occupant_id in list(room.characters):
        if occupant_id.lower() in exclude_set:
            continue
        player = world.players.get(occupant_id.lower())
        if player is not None:
            await send_to_player(player, text)


async def send_to_all(world: World, text: str, exclude: Iterable[str] = ()) -> None:
    """C equivalent: send_msg() with the "everyone online" recipient filter."""
    exclude_set = {name.lower() for name in exclude}
    for player in list(world.players.values()):
        if player.name.lower() in exclude_set:
            continue
        await send_to_player(player, text)
