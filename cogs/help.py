# cogs/help.py
import discord
from discord import app_commands
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Показать список команд бота")
    async def help(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="Command list",
            description="Команды на английском языке, описания на русском.",
            color=discord.Color.blurple()
        )

        # 🛡 MODERATION
        embed.add_field(
            name="🛡 Moderation",
            value=(
                "`/ban @user [reason]` — Забанить участника.\n"
                "`/unban user_id [reason]` — Разбанить участника по ID.\n"
                "`/mute @user [reason]` — Выдать мут (роль Muted).\n"
                "`/unmute @user` — Снять мут.\n"
                "`/warn @user [reason]` — Выдать предупреждение.\n"
                "`/warns @user` — Показать предупреждения участника.\n"
                "`/clear amount` — Удалить последние сообщения.\n"
                "`/history @user` — История модерации участника.\n"
                "`/setlog #channel` — Указать канал для логов."
            ),
            inline=False
        )

        # 🚫 ANTIMAT
        embed.add_field(
            name="🚫 Antimat",
            value=(
                "`/addword word` — Добавить запрещённое слово.\n"
                "`/delword word` — Удалить запрещённое слово.\n"
                "`/words` — Показать список запрещённых слов."
            ),
            inline=False
        )

        # 🎮 GAMES
        embed.add_field(
            name="🎮 Games",
            value=(
                "`/cs` — Команды/информация по CS.\n"
                "`/valorant` — Команды/информация по Valorant.\n"
                "`/fortnite` — Команды/информация по Fortnite."
            ),
            inline=False
        )

        # 🎵 MUSIC
        embed.add_field(
            name="🎵 Music",
            value=(
                "`/music` — Музыкальная панель / команды музыки."
            ),
            inline=False
        )

        # 🛠 DEV PANEL
        embed.add_field(
            name="🛠 Dev panel",
            value=(
                "`/givebot @user` — Выдать доступ к использованию бота.\n"
                "`/takebot @user` — Забрать доступ к использованию бота."
            ),
            inline=False
        )

        # ℹ GENERAL
        embed.add_field(
            name="ℹ General",
            value=(
                "`/help` — Показать это меню помощи."
            ),
            inline=False
        )

        embed.set_footer(
            text=f"Requested by {interaction.user}",
            icon_url=interaction.user.display_avatar.url
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
