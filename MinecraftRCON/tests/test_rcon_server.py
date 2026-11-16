import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_test_root = tempfile.TemporaryDirectory()
os.environ["MINECRAFT_SERVER_DIR"] = _test_root.name
os.environ["RCON_LOG_FILE"] = str(Path(_test_root.name) / "rcon.log")
os.environ["RCON_OPTIONS_FILE"] = str(Path(_test_root.name) / "options.json")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rcon_server as service


class RconServerTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        service.command_logger.removeHandler(service.command_log_handler)
        service.command_log_handler.close()
        _test_root.cleanup()

    def setUp(self):
        service.RCON_TOKEN = "t" * 40
        service.ALLOWED_NETWORKS = (service.ipaddress.ip_network("192.168.1.0/24"),)
        service.RATE_BUCKETS.clear()
        service.app.config["TESTING"] = True
        self.client = service.app.test_client()

    def test_ip_allowlist_blocks_untrusted_address(self):
        response = self.client.get("/backups", environ_base={"REMOTE_ADDR": "203.0.113.8"})
        self.assertEqual(response.status_code, 403)

    def test_rcon_returns_observed_output_without_claiming_execution(self):
        service.SERVER_LOG_FILE.write_text("", encoding="utf-8")
        headers = {"Authorization": f"Bearer {service.RCON_TOKEN}"}
        with patch.object(service, "send_console_command", return_value=True), patch.object(
            service, "read_console_output", return_value=["[INFO] There are 1/10 players online"]
        ):
            response = self.client.post(
                "/rcon",
                json={"command": "list"},
                headers=headers,
                environ_base={"REMOTE_ADDR": "192.168.1.10"},
            )
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["sent"])
        self.assertFalse(body["execution_confirmed"])
        self.assertEqual(len(body["console_output"]), 1)
        self.assertTrue(body["request_id"])

    def test_rate_limit_blocks_excess_requests(self):
        for _ in range(service.MAX_REQUESTS_PER_MINUTE):
            self.assertTrue(service.request_rate_allowed("192.168.1.4"))
        self.assertFalse(service.request_rate_allowed("192.168.1.4"))

    def test_backup_refuses_live_snapshot_without_cheats(self):
        (service.SERVER_DIR / "server.properties").write_text("allow-cheats=false\n", encoding="utf-8")
        with self.assertRaises(service.BackupError):
            service.run_scheduled_backup()


if __name__ == "__main__":
    unittest.main()
