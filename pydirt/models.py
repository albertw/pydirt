"""Core world data structures.

C equivalent: src/mudtypes.h (UBLOCK_REC, Location, Object structs) and
include/cflags.h (placement constants). The C version uses fixed arrays and
integer indexes (negative room numbers, int_set bitmaps); here we use plain
Python objects linked by string ids, which is slower but far easier to read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


DIRECTIONS = ("north", "east", "south", "west", "up", "down")


class Placement(Enum):
    """Mirrors include/cflags.h - where an Item currently is."""

    IN_ROOM = auto()
    IN_CONTAINER = auto()
    CARRIED_BY = auto()
    WORN_BY = auto()
    WIELDED_BY = auto()


@dataclass
class Room:
    """C equivalent: struct Location in src/mudtypes.h."""

    id: str
    zone: str
    title: str = ""
    description: str = ""
    flags: set[str] = field(default_factory=set)
    # direction -> Room id (resolved by bootstrap's second pass). None = no exit.
    exits: dict[str, Optional[str]] = field(default_factory=lambda: {d: None for d in DIRECTIONS})
    items: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)


@dataclass
class Item:
    """C equivalent: struct Object in src/mudtypes.h."""

    id: str
    zone: str
    name: str = ""
    alt_name: str = ""
    descriptions: list[str] = field(default_factory=lambda: [""] * 4)
    examine: str = ""
    flags: set[str] = field(default_factory=set)
    size: int = 1
    weight: int = 1
    value: int = 0
    damage: int = 0
    armor: int = 0
    state: int = 0
    max_state: int = 0
    linked_id: Optional[str] = None
    # placement: where the item currently lives, and the id of that holder
    # (a Room id, another Item id, or a Character name).
    placement: Placement = Placement.IN_ROOM
    location_ref: Optional[str] = None
    contents: list[str] = field(default_factory=list)


@dataclass
class Character:
    """C equivalent: shared fields of UBLOCK_REC (used by both players and mobiles)."""

    name: str
    zone: str = "world"
    location: Optional[str] = None  # Room id
    home: Optional[str] = None  # Room id to reset/respawn to
    strength: int = 100  # pstr: doubles as hit points, see src/fight.c
    max_strength: int = 100
    damage: int = 0  # pdam: unarmed/base damage
    armor: int = 0
    aggression: int = 0
    speed: int = 0
    level: int = 1
    score: int = 0
    carry_capacity: int = 20
    description: str = ""
    examine: str = ""
    flags: set[str] = field(default_factory=set)
    inventory: list[str] = field(default_factory=list)  # Item ids carried
    worn: list[str] = field(default_factory=list)  # Item ids worn
    wielded: Optional[str] = None  # Item id wielded as a weapon
    fighting: Optional[str] = None  # name of opponent, if any


@dataclass
class Mobile(Character):
    """C equivalent: UBLOCK_REC slots at/above max_players (an NPC)."""

    is_player: bool = False


@dataclass
class Player(Character):
    """C equivalent: UBLOCK_REC + PLAYER_REC for a human-controlled character."""

    is_player: bool = True
    password_hash: str = ""
    password_salt: str = ""
    writer: object = None  # asyncio.StreamWriter, set once connected
    last_target: Optional[str] = None  # pronoun resolution ("it"/"him"/"her")
