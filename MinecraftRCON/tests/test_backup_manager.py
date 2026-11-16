import tempfile
import unittest
from pathlib import Path

from backup_manager import BackupError, create_scheduled_backup, restore_backup


class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.server = self.root / "server"
        self.backups = self.root / "backups"
        (self.server / "worlds" / "Abydos").mkdir(parents=True)
        (self.server / "worlds" / "Abydos" / "level.dat").write_text("original", encoding="utf-8")
        (self.server / "server.properties").write_text("transport=nethernet\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scheduled_backup_holds_and_resumes_saving(self):
        events = []
        path = create_scheduled_backup(
            self.server,
            self.backups,
            7,
            lambda: events.append("hold") or True,
            lambda: events.append("resume") or True,
        )
        self.assertTrue(path.is_file())
        self.assertEqual(events, ["hold", "resume"])

    def test_scheduled_backup_retention_keeps_latest_count(self):
        create_scheduled_backup(self.server, self.backups, 1, lambda: True, lambda: True)
        create_scheduled_backup(self.server, self.backups, 1, lambda: True, lambda: True)
        self.assertEqual(len(list(self.backups.glob("scheduled-*.tar.gz"))), 1)

    def test_restore_replaces_world_and_creates_rollback_backup(self):
        backup = create_scheduled_backup(self.server, self.backups, 7, lambda: True, lambda: True)
        (self.server / "worlds" / "Abydos" / "level.dat").write_text("newer", encoding="utf-8")
        (self.server / ".maintenance").write_text("restore requested", encoding="utf-8")

        rollback = restore_backup(backup.name, self.server, self.backups)
        self.assertEqual((self.server / "worlds" / "Abydos" / "level.dat").read_text(), "original")
        self.assertTrue(rollback.is_file())
        self.assertFalse((self.server / ".maintenance").exists())

    def test_restore_requires_exact_backup_id(self):
        with self.assertRaises(BackupError):
            restore_backup("../outside.tar.gz", self.server, self.backups)


if __name__ == "__main__":
    unittest.main()
