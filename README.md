# astrbot_plugin_kuro_sign

AstrBot plugin for Kuro login and sign tasks.

## Features

- Web login flow: `getSmsCodeForH5 -> sdkLogin`
- Kuro Waves sign
- Kuro BBS task sign

## Commands

- `/kuro_login`
- `/kuro_status`
- `/kuro_waves_sign`
- `/kuro_bbs_sign`

## Public Network Config

For remote deployment, you only need to configure `public_ip`.

- `host`: set `0.0.0.0` (default)
- `port`: local web port, default `8765`
- `public_ip`: your public IP or domain, for example `1.2.3.4` or `bot.example.com`

The plugin auto-generates login URL as:

- `http://<public_ip>:<port>/?user=...`

No need to manually provide full URL path.
