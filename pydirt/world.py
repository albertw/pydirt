"""Process-wide world state.

C equivalent: include/global.h + src/global.c, which declare the C-global
arrays `room_data`, `objects`, `ublock`, `players`, and counters. Instead of
C globals mutated from anywhere, we bundle everything into one World object
that is passed explicitly to functions that need it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydirt.models import Item, Mobile, Player, Room


@dataclass
class World:
    rooms: dict[str, Room] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    mobiles: dict[str, Mobile] = field(default_factory=dict)
    players: dict[str, Player] = field(default_factory=dict)  # keyed by lowercase name
    levels: list[int] = field(default_factory=list)  # data/levels thresholds
    banned_patterns: list[str] = field(default_factory=list)  # data/banned_chars
    start_room: Optional[str] = None  # where new characters begin
    clock: int = 0  # advances by 2 (seconds) per tick, like timing.c's game_time
    running: bool = True

    def character(self, name: str) -> Optional[Player | Mobile]:
        """Look up any character (player or mobile) by name, player slots first."""
        player = self.players.get(name.lower())
        if player is not None:
            return player
        return self.mobiles.get(name.lower())

    def room(self, room_id: Optional[str]) -> Optional[Room]:
        if room_id is None:
            return None
        return self.rooms.get(room_id)
