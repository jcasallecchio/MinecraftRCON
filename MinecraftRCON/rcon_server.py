from datetime import datetime
import hmac
import json
import os
import re
import subprocess

from flask import Flask, jsonify, request
from waitress import serve

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

LOG_FILE = "/share/minecraftRCON/rcon_commands.log"
OPTIONS_FILE = "/data/options.json"
RCON_PORT = 19133
MAX_COMMAND_LENGTH = 1024


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


RCON_TOKEN = load_rcon_token()


def log_command(ip, command, status):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] IP: {ip or 'unknown'} | CMD: {command} | STATUS: {status}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(log_line)


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
    return bool(RCON_TOKEN) and hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/rcon", methods=["POST"])
def rcon():
    client_ip = request.remote_addr

    if not RCON_TOKEN:
        return jsonify({"status": "error", "message": "RCON token is not configured"}), 503

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

    session_id = find_screen_session("mc")
    if not session_id:
        log_command(client_ip, cmd, "ERROR: No active screen session")
        return jsonify({"status": "error", "message": "Minecraft server session is not running"}), 503

    try:
        subprocess.run(
            ["screen", "-S", session_id, "-X", "stuff", f"{cmd}\r"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        log_command(client_ip, cmd, "ERROR: Failed to send command to screen")
        return jsonify({"status": "error", "message": "Failed to send command to Minecraft"}), 503

    log_command(client_ip, cmd, "SENT")
    return jsonify({"status": "ok", "message": "Command sent to Minecraft"})


if __name__ == "__main__":
    if not RCON_TOKEN:
        raise SystemExit("[RCON] Configure rcon_token (at least 32 characters) in the add-on options.")

    print(f"[RCON] Servidor RCON iniciado na porta {RCON_PORT}")
    serve(app, host="0.0.0.0", port=RCON_PORT)
