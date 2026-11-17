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
        for endpoint in ("/api/v1/commands", "/rcon"):
            with patch.object(service, "send_console_command", return_value=True), patch.object(
                service, "read_console_output", return_value=["[INFO] There are 1/10 players online"]
            ):
                response = self.client.post(
                    endpoint,
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

    def test_versioned_info_requires_token_and_describes_bedrock(self):
        denied = self.client.get("/api/v1/info", environ_base={"REMOTE_ADDR": "192.168.1.10"})
        self.assertEqual(denied.status_code, 401)

        response = self.client.get(
            "/api/v1/info",
            headers={"Authorization": f"Bearer {service.RCON_TOKEN}"},
            environ_base={"REMOTE_ADDR": "192.168.1.10"},
        )
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["api_version"], "1")
        self.assertEqual(body["server"]["edition"], "bedrock")
        self.assertEqual(body["server"]["command_dialect"], "minecraft-bedrock")
        self.assertEqual(body["capabilities"]["command_execution"]["path"], "/api/v1/commands")

    def test_versioned_telemetry_returns_normalized_server_and_player_data(self):
        now = service.time.time()
        (service.SERVER_DIR / "server.properties").write_text(
            "level-name=Abydos\ngamemode=survival\ndifficulty=hard\nmax-players=10\n",
            encoding="utf-8",
        )
        (service.SERVER_DIR / "lastversion.txt").write_text("1.26.0\n", encoding="utf-8")
        (service.SERVER_DIR / ".server_started_at").write_text(str(now - 60), encoding="ascii")
        with service.TELEMETRY_LOCK:
            service.PLAYER_TELEMETRY.update({
                "online_count": 1,
                "max_count": 10,
                "names": ["jcasallecchio"],
                "updated_at": service.datetime.now(service.timezone.utc).isoformat(),
            })
        headers = {"Authorization": f"Bearer {service.RCON_TOKEN}"}
        with patch.object(service, "find_screen_session", return_value="123.mc"), patch.object(
            service, "_bedrock_memory_bytes", return_value=512 * 1024 * 1024
        ):
            response = self.client.get(
                "/api/v1/telemetry",
                headers=headers,
                environ_base={"REMOTE_ADDR": "192.168.1.10"},
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["server"]["status"], "running")
        self.assertEqual(body["server"]["version"], "1.26.0")
        self.assertEqual(body["server"]["world_name"], "Abydos")
        self.assertEqual(body["players"]["online_count"], 1)
        self.assertEqual(body["players"]["names"], ["jcasallecchio"])
        self.assertEqual(body["performance"]["bedrock_memory_bytes"], 512 * 1024 * 1024)

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
