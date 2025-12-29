import os
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("DISCORD_OWNER_ID", "0"))  # твой Discord ID (для /server)

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN не найден в .env")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # нужно для member_count/ролей/модерации
bot = commands.Bot(command_prefix="!", intents=intents)

EXTENSIONS = [
    "cogs.moderation",
    "cogs.antimat",
    "cogs.help",
    "cogs.cs",
    "cogs.music",
    "cogs.developer",
   "cogs.ai_moderation"
    "cogs.access",
    "cogs.antiraid",
    "cogs.dev_panel",
    "cogs.game_stats",
    "cogs.invites",
    "cogs.server",     # ✅ новый cog
]


async def load_cogs():
    for ext in EXTENSIONS:
        try:
            await bot.load_extension(ext)
            print(f"✅ Загружен модуль: {ext}")
        except Exception as e:
            print(f"❌ Ошибка при загрузке {ext}: {e}")


@bot.event
async def on_ready():
    print("=" * 60)
    print(f"🤖 Bot started as: {bot.user} ({bot.user.id})")

    # ===== СЕРВЕРА =====
    if bot.guilds:
        print(f"🏠 Bot is connected to {len(bot.guilds)} server(s):")
        for guild in bot.guilds:
            owner = guild.owner
            owner_name = owner.name if owner else "Unknown"
            print(
                f"  - {guild.name} | ID: {guild.id} | "
                f"Members: {guild.member_count} | Owner: {owner_name}"
            )
    else:
        print("🏠 Bot is not connected to any servers")

    # ===== SYNC SLASH =====
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} global slash commands")
    except Exception as e:
        print(f"❌ Slash sync error: {e}")

    # ===== Список slash-команд =====
    cmds = bot.tree.get_commands()
    print(f"📌 Slash commands list ({len(cmds)}):")
    for cmd in cmds:
        print(f"  /{cmd.qualified_name}")

    print("=" * 60)


async def main():
    await load_cogs()
    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
