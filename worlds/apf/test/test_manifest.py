"""
Static tests for APFramework world registration and archipelago.json manifest.

These tests do NOT require capabilities_data and do not attempt world generation.
They verify that the world package imports cleanly, registers with Archipelago,
and that its static metadata is well-formed.
"""

import json
import unittest
from pathlib import Path

from worlds.AutoWorld import AutoWorldRegister


class TestAPFrameworkRegistration(unittest.TestCase):
    """Verify the world is registered and its class is correctly configured."""

    def test_world_registered(self):
        self.assertIn(
            "APFramework",
            AutoWorldRegister.world_types,
            "APFramework world must be present in AutoWorldRegister.world_types",
        )

    def test_game_name_matches(self):
        world_type = AutoWorldRegister.world_types["APFramework"]
        self.assertEqual(world_type.game, "APFramework")

    def test_item_name_groups_is_dict(self):
        world_type = AutoWorldRegister.world_types["APFramework"]
        self.assertIsInstance(world_type.item_name_groups, dict)

    def test_location_name_groups_is_dict(self):
        world_type = AutoWorldRegister.world_types["APFramework"]
        self.assertIsInstance(world_type.location_name_groups, dict)


class TestAPFrameworkManifest(unittest.TestCase):
    """Verify archipelago.json is well-formed and passes AP spec requirements."""

    @classmethod
    def setUpClass(cls):
        manifest_path = Path(__file__).parent.parent / "archipelago.json"
        with manifest_path.open(encoding="utf-8") as f:
            cls.manifest = json.load(f)

    def test_game_field_present(self):
        self.assertIn("game", self.manifest)
        self.assertEqual(self.manifest["game"], "APFramework")

    def test_world_version_format(self):
        self.assertIn("world_version", self.manifest)
        ver = self.manifest["world_version"]
        parts = ver.split(".")
        self.assertEqual(len(parts), 3, "world_version must be major.minor.patch")
        for part in parts:
            self.assertTrue(part.isdigit(), f"world_version part '{part}' must be numeric")

    def test_no_legacy_version_fields(self):
        self.assertNotIn(
            "version", self.manifest,
            "archipelago.json must not contain legacy 'version' field",
        )
        self.assertNotIn(
            "compatible_version", self.manifest,
            "archipelago.json must not contain legacy 'compatible_version' field",
        )
