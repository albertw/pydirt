"""Per-client connection handling: accept, log in, run the command loop, clean up.

C equivalent: the connection-handling parts of src/main.c (``new_connection``,
``handle_packet``) plus src/mud.c's login handler chain. ``StreamReader.
readline()`` replaces C's manual byte-buffer/line-splitting (``buffer_fds``
in main.c) and the pushable input-handler stack used for login.
"""
from __future__ import annotations

import logging
from pathlib import Path

from pydirt import auth, persistence
from pydirt.commands.look import describe_room
from pydirt.parser import handle_line
from pydirt.sendsys import send_prompt, send_to_player, send_to_room
from pydirt.telnet import TelnetLineReader
from pydirt.world import World

logger = logging.getLogger("pydirt.connection")


async def handle_client(reader, writer, world: World, players_dir: Path) -> None:
    peer = writer.get_extra_info("peername")
    logger.info("connection from %s", peer)
    player = None
    try:
        player = await auth.login(reader, writer, world, players_dir)
        if player is None:
            return

        world.players[player.name.lower()] = player
        room = world.room(player.location)
        if room is not None:
            room.characters.append(player.name.lower())
            await send_to_room(world, player.location, f"{player.name} has entered the game.", exclude=[player.name])
            await send_to_player(player, describe_room(world, player, room))
        await send_prompt(player)
        logger.info("player %s logged in from %s", player.name, peer)
        telnet_reader = TelnetLineReader(reader)

        while world.running:
            result = await telnet_reader.readline()
            if result is None:
                break  # client disconnected (EOF)
            raw, had_iac = result
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                if had_iac:
                    continue  # negotiation-only line, not a pressed Enter
                await send_prompt(player)
                continue
            keep_playing = await handle_line(world, player, line)
            if not keep_playing:
                break
            await send_prompt(player)
    except (ConnectionError, OSError):
        logger.info("connection from %s dropped", peer)
    finally:
        if player is not None:
            await _disconnect(world, player, players_dir)
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass


async def _disconnect(world: World, player, players_dir: Path) -> None:
    persistence.save_player(players_dir, player)
    world.players.pop(player.name.lower(), None)
    room = world.room(player.location)
    if room is not None and player.name.lower() in room.characters:
        room.characters.remove(player.name.lower())
    await send_to_room(world, player.location, f"{player.name} has left the game.")
    logger.info("player %s disconnected", player.name)
