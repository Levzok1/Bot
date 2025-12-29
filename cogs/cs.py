# cogs/cs.py
import discord
from discord import app_commands
from discord.ext import commands


class CSGames(commands.Cog):
    """CS-раздел (игры)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Группа /cs
    cs = app_commands.Group(
        name="cs",
        description="CS: раздел игр и команд."
    )

    # /cs info
    @cs.command(
        name="info",
        description="Показать общую информацию о CS-разделе."
    )
    async def cs_info(self, interaction: discord.Interaction):
        """Общая инфа про раздел CS."""
        embed = discord.Embed(
            title="CS раздел",
            description=(
                "Здесь находятся команды, связанные с CS.\n\n"
                "Доступные команды:\n"
                "• `/cs info` — общая информация.\n"
                "• `/cs rules` — правила.\n"
                "• `/cs ranks` — ранги.\n"
            ),
            colour=discord.Colour.blurple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /cs rules
    @cs.command(
        name="rules",
        description="Показать правила для CS-раздела."
    )
    async def cs_rules(self, interaction: discord.Interaction):
        """Правила CS (можешь отредактировать под себя)."""
        embed = discord.Embed(
            title="Правила CS",
            description=(
                "1. Запрещён читинг, макросы и любые сторонние программы.\n"
                "2. Уважай напарников и противников, без оскорблений.\n"
                "3. Следуй правилам сервера и указаниям администраторов.\n"
                "4. Используй голосовой/текстовый чат по делу."
            ),
            colour=discord.Colour.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /cs ranks
    @cs.command(
        name="ranks",
        description="Показать список CS-рангов."
    )
    async def cs_ranks(self, interaction: discord.Interaction):
        """Список рангов (пример, поправь под свои роли)."""
        embed = discord.Embed(
            title="CS ранги",
            description=(
                "Примерная система рангов CS:\n"
                "• Silver\n"
                "• Gold Nova\n"
                "• Master Guardian\n"
                "• Legendary Eagle\n"
                "• Supreme / Global\n\n"
                "_Отредактируй список под свои ранги._"
            ),
            colour=discord.Colour.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CSGames(bot))
