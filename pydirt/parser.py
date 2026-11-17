"""Turns one line of player input into a dispatched command.

C equivalent: src/parse.c (``gamecom``/``xgamecom``, ``brkword``, ``chkverb``,
``doaction``, ``parse_2``). One simplification from the C version: here the
free-text tail of chat commands (say/tell/emote) is passed through untouched
instead of being lowercased and stripped of filler words by brkword - the
original's blanket word-breaking of the whole line (including spoken text)
reads as an accident of a single-pass tokenizer rather than something worth
reproducing; splitting into "structured" noun parsing (see split_nouns)
vs. "free text" commands keeps chat readable.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydirt import verbs
from pydirt.models import Player
from pydirt.sendsys import send_to_player
from pydirt.world import World

_FILLER_WORDS = {"the", "a", "an", "of", "with"}  # "with" is dropped in the C original too
_PREPOSITIONS = {"at", "on", "to", "in", "into", "from", "out"}
_PRONOUNS = {"it", "him", "her", "them"}


@dataclass
class ParsedArgs:
    raw: str  # the whole line after the verb word, untouched
    item1: str
    prep: str
    item2: str


def split_nouns(player: Player, remainder: str) -> ParsedArgs:
    """C equivalent: parse_2()/parse_1(). Lowercases, drops filler words,
    splits on the first recognized preposition, and resolves pronouns
    against the player's last-referenced target."""
    raw = remainder.strip()
    words = [w for w in raw.lower().split() if w not in _FILLER_WORDS]

    prep = ""
    item1_words: list[str] = []
    item2_words: list[str] = []
    target_list = item1_words
    for word in words:
        if not prep and word in _PREPOSITIONS:
            prep = word
            target_list = item2_words
            continue
        target_list.append(word)

    item1 = " ".join(item1_words)
    item2 = " ".join(item2_words)
    # "look at puff" / "examine puff": with a preposition but nothing before
    # it, the single target lands in item2 - promote it to item1 so handlers
    # that expect one object ("look", "examine") see it. Two-object commands
    # ("put coin in bag") keep both slots as parsed.
    if prep and not item1 and item2:
        item1, item2 = item2, ""
    if item1 in _PRONOUNS and player.last_target:
        item1 = player.last_target
    if item2 in _PRONOUNS and player.last_target:
        item2 = player.last_target
    return ParsedArgs(raw=raw, item1=item1, prep=prep, item2=item2)


def _expand_shorthand(line: str) -> str:
    """C equivalent: the leading-quote/colon shorthand in xgamecom()."""
    if line.startswith(("'", '"')):
        return "say " + line[1:]
    if line.startswith((":", ";")):
        return "emote " + line[1:]
    return line


async def handle_line(world: World, player: Player, line: str) -> bool:
    """Returns False if the connection should close (quit), True otherwise."""
    line = _expand_shorthand(line.strip())
    if not line:
        return True

    verb_word, _, remainder = line.partition(" ")
    handler = verbs.find_handler(verb_word)
    if handler is None:
        from pydirt import emotes  # imported lazily to avoid a circular import

        if await emotes.try_dispatch(world, player, verb_word, remainder):
            return True
        await send_to_player(player, "Huh?!?")
        return True

    result = await handler(world, player, remainder)
    return result is not False
