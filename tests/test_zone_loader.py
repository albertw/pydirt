"""Zone loader sanity checks (no C/mkdata equivalent - new for this port).

Run with: python -m unittest discover -s tests
"""
from __future__ import annotations

import unittest
from pathlib import Path

from pydirt.bootstrap import load_world

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class ZoneLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = load_world(DATA_DIR)

    def test_village_zone_counts(self) -> None:
        village_rooms = [r for r in self.world.rooms if r.startswith("village:")]
        village_items = [i for i in self.world.items if i.startswith("village:")]
        self.assertEqual(len(village_rooms), 24)
        self.assertEqual(len(village_items), 18)

    def test_home_zone_counts(self) -> None:
        home_rooms = [r for r in self.world.rooms if r.startswith("home:")]
        home_items = [i for i in self.world.items if i.startswith("home:")]
        home_mobiles = [m for m in self.world.mobiles if m.startswith("home:")]
        self.assertEqual(len(home_rooms), 31)
        self.assertEqual(len(home_items), 6)
        self.assertEqual(len(home_mobiles), 1)

    def test_cross_zone_exit_resolves(self) -> None:
        # Green's north exit in village.zone is "Church@start".
        green = self.world.rooms["village:green"]
        self.assertEqual(green.exits["north"], "start:church")

    def test_door_object_exit_resolves(self) -> None:
        # village.zone links Top_Boards/Bot_Boards so Cellar's "down" exit
        # and Passage's "up" exit connect through the linked door objects.
        cellar = self.world.rooms["village:cellar"]
        self.assertIsNotNone(cellar.exits["down"])

    def test_container_contents_placed(self) -> None:
        # home.zone: "birds" (IN_CONTAINER:tree) should end up inside "tree".
        tree = self.world.items["home:tree"]
        self.assertIn("home:birds", tree.contents)

    def test_every_zone_file_parses_without_crashing(self) -> None:
        self.assertGreater(len(self.world.rooms), 500)
        self.assertGreater(len(self.world.items), 400)
        self.assertGreater(len(self.world.mobiles), 90)

    def test_start_room_and_levels_loaded(self) -> None:
        # mud.c starts home-less players at the village church (or temple).
        self.assertEqual(self.world.start_room, "start:church")
        self.assertEqual(len(self.world.levels), 12)
        self.assertGreater(len(self.world.banned_patterns), 0)


if __name__ == "__main__":
    unittest.main()
