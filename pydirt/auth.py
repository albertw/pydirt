"""Player login: name entry, new-character creation, or password check.

C equivalent: src/mud.c's chain of pushable input handlers (new_player(),
the name/password prompts, talker()). Here it is a single straight-line
async function - asyncio lets us just ``await`` the next line of input
instead of installing a callback for "whatever comes next".
"""
from __future__ import annotations

import fnmatch
import logging
from pathlib import Path
from typing import Optional

from pydirt import persistence
from pydirt.models import Player
from pydirt.telnet import TelnetLineReader
from pydirt.world import World

logger = logging.getLogger("pydirt.auth")

_MAX_PASSWORD_ATTEMPTS = 3
_MIN_NAME_LEN = 3
_MAX_NAME_LEN = 12

# Telnet IAC WILL/WON'T ECHO - asks a real telnet client to stop echoing the
# password back to the screen. C equivalent: the IAC WILL ECHO sent around
# password prompts in src/mud.c.
_IAC_WILL_ECHO = bytes([255, 251, 1])
_IAC_WONT_ECHO = bytes([255, 252, 1])


def is_banned_name(world: World, name: str) -> bool:
    """C equivalent: infile() checking a new name against data/banned_chars."""
    lname = name.lower()
    for raw_pattern in world.banned_patterns:
        pattern = raw_pattern.strip()
        if pattern.startswith("!"):
            if fnmatch.fnmatch(lname, pattern[1:].strip().lower()):
                return False
        elif fnmatch.fnmatch(lname, pattern.lower()):
            return True
    return False


async def login(reader, writer, world: World, players_dir: Path) -> Optional[Player]:
    """Runs the login state machine; returns a ready-to-play Player, or None
    if the connection should be dropped."""
    telnet_reader = TelnetLineReader(reader)

    async def send(text: str) -> None:
        writer.write((text + "\r\n").encode("utf-8", errors="replace"))
        await writer.drain()

    async def read_line() -> Optional[str]:
        while True:
            raw = await telnet_reader.readline()
            if raw is None:
                return None
            line, had_iac = raw
            line = line.decode("utf-8", errors="replace").strip()
            # A line that is empty only because IAC negotiation was stripped
            # is the client's echo reply (IAC DO/DONT ECHO + CRLF) - skip it
            # rather than let it consume a name/password attempt.
            if not line and had_iac:
                continue
            return line

    async def read_password() -> Optional[str]:
        writer.write(_IAC_WILL_ECHO)
        try:
            return await read_line()
        finally:
            writer.write(_IAC_WONT_ECHO)
            await writer.drain()

    await send("Welcome to DIRT (Python port).")

    while True:
        await send("By what name do you wish to be known? ")
        name = await read_line()
        if name is None:
            return None
        name = name.strip()
        if not name.isalpha() or not (_MIN_NAME_LEN <= len(name) <= _MAX_NAME_LEN):
            await send("Names must be 3-12 letters, nothing else.")
            continue
        if is_banned_name(world, name):
            await send("That name is not allowed.")
            continue
        if name.lower() in world.players:
            await send("That character is already logged in.")
            continue
        break

    data = persistence.load_player_data(players_dir, name)
    if data is None:
        player = await _create_character(send, read_line, read_password, world, name)
    else:
        player = await _authenticate(send, read_password, world, name, data)

    if player is not None:
        player.writer = writer
    return player


async def _create_character(send, read_line, read_password, world: World, name: str) -> Optional[Player]:
    await send(f"'{name}' is a new name - create this character? (yes/no)")
    answer = await read_line()
    if answer is None or answer.strip().lower() not in ("y", "yes"):
        await send("Goodbye.")
        return None

    while True:
        await send("Choose a password: ")
        password = await read_password()
        if password is None:
            return None
        if len(password) < 4:
            await send("Password must be at least 4 characters.")
            continue
        break

    password_hash, password_salt = persistence.hash_password(password)
    player = Player(name=name, home=world.start_room, location=world.start_room)
    player.password_hash = password_hash
    player.password_salt = password_salt
    await send(f"Welcome, {name}! Type 'help' for a list of basic commands.")
    return player


async def _authenticate(send, read_password, world: World, name: str, data: dict) -> Optional[Player]:
    for _attempt in range(_MAX_PASSWORD_ATTEMPTS):
        await send("Password: ")
        password = await read_password()
        if password is None:
            return None
        if persistence.verify_password(password, data.get("password_hash", ""), data.get("password_salt", "")):
            player = Player(name=name)
            persistence.apply_saved_data(player, data)
            player.location = player.home or world.start_room
            await send(f"Welcome back, {name}!")
            return player
        await send("Incorrect password.")
    await send("Too many failed attempts. Goodbye.")
    return None
