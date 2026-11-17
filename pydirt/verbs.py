"""Verb vocabulary: data/verbs.src -> a prefix-matchable command table.

C equivalent: data/verbs.src is compiled by src/generate.c into numeric verb
IDs (verbs.h). Here it is parsed directly into a plain dict at startup, and
command handlers register themselves against one or more verb words with
the ``@verb(...)`` decorator instead of a numeric switch in parse.c/doaction.
"""
from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Optional

Handler = Callable[..., Awaitable[Optional[bool]]]

#: canonical/alias word -> handler, filled in by pydirt.commands modules.
HANDLERS: dict[str, Handler] = {}

#: every known vocabulary word -> the word it resolves to (itself for a
#: plain verb, or its alias target otherwise), in data/verbs.src file order.
VERB_TABLE: dict[str, str] = {}

#: vocabulary words in file order, so prefix-matching ("n" -> "north")
#: picks the same winner the original game would (first match wins).
_VERB_ORDER: list[str] = []


def load_verb_table(path: Path) -> None:
    """Parses ``data/verbs.src``: one verb per line, or ``alias=canonical``."""
    VERB_TABLE.clear()
    _VERB_ORDER.clear()
    for raw_line in path.read_text(encoding="latin-1").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            alias, _, target = line.partition("=")
            alias, target = alias.strip().lower(), target.strip().lower()
        else:
            alias = target = line.strip().lower()
        # A target may be referenced before it's ever declared plain (a
        # couple of mutual aliases in the real data, e.g. ask=tell /
        # tell=ask) - just declare it canonical the first time we see it.
        canonical_target = VERB_TABLE.get(target, target)
        VERB_TABLE.setdefault(canonical_target, canonical_target)
        VERB_TABLE[alias] = canonical_target
        _VERB_ORDER.append(alias)


def verb(*names: str) -> Callable[[Handler], Handler]:
    """Decorator: registers an async handler under one or more verb words."""

    def decorator(func: Handler) -> Handler:
        for name in names:
            HANDLERS[name.lower()] = func
        return func

    return decorator


def resolve_word(word: str) -> Optional[str]:
    """Case-insensitive PREFIX match against the vocabulary, mirroring
    chkverb()/Match() in parse.c: the first (file-order) match wins, so
    abbreviations behave the same way players already expect."""
    word = word.lower()
    if word in VERB_TABLE:
        return word
    for candidate in _VERB_ORDER:
        if candidate.startswith(word):
            return candidate
    return None


def find_handler(word: str) -> Optional[Handler]:
    """Resolves a typed word to a handler, trying the matched vocabulary
    word itself and then its alias target."""
    matched = resolve_word(word)
    if matched is None:
        return None
    if matched in HANDLERS:
        return HANDLERS[matched]
    canonical = VERB_TABLE.get(matched)
    return HANDLERS.get(canonical) if canonical else None
