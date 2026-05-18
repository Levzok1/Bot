# Discord Bot

A Discord bot implemented in Python using `discord.py`.

## Setup

1. Create and activate a virtual environment:
   - `python -m venv .venv`
   - ` .venv\Scripts\activate`
2. Install dependencies:
   - `python -m pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and set your bot token and optional keys:
   - `DISCORD_TOKEN=your_token_here`
   - `DISCORD_OWNER_ID=your_owner_id_here` (optional, for owner-only commands)
   - `MODERATOR_IDS=123456789012345678,987654321098765432` (optional, IDs of users who can use moderation commands)
   - `MODERATOR_ROLE_NAMES=Moderator,Helper,Team Lead` (optional, role names that can use moderation commands)
   - `OPENAI_API_KEY=your_openai_api_key_here` (optional, for AI moderation)
4. Run the bot:
   - `python bot.py`

## Music requirements

- `/play` accepts a direct link, a search query, or a playlist link.
- `yt-dlp` is required for music commands and supports YouTube, SoundCloud, Bandcamp, Vimeo, Twitch, and many other media sites.
- `ffmpeg` must be installed and available in your PATH.
- Install `discord.py[voice]` from `requirements.txt`; modern Discord voice channels require DAVE/E2EE support.
- Playlist links add up to the first 1000 tracks to the queue.
- Use `/queue start:240` to show the list around a specific number.
- Use `/jump position:240` to switch playback to a specific number from the list.
- Use `/seek seconds:90` to rewind the current track to a specific second.
- Use `/speed value:2` or `/speed value:0.25` to change playback speed.
- Use `/menu` for button controls, including queue, seek, speed, lyrics, join, and leave.
- Use `/shuffle` or the `🔀 Перемешать` button in `/menu` to shuffle the loaded queue/playlist without interrupting the current track.
- Music status messages are deleted after 2 minutes; `/play` URL links are echoed separately so the link remains visible.
- Lyrics first try platform subtitles, then LRCLIB synced lyrics by title/artist; lines are shown 1 second early.
- DRM-only services such as Spotify or Apple Music usually cannot be streamed directly.

## Windows startup

Use `cogs\run.bat` to activate the environment and start the bot.

## uv install warning

This repository includes `uv.toml` with `link-mode = "copy"`. It suppresses the Windows warning about failed hardlinks and keeps the install behavior explicit.

## Dashboard site and API

The dashboard frontend is in `bot_site`. The bot also loads `cogs.dashboard_api`, a token/OAuth protected HTTP API for real dashboard buttons.

Minimum `.env` values for local dashboard control:

- `DASHBOARD_TOKEN=change_this_long_random_secret`
- `DASHBOARD_API_HOST=127.0.0.1`
- `DASHBOARD_API_PORT=8080`
- `DASHBOARD_PUBLIC_URL=http://localhost:8080`
- `DASHBOARD_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:4173,http://127.0.0.1:4173`

Run locally:

- Start the bot from the repository root: `python bot.py`
- Open `http://localhost:8080` while the bot is running. The same backend serves the site and API, so the server list can be loaded from the first screen.
- Optional static mode: `cd bot_site`, then `python -m http.server 4173`; open `http://localhost:4173`, set API URL to `http://localhost:8080`, enter `DASHBOARD_TOKEN`, then use `Check API` / `Load servers`.

If `DASHBOARD_TOKEN` and Discord OAuth are not configured, the dashboard allows local no-auth access only on `127.0.0.1` / `localhost`. Set `DASHBOARD_TOKEN` before exposing the API outside your PC.

For Discord login through the bot application, set `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, and `DASHBOARD_DISCORD_REDIRECT_URI=http://localhost:8080/api/auth/callback`, then use the dashboard `Войти через Discord` button.

For Vercel, this repository's frontend root is `bot_site`. Set:

- Root Directory: `bot_site`
- Framework Preset: `Other`
- Build Command: `npm run build`
- Output Directory: `.`

Vercel only hosts the static frontend. The Python bot API must run separately. If the site is public, configure Discord OAuth2 with `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, and `DASHBOARD_DISCORD_REDIRECT_URI`.

## Server-specific settings

The bot now supports per-server configuration.

- Use `/config view` to see current settings for this server.
- Use `/config set <key> <value>` to save a setting for this server.
- Use `/config delete <key>` to remove a server-specific setting.

For example, to define moderator roles for this server:
- `/config set moderator_role_names Moderator,Helper`

You can also view the moderation history with:
- `/modlog` — show recent moderation actions for this server
- `/modlog @user` — show recent moderation history for a user

Warnings are configurable per server:
- `/warn @user reason` adds a warning and applies the configured tier.
- `/warnings @user` shows active warnings.
- `/clearwarns @user reason` or `/unwarn @user reason` removes active warnings.
- The dashboard and local console use the same warning store and moderation log as the slash commands.
- Dashboard settings control warn expiry and tier actions, for example 1 warn = warning, 2 warns = timeout, 3 warns = longer timeout.

For timeout/mute tiers, the bot needs the Discord `Moderate Members` permission and its role must be above the target member's role.

Environment variables still work as global fallbacks:
- `MODERATOR_IDS`
- `MODERATOR_ROLE_NAMES`

## Reaction roles

- `/reactionroles create channel title description mappings` creates a Carl-bot style role message.
- `mappings` format: `🎮=@GTA V; ⛏️=@Minecraft` or `🎮=123456789012345678; ⛏️=987654321098765432`.
- `/reactionroles add message_id emoji role` adds one emoji-role pair to an existing reaction-role message.
- `/reactionroles remove message_id emoji` removes one pair.
- `/reactionroles list` shows configured messages for the current server.

The bot needs `Manage Roles`, `Add Reactions`, `Read Message History`, and its highest role must be above roles it gives.

## Console

When the bot is running, the terminal accepts local admin commands. Type `help` in the console.

Useful examples:
- `say <channel_id> <text>` sends a message to a Discord channel.
- `menu <channel_id>` sends the music menu to a text channel.
- `play <voice_channel_id> <query>` starts music from the console.
- `shuffle <guild_id>` shuffles the loaded music queue.
- `warn <guild_id> <member_id> [reason]`, `warnings <guild_id> <member_id>`, and `clearwarns <guild_id> <member_id> [reason]` use the shared warning store.
- `modlog <guild_id> [user_id]` reads the same moderation log as `/modlog` and the dashboard.
- `rr create <channel_id> | <title> | <description> | <emoji>=<role_id>; <emoji>=<role_id>` creates a reaction-role message.
- `servers`, `channels <guild_id>`, `roles <guild_id>`, `commands` print IDs needed for console actions.

`/addword` and `/delword` accept multiple words in one command: `word: spam, flood, caps`. The typo aliases `/addworl` and `/delworl` are also registered.

## Notes

- The bot expects `DISCORD_TOKEN` in environment variables.
- Slash commands are synced on startup.
- Add or remove cogs in `bot.py` as needed.
