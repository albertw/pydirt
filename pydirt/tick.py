"""The 2-second game tick: advances the clock, wanders mobiles, resolves combat.

C equivalent: src/timing.c's ``on_timer()``, invoked every ``TIMER_INTERRUPT``
(2s) via SIGALRM from the C main loop (src/main.c). Here it is just an
asyncio task that sleeps for 2 seconds between iterations - since asyncio is
single-threaded and cooperative, nothing else runs while a tick is in
progress, matching the C original's single-process behavior.
"""
from __future__ import annotations

import asyncio
import logging
import random

from pydirt.commands.combat import resolve_round
from pydirt.sendsys import send_to_room
from pydirt.world import World

logger = logging.getLogger("pydirt.tick")

TICK_SECONDS = 2
_WANDER_CHANCE = 0.05  # per-mobile, per-tick probability of moving (C: probabilistic too)


async def tick_loop(world: World) -> None:
    while world.running:
        await asyncio.sleep(TICK_SECONDS)
        if not world.running:
            break
        world.clock += TICK_SECONDS
        try:
            await _wander_mobiles(world)
            await _resolve_fights(world)
        except Exception:  # a bug in one tick shouldn't take the server down
            logger.exception("error during tick, continuing")


async def _wander_mobiles(world: World) -> None:
    for mobile_id, mobile in list(world.mobiles.items()):
        if mobile.fighting:
            continue  # don't wander off mid-fight
        if random.random() > _WANDER_CHANCE:
            continue
        room = world.room(mobile.location)
        if room is None:
            continue
        exits = [(direction, dest) for direction, dest in room.exits.items() if dest]
        if not exits:
            continue
        direction, dest_id = random.choice(exits)
        dest_room = world.room(dest_id)
        if dest_room is None or mobile_id not in room.characters:
            continue
        room.characters.remove(mobile_id)
        dest_room.characters.append(mobile_id)
        mobile.location = dest_id
        await send_to_room(world, room.id, f"{mobile.name} leaves {direction}.")
        await send_to_room(world, dest_id, f"{mobile.name} arrives.")


async def _resolve_fights(world: World) -> None:
    for player in list(world.players.values()):
        if player.fighting:
            await resolve_round(world, player)
