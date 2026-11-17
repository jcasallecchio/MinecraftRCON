import hmac
import ipaddress
import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, jsonify, request
from waitress import serve
from backup_manager import BackupError, create_scheduled_backup, list_scheduled_backups, restore_backup

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

SERVER_DIR = Path(os.environ.get("MINECRAFT_SERVER_DIR", "/share/minecraftRCON"))
LOG_FILE = os.environ.get("RCON_LOG_FILE", str(SERVER_DIR / "rcon_commands.log"))
SERVER_LOG_FILE = SERVER_DIR / "server.log"
BACKUP_DIR = SERVER_DIR / "backups" / "scheduled"
MAINTENANCE_FILE = SERVER_DIR / ".maintenance"
OPTIONS_FILE = os.environ.get("RCON_OPTIONS_FILE", "/data/options.json")
RCON_PORT = 19133
MAX_COMMAND_LENGTH = 1024
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 5
CONSOLE_CAPTURE_SECONDS = 2.5
CONSOLE_QUIET_SECONDS = 0.35
RATE_WINDOW_SECONDS = 60
MAX_REQUESTS_PER_MINUTE = 60
MAX_COMMANDS_PER_MINUTE = 30
MAX_BACKUPS_PER_HOUR = 3
TELEMETRY_INTERVAL_SECONDS = 15
API_VERSION = "1"

Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
command_logger = logging.getLogger("rcon_commands")
command_logger.setLevel(logging.INFO)
command_logger.propagate = False
command_log_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding="utf-8",
)
command_log_handler.setFormatter(
    logging.Formatter("[%(asctime)s] IP: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
command_logger.addHandler(command_log_handler)


def load_rcon_token():
    """Read the add-on secret option, with an env var fallback for local use."""
    try:
        with open(OPTIONS_FILE, encoding="utf-8") as options_file:
            options = json.load(options_file)
    except FileNotFoundError:
        options = {}

    token = options.get("rcon_token", "") if isinstance(options, dict) else ""
    if not token:
        token = os.environ.get("RCON_TOKEN", "")
    return token.strip() if isinstance(token, str) else ""


def load_options():
    try:
        with open(OPTIONS_FILE, encoding="utf-8") as options_file:
            options = json.load(options_file)
        return options if isinstance(options, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


OPTIONS = load_options()
RCON_TOKEN = load_rcon_token()
SERVER_OPERATION_LOCK = threading.RLock()
RESTORE_REQUEST_LOCK = threading.Lock()
RATE_LIMIT_LOCK = threading.Lock()
RATE_BUCKETS = defaultdict(deque)
SCHEDULER_STOP = threading.Event()
TELEMETRY_LOCK = threading.Lock()
PLAYER_TELEMETRY = {
    "online_count": None,
    "max_count": None,
    "names": [],
    "updated_at": None,
}


def load_allowed_networks(value):
    networks = []
    for item in (value or "").split(","):
        item = item.strip()
        if item:
            networks.append(ipaddress.ip_network(item, strict=False))
    return tuple(networks)


try:
    ALLOWED_NETWORKS = load_allowed_networks(OPTIONS.get("rcon_allowed_ips", ""))
except ValueError as error:
    raise SystemExit(f"[RCON] Invalid rcon_allowed_ips setting: {error}") from error


def log_command(ip, command, status, request_id=None):
    command_logger.info("%s | CMD: %s | STATUS: %s | REQUEST_ID: %s", ip or "unknown", command, status, request_id or "-")


def client_ip_allowed(ip):
    if not ALLOWED_NETWORKS:
        return True
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address.version == network.version and address in network for network in ALLOWED_NETWORKS)


def request_rate_allowed(ip, command_request=False, backup_request=False):
    now = time.monotonic()
    if backup_request:
        limit = MAX_BACKUPS_PER_HOUR
        window = 3600
        category = "backups"
    else:
        limit = MAX_COMMANDS_PER_MINUTE if command_request else MAX_REQUESTS_PER_MINUTE
        window = RATE_WINDOW_SECONDS
        category = "commands" if command_request else "requests"
    key = (ip or "unknown", category)
    with RATE_LIMIT_LOCK:
        bucket = RATE_BUCKETS[key]
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        if len(RATE_BUCKETS) > 4096:
            for old_key in list(RATE_BUCKETS):
                if not RATE_BUCKETS[old_key] or now - RATE_BUCKETS[old_key][-1] >= 3600:
                    RATE_BUCKETS.pop(old_key, None)
        return True


def find_screen_session(session_name="mc"):
    """Return the exact screen session ID, if it exists."""
    try:
        result = subprocess.run(
            ["screen", "-ls"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    session_pattern = re.compile(rf"^\s*(\d+\.{re.escape(session_name)})\s+\(")
    for line in result.stdout.splitlines():
        match = session_pattern.search(line)
        if match:
            return match.group(1)
    return None


def authorized():
    provided = request.headers.get("Authorization", "")
    expected = f"Bearer {RCON_TOKEN}"
    return len(RCON_TOKEN) >= 32 and hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    )


def send_console_command(command):
    session_id = find_screen_session("mc")
    if not session_id:
        return False
    try:
        subprocess.run(
            ["screen", "-S", session_id, "-X", "stuff", f"{command}\r"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def read_console_output(offset, timeout=CONSOLE_CAPTURE_SECONDS, quiet=CONSOLE_QUIET_SECONDS):
    deadline = time.monotonic() + timeout
    last_change = None
    output = ""
    while time.monotonic() < deadline:
        try:
            with SERVER_LOG_FILE.open("rb") as log_file:
                log_file.seek(offset)
                current = log_file.read().decode("utf-8", errors="replace")
        except OSError:
            current = ""
        if current != output:
            output = current
            last_change = time.monotonic()
        elif output and last_change is not None and time.monotonic() - last_change >= quiet:
            break
        time.sleep(0.1)
    lines = [line[:512] for line in output.splitlines() if line.strip()][-40:]
    while sum(len(line) for line in lines) > 8192:
        lines.pop(0)
    return lines


def sample_player_telemetry():
    """Refresh online-player data from Bedrock's native `list` console command."""
    with SERVER_OPERATION_LOCK:
        try:
            log_offset = SERVER_LOG_FILE.stat().st_size
        except OSError:
            log_offset = 0
        if not send_console_command("list"):
            return False
        output = "\n".join(read_console_output(log_offset))

    match = re.search(
        r"(\d+)\s*/\s*(\d+)\s+players?\s+online\s*:?\s*(.*)",
        output,
        re.IGNORECASE,
    )
    if not match:
        return False
    names = [name.strip() for name in match.group(3).split(",") if name.strip()]
    with TELEMETRY_LOCK:
        PLAYER_TELEMETRY.update({
            "online_count": int(match.group(1)),
            "max_count": int(match.group(2)),
            "names": names,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    return True


def telemetry_scheduler():
    while not SCHEDULER_STOP.is_set():
        if find_screen_session("mc") is not None:
            try:
                if not sample_player_telemetry():
                    app.logger.debug("Bedrock player telemetry was not available in the console output")
            except Exception:
                app.logger.exception("Could not refresh Bedrock player telemetry")
        SCHEDULER_STOP.wait(TELEMETRY_INTERVAL_SECONDS)


def _read_server_properties():
    try:
        properties = {}
        for line in (SERVER_DIR / "server.properties").read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                properties[key.strip()] = value.strip()
        return properties
    except OSError:
        return {}


def _server_version():
    try:
        return (SERVER_DIR / "lastversion.txt").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _bedrock_memory_bytes():
    """Return RSS for the Bedrock process when /proc exposes it."""
    try:
        for process_dir in Path("/proc").iterdir():
            if not process_dir.name.isdigit():
                continue
            try:
                if (process_dir / "comm").read_text(encoding="utf-8").strip() != "bedrock_server":
                    continue
                for line in (process_dir / "status").read_text(encoding="utf-8").splitlines():
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
            except (OSError, ValueError, IndexError):
                continue
    except OSError:
        pass
    return None


def get_telemetry():
    properties = _read_server_properties()
    maintenance = MAINTENANCE_FILE.exists()
    running = find_screen_session("mc") is not None
    status = "maintenance" if maintenance else "running" if running else "offline"
    now = datetime.now(timezone.utc)
    started_at = None
    uptime_seconds = None
    try:
        started_at = float((SERVER_DIR / ".server_started_at").read_text(encoding="ascii").strip())
        uptime_seconds = max(0, int(time.time() - started_at)) if running else None
    except (OSError, ValueError):
        pass
    with TELEMETRY_LOCK:
        players = dict(PLAYER_TELEMETRY)
    player_sample_time = None
    if players["updated_at"]:
        try:
            player_sample_time = datetime.fromisoformat(players["updated_at"])
        except ValueError:
            pass
    player_sample_age = (now - player_sample_time).total_seconds() if player_sample_time else None
    players["stale"] = player_sample_age is None or player_sample_age > TELEMETRY_INTERVAL_SECONDS * 3
    players["sample_age_seconds"] = int(player_sample_age) if player_sample_age is not None else None
    return {
        "schema_version": f"{API_VERSION}.0",
        "collected_at": now.isoformat(),
        "server": {
            "status": status,
            "edition": "bedrock",
            "command_dialect": "minecraft-bedrock",
            "version": _server_version(),
            "uptime_seconds": uptime_seconds,
            "started_at": datetime.fromtimestamp(started_at, timezone.utc).isoformat() if started_at else None,
            "world_name": properties.get("level-name"),
            "game_mode": properties.get("gamemode"),
            "difficulty": properties.get("difficulty"),
            "max_players": _int_or_none(properties.get("max-players")),
        },
        "players": players,
        "performance": {"bedrock_memory_bytes": _bedrock_memory_bytes() if running else None},
    }


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def api_info():
    return {
        "api_version": API_VERSION,
        "addon": "bedrock_server_rcon",
        "server": {"edition": "bedrock", "command_dialect": "minecraft-bedrock", "version": _server_version()},
        "capabilities": {
            "command_execution": {"method": "POST", "path": "/api/v1/commands", "body": {"command": "string"}},
            "telemetry": {"method": "GET", "path": "/api/v1/telemetry", "refresh_seconds": TELEMETRY_INTERVAL_SECONDS},
            "command_mode": "raw_console",
            "backups": {
                "list": {"method": "GET", "path": "/backups"},
                "create": {"method": "POST", "path": "/backups"},
                "restore": {"method": "POST", "path": "/backups/{backup_id}/restore"},
            },
        },
    }


def run_scheduled_backup():
    properties_path = SERVER_DIR / "server.properties"
    try:
        properties = {
            key.strip(): value.strip().lower()
            for key, separator, value in (
                line.partition("=") for line in properties_path.read_text(encoding="utf-8-sig").splitlines()
            )
            if separator
        }
    except OSError as error:
        raise BackupError(f"Could not read server.properties before backup: {error}") from error
    if properties.get("allow-cheats") != "true":
        raise BackupError("Safe scheduled backups require allow-cheats=true so Bedrock accepts save hold/resume")

    def save_hold():
        return send_console_command("save hold")

    def save_resume():
        return send_console_command("save resume")

    with SERVER_OPERATION_LOCK:
        return create_scheduled_backup(
            SERVER_DIR,
            BACKUP_DIR,
            max(1, min(int(OPTIONS.get("backup_keep_count", 7)), 90)),
            save_hold,
            save_resume,
        )


def backup_scheduler():
    interval_hours = int(OPTIONS.get("backup_interval_hours", 24))
    if interval_hours <= 0:
        app.logger.info("Scheduled world backups are disabled")
        return
    interval_seconds = max(3600, min(interval_hours, 720) * 3600)
    while not SCHEDULER_STOP.wait(interval_seconds):
        if find_screen_session("mc") is None:
            app.logger.warning("Skipping scheduled backup because Bedrock is not running")
            continue
        try:
            backup_path = run_scheduled_backup()
            app.logger.info("Scheduled world backup created: %s", backup_path.name)
        except Exception:
            app.logger.exception("Scheduled world backup failed")


def restore_scheduled_backup(backup_id):
    if Path(backup_id).name != backup_id or not backup_id.startswith("scheduled-") or not backup_id.endswith(".tar.gz"):
        raise BackupError("Invalid scheduled backup ID")
    if not (BACKUP_DIR / backup_id).is_file():
        raise BackupError("Scheduled backup was not found")
    with SERVER_OPERATION_LOCK:
        if find_screen_session("mc") is not None:
            if not send_console_command("stop"):
                raise BackupError("Could not send stop to the running Bedrock server")
            deadline = time.monotonic() + 60
            while find_screen_session("mc") is not None and time.monotonic() < deadline:
                time.sleep(0.25)
            if find_screen_session("mc") is not None:
                raise BackupError("Bedrock did not stop within 60 seconds; restore was cancelled")

        try:
            return restore_backup(backup_id, SERVER_DIR, BACKUP_DIR)
        except Exception:
            # A successful restore helper clears the maintenance marker itself;
            # on a rollback error keep maintenance enabled to avoid booting mixed data.
            if not (SERVER_DIR / ".restore-rollback" / "transaction.json").exists():
                MAINTENANCE_FILE.unlink(missing_ok=True)
            raise


@app.get("/health")
def health():
    if MAINTENANCE_FILE.exists():
        return jsonify({"status": "maintenance"}), 503
    if find_screen_session("mc") is None:
        return jsonify({"status": "unavailable", "message": "Bedrock server is not running"}), 503
    return jsonify({"status": "ready"})


@app.before_request
def protect_rcon_routes():
    if request.path == "/health":
        return None
    client_ip = request.remote_addr or "unknown"
    if not client_ip_allowed(client_ip):
        return jsonify({"status": "error", "message": "Client IP is not allowed"}), 403
    is_command = request.path in {"/rcon", "/api/v1/commands"} and request.method == "POST"
    is_backup_operation = request.path == "/backups" and request.method == "POST" or request.path.endswith("/restore") and request.method == "POST"
    if not request_rate_allowed(client_ip, command_request=is_command, backup_request=is_backup_operation):
        return jsonify({"status": "error", "message": "Rate limit exceeded"}), 429
    return None


@app.route("/rcon", methods=["POST"])
@app.route("/api/v1/commands", methods=["POST"])
def rcon():
    client_ip = request.remote_addr

    if len(RCON_TOKEN) < 32:
        return jsonify({"status": "error", "message": "A valid RCON token is not configured"}), 503

    if not authorized():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if not request.is_json:
        log_command(client_ip, "INVALID_REQUEST", "ERROR: JSON required")
        return jsonify({"status": "error", "message": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("command"), str):
        log_command(client_ip, "INVALID_REQUEST", "ERROR: Missing string command")
        return jsonify({"status": "error", "message": "A string 'command' is required"}), 400

    cmd = data["command"].strip()
    if not cmd:
        log_command(client_ip, "EMPTY_COMMAND", "ERROR: Missing command")
        return jsonify({"status": "error", "message": "Missing command"}), 400

    if len(cmd) > MAX_COMMAND_LENGTH or any(ord(char) < 32 or ord(char) == 127 for char in cmd):
        log_command(client_ip, "INVALID_COMMAND", "ERROR: Invalid length or control character")
        return jsonify({"status": "error", "message": "Command is too long or contains control characters"}), 400

    with SERVER_OPERATION_LOCK:
        try:
            log_offset = SERVER_LOG_FILE.stat().st_size
        except OSError:
            log_offset = 0
        request_id = uuid.uuid4().hex
        if not send_console_command(cmd):
            log_command(client_ip, cmd, "ERROR: Failed to send command to screen", request_id)
            return jsonify({"status": "error", "message": "Failed to send command to Minecraft"}), 503
        console_output = read_console_output(log_offset)

    log_command(client_ip, cmd, "SENT_TO_SERVER_SESSION", request_id)
    return jsonify({
        "status": "ok",
        "request_id": request_id,
        "sent": True,
        "execution_confirmed": False,
        "console_output": console_output,
        "message": "Command sent. Console output is best-effort and does not confirm execution of this specific command.",
    })


@app.get("/api/v1/info")
def versioned_api_info():
    if not authorized():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return jsonify(api_info())


@app.get("/api/v1/telemetry")
def versioned_telemetry():
    if not authorized():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return jsonify(get_telemetry())


@app.get("/backups")
def get_backups():
    if not authorized():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return jsonify({"status": "ok", "backups": list_scheduled_backups(BACKUP_DIR)})


@app.post("/backups")
def create_backup_endpoint():
    if not authorized():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    try:
        path = run_scheduled_backup()
    except Exception as error:
        app.logger.exception("Manual world backup failed")
        return jsonify({"status": "error", "message": str(error)}), 503
    return jsonify({"status": "ok", "backup": path.name}), 201


@app.post("/backups/<backup_id>/restore")
def restore_backup_endpoint(backup_id):
    if not RESTORE_REQUEST_LOCK.acquire(blocking=False):
        return jsonify({"status": "error", "message": "Another restore is already in progress"}), 409
    try:
        return _restore_backup_request(backup_id)
    finally:
        RESTORE_REQUEST_LOCK.release()


def _restore_backup_request(backup_id):
    if not authorized():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    if Path(backup_id).name != backup_id or not backup_id.startswith("scheduled-") or not backup_id.endswith(".tar.gz"):
        return jsonify({"status": "error", "message": "Invalid scheduled backup ID"}), 400
    if not (BACKUP_DIR / backup_id).is_file():
        return jsonify({"status": "error", "message": "Scheduled backup was not found"}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("confirm") != f"restore {backup_id}":
        return jsonify({"status": "error", "message": "Confirmation must equal 'restore <backup_id>'"}), 400
    if not (SERVER_DIR / ".maintenance").exists():
        try:
            MAINTENANCE_FILE.write_text("restore requested\n", encoding="utf-8")
        except OSError as error:
            return jsonify({"status": "error", "message": f"Could not enter maintenance mode: {error}"}), 503
    try:
        rollback_path = restore_scheduled_backup(backup_id)
    except Exception as error:
        app.logger.exception("Scheduled world restore failed")
        if not (SERVER_DIR / ".restore-rollback" / "transaction.json").exists():
            MAINTENANCE_FILE.unlink(missing_ok=True)
        return jsonify({"status": "error", "message": str(error)}), 503
    return jsonify({"status": "ok", "restored": backup_id, "rollback_backup": rollback_path.name, "server_restart_expected": True}), 200


if __name__ == "__main__":
    if len(RCON_TOKEN) < 32:
        raise SystemExit("[RCON] Configure rcon_token (at least 32 characters) in the add-on options.")

    print(f"[RCON] Servidor RCON iniciado na porta {RCON_PORT}")
    threading.Thread(target=backup_scheduler, name="world-backup-scheduler", daemon=True).start()
    threading.Thread(target=telemetry_scheduler, name="bedrock-telemetry", daemon=True).start()
    serve(app, host="0.0.0.0", port=RCON_PORT)
