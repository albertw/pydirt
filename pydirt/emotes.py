"""Simplified social/emote commands, data-driven from data/actions.

C equivalent: src/actions.c (``boot_extern``/``fextern``) and the data file
data/actions itself. The real format supports gender-conditional branching
(``%<...%:...%>``, ``%[...%/...%]``); per the project plan this port keeps
only the plain substitution codes (%a/%t/%~/%^) and resolves any gendered
branch to its first option, so emotes read a little generic but never crash
on unexpected pronouns.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydirt import finder
from pydirt.commands.look import character_name
from pydirt.sendsys import send_to_player, send_to_room
from pydirt.world import World

logger = logging.getLogger("pydirt.emotes")

_GENDER_TARGET_RE = re.compile(r"%<(.*?)%:(.*?)%>")
_GENDER_ACTOR_RE = re.compile(r"%\[(.*?)%/(.*?)%\]")


@dataclass
class EmoteRecord:
    verb: str
    flags: str
    messages: dict[str, str] = field(default_factory=dict)


EMOTES: dict[str, EmoteRecord] = {}


def load_emotes(path: Path) -> None:
    EMOTES.clear()
    verb: Optional[str] = None
    flags = ""
    messages: dict[str, str] = {}

    def flush() -> None:
        if verb:
            EMOTES[verb] = EmoteRecord(verb=verb, flags=flags, messages=dict(messages))

    for raw_line in path.read_text(encoding="latin-1").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(":"):
            flush()
            parts = line[1:].split()
            verb = parts[0].lower() if parts else None
            flags = parts[1] if len(parts) > 1 else ""
            messages = {}
            continue
        if verb and ":" in line:
            msg_type, _, template = line.partition(":")
            messages[msg_type.strip().lower()] = template.strip()
    flush()
    logger.info("loaded %d emote verbs from %s", len(EMOTES), path)


def _render(template: str, actor: str, target: str = "") -> str:
    text = template
    text = _GENDER_TARGET_RE.sub(r"\1", text)
    text = _GENDER_ACTOR_RE.sub(r"\1", text)
    text = text.replace("%a", actor).replace("%t", target)
    text = text.replace("%~", "them").replace("%^", "their")
    return text


def _find_record(word: str) -> Optional[EmoteRecord]:
    word = word.lower()
    if word in EMOTES:
        return EMOTES[word]
    candidates = [name for name in EMOTES if name.startswith(word)]
    return EMOTES[candidates[0]] if len(candidates) == 1 else None


async def try_dispatch(world: World, player, verb_word: str, remainder: str) -> bool:
    """Returns True if `verb_word` matched a known emote (handled or not)."""
    record = _find_record(verb_word)
    if record is None:
        return False

    target_name = remainder.strip()
    if target_name and "s" in record.flags:
        target_id = finder.find_character_in_room(world, player.location, target_name)
        if target_id is None:
            await send_to_player(player, "They aren't here.")
            return True
        target_display = character_name(world, target_id)

        await send_to_player(player, _render(record.messages.get("sender", ""), player.name, target_display))
        others_tpl = record.messages.get("others")
        if others_tpl:
            await send_to_room(
                world, player.location, _render(others_tpl, player.name, target_display),
                exclude=[player.name, target_display],
            )
        target_player = world.players.get(target_id.lower())
        if target_player is not None:
            await send_to_player(target_player, _render(record.messages.get("target", ""), player.name, target_display))
        return True

    if "a" not in record.flags:
        await send_to_player(player, "Do that to whom?")
        return True

    await send_to_player(player, _render(record.messages.get("me", ""), player.name))
    all_tpl = record.messages.get("all")
    if all_tpl:
        await send_to_room(world, player.location, _render(all_tpl, player.name), exclude=[player.name])
    return True
