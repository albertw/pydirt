"""Telnet in-band negotiation (IAC) handling for client input.

C equivalent: the buffer handling in src/main.c (``handle_packet``/the
buffer_fds line splitter), which interprets IAC sequences in the continuous
byte stream instead of passing them into the parser. Without this, a
client's negotiation replies (e.g. IAC DO/DONT ECHO sent after the password
prompt's WILL/WONT ECHO) end up glued onto the next typed command, and
"ver" arrives as garbage that no verb matches.

Two pieces:

- ``IacStripper`` is a stateful filter fed raw stream chunks; it survives
  sequences split across read boundaries (a lone IAC byte at the end of one
  read, its argument in the next), which a naive per-line strip does not.
- ``TelnetLineReader`` wraps an ``asyncio.StreamReader``: it strips IAC from
  the stream *before* line-splitting (like the C's buffer, not per line) and
  reports whether a line contained negotiation bytes, so callers can tell a
  real empty input from a negotiation-only line.
"""
from __future__ import annotations

from typing import Optional

IAC = 255
SB = 250
SE = 240

_NORMAL = 0
_GOT_IAC = 1
_GOT_OPTION_CMD = 2  # WILL/WONT/DO/DONT - one option byte follows
_IN_SB = 3
_IN_SB_IAC = 4


class IacStripper:
    """Stateful IAC filter; feed() raw chunks, get clean bytes back."""

    def __init__(self) -> None:
        self._state = _NORMAL

    def feed(self, chunk: bytes) -> tuple[bytes, bool]:
        """Returns (cleaned_bytes, saw_iac) for this chunk."""
        out = bytearray()
        saw_iac = False
        for byte in chunk:
            if self._state == _NORMAL:
                if byte == IAC:
                    self._state = _GOT_IAC
                    saw_iac = True
                else:
                    out.append(byte)
            elif self._state == _GOT_IAC:
                if byte == IAC:  # IAC IAC escapes a literal 255 data byte
                    out.append(IAC)
                    self._state = _NORMAL
                elif byte == SB:
                    self._state = _IN_SB
                elif byte >= 251:  # WILL / WONT / DO / DONT
                    self._state = _GOT_OPTION_CMD
                else:  # NOP, SE, ... - no argument
                    self._state = _NORMAL
            elif self._state == _GOT_OPTION_CMD:
                self._state = _NORMAL
            elif self._state == _IN_SB:
                if byte == IAC:
                    self._state = _IN_SB_IAC
            elif self._state == _IN_SB_IAC:
                if byte == SE:  # IAC SE ends the sub-negotiation
                    self._state = _NORMAL
                elif byte == IAC:  # IAC IAC - escaped literal 255 inside SB
                    self._state = _IN_SB_IAC
                else:
                    self._state = _IN_SB
        return bytes(out), saw_iac

    def strip(self, raw: bytes) -> bytes:
        """One-shot convenience: strip a complete buffer."""
        return self.feed(raw)[0]


def strip_iac(raw: bytes) -> bytes:
    """Strips telnet IAC sequences from a complete byte buffer."""
    return IacStripper().strip(raw)


class TelnetLineReader:
    """Line reader over an asyncio StreamReader with IAC stripped first.

    readline() returns ``(clean_line_bytes_without_newline, had_iac)`` or
    ``None`` at end of stream. ``had_iac`` marks lines that carried telnet
    negotiation bytes, so a line that is empty after stripping can be
    recognized as the client's echo reply rather than real input.
    """

    def __init__(self, reader) -> None:
        self._reader = reader
        self._stripper = IacStripper()
        self._buf = bytearray()
        self._had_iac = bytearray()  # one flag byte per byte in _buf
        self._eof = False

    async def readline(self) -> Optional[tuple[bytes, bool]]:
        while True:
            newline = self._buf.find(b"\n")
            if newline != -1:
                line = bytes(self._buf[:newline])
                had_iac = any(self._had_iac[:newline])
                del self._buf[:newline + 1]
                del self._had_iac[:newline + 1]
                return line, had_iac
            if self._eof:
                if self._buf:
                    line, had_iac = bytes(self._buf), any(self._had_iac)
                    self._buf.clear()
                    self._had_iac.clear()
                    return line, had_iac
                return None
            chunk = await self._reader.read(1024)
            if not chunk:
                self._eof = True
                continue
            cleaned, saw_iac = self._stripper.feed(chunk)
            self._buf += cleaned
            self._had_iac += bytes([1 if saw_iac else 0]) * len(cleaned)
