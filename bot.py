import os
import asyncio
import shutil
import traceback

import discord
from discord import app_commands
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
commands_synced = False

EXTENSIONS = [
    "cogs.moderation",
    "cogs.antimat",
    "cogs.help",
    "cogs.cs",
    "cogs.music",
    "cogs.ai_moderation",
    "cogs.antiraid",
    "cogs.dev_panel",
    "cogs.game_stats",
    "cogs.invites",
    "cogs.server",
    "cogs.config",
    "cogs.interveis",
]


@bot.event
async def on_ready():
    global commands_synced

    print("==============================================")
    print(f"Бот запущен как: {bot.user} ({bot.user.id})")
    print(f"Бот подключён к {len(bot.guilds)} серверу(ам):")
    for guild in bot.guilds:
        print(f"- {guild.name} | ID: {guild.id} | Участников: {guild.member_count} | Владелец: {guild.owner}")

    if shutil.which("ffmpeg") is None:
        print("⚠️ ffmpeg не найден в PATH. Музыкальные команды не будут работать.")
        print("   Установи ffmpeg и добавь его в переменную окружения PATH.")
    if not commands_synced:
        try:
            synced = await bot.tree.sync()
            commands_synced = True
            print(f"\n✅ Синхронизировано глобальных slash-команд: {len(synced)}")
        except Exception as e:
            print(f"\n❌ Failed to sync app commands: {e}")
            traceback.print_exc()
    print("==============================================")


@bot.event
async def on_error(event_method: str, *args, **kwargs):
    print(f"❌ Unhandled bot error in {event_method}")
    traceback.print_exc()


@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f"❌ App command error: {type(error).__name__}: {error}")
    traceback.print_exc()
    message = (
        "У тебя нет прав использовать эту команду."
        if isinstance(error, app_commands.CheckFailure)
        else "Произошла ошибка при выполнении команды. Подробности записаны в консоль."
    )
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        pass


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
