"""Minimal combat: attack a mobile, trade hits once per game tick, death.

C equivalent: a small slice of src/fight.c (hit-chance/damage/death), without
spells or mobile-specific special behaviors - see the "Excluded from MVP"
notes in the project plan. Rounds are resolved from the tick loop
(pydirt/tick.py), not instantly on the ``attack`` command, mirroring how the
C version only ever processes combat from ``on_timer``.
"""
from __future__ import annotations

import random

from pydirt import finder
from pydirt.models import Mobile, Placement, Player
from pydirt.sendsys import send_to_player, send_to_room
from pydirt.verbs import verb
from pydirt.world import World


def _hit_chance(attacker, defender) -> float:
    return max(0.1, min(0.9, 0.7 - defender.armor / 100))


def _damage_roll(attacker, world: World) -> int:
    weapon = world.items.get(attacker.wielded) if getattr(attacker, "wielded", None) else None
    base = weapon.damage if weapon else attacker.damage
    return random.randint(1, max(1, base + 1))


@verb("attack")  # covers "attack"/"hit"/"kill"/"smash" aliases from data/verbs.src
async def do_attack(world: World, player: Player, remainder: str) -> None:
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1:
        await send_to_player(player, "Attack whom?")
        return

    target_id = finder.find_character_in_room(world, player.location, args.item1)
    mobile = world.mobiles.get(target_id.lower()) if target_id else None
    if mobile is None:
        await send_to_player(player, "You don't see that here to fight.")
        return

    player.fighting = target_id
    mobile.fighting = player.name.lower()
    player.last_target = target_id
    await send_to_player(player, f"You attack {mobile.name}!")
    await send_to_room(world, player.location, f"{player.name} attacks {mobile.name}!", exclude=[player.name])


async def resolve_round(world: World, player: Player) -> None:
    """Resolves one round of the player's active fight; called once per tick."""
    if not player.fighting:
        return
    mobile = world.mobiles.get(player.fighting.lower())
    if mobile is None or mobile.location != player.location:
        player.fighting = None  # opponent gone (fled/despawned/different room)
        return

    await _strike(world, player, mobile)
    if mobile.strength > 0:
        await _strike(world, mobile, player)
    if mobile.strength <= 0:
        await _handle_death(world, mobile, winner=player)
    elif player.strength <= 0:
        await _handle_death(world, player, winner=mobile)


async def _strike(world: World, attacker, defender) -> None:
    attacker_name = attacker.name
    defender_name = defender.name
    if random.random() > _hit_chance(attacker, defender):
        if isinstance(attacker, Player):
            await send_to_player(attacker, f"You miss {defender_name}.")
        if isinstance(defender, Player):
            await send_to_player(defender, f"{attacker_name} misses you.")
        return

    damage = max(1, _damage_roll(attacker, world) - defender.armor // 2)
    defender.strength -= damage
    if isinstance(attacker, Player):
        await send_to_player(attacker, f"You hit {defender_name} for {damage} damage.")
    if isinstance(defender, Player):
        await send_to_player(defender, f"{attacker_name} hits you for {damage} damage.")


async def _handle_death(world: World, loser, winner) -> None:
    room = world.room(loser.location)
    if room is not None:
        for item_id in list(loser.inventory):
            loser.inventory.remove(item_id)
            item = world.items.get(item_id)
            if item is not None:
                item.placement = Placement.IN_ROOM
                item.location_ref = loser.location
                room.items.append(item_id)
        loser.worn.clear()
        loser.wielded = None

    loser.fighting = None
    winner.fighting = None

    if isinstance(loser, Mobile):
        mobile_id = _mobile_id(world, loser)
        if room is not None and mobile_id in room.characters:
            room.characters.remove(mobile_id)
        world.mobiles.pop(mobile_id, None)
        await send_to_room(world, loser.location, f"{loser.name} has been slain!")
        if isinstance(winner, Player):
            await send_to_player(winner, f"You have slain {loser.name}!")
    else:
        # Mortal death - C equivalent: the tail of wound_player() in
        # src/fight.c: the room sees "%s has died.", score is halved,
        # strength reset, then crapup("Oh dear... you seem to be slightly
        # dead.", CRAP_SAVE|CRAP_RETURN) saves the character and disconnects
        # them (connection.py's cleanup does the save + departure message
        # once the writer closes and readline hits EOF).
        await send_to_room(world, loser.location, f"{loser.name} has died.")
        loser.score //= 2
        loser.strength = 40
        await send_to_player(loser, "Oh dear... you seem to be slightly dead.")
        if loser.writer is not None:
            loser.writer.close()


def _mobile_id(world: World, mobile: Mobile) -> str:
    for mobile_id, candidate in world.mobiles.items():
        if candidate is mobile:
            return mobile_id
    return ""
