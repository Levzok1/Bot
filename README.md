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

- `yt-dlp` is required for music commands.
- `ffmpeg` must be installed and available in your PATH.

## Windows startup

Use `cogs\run.bat` to activate the environment and start the bot.

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

Environment variables still work as global fallbacks:
- `MODERATOR_IDS`
- `MODERATOR_ROLE_NAMES`

## Notes

- The bot expects `DISCORD_TOKEN` in environment variables.
- Slash commands are synced on startup.
- Add or remove cogs in `bot.py` as needed.
