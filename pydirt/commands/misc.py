"""score, help, version, quit.

C equivalent: src/commands.c (``scorecom``, ``versioncom``) and
``quit_game`` in src/parse.c.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydirt.sendsys import send_to_player
from pydirt.verbs import verb
from pydirt.world import World


@verb("score")
async def do_score(world: World, player, remainder: str) -> None:
    lines = [
        f"Name:     {player.name}",
        f"Level:    {player.level}",
        f"Score:    {player.score}",
        f"Strength: {player.strength}/{player.max_strength}",
        f"Armor:    {player.armor}",
    ]
    await send_to_player(player, "\n".join(lines))


@verb("help")
async def do_help(world: World, player, remainder: str) -> None:
    lines = [
        "Basic commands:",
        "  look [<thing>]          examine [<thing>]     exits",
        "  north/south/east/west/up/down   (n/s/e/w/u/d also work)",
        "  get <thing>  drop <thing>  put <thing> in <container>",
        "  apply/wear <thing>  remove <thing>  wield <weapon>",
        "  give <thing> to <someone>   eat/drink <thing>",
        "  open/lift <thing>  close <thing>",
        "  say <text>  tell <name> <text>  shout <text>",
        "  inventory (i)  score  who  quit",
    ]
    await send_to_player(player, "\n".join(lines))


@verb("version")
async def do_version(world: World, player, remainder: str) -> None:
    # Build stamp = newest source mtime under pydirt/, so "ver" tells you
    # whether a running server process is older than the current tree.
    pkg_dir = Path(__file__).resolve().parent.parent
    newest = max(p.stat().st_mtime for p in pkg_dir.rglob("*.py"))
    stamp = datetime.fromtimestamp(newest, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    await send_to_player(player, f"pydirt - Python port of DIRT 3.1 (source build {stamp})")


@verb("quit")
async def do_quit(world: World, player, remainder: str) -> bool:
    # connection.py's disconnect cleanup sends the room departure message
    # and saves the character, so this handler just needs to end the session.
    await send_to_player(player, "Goodbye!")
    return False
