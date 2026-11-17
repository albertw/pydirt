"""Parser/dispatch sanity checks (no direct C equivalent - new for this port).

Run with: python -m unittest discover -s tests
"""
from __future__ import annotations

import unittest

import pydirt.commands  # noqa: F401  (registers @verb handlers)
from pydirt import verbs
from pydirt.models import Player
from pydirt.parser import handle_line, split_nouns
from pydirt.world import World


class FakeWriter:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    async def drain(self) -> None:
        return None

    def text(self) -> str:
        return b"".join(self.chunks).decode("utf-8", errors="replace")


class SplitNounsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = Player(name="Tester")

    def test_abbreviation_and_filler_words(self) -> None:
        args = split_nouns(self.player, "the rusty sword")
        self.assertEqual(args.item1, "rusty sword")

    def test_preposition_split(self) -> None:
        args = split_nouns(self.player, "sword in the bag")
        self.assertEqual(args.item1, "sword")
        self.assertEqual(args.prep, "in")
        self.assertEqual(args.item2, "bag")

    def test_pronoun_resolution(self) -> None:
        self.player.last_target = "village:rope"
        args = split_nouns(self.player, "it")
        self.assertEqual(args.item1, "village:rope")


class VerbResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from pathlib import Path

        verbs.load_verb_table(Path(__file__).resolve().parent.parent / "data" / "verbs.src")

    def test_direction_abbreviation(self) -> None:
        self.assertEqual(verbs.resolve_word("n"), "north")

    def test_inventory_abbreviation(self) -> None:
        self.assertEqual(verbs.resolve_word("i"), "i")

    def test_alias_resolves_to_handler(self) -> None:
        self.assertIsNotNone(verbs.find_handler("take"))  # take=get
        self.assertIs(verbs.find_handler("take"), verbs.find_handler("get"))


class HandleLineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from pathlib import Path

        data_dir = Path(__file__).resolve().parent.parent / "data"
        verbs.load_verb_table(data_dir / "verbs.src")
        self.world = World()
        self.world.start_room = None
        self.player = Player(name="Tester")
        self.player.writer = FakeWriter()

    async def test_unknown_command_says_huh(self) -> None:
        await handle_line(self.world, self.player, "xyzzyzzy")
        self.assertIn("Huh?!?", self.player.writer.text())

    async def test_quit_signals_disconnect(self) -> None:
        result = await handle_line(self.world, self.player, "quit")
        self.assertFalse(result)

    async def test_say_shorthand(self) -> None:
        await handle_line(self.world, self.player, "'hello there")
        self.assertIn('You say "hello there"', self.player.writer.text())


if __name__ == "__main__":
    unittest.main()
