"""Loads data/ZONES/*.zone plus a few small config files into a World.

C equivalent: src/bootstrap.c (``bootstrap()``, ``boot_zones``,
``load_locations/mobiles/objects``). The C version reads pre-compiled binary
tables produced offline by src/mkdata.c; this module parses the ``.zone``
source text directly (see pydirt/zone_loader.py) so there is no separate
build step to run before playing.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

from pydirt import zone_loader
from pydirt.models import Item, Mobile, Placement, Room
from pydirt.world import World

logger = logging.getLogger("pydirt.bootstrap")


def _as_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _resolve_ref(raw: str, default_zone: str) -> tuple[str, str]:
    """Splits a ``name`` or ``name@zone`` reference into (zone, local_name)."""
    raw = raw.strip()
    if "@" in raw:
        name, _, zone = raw.partition("@")
        return zone.strip().lower(), name.strip().lower()
    return default_zone.lower(), raw.lower()


def _read_files_manifest(path: Path) -> dict[str, str]:
    """Parses data/ZONES/files: zone_name -> source .zone filename.

    Lines starting with ``../`` name mkdata's compiled *output* files and
    are not zone sources, so they are skipped (see pydirt/zone_loader.py docstring).
    """
    mapping: dict[str, str] = {}
    for raw_line in path.read_text(encoding="latin-1").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("../"):
            continue
        parts = line.split()
        zone_name = parts[0].lower()
        file_name = parts[1] if len(parts) > 1 else f"{zone_name}.zone"
        mapping[zone_name] = file_name
    return mapping


def _merge_zone(
    world: World,
    zone_name: str,
    parsed: zone_loader.ZoneSource,
    raw_items: dict[str, tuple[str, zone_loader.ItemTemplate]],
    raw_mobiles: dict[str, tuple[str, zone_loader.MobileTemplate]],
    raw_room_exits: dict[str, tuple[str, dict[str, str]]],
) -> None:
    for local_name, room_tmpl in parsed.rooms.items():
        room_id = f"{zone_name}:{local_name}"
        world.rooms[room_id] = Room(
            id=room_id,
            zone=zone_name,
            title=room_tmpl.title,
            description=room_tmpl.description,
            flags=room_tmpl.flags,
        )
        raw_room_exits[room_id] = (zone_name, room_tmpl.exits)

    for local_name, item_tmpl in parsed.items.items():
        item_id = f"{zone_name}:{local_name}"
        world.items[item_id] = Item(
            id=item_id,
            zone=zone_name,
            name=item_tmpl.pname or item_tmpl.name,
            alt_name=item_tmpl.alt_name,
            descriptions=list(item_tmpl.descriptions),
            examine=item_tmpl.examine,
            flags=item_tmpl.flags,
            size=item_tmpl.size,
            weight=item_tmpl.weight,
            value=item_tmpl.value,
            damage=item_tmpl.damage,
            armor=item_tmpl.armor,
            state=item_tmpl.state,
            max_state=item_tmpl.max_state,
        )
        raw_items[item_id] = (zone_name, item_tmpl)

    for local_name, mob_tmpl in parsed.mobiles.items():
        mobile_id = f"{zone_name}:{local_name}"
        world.mobiles[mobile_id] = Mobile(
            name=mob_tmpl.pname or mob_tmpl.name,
            zone=zone_name,
            strength=mob_tmpl.strength,
            max_strength=mob_tmpl.strength,
            damage=mob_tmpl.damage,
            armor=mob_tmpl.armor,
            aggression=mob_tmpl.aggression,
            speed=mob_tmpl.speed,
            description=mob_tmpl.description,
            examine=mob_tmpl.examine,
            flags=mob_tmpl.flags,
        )
        raw_mobiles[mobile_id] = (zone_name, mob_tmpl)


def _resolve_item_placements(
    world: World, raw_items: dict[str, tuple[str, zone_loader.ItemTemplate]]
) -> None:
    """Fills in Item.placement/location_ref/contents and Item.linked_id."""
    for item_id, (zone_name, tmpl) in raw_items.items():
        item = world.items[item_id]
        if tmpl.linked:
            link_zone, link_name = _resolve_ref(tmpl.linked, zone_name)
            link_id = f"{link_zone}:{link_name}"
            if link_id in world.items:
                item.linked_id = link_id
            else:
                logger.warning("item %s links to unknown item %s", item_id, link_id)

        loc = tmpl.location_raw.strip()
        if not loc:
            continue
        if ":" in loc:
            kind, _, target_raw = loc.partition(":")
        else:
            kind, target_raw = "IN_ROOM", loc
        kind = kind.strip().upper()
        target_zone, target_name = _resolve_ref(target_raw, zone_name)

        if kind == "IN_ROOM":
            room_id = f"{target_zone}:{target_name}"
            room = world.rooms.get(room_id)
            if room is None:
                logger.warning("item %s placed in unknown room %s", item_id, room_id)
                continue
            item.placement = Placement.IN_ROOM
            item.location_ref = room_id
            room.items.append(item_id)
        elif kind == "IN_CONTAINER":
            container_id = f"{target_zone}:{target_name}"
            container = world.items.get(container_id)
            if container is None:
                logger.warning("item %s placed in unknown container %s", item_id, container_id)
                continue
            item.placement = Placement.IN_CONTAINER
            item.location_ref = container_id
            container.contents.append(item_id)
        else:
            logger.warning(
                "item %s has unsupported placement kind %r, skipping placement",
                item_id, kind,
            )


def _resolve_exit_dest(world: World, zone_name: str, raw_dest: str) -> Optional[str]:
    raw_dest = raw_dest.strip()
    if raw_dest.startswith("^"):
        door_zone, door_name = _resolve_ref(raw_dest[1:], zone_name)
        door_id = f"{door_zone}:{door_name}"
        door_item = world.items.get(door_id)
        if door_item is None:
            logger.warning("exit references unknown door object %s", door_id)
            return None
        partner = world.items.get(door_item.linked_id) if door_item.linked_id else None
        if partner is None or partner.placement != Placement.IN_ROOM:
            logger.warning("door object %s has no resolvable destination room", door_id)
            return None
        return partner.location_ref
    if raw_dest.startswith("#"):
        logger.warning("special numeric exit %r is not supported, skipping", raw_dest)
        return None
    dest_zone, dest_name = _resolve_ref(raw_dest, zone_name)
    dest_room_id = f"{dest_zone}:{dest_name}"
    if dest_room_id not in world.rooms:
        logger.warning("exit destination room not found: %s", dest_room_id)
        return None
    return dest_room_id


def _resolve_room_exits(world: World, raw_room_exits: dict[str, tuple[str, dict[str, str]]]) -> None:
    direction_names = {"n": "north", "e": "east", "s": "south", "w": "west", "u": "up", "d": "down"}
    for room_id, (zone_name, exits) in raw_room_exits.items():
        room = world.rooms[room_id]
        for direction, raw_dest in exits.items():
            full_direction = direction_names.get(direction)
            if full_direction is None:
                logger.warning("room %s has unknown exit direction %r", room_id, direction)
                continue
            room.exits[full_direction] = _resolve_exit_dest(world, zone_name, raw_dest)


def _place_mobiles(world: World, raw_mobiles: dict[str, tuple[str, zone_loader.MobileTemplate]]) -> None:
    for mobile_id, (zone_name, tmpl) in raw_mobiles.items():
        mobile = world.mobiles[mobile_id]
        loc = tmpl.location_raw.strip()
        if not loc:
            logger.warning("mobile %s has no Location, leaving unplaced", mobile_id)
            continue
        room_zone, room_name = _resolve_ref(loc, zone_name)
        room_id = f"{room_zone}:{room_name}"
        room = world.rooms.get(room_id)
        if room is None:
            logger.warning("mobile %s has unknown home room %s", mobile_id, room_id)
            continue
        mobile.location = room_id
        mobile.home = room_id
        room.characters.append(mobile_id)


def _load_levels(world: World, path: Path) -> None:
    if not path.exists():
        return
    lines = [line.strip() for line in path.read_text(encoding="latin-1").splitlines() if line.strip()]
    if not lines:
        return
    count = _as_int(lines[0])
    world.levels = [_as_int(value) for value in lines[1:1 + count]]


def _load_banned_chars(world: World, path: Path) -> None:
    if not path.exists():
        return
    patterns = []
    for line in path.read_text(encoding="latin-1").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    world.banned_patterns = patterns


def load_world(data_dir: Path) -> World:
    """Parses every zone in data/ZONES/files and returns a populated World."""
    world = World()
    zones_dir = data_dir / "ZONES"
    file_map = _read_files_manifest(zones_dir / "files")

    by_file: dict[str, list[str]] = defaultdict(list)
    for zone_name, file_name in file_map.items():
        by_file[file_name].append(zone_name)

    raw_items: dict[str, tuple[str, zone_loader.ItemTemplate]] = {}
    raw_mobiles: dict[str, tuple[str, zone_loader.MobileTemplate]] = {}
    raw_room_exits: dict[str, tuple[str, dict[str, str]]] = {}

    for file_name, zone_names in by_file.items():
        path = zones_dir / file_name
        if not path.exists():
            logger.warning("zone source file missing: %s (zones: %s)", file_name, zone_names)
            continue
        file_text = path.read_text(encoding="latin-1")
        sections = zone_loader.split_zone_sections(file_text)
        for zone_name in zone_names:
            section_text = sections.get(zone_name, sections.get(""))
            if section_text is None:
                logger.warning("zone %r not found as a %%zone: section in %s", zone_name, file_name)
                continue
            try:
                parsed = zone_loader.parse_zone_text(section_text)
            except Exception:  # best-effort: one bad zone shouldn't stop the boot
                logger.exception("failed to parse zone %r from %s, skipping", zone_name, file_name)
                continue
            _merge_zone(world, zone_name, parsed, raw_items, raw_mobiles, raw_room_exits)

    _resolve_item_placements(world, raw_items)
    _resolve_room_exits(world, raw_room_exits)
    _place_mobiles(world, raw_mobiles)

    # C equivalent: mud.c's setploc() picks LOC_START_TEMPLE/LOC_START_CHURCH
    # (the start zone's temple and village church) when a player has no home.
    world.start_room = next(
        (room_id for room_id in ("start:church", "start:temple") if room_id in world.rooms),
        next(iter(world.rooms), None),
    )

    _load_levels(world, data_dir / "levels")
    _load_banned_chars(world, data_dir / "banned_chars")

    logger.info(
        "world loaded: %d rooms, %d items, %d mobiles across %d zones",
        len(world.rooms), len(world.items), len(world.mobiles), len(by_file),
    )
    return world
