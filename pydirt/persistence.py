"""Player persistence: one JSON file per character, hashed passwords.

C equivalent: src/uaf.c (PERSONA records packed into the binary ``uaf_rand``
file - a raw, compiler/ABI-dependent format). Here each player is a
human-readable JSON file under data/players/, and passwords are salted +
PBKDF2-hashed rather than ever stored or compared in plaintext (OWASP A02/A07).

Matching the C PERSONA's scope: only identity/stats/flags persist, not the
live room/inventory - a login always starts fresh at the character's home
room, just like uaf.c's player2pers()/pers2player() never touch ``ploc`` or
object sets.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Optional

from pydirt.models import Player

_PBKDF2_ITERATIONS = 200_000


def _player_path(players_dir: Path, name: str) -> Path:
    return players_dir / f"{name.lower()}.json"


def hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    """Returns (hash_hex, salt_hex); generates a new random salt if none given."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    if not password_hash or not password_salt:
        return False
    computed, _ = hash_password(password, bytes.fromhex(password_salt))
    return hmac.compare_digest(computed, password_hash)


def load_player_data(players_dir: Path, name: str) -> Optional[dict]:
    path = _player_path(players_dir, name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def apply_saved_data(player: Player, data: dict) -> None:
    player.password_hash = data.get("password_hash", "")
    player.password_salt = data.get("password_salt", "")
    player.home = data.get("home")
    player.strength = data.get("strength", player.strength)
    player.max_strength = data.get("max_strength", player.max_strength)
    player.damage = data.get("damage", player.damage)
    player.armor = data.get("armor", player.armor)
    player.level = data.get("level", player.level)
    player.score = data.get("score", player.score)
    player.carry_capacity = data.get("carry_capacity", player.carry_capacity)
    player.description = data.get("description", player.description)
    player.flags = set(data.get("flags", []))


def save_player(players_dir: Path, player: Player) -> None:
    players_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "name": player.name,
        "password_hash": player.password_hash,
        "password_salt": player.password_salt,
        "home": player.home,
        "strength": player.strength,
        "max_strength": player.max_strength,
        "damage": player.damage,
        "armor": player.armor,
        "level": player.level,
        "score": player.score,
        "carry_capacity": player.carry_capacity,
        "description": player.description,
        "flags": sorted(player.flags),
    }
    _player_path(players_dir, player.name).write_text(json.dumps(data, indent=2), encoding="utf-8")
