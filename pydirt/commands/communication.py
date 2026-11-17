"""say, tell/ask, who, shout.

C equivalent: src/commands.c (``saycom``, ``tellcom``, ``shoutcom``) and the
connected-player listing in ``whocom``/src/mobile.c.
"""
from __future__ import annotations

from pydirt.sendsys import send_to_all, send_to_player, send_to_room
from pydirt.verbs import verb
from pydirt.world import World


@verb("say")
async def do_say(world: World, player, remainder: str) -> None:
    message = remainder.strip()
    if not message:
        await send_to_player(player, "Say what?")
        return
    await send_to_player(player, f'You say "{message}"')
    await send_to_room(world, player.location, f'{player.name} says "{message}"', exclude=[player.name])


@verb("tell")  # covers both "tell" and "ask", which are mutual aliases in data/verbs.src
async def do_tell(world: World, player, remainder: str) -> None:
    target_name, _, message = remainder.strip().partition(" ")
    message = message.strip()
    if not target_name or not message:
        await send_to_player(player, "Tell whom what?")
        return

    target = world.players.get(target_name.lower())
    if target is None:
        await send_to_player(player, "There's no such player connected.")
        return
    if target.name.lower() == player.name.lower():
        await send_to_player(player, "You tell yourself... and you agree.")
        return

    await send_to_player(player, f'You tell {target.name} "{message}"')
    await send_to_player(target, f'{player.name} tells you "{message}"')
    player.last_target = target.name
    target.last_target = player.name


@verb("who")
async def do_who(world: World, player, remainder: str) -> None:
    lines = ["Players online:"]
    for other in sorted(world.players.values(), key=lambda p: p.name.lower()):
        lines.append(f"  {other.name} (level {other.level})")
    await send_to_player(player, "\n".join(lines))


@verb("shout")
async def do_shout(world: World, player, remainder: str) -> None:
    """C equivalent: shoutcom() in src/commands.c - everyone online hears it."""
    message = remainder.strip()
    if not message:
        await send_to_player(player, "Shout what?")
        return
    await send_to_player(player, f'You shout "{message}"')
    await send_to_all(world, f'{player.name} shouts "{message}"', exclude=[player.name])
