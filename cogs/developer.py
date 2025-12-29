# cogs/developer.py
import discord
from discord.ext import commands
from discord import app_commands

# 🔹 Сюда вставь СВОЙ Discord ID
OWNER_ID = 914221453258420265


def owner_only():
    """Чекер: доступ только владельцу бота (по Discord ID)."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id != OWNER_ID:
            # можно ничего не писать — просто тихо отказать
            raise app_commands.CheckFailure("Only bot owner can use this command.")
        return True
    return app_commands.check(predicate)


class Developer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="leave",
        description="Заставить бота выйти с сервера по ID (только владелец бота)."
    )
    @app_commands.describe(server_id="ID сервера, который бот должен покинуть")
    @owner_only()  # ← проверка на владельца
    async def leave_server(self, interaction: discord.Interaction, server_id: int):
        guild = self.bot.get_guild(server_id)

        if guild is None:
            await interaction.response.send_message(
                "❌ Бот не находится на сервере с таким ID.",
                ephemeral=True
            )
            return

        name = guild.name
        await guild.leave()

        await interaction.response.send_message(
            f"✅ Бот покинул сервер **{name}** (ID: `{server_id}`).",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Developer(bot))
