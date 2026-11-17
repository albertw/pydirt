"""Shared lookup helpers: resolving a typed word to an Item or Character.

C equivalent: scattered object/name-matching helpers in src/objsys.c and the
noun-resolution half of src/parse.c's parse_1()/parse_2().
"""
from __future__ import annotations

from typing import Optional

from pydirt.models import Item
from pydirt.world import World


def _matches(item: Item, name: str) -> bool:
    name = name.lower()
    local_name = item.id.split(":")[-1]
    return name in (item.name.lower(), item.alt_name.lower(), local_name)


def find_item_in(world: World, container_ids: list[str], name: str) -> Optional[Item]:
    for item_id in container_ids:
        item = world.items.get(item_id)
        if item and _matches(item, name):
            return item
    return None


def find_item_in_room(world: World, room_id: Optional[str], name: str) -> Optional[Item]:
    room = world.room(room_id)
    if room is None:
        return None
    return find_item_in(world, room.items, name)


def find_item_in_inventory(world: World, character, name: str) -> Optional[Item]:
    return find_item_in(world, character.inventory, name)


def find_item_anywhere(world: World, character, room_id: Optional[str], name: str) -> Optional[Item]:
    """Checks inventory first, then the room - matches getcom()'s lookup order."""
    item = find_item_in_inventory(world, character, name)
    if item is not None:
        return item
    return find_item_in_room(world, room_id, name)


def find_character_in_room(world: World, room_id: Optional[str], name: str) -> Optional[str]:
    """Returns the occupant id (player name or mobile id) matching ``name``."""
    room = world.room(room_id)
    if room is None:
        return None
    name = name.lower()
    for char_id in room.characters:
        player = world.players.get(char_id.lower())
        if player and player.name.lower() == name:
            return char_id
        mobile = world.mobiles.get(char_id.lower())
        if mobile and (mobile.name.lower() == name or char_id.split(":")[-1] == name):
            return char_id
    return None
