# Bedrock Homeassistant Server with RCON

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

## Installation

_Addon running a Minecraft Bedrock Sever with RCON via stdin on Home Assistant._

For configuration use the add-on configuration UI of Home Assistant.

## RCON API

Configure `rcon_token` in the add-on's Configuration tab. The token must have at least 32 characters. The option may remain empty while an update is installed, but the add-on will log a clear error and stop before starting the Minecraft server until a valid token is set.

Before starting Bedrock, the add-on ensures that `transport=nethernet` is present in `server.properties`.

Send commands to `POST http://<host>:19133/rcon` with `Content-Type: application/json`, an `Authorization: Bearer <token>` header, and a body such as `{"command":"list"}`. The endpoint accepts one command per request and limits commands to 1024 characters. Responses include a `request_id` and recent console lines when available; those lines are best-effort and do not prove that Minecraft executed that specific command.

The unauthenticated `GET http://<host>:19133/health` endpoint returns `ready` only while the Bedrock session is running.

RCON command logs are written to `/share/minecraftRCON/rcon_commands.log` and rotated at 2 MiB, keeping up to five previous files.

## RCON network access

`rcon_allowed_ips` accepts comma-separated IP addresses or CIDR ranges, for example `192.168.15.0/24`. Leave it empty to allow requests from any address that can reach port 19133. The API also limits each IP to 60 requests per minute and 30 commands per minute. The endpoint uses HTTP, so keep it on a trusted network or access it through a VPN or HTTPS reverse proxy.

## World backups and restore

`backup_interval_hours` defaults to 24; set it to `0` to disable scheduled backups. `backup_keep_count` defaults to 7. Scheduled backups are compressed into `/share/minecraftRCON/backups/scheduled/`. The add-on briefly puts Bedrock in save-hold mode while copying the world data, resumes saving, then compresses the snapshot. Bedrock must have `allow-cheats=true`; the add-on refuses to make a potentially inconsistent live backup when save hold is unavailable. The official [`/save` command](https://learn.microsoft.com/en-us/minecraft/creator/commands/commands/save?view=minecraft-bedrock-stable) documents the dedicated-server save modes.

Use `GET /backups` with the Bearer token to list snapshots and `POST /backups` to create one immediately. To restore a snapshot, send `POST /backups/<backup-id>/restore` with JSON `{"confirm":"restore <backup-id>"}`. Restore stops Bedrock cleanly, creates a pre-restore rollback archive, applies the selected snapshot, then the watchdog starts the server again. The explicit confirmation must exactly match the backup ID.

The server updater keeps a rollback journal until the new files and settings are installed. If the add-on exits mid-update, the next boot restores the previous files before continuing.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
