# Bedrock Homeassistant Server with RCON

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

## Installation

_Addon running a Minecraft Bedrock Sever with RCON via stdin on Home Assistant._

For configuration use the add-on configuration UI of Home Assistant.

## RCON API

Configure `rcon_token` in the add-on's Configuration tab. The token must have at least 32 characters. The option may remain empty while an update is installed, but the add-on will log a clear error and stop before starting the Minecraft server until a valid token is set.

Send commands to `POST http://<host>:19133/rcon` with `Content-Type: application/json`, an `Authorization: Bearer <token>` header, and a body such as `{"command":"list"}`. The endpoint accepts one command per request and limits commands to 1024 characters.

The unauthenticated `GET http://<host>:19133/health` endpoint is only for readiness checks and returns whether the HTTP service is responding.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
