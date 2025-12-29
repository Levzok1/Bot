import discord
from discord.ext import commands
from discord import app_commands


class GameStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ===== Valorant =====
    @app_commands.command(
        name="valorant",
        description="Показать пример статистики Valorant (каркас).",
    )
    @app_commands.describe(nickname="Ник/тег игрока, например TenZ#NA1")
    async def valorant_stats(
        self, interaction: discord.Interaction, nickname: str
    ):
        # TODO: подключить настоящий Riot API
        embed = discord.Embed(
            title=f"Valorant статы: {nickname}",
            color=discord.Color.red(),
        )
        embed.add_field(name="Ранг", value="Diamond 2 (пример)", inline=True)
        embed.add_field(name="K/D", value="1.23 (пример)", inline=True)
        embed.add_field(name="Матчей", value="123 (пример)", inline=True)
        embed.set_footer(text="Реальные данные можно подключить через Riot API.")
        await interaction.response.send_message(embed=embed)

    # ===== Fortnite =====
    @app_commands.command(
        name="fortnite",
        description="Показать пример статистики Fortnite (каркас).",
    )
    @app_commands.describe(nickname="Ник в Fortnite")
    async def fortnite_stats(
        self, interaction: discord.Interaction, nickname: str
    ):
        # TODO: подключить Fortnite Tracker API
        embed = discord.Embed(
            title=f"Fortnite статы: {nickname}",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Победы", value="42 (пример)", inline=True)
        embed.add_field(name="Матчей", value="420 (пример)", inline=True)
        embed.add_field(name="K/D", value="2.5 (пример)", inline=True)
        embed.set_footer(
            text="Реальные данные можно подключить через Fortnite Tracker API."
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GameStats(bot))
