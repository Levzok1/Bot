import os
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN не задан в окружении")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

EXTENSIONS = [
    "cogs.moderation",
    "cogs.antimat",
    "cogs.help",
    "cogs.cs",
    "cogs.music",
    "cogs.ai_moderation",
    "cogs.access",
    "cogs.antiraid",
    "cogs.dev_panel",
    "cogs.game_stats",
    "cogs.invites",
    "cogs.server",
    "cogs.config",
    "cogs.modlog",
]


@bot.event
async def on_ready():
    print("==============================================")
    print(f"Бот запущен как: {bot.user} ({bot.user.id})")
    print(f"Бот подключён к {len(bot.guilds)} серверу(ам):")
    for guild in bot.guilds:
        print(f"- {guild.name} | ID: {guild.id} | Участников: {guild.member_count} | Владелец: {guild.owner}")
    try:
        synced = await bot.tree.sync()
        print(f"\n✅ Синхронизировано глобальных slash-команд: {len(synced)}")
    except Exception as e:
        print(f"\n❌ Failed to sync app commands: {e}")
    print("==============================================")


async def main():
    async with bot:
        for ext in EXTENSIONS:
            try:
                await bot.load_extension(ext)
                print(f"✅ Загружен модуль: {ext}")
            except Exception as e:
                print(f"❌ Ошибка при загрузке модуля {ext}: {e}")
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
