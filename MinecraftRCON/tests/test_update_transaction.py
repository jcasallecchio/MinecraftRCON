import tempfile
import json
import unittest
from pathlib import Path

from update_transaction import apply, commit, recover


class UpdateTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.server = self.root / "server"
        self.stage = self.root / "stage"
        self.server.mkdir()
        self.stage.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_recovery_restores_previous_files_and_removes_new_files(self):
        (self.server / "bedrock_server").write_text("old-bin", encoding="utf-8")
        (self.server / "old-lib.so").write_text("old-lib", encoding="utf-8")
        (self.server / ".bedrock-managed-files.json").write_text(
            json.dumps({"files": ["bedrock_server", "old-lib.so"]}), encoding="utf-8"
        )
        (self.stage / "bedrock_server").write_text("new-bin", encoding="utf-8")
        (self.stage / "new-lib.so").write_text("new-lib", encoding="utf-8")

        apply(self.stage, self.server)
        self.assertEqual((self.server / "bedrock_server").read_text(), "new-bin")
        self.assertFalse((self.server / "old-lib.so").exists())
        self.assertTrue(recover(self.server))
        self.assertEqual((self.server / "bedrock_server").read_text(), "old-bin")
        self.assertEqual((self.server / "old-lib.so").read_text(), "old-lib")
        self.assertFalse((self.server / "new-lib.so").exists())

    def test_commit_removes_obsolete_managed_files(self):
        (self.server / "bedrock_server").write_text("old-bin", encoding="utf-8")
        (self.server / "obsolete.so").write_text("obsolete", encoding="utf-8")
        (self.server / ".bedrock-managed-files.json").write_text(
            json.dumps({"files": ["bedrock_server", "obsolete.so"]}), encoding="utf-8"
        )
        (self.stage / "bedrock_server").write_text("new-bin", encoding="utf-8")

        apply(self.stage, self.server)
        commit(self.server)
        self.assertFalse((self.server / "obsolete.so").exists())
        manifest = json.loads((self.server / ".bedrock-managed-files.json").read_text())
        self.assertEqual(manifest["files"], ["bedrock_server"])

    def test_commit_keeps_new_files(self):
        (self.server / "bedrock_server").write_text("old-bin", encoding="utf-8")
        (self.stage / "bedrock_server").write_text("new-bin", encoding="utf-8")

        apply(self.stage, self.server)
        commit(self.server)
        self.assertEqual((self.server / "bedrock_server").read_text(), "new-bin")
        self.assertFalse(recover(self.server))

    def test_apply_requires_server_binary(self):
        (self.stage / "lib.so").write_text("library", encoding="utf-8")
        with self.assertRaises(Exception):
            apply(self.stage, self.server)
        self.assertFalse((self.server / "lib.so").exists())


if __name__ == "__main__":
    unittest.main()
