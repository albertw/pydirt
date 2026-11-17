"""Parser for the human-authored ``.zone`` world-source files.

C equivalent: src/mkdata.c (the offline compiler that turns ``.zone`` files
into the binary tables src/bootstrap.c loads at runtime). DIRT never parses
``.zone`` text at server startup - mkdata does it once, ahead of time. Here
we parse it directly at startup instead, trading a bit of start-up time for
one less moving part / build step, which is friendlier for learning the flow.

Only the constructs actually used by the files under data/ZONES are
supported (see Decisions in the project plan): quoted/bracketed field values,
room headers with direction exits ending in ``;``, ``lflags{...}``, and a
``title^ ... ^`` description block. Anything unexpected is logged and
skipped rather than raising, so a single malformed record doesn't take the
whole server down.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("pydirt.zone_loader")

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\[[0-9]*\])?")
_BARE_TOKEN_RE = re.compile(r"\S+")
_LFLAGS_RE = re.compile(r"[Ll][Ff][Ll][Aa][Gg](?:[Ss])?")  # 'lflag' abbreviation appears in a couple of files
_SECTION_RE = re.compile(r"^%(mobiles|objects|locations)\s*$", re.IGNORECASE)
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


# --- Templates: plain parsed data, not yet linked into the World -----------

@dataclass
class RoomTemplate:
    name: str  # local (lowercase) name, unique within its zone
    exits: dict[str, str] = field(default_factory=dict)  # dir -> raw dest text
    flags: set[str] = field(default_factory=set)
    title: str = ""
    description: str = ""


@dataclass
class ItemTemplate:
    name: str
    pname: str = ""
    alt_name: str = ""
    location_raw: str = ""  # e.g. "IN_ROOM:cellar" or "IN_CONTAINER:barrel"
    flags: set[str] = field(default_factory=set)
    descriptions: list[str] = field(default_factory=lambda: [""] * 4)
    examine: str = ""
    size: int = 1
    weight: int = 1
    value: int = 0
    damage: int = 0
    armor: int = 0
    state: int = 0
    max_state: int = 0
    linked: str = ""


@dataclass
class MobileTemplate:
    name: str
    pname: str = ""
    location_raw: str = ""  # room name the mobile starts in
    description: str = ""
    examine: str = ""
    strength: int = 100
    damage: int = 0
    armor: int = 0
    aggression: int = 0
    speed: int = 0
    flags: set[str] = field(default_factory=set)


@dataclass
class ZoneSource:
    """Everything parsed from one ``%zone:`` section of a .zone file."""

    rooms: dict[str, RoomTemplate] = field(default_factory=dict)
    items: dict[str, ItemTemplate] = field(default_factory=dict)
    mobiles: dict[str, MobileTemplate] = field(default_factory=dict)


def strip_preprocessor(text: str) -> str:
    """Drop /* ... */ comments and C-preprocessor lines (#include/#define/
    #undef); no macros are actually substituted in practice, see
    cflags.h/undef.h discussion."""
    text = _BLOCK_COMMENT_RE.sub("", text)
    kept = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


class _Scanner:
    """Minimal hand-written lexer/cursor over raw zone-source text."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def skip_ws(self) -> None:
        while self.pos < self.length and self.text[self.pos].isspace():
            self.pos += 1

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < self.length else ""

    def at_end(self) -> bool:
        self.skip_ws()
        return self.pos >= self.length

    def read_field_name(self) -> Optional[str]:
        self.skip_ws()
        match = _IDENT_RE.match(self.text, self.pos)
        if not match:
            return None
        self.pos = match.end()
        return match.group(0)

    def skip_inline_ws(self) -> None:
        """Skips spaces/tabs only (not newlines) - a bare value never
        continues onto the next line, so a blank ``Field =`` is empty."""
        while self.pos < self.length and self.text[self.pos] in " \t":
            self.pos += 1

    def read_value(self):
        """Returns a str for ``field = value``/quoted text, or a set[str]
        for ``field { flag list }``."""
        self.skip_inline_ws()
        char = self.peek()
        if char in ("", "\n", "\r"):
            # A quote/brace value may open on the next line (e.g.
            # "Examine =\n\"text\""); a bare value never does, so only
            # cross the newline if a quote/brace is actually waiting there.
            saved = self.pos
            self.skip_ws()
            char = self.peek()
            if char not in ('"', "'", "`", "^", "{"):
                self.pos = saved
                return ""
        if char in ('"', "'", "`", "^"):
            quote = char
            self.pos += 1
            end = self.text.find(quote, self.pos)
            if end == -1:
                end = self.length
            value = self.text[self.pos:end]
            self.pos = min(end + 1, self.length)
            return value.strip()
        if char == "{":
            self.pos += 1
            end = self.text.find("}", self.pos)
            if end == -1:
                end = self.length
            flags_text = self.text[self.pos:end]
            self.pos = min(end + 1, self.length)
            return set(flags_text.split())
        match = _BARE_TOKEN_RE.match(self.text, self.pos)
        if not match:
            return ""
        self.pos = match.end()
        return match.group(0)


def _parse_records(text: str) -> list[dict]:
    """Reads ``Field = value`` / ``Field {flags}`` pairs into records.

    A record ends when ``End = ...`` is seen, or (since ``End`` is
    frequently omitted in the real data) when a second ``Name`` field
    appears, which can only legally start a new record.
    """
    scanner = _Scanner(text)
    records: list[dict] = []
    current: dict = {}
    while not scanner.at_end():
        name = scanner.read_field_name()
        if name is None:
            # Unexpected token (stray punctuation, etc.) - skip this line
            # and keep going rather than silently dropping the rest of the
            # section.
            newline = scanner.text.find("\n", scanner.pos)
            if newline == -1:
                break
            logger.warning(
                "unexpected content, skipping line: %r",
                scanner.text[scanner.pos:newline].strip(),
            )
            scanner.pos = newline + 1
            continue
        scanner.skip_ws()
        if scanner.peek() == "=":
            scanner.pos += 1
        value = scanner.read_value()
        key = name.lower()
        if key == "name" and current:
            records.append(current)
            current = {}
        current[key] = value
        if key == "end":
            records.append(current)
            current = {}
    if current:
        records.append(current)
    return records


def _as_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_objects_section(text: str) -> dict[str, ItemTemplate]:
    items: dict[str, ItemTemplate] = {}
    for fields in _parse_records(text):
        name = fields.get("name")
        if not name:
            logger.warning("object record missing Name field, skipping: %s", fields)
            continue
        tmpl = ItemTemplate(name=name)
        tmpl.pname = fields.get("pname", "")
        tmpl.alt_name = fields.get("altname", "")
        tmpl.location_raw = fields.get("location", "")
        tmpl.flags = fields.get("oflags", set()) or set()
        tmpl.examine = fields.get("examine", "")
        tmpl.size = _as_int(fields.get("size"), 1)
        tmpl.weight = _as_int(fields.get("weight"), 1)
        tmpl.value = _as_int(fields.get("bvalue"), 0)
        tmpl.damage = _as_int(fields.get("damage"), 0)
        tmpl.armor = _as_int(fields.get("armor"), 0)
        tmpl.state = _as_int(fields.get("state"), 0)
        tmpl.max_state = _as_int(fields.get("maxstate"), 0)
        tmpl.linked = fields.get("linked", "")
        # "Desc[]" (no index) is a typo seen in a couple of source files;
        # treat it the same as "Desc[0]".
        if "desc[]" in fields and "desc[0]" not in fields:
            fields["desc[0]"] = fields["desc[]"]
        for index in range(4):
            desc = fields.get(f"desc[{index}]")
            if desc is not None:
                tmpl.descriptions[index] = desc
        items[name.lower()] = tmpl
    return items


def _parse_mobiles_section(text: str) -> dict[str, MobileTemplate]:
    mobiles: dict[str, MobileTemplate] = {}
    for fields in _parse_records(text):
        name = fields.get("name")
        if not name:
            logger.warning("mobile record missing Name field, skipping: %s", fields)
            continue
        tmpl = MobileTemplate(name=name)
        tmpl.pname = fields.get("pname", "")
        tmpl.location_raw = fields.get("location", "")
        tmpl.description = fields.get("description", "")
        tmpl.examine = fields.get("examine", "")
        tmpl.strength = _as_int(fields.get("strength"), 100)
        tmpl.damage = _as_int(fields.get("damage"), 0)
        tmpl.armor = _as_int(fields.get("armor"), 0)
        tmpl.aggression = _as_int(fields.get("aggression"), 0)
        tmpl.speed = _as_int(fields.get("speed"), 0)
        flags: set[str] = set()
        for key in ("pflags", "mflags", "sflags"):
            flags |= fields.get(key, set()) or set()
        tmpl.flags = flags
        mobiles[name.lower()] = tmpl
    return mobiles


def _parse_room_header(scanner: _Scanner) -> tuple[str, dict[str, str]]:
    scanner.skip_ws()
    end = scanner.text.find(";", scanner.pos)
    if end == -1:
        end = scanner.length
    header = scanner.text[scanner.pos:end]
    scanner.pos = min(end + 1, scanner.length)
    tokens = header.split()
    name = tokens[0] if tokens else ""
    exits: dict[str, str] = {}
    for token in tokens[1:]:
        if ":" not in token:
            continue
        direction, dest = token.split(":", 1)
        exits[direction.lower()] = dest
    return name, exits


def _parse_lflags(scanner: _Scanner) -> set[str]:
    scanner.skip_ws()
    match = _LFLAGS_RE.match(scanner.text, scanner.pos)
    if not match:
        logger.warning("expected 'lflags' at position %d, found %r", scanner.pos,
                        scanner.text[scanner.pos:scanner.pos + 20])
        return set()
    scanner.pos = match.end()
    scanner.skip_ws()
    if scanner.peek() != "{":
        return set()
    scanner.pos += 1
    end = scanner.text.find("}", scanner.pos)
    if end == -1:
        end = scanner.length
    flags_text = scanner.text[scanner.pos:end]
    scanner.pos = min(end + 1, scanner.length)
    return set(flags_text.split())


def _parse_title_and_description(scanner: _Scanner) -> tuple[str, str]:
    scanner.skip_ws()
    caret = scanner.text.find("^", scanner.pos)
    if caret == -1:
        return scanner.text[scanner.pos:].strip(), ""
    title = scanner.text[scanner.pos:caret].strip()
    scanner.pos = caret + 1
    rest = scanner.text[scanner.pos:]
    terminator = re.search(r"\n[ \t]*\^[ \t]*(\n|$)", rest)
    if terminator:
        description = rest[:terminator.start()]
        scanner.pos += terminator.end()
    else:
        description = rest
        scanner.pos = scanner.length
    return title, description.strip("\n")


def _parse_locations_section(text: str) -> dict[str, RoomTemplate]:
    scanner = _Scanner(text)
    rooms: dict[str, RoomTemplate] = {}
    while not scanner.at_end():
        name, exits = _parse_room_header(scanner)
        if not name:
            break
        flags = _parse_lflags(scanner)
        title, description = _parse_title_and_description(scanner)
        rooms[name.lower()] = RoomTemplate(
            name=name, exits=exits, flags=flags, title=title, description=description,
        )
    return rooms


def parse_zone_text(text: str) -> ZoneSource:
    """Parses the body of a single ``%zone:`` section (or a whole file with
    no ``%zone:`` markers) into rooms/items/mobiles templates."""
    text = strip_preprocessor(text)
    sections: dict[str, str] = {}
    current = None
    buffer: list[str] = []
    for line in text.splitlines():
        match = _SECTION_RE.match(line.strip())
        if match:
            if current is not None:
                sections[current] = "\n".join(buffer)
            current = match.group(1).lower()
            buffer = []
        else:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer)

    zone = ZoneSource()
    if "objects" in sections:
        zone.items = _parse_objects_section(sections["objects"])
    if "mobiles" in sections:
        zone.mobiles = _parse_mobiles_section(sections["mobiles"])
    if "locations" in sections:
        zone.rooms = _parse_locations_section(sections["locations"])
    return zone


_ZONE_MARKER_RE = re.compile(r"^%zone:\s*(\S+)", re.IGNORECASE | re.MULTILINE)


def split_zone_sections(file_text: str) -> dict[str, str]:
    """Splits a .zone file on ``%zone:name`` markers.

    Returns {zone_name: section_text}. If there are no markers, returns
    {"": file_text} and the caller supplies the zone name from data/ZONES/files.
    """
    markers = list(_ZONE_MARKER_RE.finditer(file_text))
    if not markers:
        return {"": file_text}
    sections: dict[str, str] = {}
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(file_text)
        sections[marker.group(1).lower()] = file_text[start:end]
    return sections
