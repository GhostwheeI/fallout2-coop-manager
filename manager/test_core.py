import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core import Installation, clean_environment, validate_address, validate_player, asset_fingerprint, write_local_config


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = Installation(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def seed_world(self):
        world = self.app.directory("server")
        for name in ("master.dat", "critter.dat", "patch000.dat", "fallout2.cfg", "fallout2-ce.exe", "f2_server.exe"):
            world.mkdir(exist_ok=True)
            (world / name).write_bytes(b"test")
        slot = world / "data" / "SAVEGAME" / "SLOT16"
        slot.mkdir(parents=True)
        (slot / "SAVE.DAT").write_bytes(b"saved character")
        maps = world / "data" / "MAPS"
        maps.mkdir()
        (maps / "ARVILLAG.SAV").write_bytes(b"visited map")
        return world, slot, maps

    def test_address_and_names_reject_shell_text(self):
        self.assertEqual(validate_address("friend.nord:9300"), ("friend.nord", 9300))
        self.assertEqual(validate_address("100.80.2.3"), ("100.80.2.3", 9300))
        self.assertEqual(validate_player("Player_2"), "Player_2")
        for value in ("127.0.0.1&calc", "a:65536", "a:1", "https://example.com"):
            with self.assertRaises(ValueError):
                validate_address(value)
        with self.assertRaises(ValueError):
            validate_player("a & b")

    def test_production_environment_drops_dangerous_inherited_flags(self):
        with patch.dict(os.environ, {"F2_HEADLESS_PROBE": "1", "f2_server_cmd": "9301", "F2_SERVER_LOAD": "16", "SDL_VIDEODRIVER": "dummy", "DEBUGACTIVE": "log"}):
            env = self.app.server_env(None)
        self.assertNotIn("F2_SERVER_CMD", env)
        self.assertNotIn("f2_server_cmd", env)
        self.assertNotIn("F2_HEADLESS_PROBE", env)
        self.assertNotIn("SDL_VIDEODRIVER", env)
        self.assertNotIn("F2_SERVER_LOAD", env)
        self.assertEqual(env["F2_SERVER_MAP"], "artemple.map")

    def test_resume_does_not_start_new_game(self):
        self.seed_world()
        env = self.app.server_env(16)
        self.assertEqual(env["F2_SERVER_LOAD"], "16")
        self.assertNotIn("F2_SERVER_MAP", env)
        with self.assertRaises(ValueError):
            self.app.server_env(15)

    def test_separate_client_and_world_and_client_identity(self):
        self.assertNotEqual(self.app.directory("client"), self.app.directory("server"))
        env = self.app.client_env("100.70.1.2", "Friend")
        self.assertEqual(env["F2_PLAYER_NAME"], "Friend")
        self.assertEqual(env["F2_CLIENT_CONNECT"], "100.70.1.2:9300")
        self.assertNotIn("F2_SERVER_CMD", env)

    def test_backup_and_restore_preserve_saved_state(self):
        world, slot, maps = self.seed_world()
        archive = self.app.backup()
        self.assertIsNotNone(archive)
        (slot / "SAVE.DAT").write_bytes(b"later character")
        (maps / "OTHER.SAV").write_bytes(b"later map")
        self.app.restore(archive)
        self.assertEqual((slot / "SAVE.DAT").read_bytes(), b"saved character")
        self.assertEqual((maps / "ARVILLAG.SAV").read_bytes(), b"visited map")
        self.assertFalse((maps / "OTHER.SAV").exists())
        self.assertGreaterEqual(len(list((self.root / "Backups").glob("*.zip"))), 2)

    def test_restore_rejects_traversal_before_touching_world(self):
        _, slot, _ = self.seed_world()
        for malicious in ("../../escape.txt", "data/SAVEGAME/../../escape.txt", "C:/escape.txt", "data/MAPS/game.exe"):
            archive = self.root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("data/SAVEGAME/SLOT16/SAVE.DAT", b"overwrite")
                output.writestr(malicious, b"bad")
            with self.assertRaises(ValueError):
                self.app.restore(archive)
            self.assertEqual((slot / "SAVE.DAT").read_bytes(), b"saved character")

    def test_fingerprint_detects_loose_mods_but_ignores_saves(self):
        world, slot, _ = self.seed_world()
        first = asset_fingerprint(world)["fingerprint"]
        (slot / "SAVE.DAT").write_bytes(b"new save")
        self.assertEqual(first, asset_fingerprint(world)["fingerprint"])
        script = world / "data" / "scripts" / "mod.int"
        script.parent.mkdir()
        script.write_bytes(b"mod")
        self.assertNotEqual(first, asset_fingerprint(world)["fingerprint"])

    def test_config_round_trip(self):
        self.app.config["player"] = "Friend"
        self.app.save_config()
        self.assertEqual(Installation(self.root).config["player"], "Friend")

    def test_imported_config_cannot_write_back_to_original_game(self):
        source = self.root / "source.cfg"
        destination = self.root / "local.cfg"
        source.write_text('[system]\nmaster_dat=C:/Steam/master.dat\nmaster_patches=C:/Steam/data\ncritter_patches=../../other\n', encoding="utf-8")
        write_local_config(source, destination)
        text = destination.read_text(encoding="utf-8")
        self.assertIn("master_patches = data", text)
        self.assertIn("critter_patches = data", text)
        self.assertNotIn("C:/Steam", text)

    def test_broken_settings_recover_without_losing_original(self):
        self.app.settings_path.write_text("invalid JSON", encoding="utf-8")
        recovered = Installation(self.root)
        self.assertEqual(recovered.config["port"], 9300)
        self.assertTrue(self.app.settings_path.with_suffix(".invalid.json").exists())

    def test_failed_restore_rolls_back_current_world(self):
        _, slot, maps = self.seed_world()
        archive = self.app.backup()
        (slot / "SAVE.DAT").write_bytes(b"current progress")
        replace = Path.replace
        def fail_map_swap(path, target):
            if path.name == "next-maps":
                raise OSError("simulated locked directory")
            return replace(path, target)
        with patch.object(Path, "replace", fail_map_swap):
            with self.assertRaises(OSError):
                self.app.restore(archive)
        self.assertEqual((slot / "SAVE.DAT").read_bytes(), b"current progress")
        self.assertEqual((maps / "ARVILLAG.SAV").read_bytes(), b"visited map")


if __name__ == "__main__":
    unittest.main(verbosity=2)
