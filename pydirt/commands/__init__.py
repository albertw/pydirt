"""Importing this package registers every built-in command's @verb handler.

C equivalent: there's no single dispatch table in the C version - commands
are spread across parse.c's switch statement and commands.c. Here, each
module simply registers its handlers into pydirt.verbs.HANDLERS at import
time, so pydirt/server.py only needs ``import pydirt.commands`` once.
"""
from pydirt.commands import communication, combat, items, look, misc, movement  # noqa: F401
