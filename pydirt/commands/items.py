"""get/take, drop, wear/apply, wield, inventory, open/close, remove, put, give, eat/drink.

C equivalent: handlers in src/parse.c (``getcom``, ``dropobj``, ``wearcom``,
``wieldcom``) and the underlying object-list bookkeeping in src/objsys.c
(``removecom``, ``putcom``, ``givecom``).
"""
from __future__ import annotations

from pydirt import finder
from pydirt.models import Item, Placement
from pydirt.sendsys import send_to_player, send_to_room
from pydirt.verbs import verb
from pydirt.world import World


def _carried_weight(world: World, player) -> int:
    return sum(world.items[i].weight for i in player.inventory if i in world.items)


@verb("get")
async def do_get(world: World, player, remainder: str) -> None:
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1:
        await send_to_player(player, "Get what?")
        return

    room = world.room(player.location)

    # "get <thing> from <container>" - C's getcom() searches containers too.
    container = None
    if args.prep in ("from", "out") and args.item2:
        container = finder.find_item_anywhere(world, player, player.location, args.item2)
        if container is None:
            await send_to_player(player, "You don't see that here.")
            return
        if "Container" not in container.flags:
            await send_to_player(player, f"The {container.name} isn't a container.")
            return
        if _is_openable(container) and not _is_open(container):
            await send_to_player(player, f"The {container.name} is closed.")
            return
        item = finder.find_item_in(world, container.contents, args.item1)
    else:
        item = finder.find_item_in_room(world, player.location, args.item1)
    if item is None:
        await send_to_player(player, "You don't see that here.")
        return
    if "NoGet" in item.flags:
        await send_to_player(player, "You can't take that.")
        return
    if _carried_weight(world, player) + item.weight > player.carry_capacity:
        await send_to_player(player, "Your hands are full.")
        return

    if container is not None:
        container.contents.remove(item.id)
    elif room is not None and item.id in room.items:
        room.items.remove(item.id)
    item.placement = Placement.CARRIED_BY
    item.location_ref = player.name
    player.inventory.append(item.id)
    player.last_target = item.id

    await send_to_player(player, f"You get the {item.name}.")
    await send_to_room(world, player.location, f"{player.name} picks up the {item.name}.", exclude=[player.name])


@verb("drop")
async def do_drop(world: World, player, remainder: str) -> None:
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1:
        await send_to_player(player, "Drop what?")
        return

    item = finder.find_item_in_inventory(world, player, args.item1)
    if item is None:
        await send_to_player(player, "You aren't carrying that.")
        return

    player.inventory.remove(item.id)
    if item.id in player.worn:
        player.worn.remove(item.id)
    if player.wielded == item.id:
        player.wielded = None
    room = world.room(player.location)
    if room is not None:
        room.items.append(item.id)
    item.placement = Placement.IN_ROOM
    item.location_ref = player.location

    await send_to_player(player, f"You drop the {item.name}.")
    await send_to_room(world, player.location, f"{player.name} drops the {item.name}.", exclude=[player.name])


@verb("apply")  # canonical for "wear" per data/verbs.src (wear=apply)
async def do_wear(world: World, player, remainder: str) -> None:
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1:
        await send_to_player(player, "Wear what?")
        return

    item = finder.find_item_in_inventory(world, player, args.item1)
    if item is None:
        await send_to_player(player, "You aren't carrying that.")
        return
    if "Wearable" not in item.flags:
        await send_to_player(player, "You can't wear that.")
        return
    if item.id in player.worn:
        await send_to_player(player, "You're already wearing that.")
        return

    player.worn.append(item.id)
    item.placement = Placement.WORN_BY
    await send_to_player(player, f"You wear the {item.name}.")
    await send_to_room(world, player.location, f"{player.name} wears the {item.name}.", exclude=[player.name])


@verb("wield")
async def do_wield(world: World, player, remainder: str) -> None:
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1:
        await send_to_player(player, "Wield what?")
        return

    item = finder.find_item_in_inventory(world, player, args.item1)
    if item is None:
        await send_to_player(player, "You aren't carrying that.")
        return
    if "Weapon" not in item.flags:
        await send_to_player(player, "That isn't a weapon.")
        return

    player.wielded = item.id
    item.placement = Placement.WIELDED_BY
    await send_to_player(player, f"You wield the {item.name}.")
    await send_to_room(world, player.location, f"{player.name} wields the {item.name}.", exclude=[player.name])


@verb("i")  # canonical for "inventory" per data/verbs.src (inventory=i)
async def do_inventory(world: World, player, remainder: str) -> None:
    if not player.inventory:
        await send_to_player(player, "You aren't carrying anything.")
        return
    lines = ["You are carrying:"]
    for item_id in player.inventory:
        item = world.items.get(item_id)
        if item is None:
            continue
        tag = " (worn)" if item_id in player.worn else " (wielded)" if player.wielded == item_id else ""
        lines.append(f"  {item.name}{tag}")
    await send_to_player(player, "\n".join(lines))


def _is_openable(item: Item) -> bool:
    return "Openable" in item.flags


def _is_open(item: Item) -> bool:
    # state 0 = closed, max_state (usually 1) = open - see _is_closed() in look.py
    return _is_openable(item) and item.state > 0


@verb("lift")  # canonical for "open" per data/verbs.src (open=lift)
async def do_open(world: World, player, remainder: str) -> None:
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1:
        await send_to_player(player, "Open what?")
        return

    item = finder.find_item_anywhere(world, player, player.location, args.item1)
    if item is None:
        await send_to_player(player, "You don't see that here.")
        return
    if not _is_openable(item):
        await send_to_player(player, "You can't open that.")
        return
    if _is_open(item):
        await send_to_player(player, "It is already open.")
        return

    item.state = item.max_state
    # linked doors open together - C equivalent: setdoor() following olinked()
    partner = world.items.get(item.linked_id) if item.linked_id else None
    if partner is not None:
        partner.state = partner.max_state
    await send_to_player(player, f"You open the {item.name}.")
    await send_to_room(world, player.location, f"{player.name} opens the {item.name}.", exclude=[player.name])


@verb("close")
async def do_close(world: World, player, remainder: str) -> None:
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1:
        await send_to_player(player, "Close what?")
        return

    item = finder.find_item_anywhere(world, player, player.location, args.item1)
    if item is None:
        await send_to_player(player, "You don't see that here.")
        return
    if not _is_openable(item):
        await send_to_player(player, "You can't close that.")
        return
    if not _is_open(item):
        await send_to_player(player, "It is already closed.")
        return

    item.state = 0
    partner = world.items.get(item.linked_id) if item.linked_id else None
    if partner is not None:
        partner.state = 0
    await send_to_player(player, f"You close the {item.name}.")
    await send_to_room(world, player.location, f"{player.name} closes the {item.name}.", exclude=[player.name])


@verb("remove")
async def do_remove(world: World, player, remainder: str) -> None:
    """C equivalent: removecom() in src/objsys.c - worn item back to carried."""
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1:
        await send_to_player(player, "Remove what?")
        return

    item = finder.find_item_in_inventory(world, player, args.item1)
    if item is None:
        await send_to_player(player, "You aren't carrying that.")
        return
    if item.id not in player.worn:
        await send_to_player(player, "You're not wearing it.")
        return

    player.worn.remove(item.id)
    item.placement = Placement.CARRIED_BY
    await send_to_player(player, "Ok.")
    await send_to_room(world, player.location, f"{player.name} removes the {item.name}.", exclude=[player.name])


@verb("put")
async def do_put(world: World, player, remainder: str) -> None:
    """C equivalent: putcom() in src/objsys.c - "put coin in bag"."""
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1 or not args.item2:
        await send_to_player(player, "Put what in what?")
        return

    item = finder.find_item_in_inventory(world, player, args.item1)
    if item is None:
        await send_to_player(player, "You aren't carrying that.")
        return

    container = finder.find_item_anywhere(world, player, player.location, args.item2)
    if container is None:
        await send_to_player(player, "You don't see that here.")
        return
    if "Container" not in container.flags:
        await send_to_player(player, f"The {container.name} isn't a container.")
        return
    if container.id == item.id:
        await send_to_player(player, "You can't put something inside itself.")
        return
    if _is_openable(container) and not _is_open(container):
        await send_to_player(player, f"The {container.name} is closed.")
        return

    player.inventory.remove(item.id)
    item.placement = Placement.IN_CONTAINER
    item.location_ref = container.id
    container.contents.append(item.id)
    player.last_target = container.id

    await send_to_player(player, f"You put the {item.name} in the {container.name}.")
    await send_to_room(
        world, player.location,
        f"{player.name} puts the {item.name} in the {container.name}.",
        exclude=[player.name],
    )


@verb("give")
async def do_give(world: World, player, remainder: str) -> None:
    """C equivalent: givecom() in src/objsys.c - "give coin to beggar"."""
    from pydirt.commands.look import character_name
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1 or not args.item2:
        await send_to_player(player, "Give what to whom?")
        return

    item = finder.find_item_in_inventory(world, player, args.item1)
    if item is None:
        await send_to_player(player, "You aren't carrying that.")
        return

    target_id = finder.find_character_in_room(world, player.location, args.item2)
    if target_id is None or target_id.lower() == player.name.lower():
        await send_to_player(player, "There's nobody like that here.")
        return

    player.inventory.remove(item.id)
    if item.id in player.worn:
        player.worn.remove(item.id)
    item.placement = Placement.CARRIED_BY
    item.location_ref = target_id

    target_player = world.players.get(target_id.lower())
    if target_player is not None:
        target_player.inventory.append(item.id)
    else:
        mobile = world.mobiles.get(target_id)
        if mobile is not None:
            mobile.inventory.append(item.id)
    player.last_target = target_id

    target_name = character_name(world, target_id)
    await send_to_player(player, f"You give the {item.name} to {target_name}.")
    if target_player is not None:
        await send_to_player(target_player, f"{player.name} gives you the {item.name}.")
    await send_to_room(
        world, player.location,
        f"{player.name} gives the {item.name} to {target_name}.",
        exclude=[player.name, target_id.lower()],
    )


@verb("drink")  # canonical for "eat" per data/verbs.src (eat=drink)
async def do_drink(world: World, player, remainder: str) -> None:
    from pydirt.parser import split_nouns

    args = split_nouns(player, remainder)
    if not args.item1:
        await send_to_player(player, "Eat/drink what?")
        return

    item = finder.find_item_anywhere(world, player, player.location, args.item1)
    if item is None:
        await send_to_player(player, "You don't see that here.")
        return
    if "Food" not in item.flags:
        await send_to_player(player, "You can't eat/drink that.")
        return

    # C equivalent: eating consumes the item and tops up strength (pstr()).
    player.inventory.remove(item.id)
    if item.id in player.worn:
        player.worn.remove(item.id)
    room = world.room(player.location)
    if room is not None and item.id in room.items:
        room.items.remove(item.id)
    item.placement = Placement.IN_ROOM
    item.location_ref = player.location
    player.strength = min(player.max_strength, player.strength + 10)

    await send_to_player(player, f"You eat the {item.name}. Yum.")
    await send_to_room(world, player.location, f"{player.name} eats the {item.name}.", exclude=[player.name])
